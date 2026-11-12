# Refactor Audit: Single-User -> Multi-User/Workspace

## 1) Safe to Keep
- Next.js app structure and route-handler architecture (`app/`, `app/api/`)
- Prisma + PostgreSQL baseline
- Existing document/database CRUD flow patterns
- Seed/reset entry points (`prisma/seed.ts`, `scripts/reset.ts`, `app/api/reset`)

## 2) Must Be Refactored
- Session model: `webarena_session=1` -> user-bound session + active workspace cookie
- All content APIs: add workspace scoping and page permission checks
- Page model: add workspace ownership and access level controls
- Sidebar/main shell: add workspace switcher and tabs
- Editor: add image block support
- Collaboration data plane: comments, mentions, attachments, share links

## 3) Required Schema Changes
- Added: `Workspace`, `WorkspaceMembership`, `WorkspaceTab`
- Expanded: `Page` now has `workspaceId`, `createdById`, `accessLevel`, `icon`
- Added page ACL: `PagePermission`
- Added public sharing: `ShareLink`
- Added collaboration: `Comment`, `CommentMention`, `Attachment`
- Expanded `BlockType` with `image`; `Block` includes `imageUrl`
- Existing database tables kept and linked through page/workspace model

## 4) Recommended Migration Path
1. Apply destructive migration (`20260305143000_multi_workspace`) in dev/test.
2. Run deterministic seed/reset to repopulate baseline entities.
3. Update evaluator calls to workspace-scoped APIs where needed.
4. Validate private-page permission scenarios and shared-link reads.
5. Add non-destructive data migration only if legacy production data must be preserved.
