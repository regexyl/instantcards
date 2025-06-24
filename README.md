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
- Handle lexemes
- Flag when unidic-lite is not able to handle certain words
- Support non-Japanese languages (`from_language`)
- Translate atoms (currently relying on Mochi here)
- Evaluate transcription confidence level
- RLS in DB
- Refactor helpers (e.g. `get_media_bucket`)
