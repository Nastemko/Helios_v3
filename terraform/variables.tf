variable "project_id" {
  description = "GCP project ID that will hold the registry and the service."
  type        = string
}

variable "region" {
  description = <<-EOT
    Deployment region. Must be one where Cloud Run offers the NVIDIA L4:
    us-central1, us-east4, europe-west1, europe-west4, asia-southeast1
    (asia-south1 is invitation-only). Applying in any other region fails.
  EOT
  type        = string
  default     = "us-central1"

  validation {
    condition = contains(
      ["us-central1", "us-east4", "europe-west1", "europe-west4", "asia-southeast1"],
      var.region
    )
    error_message = "Region must be one where Cloud Run offers the NVIDIA L4."
  }
}

variable "service_name" {
  description = "Name of the Cloud Run service."
  type        = string
  default     = "helios-ithaca"
}

variable "repository_id" {
  description = "Artifact Registry repository holding the inference image."
  type        = string
  default     = "helios"
}

variable "image" {
  description = <<-EOT
    Container image for the service.

    Defaults to Google's public placeholder because Cloud Run validates the
    image at apply time: pointing a fresh service at an empty repository fails
    the apply outright. Deploy once with this default, push the real image,
    then redeploy.

    The service ignores changes to this field (see service.tf), so after the
    first apply the image is owned by the build pipeline, not by tofu. Prefer a
    digest over a tag -- with a floating tag, tofu sees no diff when the image
    content changes underneath it.
  EOT
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "enable_auth" {
  description = <<-EOT
    Whether the service verifies caller ID tokens (ITHACA_DEBUG=False).

    Leave false for the first apply. ITHACA_AUDIENCE must be the service's own
    URL, which does not exist until the service does, and the service refuses
    to boot when auth is on with no audience configured (auth.py's
    validate_auth_config). So: apply once with false, then flip to true and
    re-apply once the URL is known.

    Cloud Run IAM still rejects unauthenticated callers either way -- this
    controls only the second, in-process layer.
  EOT
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = <<-EOT
    Billing account ID for the budget, e.g. "000000-000000-000000".
    Only read when enable_budget is true.
  EOT
  type        = string
  default     = ""
}

variable "enable_budget" {
  description = <<-EOT
    Whether to create the budget.

    Kept behind a flag because creating one requires billing.budgets.create on
    the *billing account* (roles/billing.admin or roles/billing.costsManager) --
    project-owner is not sufficient. The provider has no project-scoped budget
    resource, so if the apply 403s here, set this false and create the budget
    in the console instead, which does have a project-scoped path.
  EOT
  type        = bool
  default     = true
}

variable "budget_amount_usd" {
  description = <<-EOT
    Monthly budget in whole US dollars.

    NOTE: whole dollars, not cents. The provider's own documentation examples
    use units = "100000", which is a $100,000 budget -- a 1000x misread waiting
    to happen.

    This is an ALERT threshold, not a spending cap: GCP does not stop charges
    when it is crossed. The real cost guards are max_instance_count,
    scale-to-zero and the request timeout in service.tf.
  EOT
  type        = string
  default     = "20"
}

variable "max_instances" {
  description = <<-EOT
    Instance ceiling. This is the primary cost guard: an L4 instance bills at
    roughly $0.71/hr while active, so this bounds the worst case. Default
    quota is 3 L4s per region, so values above that fail regardless.
  EOT
  type        = number
  default     = 1
}

variable "request_timeout_seconds" {
  description = <<-EOT
    Per-request timeout. Must exceed the backend client's own timeout
    (IthacaServiceSettings.TIMEOUT, currently 240s) so the client gives up
    first and degrades gracefully, rather than Cloud Run severing the
    connection underneath it.
  EOT
  type        = number
  default     = 300

  validation {
    condition     = var.request_timeout_seconds > 240
    error_message = "Must exceed the backend client timeout of 240s."
  }
}
