# Service APIs.
#
# Enablement is slow and eventually-consistent: a resource created immediately
# after its API is enabled can fail with a "not enabled" error that succeeds on
# retry. Everything downstream therefore depends_on these explicitly rather
# than relying on tofu's implicit ordering, and the README suggests applying
# this file first with -target.
#
# disable_on_destroy is false throughout: tearing down this stack should not
# disable APIs that other things in the project may depend on.

locals {
  required_apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    # Needed by the backend to mint ID tokens for this service.
    "iamcredentials.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)

  service            = each.value
  disable_on_destroy = false
}

# Separate from the set above because it is conditional: only needed when a
# budget is being managed here.
resource "google_project_service" "billing_budgets" {
  count = var.enable_budget ? 1 : 0

  service            = "billingbudgets.googleapis.com"
  disable_on_destroy = false
}
