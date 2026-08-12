# Provider pin and state backend.
#
# No `backend` block is declared, so state is local (./terraform.tfstate). That
# is a deliberate choice for a single-operator deployment, and it has one
# consequence worth knowing: state lives only on this machine and is not
# locked. Do not run apply from two places, and back the file up -- losing it
# means tofu no longer knows about the resources it created.
#
# State also contains resource metadata that should not be published; see
# .gitignore in this directory.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source = "hashicorp/google"
      # Pinned to a major version: the 6 -> 7 bump carried breaking changes,
      # and an unpinned provider would take them silently on the next init.
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
