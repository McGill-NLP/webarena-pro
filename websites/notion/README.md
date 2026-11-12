# Notion Sandbox (WebArena-Pro)
A multi-user, multi-workspace Notion-like sandbox for WebArena-style task execution and evaluation.

## What Changed
- Multi-user sessions and workspace switching
- Workspace memberships (`owner`, `editor`, `viewer`)
- Page-level access (`workspace` or `private`) and per-user page permissions
- Workspace tab model (open/close page tabs)
- Public share links for pages
- Page-level comments with basic `@email` mentions
- Attachments (URL and multipart upload)
- Image blocks in document editor
- Deterministic seed/reset across all entities

## Core Stack
- Next.js + TypeScript
- Tailwind CSS
- PostgreSQL
- Prisma ORM

## Docker Quick Start
The default local setup is now a self-contained Docker image. The image includes PostgreSQL, schema migration, and seeded data, so you do not need `docker compose`, a separate seed step, or a local Git checkout at runtime.

1. Build the image:

```bash
docker build -t yeonjooooni/notion-sandbox:populated .
```

2. Run the container:

```bash
docker run -d --name notion -p 3000:3000 yeonjooooni/notion-sandbox:populated
```

3. Open `http://localhost:3000/login`

If a previous container already uses the same name, recreate it:

```bash
docker rm -f notion
docker run -d --name notion -p 3000:3000 yeonjooooni/notion-sandbox:populated
```

## Reset
To restore the seeded baseline inside the container:

```bash
docker exec notion /app/docker-entry-seeded.sh reset
```

You can also remove and recreate the container from the same image:

```bash
docker rm -f notion
docker run -d --name notion -p 3000:3000 yeonjooooni/notion-sandbox:populated
```

## Source Development
Use this only when you are actively editing the website source and want hot reload instead of the packaged Docker runtime.

1. Start PostgreSQL:

```bash
docker compose up -d
```

2. Create `.env`:

```bash
DATABASE_URL="postgresql://webarena:webarena@localhost:5432/webarena?schema=public"
PASSWORD_SALT="change_me"
```

3. Install dependencies, migrate, and seed:

```bash
npm install
npm run prisma:migrate
npm run db:seed
```

4. Run the dev server:

```bash
npm run dev
```

Open `http://localhost:3000/login`.

If you see `Cannot find module './xxx.js'` from `.next/server/webpack-runtime.js`, stop all running dev servers and rebuild Next cache once:

```bash
npm run clean:next
npm run dev
```

## Seeded Users
All users use password `password123`.
- `demo@webarena.local`
- `alex@webarena.local`
- `mina@webarena.local`

## Source Development Reset
For source-development reset without Docker packaging:
- CLI: `npm run db:reset`
- API: `POST /api/reset`

## Main Routes
- `/login`
- `/app`
- `/app/page/:pageId`
- `/app/database/:pageId`
- `/share/:token`

## Manual Checklist (Notion-like MVP)
- [ ] Sidebar can collapse/expand from toggle button and `Cmd/Ctrl + \`.
- [ ] Sidebar state persists after refresh.
- [ ] Page can be dragged onto another page to become a child page.
- [ ] Page can be moved to trash from sidebar row action.
- [ ] Trash section shows deleted pages and supports restore/permanent delete.
- [ ] New database creates with only one `Name` (title) property by default.
- [ ] Database creation works for both full-page and inline modes.
- [ ] Database rows can be reordered by drag-and-drop.
- [ ] Document editor supports slash commands (`/`) for block conversion.
- [ ] Markdown shortcuts convert block type (`#`, `##`, `###`, `-`, `1.`, `[]`, `>`, `````).
- [ ] Block context menu has `Copy link to block`, `Duplicate`, `Delete`, `Turn into`.
- [ ] Opening `/app/page/:id#block-:blockId` scrolls/highlights the target block.
- [ ] Block drag-and-drop reorders blocks and persists.
- [ ] Image upload works via drag/drop, paste, and slash-command upload flow.
- [ ] Page `...` menu toggles page settings (`small text`, `full width`, `lock`, `font`) and persists.
- [ ] Theme mode toggle (`light`, `dark`, `system`) is available in page `...` menu.
- [ ] System mode follows OS dark/light preference changes.
- [ ] Database view settings panel opens from top-right settings icon.
- [ ] Block handle uses left `+` and `...` controls (no separate drag button).

## Evaluation-Friendly APIs
- `GET /api/pages/:id`
- `GET /api/pages/:id/blocks`
- `GET /api/databases/:id`
- `GET /api/databases/:id/rows`
- `GET /api/pages/:id/comments`
- `GET /api/pages/:id/permissions`
- `GET /api/pages/:id/attachments`
- `GET /api/pages/:id/share-links`
- `GET /api/workspaces`
- `GET /api/tabs`
- `POST /api/reset`

## Migration Notes
- A destructive schema migration is included at `prisma/migrations/20260305143000_multi_workspace/migration.sql`.
- This migration rebuilds tables/enums to move from single-user to multi-user/workspace domain.
- Recommended path from old local DB state:
  1. backup if needed
  2. run migration
  3. run seed/reset to restore deterministic baseline

## Evaluator image compatibility

Before releasing an image, run the [authenticated evaluator image gate](../../docs/source/evaluator-images.md) against an isolated container. A successful source build does not verify the published Docker Hub image.

## Row date regression

Row-page date inputs stay editable while saving. Writes to the same property run
in edit order, preventing a slow partial-year save from replacing a later date.

Against a disposable seeded container (the test edits and clears a task date):

```bash
uv run --with playwright python -m playwright install chromium
BASE_URL=http://127.0.0.1:3000 uv run --with playwright python tests/test_row_date_browser.py
```

The check types a year at 1280×720 with delayed saves, verifies focus and persisted
values after reload, checks clearing, and ensures a viewer still cannot edit.

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.
