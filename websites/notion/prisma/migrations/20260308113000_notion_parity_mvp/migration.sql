-- Notion-parity MVP schema changes: soft delete, page settings, richer blocks.

DO $$ BEGIN
  CREATE TYPE "PageFontStyle" AS ENUM ('default', 'serif', 'mono');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

ALTER TYPE "BlockType" ADD VALUE IF NOT EXISTS 'quote';
ALTER TYPE "BlockType" ADD VALUE IF NOT EXISTS 'divider';
ALTER TYPE "BlockType" ADD VALUE IF NOT EXISTS 'code';
ALTER TYPE "BlockType" ADD VALUE IF NOT EXISTS 'callout';

ALTER TABLE "Page"
  ADD COLUMN IF NOT EXISTS "deletedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "isSmallText" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "isFullWidth" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "isLocked" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "fontStyle" "PageFontStyle" NOT NULL DEFAULT 'default';

ALTER TABLE "Block"
  ADD COLUMN IF NOT EXISTS "propsJson" JSONB,
  ADD COLUMN IF NOT EXISTS "richTextJson" JSONB;

CREATE INDEX IF NOT EXISTS "Page_workspaceId_deletedAt_parentPageId_idx" ON "Page"("workspaceId", "deletedAt", "parentPageId");
