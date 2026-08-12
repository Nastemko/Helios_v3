# Ithaca inference service — OpenTofu

Deploys `ithaca-service/` to Cloud Run on an NVIDIA L4 that scales to zero.

State is **local** (`./terraform.tfstate`), gitignored, unlocked. It is the only
record of what exists in GCP — back it up somewhere outside the repo, and do
not apply from two machines.

## Cost

An L4 bills at roughly **$0.71/hour of active instance time**. Three guards
bound that:

| Guard | Where | Effect |
|---|---|---|
| `min_instance_count = 0` | `service.tf` | No idle billing. A pinned instance would cost ~$500/mo. |
| `max_instance_count = 1` | `var.max_instances` | A runaway caller cannot fan out across GPUs. |
| `timeout = 300s` | `var.request_timeout_seconds` | One pathological restore cannot hold a GPU for an hour. |

The $20 budget is an **alert, not a cap** — GCP does not stop charges when it
fires. The guards above are what actually bound spend.

## Prerequisites

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
cp terraform.tfvars.example terraform.tfvars   # then edit
```

For the budget you need **`roles/billing.admin` or `roles/billing.costsManager`
on the billing account** — project-owner is not enough, because the provider
only calls the billing-account-scoped API. If apply 403s there, set
`enable_budget = false` and create the budget in the console, which has a
project-scoped path the provider cannot reach.

```bash
gcloud billing accounts list    # find billing_account_id
```

## Deploy

**1. Enable APIs first.** Enablement is eventually-consistent; doing it in the
same pass as everything else causes spurious "API not enabled" failures.

```bash
tofu init
tofu apply -target=google_project_service.apis
```

**2. First apply** — creates the registry, service accounts, IAM and budget.
The service comes up on Google's placeholder image, because Cloud Run validates
the image at apply time and a fresh repository is empty.

```bash
tofu apply
```

**3. Build the real image.** Server-side, so ~2GB of checkpoints never cross
your uplink. Takes a while.

```bash
cd .. && gcloud builds submit ./ithaca-service \
  --config=ithaca-service/cloudbuild.yaml \
  --region=us-central1
```

**4. Deploy it.** Pin by digest — with a floating tag, tofu sees no diff when
image content changes.

```bash
gcloud artifacts docker images describe \
  us-central1-docker.pkg.dev/PROJECT/helios/ithaca:latest --format='value(image_summary.digest)'

gcloud run deploy helios-ithaca \
  --image us-central1-docker.pkg.dev/PROJECT/helios/ithaca@sha256:DIGEST \
  --region us-central1
```

The service ignores tofu-side image changes after the first apply, so the build
pipeline owns this field from here.

**5. Turn on auth.** Check the constructed audience matches the real URL first:

```bash
tofu output audience_matches   # must be true
```

If false, the audience would be wrong and every call would 401 — fix
`service_name` or set `ITHACA_AUDIENCE` by hand instead of flipping the flag.
If true:

```bash
tofu apply -var=enable_auth=true
```

## Wire up the backend

```bash
tofu output backend_env
```

Both values go on the backend (`ITHACA_SERVICE_URL`, `ITHACA_SERVICE_AUDIENCE`,
read by `IthacaServiceSettings`). The backend must authenticate as
`tofu output invoker_service_account` — the only identity holding
`roles/run.invoker`.

The audience must have **no path component**. A trailing path is the usual
cause of a 401 that looks like a credentials problem but is an audience
mismatch.

## Verify

```bash
URL=$(tofu output -raw service_url)

curl -s -o /dev/null -w '%{http_code}\n' $URL/health
# 403 — proves the service is private

curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" $URL/health
# 200, both languages available: true — proves checkpoints baked in correctly

gcloud run services describe helios-ithaca --region us-central1 \
  --format='value(spec.template.spec.containers[0].resources.limits)'
# shows nvidia.com/gpu: '1'
```

**Time a cold call, then an immediate warm one.** The gap is checkpoint-load
cost and decides whether scale-to-zero is tolerable for interactive use.

**Run the benchmark.** This is the gate that was never run:

```bash
cd ../ithaca-service
PYTHONPATH=./src uv run python src/scripts/bench_ithaca.py --out bench/gpu.json
```

Compare against a CPU baseline. **≥3x at beam 35** justifies the GPU; less, and
the CPU extraction alone was the win and this stack should come back down.
Predictions must be identical — the script records the full list for that diff.

## Teardown

```bash
tofu destroy
```

`deletion_protection = false` is set on the service so this works. APIs are
left enabled deliberately (`disable_on_destroy = false`) — other things in the
project may depend on them.

## Gotchas

- **Region must offer the L4**: `us-central1`, `us-east4`, `europe-west1`,
  `europe-west4`, `asia-southeast1`. Enforced by a variable validation.
- **`gpu_zonal_redundancy_disabled = true` is load-bearing**, not just a cost
  setting. The 3-GPU default quota is auto-granted only for the non-redundant
  config; the redundant quota commonly starts at zero.
- **`launch_stage` is deliberately unset.** GPUs are GA; setting `BETA` causes
  perpetual diffs because the API rewrites the field.
- **Budget units are whole dollars.** `"20"` is $20. Provider docs show
  `"100000"` for a $100,000 budget — an easy 1000x misread.
