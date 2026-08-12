output "service_url" {
  description = <<-EOT
    The service's real URL. Feeds both ITHACA_SERVICE_URL and
    ITHACA_SERVICE_AUDIENCE on the backend.
  EOT
  value       = google_cloud_run_v2_service.ithaca.uri
}

output "expected_service_url" {
  description = <<-EOT
    The URL that was constructed for the service's own ITHACA_AUDIENCE.

    Compare with service_url before setting enable_auth = true. If they differ,
    the audience will be wrong and every call will 401 -- change service_name
    or set ITHACA_AUDIENCE by hand rather than flipping the flag.
  EOT
  value       = local.expected_service_url
}

output "audience_matches" {
  description = "False means do not enable auth yet; see expected_service_url."
  value       = local.expected_service_url == google_cloud_run_v2_service.ithaca.uri
}

output "invoker_service_account" {
  description = <<-EOT
    Service account the backend must authenticate as. Give the backend a key
    for this, or bind it to the backend's own runtime identity via
    roles/iam.serviceAccountTokenCreator.
  EOT
  value       = google_service_account.invoker.email
}

output "runtime_service_account" {
  description = "Service account the Cloud Run service runs as."
  value       = google_service_account.runtime.email
}

output "image_repository" {
  description = "Artifact Registry path to push the inference image to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}

output "backend_env" {
  description = <<-EOT
    Environment variables to set on the Helios backend so it reaches this
    service. Both keys are read by IthacaServiceSettings (env_prefix
    ITHACA_SERVICE_) in backend/src/config.py.
  EOT
  value = {
    ITHACA_SERVICE_URL      = google_cloud_run_v2_service.ithaca.uri
    ITHACA_SERVICE_AUDIENCE = google_cloud_run_v2_service.ithaca.uri
  }
}
