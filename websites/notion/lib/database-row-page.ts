export const DATABASE_ROW_PAGE_PREFIX = "page_row_";

export function pageIdForDatabaseRow(rowId: string) {
  return `${DATABASE_ROW_PAGE_PREFIX}${rowId}`;
}

export function rowIdFromDatabaseRowPageId(pageId: string) {
  if (!pageId.startsWith(DATABASE_ROW_PAGE_PREFIX)) return null;
  const rowId = pageId.slice(DATABASE_ROW_PAGE_PREFIX.length).trim();
  return rowId.length > 0 ? rowId : null;
}
