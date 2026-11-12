-- CreateEnum
CREATE TYPE "PageType" AS ENUM ('document', 'database');

-- CreateEnum
CREATE TYPE "BlockType" AS ENUM ('paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item', 'todo', 'toggle');

-- CreateEnum
CREATE TYPE "DatabasePropertyType" AS ENUM ('title', 'text', 'select', 'multi_select', 'checkbox', 'date');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Page" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "type" "PageType" NOT NULL,
    "parentPageId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Page_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Block" (
    "id" TEXT NOT NULL,
    "pageId" TEXT NOT NULL,
    "type" "BlockType" NOT NULL,
    "contentText" TEXT,
    "checked" BOOLEAN,
    "position" INTEGER NOT NULL,
    "parentBlockId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Block_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Database" (
    "id" TEXT NOT NULL,
    "pageId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Database_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DatabaseProperty" (
    "id" TEXT NOT NULL,
    "databaseId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "type" "DatabasePropertyType" NOT NULL,
    "position" INTEGER NOT NULL,
    "configJson" JSONB NOT NULL,

    CONSTRAINT "DatabaseProperty_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DatabaseRow" (
    "id" TEXT NOT NULL,
    "databaseId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "position" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "DatabaseRow_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DatabaseCellValue" (
    "id" TEXT NOT NULL,
    "rowId" TEXT NOT NULL,
    "propertyId" TEXT NOT NULL,
    "valueJson" JSONB NOT NULL,

    CONSTRAINT "DatabaseCellValue_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE INDEX "Block_pageId_position_idx" ON "Block"("pageId", "position");

-- CreateIndex
CREATE UNIQUE INDEX "Database_pageId_key" ON "Database"("pageId");

-- CreateIndex
CREATE INDEX "DatabaseProperty_databaseId_position_idx" ON "DatabaseProperty"("databaseId", "position");

-- CreateIndex
CREATE INDEX "DatabaseRow_databaseId_position_idx" ON "DatabaseRow"("databaseId", "position");

-- CreateIndex
CREATE UNIQUE INDEX "DatabaseCellValue_rowId_propertyId_key" ON "DatabaseCellValue"("rowId", "propertyId");

-- AddForeignKey
ALTER TABLE "Page" ADD CONSTRAINT "Page_parentPageId_fkey" FOREIGN KEY ("parentPageId") REFERENCES "Page"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Block" ADD CONSTRAINT "Block_parentBlockId_fkey" FOREIGN KEY ("parentBlockId") REFERENCES "Block"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Block" ADD CONSTRAINT "Block_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Database" ADD CONSTRAINT "Database_pageId_fkey" FOREIGN KEY ("pageId") REFERENCES "Page"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DatabaseProperty" ADD CONSTRAINT "DatabaseProperty_databaseId_fkey" FOREIGN KEY ("databaseId") REFERENCES "Database"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DatabaseRow" ADD CONSTRAINT "DatabaseRow_databaseId_fkey" FOREIGN KEY ("databaseId") REFERENCES "Database"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DatabaseCellValue" ADD CONSTRAINT "DatabaseCellValue_rowId_fkey" FOREIGN KEY ("rowId") REFERENCES "DatabaseRow"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DatabaseCellValue" ADD CONSTRAINT "DatabaseCellValue_propertyId_fkey" FOREIGN KEY ("propertyId") REFERENCES "DatabaseProperty"("id") ON DELETE CASCADE ON UPDATE CASCADE;
