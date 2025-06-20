variable "name" {
  description = "The name of the Cloud Function"
  type        = string
}

variable "description" {
  description = "Description of the Cloud Function"
  type        = string
  default     = ""
}

variable "runtime" {
  description = "The runtime to use for the function"
  type        = string
  default     = "python310"
}

variable "source_dir" {
  description = "The directory containing the source code"
  type        = string
}

variable "entry_point" {
  description = "The function entry point"
  type        = string
}

variable "environment_variables" {
  description = "Environment variables to set for the function"
  type        = map(string)
  default     = {}
}

variable "secret_environment_variables" {
  description = "Secret environment variables to set for the function"
  type        = map(string)
  default     = {}
}

# Create a ZIP archive of the source code
data "archive_file" "source" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "/tmp/${var.name}.zip"
}

# Upload the source code to a Cloud Storage bucket
resource "google_storage_bucket_object" "source" {
  name   = "${var.name}-${data.archive_file.source.output_md5}.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = data.archive_file.source.output_path
}

# Create a bucket for the function source code
resource "google_storage_bucket" "function_bucket" {
  name     = "${var.name}-source"
  location = "US"
  uniform_bucket_level_access = true
}

# Create the Cloud Function
resource "google_cloudfunctions2_function" "function" {
  name        = var.name
  description = var.description
  location    = "europe-west2"

  build_config {
    runtime     = var.runtime
    entry_point = var.entry_point
    source {
      storage_source {
        bucket = google_storage_bucket.function_bucket.name
        object = google_storage_bucket_object.source.name
      }
    }
  }

  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 540
    service_account_email = google_service_account.function_service_account.email
    
    environment_variables = var.environment_variables
    
    dynamic "secret_environment_variables" {
      for_each = var.secret_environment_variables
      content {
        key        = secret_environment_variables.key
        project_id = data.google_project.project.project_id
        secret     = secret_environment_variables.value
        version    = "latest"
      }
    }
  }
}

# Get project data
data "google_project" "project" {}

# Create service account for the function
resource "google_service_account" "function_service_account" {
  account_id   = "${var.name}-sa"
  display_name = "Service account for ${var.name} Cloud Function"
}

# Grant Secret Manager Secret Accessor role to the service account
resource "google_project_iam_member" "secret_accessor" {
  project = data.google_project.project.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.function_service_account.email}"
}

# Output the function URL
output "function_url" {
  description = "The URL of the deployed Cloud Function"
  value       = google_cloudfunctions2_function.function.url
} 