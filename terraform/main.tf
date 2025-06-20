terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    # Configure during init
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "workflows.googleapis.com",
    "speech.googleapis.com",
    "translate.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com"
  ])
  
  service = each.key
  disable_on_destroy = false
}

# Storage buckets
resource "google_storage_bucket" "media_bucket" {
  name     = "${var.project_id}-media"
  location = var.region
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = var.media_retention_days
    }
    action {
      type = "Delete"
    }
  }
}

# Secret Manager secrets
resource "google_secret_manager_secret" "zep_api_key" {
  secret_id = "zep-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "mochi_api_key" {
  secret_id = "mochi-api-key"
  replication {
    auto {}
  }
}

# Replace SendGrid API key secret with Postmark
resource "google_secret_manager_secret" "postmark_api_token" {
  secret_id = "postmark-api-token"
  replication {
    auto {}
  }
}

# Cloud Functions
module "youtube_processor" {
  source = "./modules/cloud_function"
  
  name        = "youtube-processor"
  description = "Processes YouTube videos and extracts audio"
  runtime     = "python310"
  
  source_dir  = "../src/functions/youtube_processor"
  entry_point = "process_video"
  
  environment_variables = {
    MEDIA_BUCKET = google_storage_bucket.media_bucket.name
  }
  
  secret_environment_variables = {
    ZEP_API_KEY = google_secret_manager_secret.zep_api_key.secret_id
  }
}

module "transcription_processor" {
  source = "./modules/cloud_function"
  
  name        = "transcription-processor"
  description = "Transcribes audio using Speech-to-Text"
  runtime     = "python310"
  
  source_dir  = "../src/functions/transcription_processor"
  entry_point = "process_transcription"
  
  environment_variables = {
    MEDIA_BUCKET = google_storage_bucket.media_bucket.name
  }
}

module "translation_processor" {
  source = "./modules/cloud_function"
  
  name        = "translation-processor"
  description = "Translates and extracts vocabulary"
  runtime     = "python310"
  
  source_dir  = "../src/functions/translation_processor"
  entry_point = "process_translation"
  
  environment_variables = {
    MEDIA_BUCKET = google_storage_bucket.media_bucket.name
    ZEP_ENDPOINT = var.zep_api_endpoint
  }
  
  secret_environment_variables = {
    ZEP_API_KEY = google_secret_manager_secret.zep_api_key.secret_id
  }
}

module "cards_processor" {
  source = "./modules/cloud_function"
  
  name        = "cards-processor"
  description = "Creates flashcards from processed content"
  runtime     = "python310"
  
  source_dir  = "../src/functions/cards_processor"
  entry_point = "create_cards"
  
  secret_environment_variables = {
    MOCHI_API_KEY = google_secret_manager_secret.mochi_api_key.secret_id
  }
}

# Update notification processor function
module "notification_processor" {
  source = "./modules/cloud_function"
  
  name        = "notification-processor"
  description = "Sends completion notifications to users"
  runtime     = "python310"
  
  source_dir  = "../src/functions/notification_processor"
  entry_point = "send_notification"
  
  environment_variables = {
    SENDER_EMAIL   = var.sender_email
    MOCHI_DECK_URL = var.mochi_deck_url
  }
  
  secret_environment_variables = {
    POSTMARK_API_TOKEN = google_secret_manager_secret.postmark_api_token.secret_id
  }
}

# Cloud Workflow
resource "google_workflows_workflow" "video_to_cards" {
  name            = "video-to-cards-workflow"
  region          = var.region
  source_contents = templatefile("${path.module}/workflow.yaml", {
    youtube_processor_url        = module.youtube_processor.function_url
    transcription_processor_url  = module.transcription_processor.function_url
    translation_processor_url    = module.translation_processor.function_url
    cards_processor_url          = module.cards_processor.function_url
    notification_processor_url   = module.notification_processor.function_url
  })
  
  depends_on = [
    google_project_service.required_apis
  ]
}

output "workflow_url" {
  description = "The URL of the deployed workflow"
  value       = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${google_workflows_workflow.video_to_cards.name}/executions"
}

output "workflow_name" {
  description = "The name of the deployed workflow"
  value       = google_workflows_workflow.video_to_cards.name
}

output "youtube_processor_url" {
  description = "URL of the YouTube processor function"
  value       = module.youtube_processor.function_url
}

output "transcription_processor_url" {
  description = "URL of the transcription processor function"
  value       = module.transcription_processor.function_url
}

output "translation_processor_url" {
  description = "URL of the translation processor function"
  value       = module.translation_processor.function_url
}

output "cards_processor_url" {
  description = "URL of the cards processor function"
  value       = module.cards_processor.function_url
}

output "notification_processor_url" {
  description = "URL of the notification processor function"
  value       = module.notification_processor.function_url
} 