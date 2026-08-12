# Artifact Registry for the inference image.
#
# The image is built by Cloud Build (see ithaca-service/cloudbuild.yaml) rather
# than by tofu. Shelling out to a builder during apply would make the apply
# non-hermetic and require Docker on whatever runs it; keeping the build a
# separate, explicit command is both simpler and easier to re-run.

data "google_project" "this" {}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "Helios container images (Ithaca/Aeneas inference)."

  depends_on = [google_project_service.apis]
}

# Cloud Build's default service agent needs to push into the repository above.
# It exists implicitly once cloudbuild.googleapis.com is enabled, so it is
# referenced by address rather than declared.
resource "google_artifact_registry_repository_iam_member" "cloudbuild_writer" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.this.number}@cloudbuild.gserviceaccount.com"
}
