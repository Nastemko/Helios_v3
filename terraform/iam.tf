# Identities.
#
# Two service accounts, kept distinct so that "what the service runs as" and
# "who may call it" are separate identities. Collapsing them into one would
# mean the thing being protected and the thing granted access are the same
# principal, which defeats the point of the invoker binding.

# What the Cloud Run service runs as. Deliberately granted no project roles:
# the service reads nothing from GCP -- its checkpoints are baked into the
# image and it holds no state.
resource "google_service_account" "runtime" {
  account_id   = "ithaca-runtime"
  display_name = "Ithaca inference service runtime"
  description  = "Identity the Ithaca Cloud Run service runs as. Holds no project roles by design."
}

# What the backend authenticates as when calling the service. The backend mints
# an ID token for this identity (see backend/src/services/ithaca_client.py) and
# presents it as a bearer token.
resource "google_service_account" "invoker" {
  account_id   = "ithaca-invoker"
  display_name = "Ithaca inference service caller"
  description  = "Identity the Helios backend uses to invoke the Ithaca service."
}

# The only grant that matters. Because this is a member binding rather than an
# authoritative policy, it adds to the service's IAM without clobbering
# anything else bound to it.
#
# Note what is NOT here: no allUsers member. The service is private, and an
# unauthenticated request is rejected by Cloud Run before it reaches the
# container. In-process token verification (auth.py) is the second layer,
# confirming the token's audience names this service specifically.
resource "google_cloud_run_v2_service_iam_member" "backend_invoker" {
  project  = google_cloud_run_v2_service.ithaca.project
  location = google_cloud_run_v2_service.ithaca.location
  name     = google_cloud_run_v2_service.ithaca.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.invoker.email}"
}
