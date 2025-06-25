# Notification Processor

This Cloud Function sends email notifications when video processing is complete using Gmail SMTP.

## Setup

### 1. Enable Gmail App Passwords

1. Go to your Google Account settings
2. Navigate to "Security" > "2-Step Verification"
3. Scroll down to "App passwords"
4. Generate a new app password for "Mail"
5. Save this password securely

### 2. Environment Variables

Set these environment variables in your Cloud Function:

- `SENDER_EMAIL`: Your Gmail address (e.g., "your-email@gmail.com")
- `SENDER_PASSWORD`: The app password generated in step 1 (NOT your regular Gmail password)
- `MOCHI_DECK_URL`: URL template for viewing Mochi decks

### 3. Deploy

The function uses standard Python libraries and doesn't require additional dependencies.

## Usage

Send a POST request with:

```json
{
  "email": "recipient@example.com",
  "job_id": "job-123",
  "stats": {
    "cards_created": 42,
    "new_words": 38,
    "processing_time": 123.45
  }
}
```

## Security Notes

- Use app passwords, not your regular Gmail password
- Store the app password in Google Secret Manager for production
- Never commit passwords to version control
- Consider using Google Secret Manager for production deployments

## Why SMTP instead of Gmail API?

- ✅ Much simpler setup - no complex API authentication
- ✅ Uses standard Python libraries
- ✅ No additional dependencies
- ✅ Easier to debug and maintain
- ✅ Works with any Gmail account
