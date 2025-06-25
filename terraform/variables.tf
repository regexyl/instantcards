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

variable "openai_api_key" {
  description = "The OpenAI API key for transcription services"
  type        = string
  sensitive   = true
}

variable "db_url" {
  description = "The database URL"
  type        = string
  sensitive   = true
}

variable "mochi_api_key" {
  description = "The Mochi API key"
  type        = string
  sensitive   = true
}

variable "mochi_block_template_id" {
  description = "The Mochi block template ID"
  type        = string
}

variable "mochi_atom_template_id" {
  description = "The Mochi atom template ID"
  type        = string
}

variable "mochi_atom_deck_id" {
  description = "The Mochi atom deck ID"
  type        = string
}

variable "mochi_block_deck_id" {
  description = "The Mochi block deck ID"
  type        = string
}