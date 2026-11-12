# Acidwave (Spotify-like Music Player)

Pre-populated Acidwave music streaming app with 30 classic songs, 25 artists, and full playlist/favorites support.

## Quick Start

```bash
# Build (downloads audio from Hugging Face during the frontend build)
HF_TOKEN=... docker build --secret id=hf_token,env=HF_TOKEN -t webarenapro/acidwave .

# Run
docker run -d --name acidwave -p 3000:80 webarenapro/acidwave

# Reset (wipe all changes, back to clean seed state)
docker rm -f acidwave
docker run -d --name acidwave -p 3000:80 webarenapro/acidwave
```

Access Acidwave at **http://localhost:3000**

## Credentials

| Role  | Username | Password |
|-------|----------|----------|
| User  | `aciduser`  | `aciduser`  |

> Accounts are stored in the browser's localStorage. You can also register a new account on first visit.

## API Endpoints

The backend runs on `/api` (proxied from nginx):

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/songs` | List songs (search, genre, artist_id, album_id, limit, offset) |
| `GET /api/artists` | List artists |
| `GET /api/albums` | List albums |
| `GET /api/playlists` | List playlists |
| `GET /api/favorites` | Get favorites (user_id query param) |
| `GET /api/stream?url=<audio_url>` | Audio stream proxy |

## Architecture

- **Frontend**: React + Vite + Tailwind CSS, served via nginx on port 80
- **Backend**: Express.js + PostgreSQL (pg), runs on port 3000 (internal)
- **Database**: PostgreSQL with 30 songs, 25 artists, 27 albums pre-seeded
- Single Docker container — PostgreSQL data baked into the image
- **Audio data**: local `/audio/*.mp3` song assets are downloaded at build time from `WebArena-Pro/acidwave-data`

## Cross-site transcription task

Task 310 uses **Velvet Circuit** (`/audio/eaeb.mp3`, 315 seconds), credited to
Wanda & Nova deViator's **Oral Pacification**. The seeded audio has English
vocals. Grading requires a document in MyDrive; any document filename or title
is accepted. The transcription criterion retains the original reference lyrics.
Task 310 checks document creation at Tier 0 using MyDrive file IDs captured before
the task. A new document must belong to agent1 and remain outside the trash;
renaming, moving or restoring an existing file does not count. This requires a
MyDrive image with file snapshot metadata; older images use the judge fallback.

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.
