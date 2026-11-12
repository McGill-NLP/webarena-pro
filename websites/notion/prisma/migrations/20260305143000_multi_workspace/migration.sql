-- Rebuild schema for multi-user + multi-workspace capabilities.

DROP TABLE IF EXISTS "CommentMention" CASCADE;
DROP TABLE IF EXISTS "Comment" CASCADE;
DROP TABLE IF EXISTS "Attachment" CASCADE;
DROP TABLE IF EXISTS "ShareLink" CASCADE;
DROP TABLE IF EXISTS "PagePermission" CASCADE;
DROP TABLE IF EXISTS "WorkspaceTab" CASCADE;
DROP TABLE IF EXISTS "WorkspaceMembership" CASCADE;
DROP TABLE IF EXISTS "Workspace" CASCADE;
DROP TABLE IF EXISTS "DatabaseCellValue" CASCADE;
DROP TABLE IF EXISTS "DatabaseRow" CASCADE;
DROP TABLE IF EXISTS "DatabaseProperty" CASCADE;
DROP TABLE IF EXISTS "Database" CASCADE;
DROP TABLE IF EXISTS "Block" CASCADE;
DROP TABLE IF EXISTS "Page" CASCADE;
DROP TABLE IF EXISTS "User" CASCADE;

DROP TYPE IF EXISTS "PageType" CASCADE;
DROP TYPE IF EXISTS "BlockType" CASCADE;
DROP TYPE IF EXISTS "DatabasePropertyType" CASCADE;
DROP TYPE IF EXISTS "WorkspaceRole" CASCADE;
DROP TYPE IF EXISTS "PagePermissionRole" CASCADE;
DROP TYPE IF EXISTS "PageAccessLevel" CASCADE;

CREATE TYPE "PageType" AS ENUM ('document', 'database');
CREATE TYPE "BlockType" AS ENUM ('paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item', 'todo', 'toggle', 'image');
CREATE TYPE "DatabasePropertyType" AS ENUM ('title', 'text', 'select', 'multi_select', 'checkbox', 'date');
CREATE TYPE "WorkspaceRole" AS ENUM ('owner', 'editor', 'viewer');
CREATE TYPE "PagePermissionRole" AS ENUM ('editor', 'commenter', 'viewer');
CREATE TYPE "PageAccessLevel" AS ENUM ('workspace', 'private');

CREATE TABLE "User" (
  "id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "passwordHash" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Workspace" (
  "id" TEXT NOT NULL,
  "slug" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Workspace_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "WorkspaceMembership" (
  "id" TEXT NOT NULL,
  "workspaceId" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "role" "WorkspaceRole" NOT NULL,
  "lastActiveAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "WorkspaceMembership_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Page" (
  "id" TEXT NOT NULL,
  "workspaceId" TEXT NOT NULL,
  "createdById" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "type" "PageType" NOT NULL,
  "accessLevel" "PageAccessLevel" NOT NULL DEFAULT 'workspace',
  "parentPageId" TEXT,
  "icon" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Page_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "WorkspaceTab" (
  "id" TEXT NOT NULL,
  "membershipId" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "position" INTEGER NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "WorkspaceTab_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "PagePermission" (
  "id" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "role" "PagePermissionRole" NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "PagePermission_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ShareLink" (
  "id" TEXT NOT NULL,
  "token" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "createdById" TEXT NOT NULL,
  "isActive" BOOLEAN NOT NULL DEFAULT true,
  "expiresAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ShareLink_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Block" (
  "id" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "type" "BlockType" NOT NULL,
  "contentText" TEXT,
  "checked" BOOLEAN,
  "imageUrl" TEXT,
  "position" INTEGER NOT NULL,
  "parentBlockId" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Block_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Comment" (
  "id" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "authorId" TEXT NOT NULL,
  "parentCommentId" TEXT,
  "content" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Comment_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "CommentMention" (
  "id" TEXT NOT NULL,
  "commentId" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "CommentMention_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Attachment" (
  "id" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "uploadedById" TEXT NOT NULL,
  "fileName" TEXT NOT NULL,
  "fileUrl" TEXT NOT NULL,
  "mimeType" TEXT NOT NULL,
  "sizeBytes" INTEGER NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Attachment_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Database" (
  "id" TEXT NOT NULL,
  "pageId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Database_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "DatabaseProperty" (
  "id" TEXT NOT NULL,
  "databaseId" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "type" "DatabasePropertyType" NOT NULL,
  "position" INTEGER NOT NULL,
  "configJson" JSONB NOT NULL,
  CONSTRAINT "DatabaseProperty_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "DatabaseRow" (
  "id" TEXT NOT NULL,
  "databaseId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "position" INTEGER NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "DatabaseRow_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "DatabaseCellValue" (
  "id" TEXT NOT NULL,
  "rowId" TEXT NOT NULL,
  "propertyId" TEXT NOT NULL,
  "valueJson" JSONB NOT NULL,
  CONSTRAINT "DatabaseCellValue_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "User_email_key" ON "User"("email");
CREATE UNIQUE INDEX "Workspace_slug_key" ON "Workspace"("slug");
CREATE UNIQUE INDEX "WorkspaceMembership_workspaceId_userId_key" ON "WorkspaceMembership"("workspaceId", "userId");
CREATE INDEX "WorkspaceMembership_userId_idx" ON "WorkspaceMembership"("userId");
CREATE INDEX "Page_workspaceId_title_idx" ON "Page"("workspaceId", "title");
CREATE INDEX "Page_workspaceId_parentPageId_idx" ON "Page"("workspaceId", "parentPageId");
CREATE UNIQUE INDEX "WorkspaceTab_membershipId_pageId_key" ON "WorkspaceTab"("membershipId", "pageId");
CREATE INDEX "WorkspaceTab_membershipId_position_idx" ON "WorkspaceTab"("membershipId", "position");
CREATE UNIQUE INDEX "PagePermission_pageId_userId_key" ON "PagePermission"("pageId", "userId");
CREATE INDEX "PagePermission_userId_role_idx" ON "PagePermission"("userId", "role");
CREATE UNIQUE INDEX "ShareLink_token_key" ON "ShareLink"("token");
CREATE INDEX "Block_pageId_position_idx" ON "Block"("pageId", "position");
CREATE INDEX "Comment_pageId_createdAt_idx" ON "Comment"("pageId", "createdAt");
CREATE UNIQUE INDEX "CommentMention_commentId_userId_key" ON "CommentMention"("commentId", "userId");
CREATE INDEX "CommentMention_userId_idx" ON "CommentMention"("userId");
CREATE INDEX "Attachment_pageId_createdAt_idx" ON "Attachment"("pageId", "createdAt");
CREATE UNIQUE INDEX "Database_pageId_key" ON "Database"("pageId");
CREATE INDEX "DatabaseProperty_databaseId_position_idx" ON "DatabaseProperty"("databaseId", "position");
CREATE INDEX "DatabaseRow_databaseId_position_idx" ON "DatabaseRow"("databaseId", "position");
CREATE UNIQUE INDEX "DatabaseCellValue_rowId_propertyId_key" ON "DatabaseCellValue"("rowId", "propertyId");

ALTER TABLE "WorkspaceMembership" ADD CONSTRAINT "WorkspaceMembership_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WorkspaceMembership" ADD CONSTRAINT "WorkspaceMembership_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Page" ADD CONSTRAINT "Page_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Page" ADD CONSTRAINT "Page_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "Page" ADD CONSTRAINT "Page_parentPageId_fkey" FOREIGN KEY ("parentPageId") REFERENCES "Page"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "WorkspaceTab" ADD CONSTRAINT "WorkspaceTab_membershipId_fkey" FOREIGN KEY ("membershipId") REFERENCES "WorkspaceMembership"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WorkspaceTab" ADD CONSTRAINT "WorkspaceTab_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "PagePermission" ADD CONSTRAINT "PagePermission_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "PagePermission" ADD CONSTRAINT "PagePermission_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ShareLink" ADD CONSTRAINT "ShareLink_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ShareLink" ADD CONSTRAINT "ShareLink_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Block" ADD CONSTRAINT "Block_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Block" ADD CONSTRAINT "Block_parentBlockId_fkey" FOREIGN KEY ("parentBlockId") REFERENCES "Block"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "Comment" ADD CONSTRAINT "Comment_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Comment" ADD CONSTRAINT "Comment_authorId_fkey" FOREIGN KEY ("authorId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Comment" ADD CONSTRAINT "Comment_parentCommentId_fkey" FOREIGN KEY ("parentCommentId") REFERENCES "Comment"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "CommentMention" ADD CONSTRAINT "CommentMention_commentId_fkey" FOREIGN KEY ("commentId") REFERENCES "Comment"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "CommentMention" ADD CONSTRAINT "CommentMention_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Attachment" ADD CONSTRAINT "Attachment_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Attachment" ADD CONSTRAINT "Attachment_uploadedById_fkey" FOREIGN KEY ("uploadedById") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Database" ADD CONSTRAINT "Database_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "DatabaseProperty" ADD CONSTRAINT "DatabaseProperty_databaseId_fkey" FOREIGN KEY ("databaseId") REFERENCES "Database"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "DatabaseRow" ADD CONSTRAINT "DatabaseRow_databaseId_fkey" FOREIGN KEY ("databaseId") REFERENCES "Database"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "DatabaseCellValue" ADD CONSTRAINT "DatabaseCellValue_rowId_fkey" FOREIGN KEY ("rowId") REFERENCES "DatabaseRow"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "DatabaseCellValue" ADD CONSTRAINT "DatabaseCellValue_propertyId_fkey" FOREIGN KEY ("propertyId") REFERENCES "DatabaseProperty"("id") ON DELETE CASCADE ON UPDATE CASCADE;
