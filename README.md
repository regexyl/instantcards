# instantcards

<TBC>

## Setup

### Initialize Google Cloud

```
gcloud init
```

### Update sql codegen

```
sqlacodegen <DB_URL>
```

## Improvements

- Auth
- Send every error initially through email (for me)
- Handle lexemes
- Flag when unidic-lite is not able to handle certain words
- change field `audio_url` in db to `audio_path`
- store thumbnails in db
- Batch API calls to Mochi
- Add an eval layer to filter out block cards that are too easy
- Support non-Japanese languages (`from_language`)
- Translate atoms (currently relying on Mochi here)
- Evaluate transcription confidence level
- RLS in DB
- Refactor helpers (e.g. `get_media_bucket`)
