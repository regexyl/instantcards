variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The default GCP region for resource deployment"
  type        = string
  default     = "europe-west2"
}

variable "zep_api_endpoint" {
  description = "The Zep API endpoint URL"
  type        = string
}

variable "media_retention_days" {
  description = "Number of days to retain media files before deletion"
  type        = number
  default     = 7
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "service_account_email" {
  description = "The email of the service account to use for the Cloud Functions"
  type        = string
  default     = null
}

variable "mochi_deck_url" {
  description = "The URL template for viewing Mochi decks"
  type        = string
  default     = "https://app.mochi.cards/decks/{deck_id}"
}

variable "sender_email" {
  description = "The email address to send notifications from"
  type        = string
} 