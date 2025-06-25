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

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "openai-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "openai_api_key" {
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = var.openai_api_key
}


# Add DB URL secret
resource "google_secret_manager_secret" "db_url" {
  secret_id = "db-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = var.db_url
}

# Replace SendGrid API key secret with Postmark
resource "google_secret_manager_secret" "postmark_api_token" {
  secret_id = "postmark-api-token"
  replication {
    auto {}
  }
}

# Cloud Functions
module "job_manager" {
  source = "./modules/cloud_function"
  
  name        = "job-manager"
  description = "Manages job creation and status tracking in the database"
  runtime     = "python310"
  
  source_dir  = "../src/functions/job_manager"
  entry_point = "manage_job"
  
  secret_environment_variables = {
    DB_URL = google_secret_manager_secret.db_url.secret_id
  }
}

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

module "transcription_translation_cards_processor" {
  source = "./modules/cloud_function"
  
  name        = "transcription-translation-cards-processor"
  description = "Transcribes audio and translates content using OpenAI. Creates cards in Mochi."
  runtime     = "python310"
  
  source_dir  = "../src/functions/transcription_processor"
  entry_point = "process_transcription_and_translation"
  
  environment_variables = {
    MEDIA_BUCKET = google_storage_bucket.media_bucket.name
  }
  
  secret_environment_variables = {
    OPENAI_API_KEY = google_secret_manager_secret.openai_api_key.secret_id
    DB_URL = google_secret_manager_secret.db_url.secret_id
  }
}

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
    DB_URL = google_secret_manager_secret.db_url.secret_id
  }
}

resource "google_workflows_workflow" "video_to_cards" {
  name            = "video-to-cards-workflow"
  region          = var.region
  source_contents = templatefile("${path.module}/workflow.yaml", {
    job_manager_url              = module.job_manager.function_url
    youtube_processor_url        = module.youtube_processor.function_url
    transcription_translation_cards_processor_url  = module.transcription_translation_cards_processor.function_url
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

output "job_manager_url" {
  description = "URL of the job manager function"
  value       = module.job_manager.function_url
}

output "youtube_processor_url" {
  description = "URL of the YouTube processor function"
  value       = module.youtube_processor.function_url
}

output "transcription_translation_cards_processor_url" {
  description = "URL of the transcription translation cards processor function"
  value       = module.transcription_translation_cards_processor.function_url
}

output "notification_processor_url" {
  description = "URL of the notification processor function"
  value       = module.notification_processor.function_url
} 