# Spend alerting.
#
# IMPORTANT: a budget is an ALERT, not a cap. GCP does not stop charges or shut
# anything down when a threshold is crossed -- it sends email. The structural
# cost guards are in service.tf: scale-to-zero, max_instance_count, and the
# request timeout. Those are what actually bound spend.
#
# Creating this requires billing.budgets.create on the BILLING ACCOUNT
# (roles/billing.admin or roles/billing.costsManager). Project-owner is not
# enough: the provider only calls the billing-account-scoped API. The console
# has a project-scoped path with laxer requirements, but the provider has no
# resource for it. If this 403s, set enable_budget = false and use the console.

resource "google_billing_budget" "monthly" {
  count = var.enable_budget ? 1 : 0

  lifecycle {
    # Catches the empty-string case at plan time. Without this the apply fails
    # partway through with an opaque API error about a malformed parent
    # resource name.
    precondition {
      condition     = var.billing_account_id != ""
      error_message = "billing_account_id must be set when enable_budget is true (format: 000000-000000-000000). Set enable_budget = false to skip the budget."
    }
  }

  billing_account = var.billing_account_id
  display_name    = "${var.service_name}-monthly"

  budget_filter {
    # Project NUMBER, not project ID, and the "projects/" prefix is required.
    projects = ["projects/${data.google_project.this.number}"]

    # Count credits against the budget, so the alert reflects what is actually
    # owed rather than gross usage.
    credit_types_treatment = "INCLUDE_ALL_CREDITS"

    # calendar_period is left unset: it defaults to MONTH, which is what is
    # wanted. It is also mutually exclusive with custom_period.
  }

  amount {
    specified_amount {
      currency_code = "USD"
      # Whole dollars. "20" is twenty dollars -- the provider's documentation
      # examples show "100000" for a $100,000 budget, which is easy to copy
      # into a 1000x mistake.
      units = var.budget_amount_usd
    }
  }

  # Escalating alerts on actual spend.
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  # Forecast-based: fires when GCP projects the month will end over budget,
  # which arrives early enough to act on. With a GPU that can bill ~$0.71/hr,
  # the warning that matters is the one before the money is spent.
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  # No all_updates_rule block: omitting it means alerts go to the billing
  # account's admins and users by email, with no Pub/Sub topic to maintain.

  depends_on = [google_project_service.billing_budgets]
}
