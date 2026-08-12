# The GPU inference service.
#
# Three GPU settings sit at three different nesting levels, which is the
# easiest thing here to get wrong:
#
#   nvidia.com/gpu                 -> template.containers.resources.limits (map key)
#   node_selector                  -> a block on template, sibling of containers
#   gpu_zonal_redundancy_disabled  -> a plain bool on template
#
# launch_stage is deliberately unset: Cloud Run GPUs are GA, and setting BETA
# causes perpetual diffs because the API rewrites the field.

locals {
  # Cloud Run's deterministic URL form for a v2 service. Used only to set the
  # service's own expected audience, where reading the resource's `uri`
  # attribute would create a dependency cycle.
  #
  # Every other consumer should use the real attribute via
  # `tofu output service_url`, not this reconstruction.
  expected_service_url = "https://${var.service_name}-${data.google_project.this.number}.${var.region}.run.app"
}

resource "google_cloud_run_v2_service" "ithaca" {
  name     = var.service_name
  location = var.region

  # v2 resources default this to true, which would block `tofu destroy`.
  deletion_protection = false

  # The backend is not on GCP yet, so ingress cannot be restricted to internal
  # traffic. Access control is IAM, not network position: the service is
  # private and requires roles/run.invoker. Tighten to INGRESS_TRAFFIC_INTERNAL
  # once the backend moves into the same VPC.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    # Must exceed the backend client's 240s timeout so the client is the one
    # that gives up first and degrades to available=false.
    timeout = "${var.request_timeout_seconds}s"

    # One request per instance. Beam search saturates the accelerator, so a
    # second concurrent request would contend rather than pipeline; let Cloud
    # Run queue instead. This also replaces the in-process semaphore the old
    # in-backend implementation used.
    max_instance_request_concurrency = 1

    scaling {
      # Scale to zero -- the entire reason for extracting this service. An idle
      # GPU instance bills continuously, so a nonzero floor would cost roughly
      # $500/month and blow the budget in about a day.
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        # L4 requires at least 4 CPU / 16Gi; 8/32 is Google's recommendation
        # and leaves headroom for the ~2GB of checkpoints plus JAX's host-side
        # allocations.
        limits = {
          "cpu"            = "8"
          "memory"         = "32Gi"
          "nvidia.com/gpu" = "1"
        }

        # Cold start here is dominated by loading checkpoints on the CPU before
        # anything touches the GPU, so the boost is worth having.
        startup_cpu_boost = true
      }

      env {
        name = "ITHACA_DEBUG"
        # "False" turns on caller token verification. Note the service refuses
        # to boot when this is False and ITHACA_AUDIENCE is empty, which is why
        # the two move together.
        value = var.enable_auth ? "False" : "True"
      }

      # The expected audience is this service's own URL. It cannot be read from
      # the resource's own `uri` attribute -- that would be a self-reference
      # and tofu rejects it as a dependency cycle -- so the URL is reconstructed
      # from its documented, deterministic form instead.
      #
      # This is why enable_auth is a two-pass flag: on the first apply the
      # service does not exist, so nothing can confirm the constructed URL is
      # right. Verify it against `tofu output service_url` before flipping the
      # flag; outputs.tf surfaces both for exactly this comparison.
      #
      # The audience must have no path component -- a trailing path is the
      # usual cause of a 401 that looks like a credentials problem but is
      # really an audience mismatch.
      dynamic "env" {
        for_each = var.enable_auth ? [1] : []
        content {
          name  = "ITHACA_AUDIENCE"
          value = local.expected_service_url
        }
      }

      # Fails closed: an instance that cannot load its checkpoints never
      # receives traffic. The threshold is generous (30 x 15s = 7.5 min)
      # because the wait is a ~2GB pickle load, not GPU initialisation.
      #
      # /health is unauthenticated precisely so probes can reach it.
      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 30
        period_seconds        = 15
        timeout_seconds       = 5
        failure_threshold     = 30
      }
    }

    node_selector {
      accelerator = "nvidia-l4"
    }

    # Not merely a cost setting. The 3-GPU-per-region default quota is granted
    # automatically only for the non-redundant configuration; the redundant
    # quota commonly starts at zero, so leaving this at its default is the
    # most likely cause of an apply failing on quota despite GPUs being GA.
    gpu_zonal_redundancy_disabled = true
  }

  lifecycle {
    # After the first apply the image belongs to the build pipeline, not to
    # tofu. Without this, every apply would revert the deployed image to
    # var.image -- which defaults to the placeholder.
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }

  depends_on = [google_project_service.apis]
}
