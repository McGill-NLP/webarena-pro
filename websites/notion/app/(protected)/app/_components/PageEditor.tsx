"use client";

import {
  ArrowUpCircle,
  AtSign,
  Bold,
  Check,
  Ellipsis,
  Code2,
  Heading1,
  Heading2,
  Heading3,
  ImageIcon,
  Italic,
  Link2,
  List,
  ListOrdered,
  MessageSquare,
  Minus,
  MoreHorizontal,
  Plus,
  Quote,
  SmilePlus,
  Sigma,
  SquareCheck,
  Strikethrough,
  Type,
  Underline,
  ChevronRight,
  AlertCircle,
  Palette,
  Paperclip,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ComponentType, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import DatabaseTable from "./DatabaseTable";

type BlockType =
  | "paragraph"
  | "heading_1"
  | "heading_2"
  | "heading_3"
  | "bulleted_list_item"
  | "numbered_list_item"
  | "todo"
  | "toggle"
  | "image"
  | "quote"
  | "divider"
  | "code"
  | "callout";

type Block = {
  id: string;
  type: BlockType;
  contentText: string | null;
  checked: boolean | null;
  imageUrl: string | null;
  position: number;
  parentBlockId: string | null;
  propsJson: any;
  richTextJson: any;
};

type SlashCommand = {
  id: string;
  label: string;
  description: string;
  type?: BlockType;
  action?: "image_upload" | "create_inline_database" | "create_child_page" | "create_full_database" | "create_inline_table";
  keywords: string;
  icon: ComponentType<{ className?: string }>;
};

type LinkedPageView = "inline" | "link";

type InlineToolbarState = {
  blockId: string;
  start: number;
  end: number;
  x: number;
  y: number;
};

type InlineMark = {
  start: number;
  end: number;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  strikethrough?: boolean;
  code?: boolean;
  equation?: boolean;
  link?: string;
  color?: string;
  backgroundColor?: string;
};

type InlineStyle = Omit<InlineMark, "start" | "end">;
type ToggleInlineMarkKey = "bold" | "italic" | "underline" | "strikethrough" | "code" | "equation";

type DropIndicatorState = {
  overId: string;
  parentBlockId: string | null;
};

type CommentItem = {
  id: string;
  content: string;
  createdAt: string;
  parentCommentId: string | null;
  author: {
    id: string;
    email: string;
  };
  mentions: Array<{
    id: string;
    user: {
      id: string;
      email: string;
    };
  }>;
};

type CommentMeta = {
  blockId: string;
  quote: string;
};

type CommentReaction = {
  emoji: string;
  userIds: string[];
};

type CommentUiMeta = {
  reactions?: CommentReaction[];
};

type ParsedComment = CommentItem & {
  displayContent: string;
  anchorBlockId: string | null;
  anchorQuote: string | null;
  uiMeta: CommentUiMeta;
};

type CommentThreadGroup = {
  blockId: string;
  blockQuote: string;
  threads: ParsedComment[];
  composer: {
    blockId: string;
    quote: string;
    text: string;
    parentCommentId: string | null;
  } | null;
};

type MentionCandidate = {
  id: string;
  email: string;
};

const PAGE_COMMENT_ANCHOR = "__page__";

const INDENT_SIZE = 18;

const MAX_UNDO_STACK = 80;
const UNDO_COALESCE_MS = 450;

const CODE_LANGUAGES = [
  "plain",
  "typescript",
  "javascript",
  "python",
  "java",
  "cpp",
  "go",
  "rust",
  "sql",
  "html",
  "css",
];

const TURN_INTO_TYPES: { value: BlockType; label: string; icon: SlashCommand["icon"] }[] = [
  { value: "paragraph", label: "Text", icon: Type },
  { value: "heading_1", label: "Heading 1", icon: Heading1 },
  { value: "heading_2", label: "Heading 2", icon: Heading2 },
  { value: "heading_3", label: "Heading 3", icon: Heading3 },
  { value: "bulleted_list_item", label: "Bulleted list", icon: List },
  { value: "numbered_list_item", label: "Numbered list", icon: ListOrdered },
  { value: "todo", label: "To-do list", icon: SquareCheck },
  { value: "toggle", label: "Toggle list", icon: ChevronRight },
  { value: "code", label: "Code", icon: Code2 },
  { value: "quote", label: "Quote", icon: Quote },
  { value: "callout", label: "Callout", icon: AlertCircle },
  { value: "image", label: "Image", icon: ImageIcon },
  { value: "divider", label: "Divider", icon: Minus },
];

const SLASH_COMMANDS: SlashCommand[] = [
  { id: "text", label: "Text", description: "Plain text", type: "paragraph", keywords: "text paragraph", icon: Type },
  { id: "h1", label: "Heading 1", description: "Large section heading", type: "heading_1", keywords: "h1 heading", icon: Heading1 },
  { id: "h2", label: "Heading 2", description: "Medium section heading", type: "heading_2", keywords: "h2 heading", icon: Heading2 },
  { id: "h3", label: "Heading 3", description: "Small section heading", type: "heading_3", keywords: "h3 heading", icon: Heading3 },
  { id: "bullet", label: "Bulleted list", description: "Create a bulleted list", type: "bulleted_list_item", keywords: "bullet list", icon: List },
  { id: "number", label: "Numbered list", description: "Create a numbered list", type: "numbered_list_item", keywords: "number list", icon: ListOrdered },
  { id: "todo", label: "To-do list", description: "Track tasks", type: "todo", keywords: "todo checkbox", icon: SquareCheck },
  { id: "toggle", label: "Toggle list", description: "Expandable content", type: "toggle", keywords: "toggle collapse", icon: ChevronRight },
  { id: "code", label: "Code", description: "Code snippet", type: "code", keywords: "code markdown", icon: Code2 },
  { id: "quote", label: "Quote", description: "Quoted text", type: "quote", keywords: "quote blockquote", icon: Quote },
  { id: "callout", label: "Callout", description: "Highlighted block", type: "callout", keywords: "callout tip", icon: AlertCircle },
  { id: "page", label: "Page", description: "Create a sub-page", action: "create_child_page", keywords: "page subpage /page", icon: Type },
  { id: "db_full", label: "Database (full page)", description: "Create a full page database", action: "create_full_database", keywords: "database full page db /db", icon: List },
  { id: "image_upload", label: "Image upload", description: "Upload image file", action: "image_upload", keywords: "image upload file", icon: ImageIcon },
  { id: "inline_db", label: "Inline database", description: "Create database under this page", action: "create_inline_database", keywords: "database table inline inline-db /inline-db", icon: List },
  { id: "inline_table", label: "Table", description: "Create an inline table", action: "create_inline_table", keywords: "table inline /table", icon: List },
];

const MARKDOWN_SHORTCUTS: Record<string, BlockType> = {
  "#": "heading_1",
  "##": "heading_2",
  "###": "heading_3",
  "-": "bulleted_list_item",
  "1.": "numbered_list_item",
  "[]": "todo",
  ">": "quote",
  "--": "divider",
  "---": "divider",
  "```": "code",
};

const TEXT_MERGE_BLOCK_TYPES: BlockType[] = [
  "paragraph",
  "heading_1",
  "heading_2",
  "heading_3",
  "bulleted_list_item",
  "numbered_list_item",
  "todo",
  "toggle",
  "quote",
  "code",
  "callout",
];

const INLINE_TEXT_COLORS: Array<{ id: string; label: string; value: string | null }> = [
  { id: "default", label: "Default", value: null },
  { id: "gray", label: "Gray", value: "#787774" },
  { id: "brown", label: "Brown", value: "#9f6b53" },
  { id: "orange", label: "Orange", value: "#d9730d" },
  { id: "yellow", label: "Yellow", value: "#cb912f" },
  { id: "green", label: "Green", value: "#4d8b6a" },
  { id: "blue", label: "Blue", value: "#337ea9" },
  { id: "purple", label: "Purple", value: "#9065b0" },
  { id: "pink", label: "Pink", value: "#c14c8a" },
  { id: "red", label: "Red", value: "#d44c47" },
];

const INLINE_BG_COLORS: Array<{ id: string; label: string; value: string | null }> = [
  { id: "default", label: "Default", value: null },
  { id: "gray", label: "Gray", value: "#f1f1ef" },
  { id: "brown", label: "Brown", value: "#f4eeee" },
  { id: "orange", label: "Orange", value: "#fbeedd" },
  { id: "yellow", label: "Yellow", value: "#fbf3db" },
  { id: "green", label: "Green", value: "#edf3ec" },
  { id: "blue", label: "Blue", value: "#e7f3f8" },
  { id: "purple", label: "Purple", value: "#f6f3f8" },
  { id: "pink", label: "Pink", value: "#faeff4" },
  { id: "red", label: "Red", value: "#fdebec" },
];

const COMMENT_REACTION_EMOJIS = ["👍", "❤️", "🔥", "👏", "🎉", "🤔"];

const COMMENT_META_PREFIX = "[[ANCHOR:";
const COMMENT_UI_META_PREFIX = "[[META:";

function encodeCommentMeta(meta: CommentMeta) {
  try {
    return btoa(unescape(encodeURIComponent(JSON.stringify(meta))));
  } catch {
    return "";
  }
}

function decodeCommentMeta(encoded: string): CommentMeta | null {
  try {
    const decoded = decodeURIComponent(escape(atob(encoded)));
    const parsed = JSON.parse(decoded) as Partial<CommentMeta>;
    if (!parsed?.blockId || typeof parsed.blockId !== "string") return null;
    return {
      blockId: parsed.blockId,
      quote: typeof parsed.quote === "string" ? parsed.quote : "",
    };
  } catch {
    return null;
  }
}

function decodeCommentUiMeta(encoded: string): CommentUiMeta {
  try {
    const decoded = decodeURIComponent(escape(atob(encoded)));
    const parsed = JSON.parse(decoded) as Partial<CommentUiMeta>;
    const reactions = Array.isArray(parsed?.reactions)
      ? parsed.reactions
          .map((item) => ({
            emoji: typeof (item as { emoji?: unknown }).emoji === "string" ? String((item as { emoji?: string }).emoji) : "",
            userIds: Array.isArray((item as { userIds?: unknown }).userIds)
              ? ((item as { userIds?: unknown[] }).userIds ?? []).map((userId) => String(userId))
              : [],
          }))
          .filter((item) => item.emoji.length > 0 && item.userIds.length > 0)
      : [];
    return { reactions };
  } catch {
    return { reactions: [] };
  }
}

function encodeCommentUiMeta(meta: CommentUiMeta) {
  try {
    return btoa(unescape(encodeURIComponent(JSON.stringify(meta))));
  } catch {
    return "";
  }
}

function parseAnchoredContent(raw: string) {
  const text = raw ?? "";
  if (!text.startsWith(COMMENT_META_PREFIX) && !text.startsWith(COMMENT_UI_META_PREFIX)) {
    return {
      anchorBlockId: null as string | null,
      anchorQuote: null as string | null,
      displayContent: text,
      uiMeta: { reactions: [] } as CommentUiMeta,
    };
  }
  let rest = text;
  let anchorBlockId: string | null = null;
  let anchorQuote: string | null = null;
  let uiMeta: CommentUiMeta = { reactions: [] };

  if (rest.startsWith(COMMENT_META_PREFIX)) {
    const end = rest.indexOf("]]");
    if (end !== -1) {
      const encoded = rest.slice(COMMENT_META_PREFIX.length, end);
      const meta = decodeCommentMeta(encoded);
      anchorBlockId = meta?.blockId ?? null;
      anchorQuote = meta?.quote ?? null;
      rest = rest.slice(end + 2).replace(/^\n+/, "");
    }
  }

  if (rest.startsWith(COMMENT_UI_META_PREFIX)) {
    const end = rest.indexOf("]]");
    if (end !== -1) {
      const encoded = rest.slice(COMMENT_UI_META_PREFIX.length, end);
      uiMeta = decodeCommentUiMeta(encoded);
      rest = rest.slice(end + 2).replace(/^\n+/, "");
    }
  }

  return {
    anchorBlockId,
    anchorQuote,
    displayContent: rest || text,
    uiMeta,
  };
}

function buildCommentContent(input: {
  blockId: string | null;
  quote: string | null;
  text: string;
  uiMeta?: CommentUiMeta;
}) {
  const parts: string[] = [];
  if (input.blockId) {
    const encodedMeta = encodeCommentMeta({
      blockId: input.blockId,
      quote: input.quote ?? "",
    });
    if (encodedMeta) {
      parts.push(`${COMMENT_META_PREFIX}${encodedMeta}]]`);
    }
  }
  const hasReactions = (input.uiMeta?.reactions ?? []).some((item) => item.userIds.length > 0);
  if (hasReactions) {
    const encodedUiMeta = encodeCommentUiMeta({
      reactions: (input.uiMeta?.reactions ?? []).filter((item) => item.userIds.length > 0),
    });
    if (encodedUiMeta) {
      parts.push(`${COMMENT_UI_META_PREFIX}${encodedUiMeta}]]`);
    }
  }
  parts.push(input.text.trim());
  return parts.join("\n");
}

type InlineTableModel = {
  rows: number;
  cols: number;
  cells: string[][];
};

function createInlineTable(rows = 2, cols = 3): InlineTableModel {
  const safeRows = Math.max(1, Math.min(20, Math.trunc(rows)));
  const safeCols = Math.max(1, Math.min(20, Math.trunc(cols)));
  const cells = Array.from({ length: safeRows }, () => Array.from({ length: safeCols }, () => ""));
  return { rows: safeRows, cols: safeCols, cells };
}

function parseInlineTableModel(propsJson: unknown): InlineTableModel | null {
  if (!propsJson || typeof propsJson !== "object") return null;
  const source = (propsJson as { inlineTable?: unknown }).inlineTable;
  if (!source || typeof source !== "object") return null;
  const rows = Number((source as { rows?: unknown }).rows);
  const cols = Number((source as { cols?: unknown }).cols);
  if (!Number.isFinite(rows) || !Number.isFinite(cols)) return null;
  const normalized = createInlineTable(rows, cols);
  const rawCells = Array.isArray((source as { cells?: unknown }).cells) ? ((source as { cells?: unknown }).cells as unknown[]) : [];
  normalized.cells = normalized.cells.map((row, rowIndex) =>
    row.map((_, colIndex) => {
      const rawRow = Array.isArray(rawCells[rowIndex]) ? (rawCells[rowIndex] as unknown[]) : [];
      const rawValue = rawRow[colIndex];
      return rawValue == null ? "" : String(rawValue);
    })
  );
  return normalized;
}

export default function PageEditor({
  pageId,
  initialBlocks,
  editable = true,
}: {
  pageId: string;
  initialBlocks: Block[];
  editable?: boolean;
}) {
  const router = useRouter();
  const [blocks, setBlocks] = useState<Block[]>(initialBlocks);
  const [focusedBlockId, setFocusedBlockId] = useState<string | null>(null);
  const [slash, setSlash] = useState<{ blockId: string; query: string } | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  const [menuState, setMenuState] = useState<{ blockId: string; query: string } | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ left: number; top: number }>({ left: 12, top: 12 });
  const [turnIntoHoverBlockId, setTurnIntoHoverBlockId] = useState<string | null>(null);
  const [draggingBlockId, setDraggingBlockId] = useState<string | null>(null);
  const [dropIndicator, setDropIndicator] = useState<DropIndicatorState | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [highlightedBlockId, setHighlightedBlockId] = useState<string | null>(null);
  const [pendingFocusBlockId, setPendingFocusBlockId] = useState<string | null>(null);
  const [inlineToolbar, setInlineToolbar] = useState<InlineToolbarState | null>(null);
  const [inlineColorOpen, setInlineColorOpen] = useState(false);
  const [selectedBlockIds, setSelectedBlockIds] = useState<Set<string>>(new Set());
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [commentComposer, setCommentComposer] = useState<{
    blockId: string;
    quote: string;
    text: string;
    parentCommentId: string | null;
  } | null>(null);
  const [commentMenuId, setCommentMenuId] = useState<string | null>(null);
  const [editingComment, setEditingComment] = useState<{ id: string; text: string } | null>(null);
  const [reactionPickerForCommentId, setReactionPickerForCommentId] = useState<string | null>(null);
  const [viewerUserId, setViewerUserId] = useState<string>("");
  const [mentionCandidates, setMentionCandidates] = useState<MentionCandidate[]>([]);
  const [mentionPickerKey, setMentionPickerKey] = useState<string | null>(null);
  const [linkPopup, setLinkPopup] = useState<{ blockId: string; start: number; end: number; x: number; y: number; showRenderedImmediately?: boolean } | null>(null);
  const [linkPopupValue, setLinkPopupValue] = useState("");

  const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const uploadTargetBlockIdRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const commentFileInputRef = useRef<HTMLInputElement | null>(null);
  const commentUploadTargetRef = useRef<{ key: string; blockId: string; quote: string; parentCommentId: string | null } | null>(null);
  const toolbarRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const draggingBlockIdRef = useRef<string | null>(null);
  const draggingBlockIdsRef = useRef<Set<string>>(new Set());
  const dragStartXRef = useRef(0);
  const pointerDragRef = useRef<{ blockId: string; startX: number; startY: number; isDragging: boolean } | null>(null);
  const deleteZoneRef = useRef<HTMLDivElement | null>(null);
  const justDraggedRef = useRef(false);
  const marqueePointerRef = useRef<{ startX: number; startY: number; isSelecting: boolean } | null>(null);
  const [marqueeRect, setMarqueeRect] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const undoStackRef = useRef<Block[][]>([]);
  const isRestoringRef = useRef(false);
  const lastUndoAtRef = useRef(0);
  const editSessionSnapshotRef = useRef<Record<string, Block[]>>({});
  const suppressNextBlurSaveRef = useRef<Set<string>>(new Set());
  const blocksRef = useRef(blocks);
  blocksRef.current = blocks;
  const focusedBlockIdRef = useRef(focusedBlockId);
  focusedBlockIdRef.current = focusedBlockId;
  const tableResizeRef = useRef<{
    blockId: string;
    startX: number;
    startY: number;
    startRows: number;
    startCols: number;
  } | null>(null);

  const orderedBlocks = useMemo(() => [...blocks].sort((a, b) => a.position - b.position), [blocks]);
  const blockMap = useMemo(() => new Map(orderedBlocks.map((block) => [block.id, block])), [orderedBlocks]);

  const blockMapRef = useRef(blockMap);
  blockMapRef.current = blockMap;
  const selectedBlockIdsRef = useRef(selectedBlockIds);
  selectedBlockIdsRef.current = selectedBlockIds;
  const dropIndicatorRef = useRef<DropIndicatorState | null>(null);
  dropIndicatorRef.current = dropIndicator;
  const orderedBlocksRef = useRef(orderedBlocks);
  orderedBlocksRef.current = orderedBlocks;

  // Action refs — updated every render so the pointer-drag useEffect (empty deps)
  // always calls the latest version of these functions (avoids stale closure).
  const dropActionRef = useRef<((sourceId: string, targetId: string, parentId: string | null, multiIds: string[] | null) => void) | null>(null);
  const deleteActionRef = useRef<((id: string, multiIds: string[] | null) => void) | null>(null);

  // Assign every render so the empty-dep useEffect always calls the latest function versions.
  dropActionRef.current = (sourceId, targetId, parentId, multiIds) => {
    if (multiIds) void moveMultipleBlocks(multiIds, targetId);
    else void moveBlockWithHierarchy(sourceId, targetId, parentId);
  };
  deleteActionRef.current = (id, multiIds) => {
    if (multiIds) void deleteMultipleBlocks(multiIds);
    else void deleteBlock(id);
  };

  function requestFocusBlock(blockId: string | null) {
    setFocusedBlockId(blockId);
    setPendingFocusBlockId(blockId);
  }

  function toggleBlockSelection(blockId: string) {
    setSelectedBlockIds((prev) => {
      const next = new Set(prev);
      if (next.has(blockId)) next.delete(blockId);
      else next.add(blockId);
      return next;
    });
  }

  function beginMarqueeSelection(event: ReactMouseEvent<HTMLDivElement>) {
    if (!editable) return;
    if (event.button !== 0) return;
    const target = event.target as HTMLElement | null;
    if (!target) return;
    if (target.closest("textarea,input,button,select,a,[data-no-marquee='1']")) return;
    const active = document.activeElement as HTMLElement | null;
    if (active && (active.tagName === "TEXTAREA" || active.tagName === "INPUT")) {
      active.blur();
    }
    setFocusedBlockId(null);
    marqueePointerRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      isSelecting: false,
    };
  }

  async function refreshComments() {
    const response = await fetch(`/api/pages/${pageId}/comments`);
    if (!response.ok) return;
    const data = await response.json();
    setComments(data.comments ?? []);
  }

  async function postComment(input: {
    blockId: string;
    text: string;
    quote?: string;
    parentCommentId?: string | null;
    preserveAnchor?: boolean;
  }) {
    const trimmed = input.text.trim();
    if (!trimmed) return;

    let content = trimmed;
    if (!input.parentCommentId || input.preserveAnchor) {
      content = buildCommentContent({
        blockId: input.blockId,
        quote: input.quote ?? "",
        text: trimmed,
      });
    }

    const response = await fetch(`/api/pages/${pageId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        parentCommentId: input.parentCommentId ?? null,
      }),
    });
    if (!response.ok) return;
    await refreshComments();
    window.dispatchEvent(new Event("comments:refresh"));
  }

  async function updateCommentContent(commentId: string, content: string) {
    const response = await fetch(`/api/pages/${pageId}/comments/${commentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) return false;
    await refreshComments();
    window.dispatchEvent(new Event("comments:refresh"));
    return true;
  }

  async function resolveComment(commentId: string) {
    const response = await fetch(`/api/pages/${pageId}/comments/${commentId}`, {
      method: "DELETE",
    });
    if (!response.ok) return;
    await refreshComments();
    window.dispatchEvent(new Event("comments:refresh"));
  }

  function updateCommentComposerText(target: {
    blockId: string;
    quote: string;
    parentCommentId: string | null;
    nextText: string;
  }) {
    setCommentComposer((prev) => {
      if (!prev || prev.blockId !== target.blockId || prev.parentCommentId !== target.parentCommentId) {
        return {
          blockId: target.blockId,
          quote: target.quote,
          text: target.nextText,
          parentCommentId: target.parentCommentId,
        };
      }
      return {
        ...prev,
        text: target.nextText,
      };
    });
  }

  function appendToComposer(target: {
    blockId: string;
    quote: string;
    parentCommentId: string | null;
    textToAppend: string;
  }) {
    setCommentComposer((prev) => {
      const base =
        prev && prev.blockId === target.blockId && prev.parentCommentId === target.parentCommentId ? prev.text : "";
      return {
        blockId: target.blockId,
        quote: target.quote,
        parentCommentId: target.parentCommentId,
        text: `${base}${target.textToAppend}`,
      };
    });
  }

  function openCommentFilePicker(target: {
    key: string;
    blockId: string;
    quote: string;
    parentCommentId: string | null;
  }) {
    commentUploadTargetRef.current = target;
    commentFileInputRef.current?.click();
  }

  function insertMentionInComposer(target: {
    blockId: string;
    quote: string;
    parentCommentId: string | null;
    candidate: MentionCandidate;
  }) {
    const existing =
      commentComposer &&
      commentComposer.blockId === target.blockId &&
      commentComposer.parentCommentId === target.parentCommentId
        ? commentComposer.text
        : "";
    const prefix = existing.length > 0 && !/\s$/.test(existing) ? " " : "";
    appendToComposer({
      blockId: target.blockId,
      quote: target.quote,
      parentCommentId: target.parentCommentId,
      textToAppend: `${prefix}@${target.candidate.email} `,
    });
    setMentionPickerKey(null);
  }

  async function submitReply(blockId: string, thread: ParsedComment, text: string) {
    if (!text.trim()) return;
    await postComment({
      blockId,
      quote: thread.anchorQuote ?? "",
      text,
      parentCommentId: thread.id,
    });
    setCommentComposer(null);
    setMentionPickerKey(null);
  }

  async function submitTopLevelComment(blockId: string, quote: string, text: string) {
    if (!text.trim()) return;
    await postComment({
      blockId,
      quote,
      text,
    });
    setCommentComposer(null);
    setMentionPickerKey(null);
  }

  function openInlineColorPaletteForBlock(blockId: string) {
    setMenuState(null);
    requestFocusBlock(blockId);
    const tryOpen = (attempt: number) => {
      const textarea = textareaRefs.current[blockId];
      if (!textarea) {
        if (attempt < 8) {
          window.setTimeout(() => tryOpen(attempt + 1), 25);
        }
        return;
      }
      textarea.focus();
      const len = textarea.value.length;
      if (len > 0) {
        textarea.setSelectionRange(0, len);
        updateInlineToolbarFromTextarea(blockId, textarea);
        setInlineColorOpen(true);
      }
    };
    tryOpen(0);
  }

  function setInlineTableCell(blockId: string, rowIndex: number, colIndex: number, value: string) {
    setBlocks((prev) =>
      prev.map((item) => {
        if (item.id !== blockId) return item;
        const table = parseInlineTableModel(item.propsJson);
        if (!table) return item;
        const nextTable: InlineTableModel = {
          rows: table.rows,
          cols: table.cols,
          cells: table.cells.map((row, rIdx) => row.map((cell, cIdx) => (rIdx === rowIndex && cIdx === colIndex ? value : cell))),
        };
        return {
          ...item,
          propsJson: {
            ...(item.propsJson ?? {}),
            inlineTable: nextTable,
          },
        };
      })
    );
  }

  function resizeInlineTable(blockId: string, rows: number, cols: number) {
    setBlocks((prev) =>
      prev.map((item) => {
        if (item.id !== blockId) return item;
        const table = parseInlineTableModel(item.propsJson) ?? createInlineTable();
        const nextRows = Math.max(1, Math.min(20, Math.trunc(rows)));
        const nextCols = Math.max(1, Math.min(20, Math.trunc(cols)));
        const nextCells = Array.from({ length: nextRows }, (_, rowIndex) =>
          Array.from({ length: nextCols }, (_, colIndex) => table.cells[rowIndex]?.[colIndex] ?? "")
        );
        return {
          ...item,
          propsJson: {
            ...(item.propsJson ?? {}),
            inlineTable: {
              rows: nextRows,
              cols: nextCols,
              cells: nextCells,
            },
          },
        };
      })
    );
  }

  async function persistInlineTable(blockId: string, overrideTable?: InlineTableModel | null) {
    const block = blocksRef.current.find((item) => item.id === blockId);
    if (!block) return;
    const table = overrideTable ?? parseInlineTableModel(block.propsJson);
    if (!table) return;
    await updateBlock(
      block.id,
      {
        propsJson: {
          ...(block.propsJson ?? {}),
          inlineTable: table,
        },
      },
      { trackUndo: true }
    );
  }

  function openBlockActionMenu(blockId: string, anchor: HTMLElement) {
    const rect = anchor.getBoundingClientRect();
    const width = 320;
    const height = 520;
    const left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + 8));
    const top = Math.max(12, Math.min(window.innerHeight - height - 12, rect.bottom + 6));
    setMenuPosition({ left, top });
    setTurnIntoHoverBlockId(null);
    setMenuState((prev) => (prev?.blockId === blockId ? null : { blockId, query: "" }));
  }

  useEffect(() => {
    let cancelled = false;
    const refreshBlocks = async () => {
      try {
        const response = await fetch(`/api/pages/${pageId}/blocks`);
        if (!response.ok || cancelled) return;
        const data = await response.json();
        const freshBlocks = data.blocks ?? [];
        if (!cancelled) {
          setBlocks(freshBlocks);
          if (editable && freshBlocks.length === 0) {
            void createBlock({ type: "paragraph" });
          }
        }
      } catch {
        // fall back to initialBlocks already set via useState
      }
    };
    void refreshBlocks();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId, editable]);

  useEffect(() => {
    void refreshComments();
    const onRefresh = () => {
      void refreshComments();
    };
    window.addEventListener("comments:refresh", onRefresh);
    return () => window.removeEventListener("comments:refresh", onRefresh);
  }, [pageId]);

  useEffect(() => {
    const onHeaderAddComment = (event: Event) => {
      const customEvent = event as CustomEvent<{ pageId?: string }>;
      if (customEvent.detail?.pageId && customEvent.detail.pageId !== pageId) return;
      setCommentComposer({
        blockId: PAGE_COMMENT_ANCHOR,
        quote: "",
        text: "",
        parentCommentId: null,
      });
      setMentionPickerKey(null);
      setInlineToolbar(null);
      setInlineColorOpen(false);
    };

    window.addEventListener("page:add-comment", onHeaderAddComment as EventListener);
    return () => window.removeEventListener("page:add-comment", onHeaderAddComment as EventListener);
  }, [pageId]);

  useEffect(() => {
    if (!pendingFocusBlockId) return;
    const element = textareaRefs.current[pendingFocusBlockId];
    if (element) {
      element.focus();
      const len = element.value.length;
      element.setSelectionRange(len, len);
      setPendingFocusBlockId(null);
    }
  }, [blocks, pendingFocusBlockId]);

  useEffect(() => {
    const syncFromHash = () => {
      const hash = window.location.hash;
      if (!hash.startsWith("#block-")) return;
      const blockId = hash.replace("#block-", "");
      setHighlightedBlockId(blockId);
      const element = document.getElementById(`block-${blockId}`);
      if (element) {
        element.scrollIntoView({ block: "center", behavior: "smooth" });
      }
      window.setTimeout(() => setHighlightedBlockId(null), 1800);
    };

    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  useEffect(() => {
    const handleDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (toolbarRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      if ((target as HTMLElement).closest?.("[data-link-popup='1']")) return;
      setInlineToolbar(null);
      setInlineColorOpen(false);
      setLinkPopup(null);
      if (menuState) {
        setMenuState(null);
        setTurnIntoHoverBlockId(null);
      }
      if (!(target as HTMLElement).closest?.("[data-comment-menu='1']")) {
        setCommentMenuId(null);
        setReactionPickerForCommentId(null);
        setMentionPickerKey(null);
      }
      const clickedInsideCommentPanel = (target as HTMLElement).closest?.("[data-comment-panel='1']");
      const clickedInsidePageCommentPanel = (target as HTMLElement).closest?.("[data-page-comment-panel='1']");
      const clickedHeaderCommentButton = (target as HTMLElement).closest?.("[data-header-comment='1']");
      if (!clickedInsideCommentPanel && !clickedInsidePageCommentPanel && !clickedHeaderCommentButton && commentComposer?.text.trim() === "") {
        setCommentComposer(null);
      }
    };

    document.addEventListener("mousedown", handleDown);
    return () => document.removeEventListener("mousedown", handleDown);
  }, [menuState, commentComposer]);

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      const resize = tableResizeRef.current;
      if (!resize) return;
      event.preventDefault();
      const rowDelta = Math.round((event.clientY - resize.startY) / 44);
      const colDelta = Math.round((event.clientX - resize.startX) / 140);
      resizeInlineTable(resize.blockId, resize.startRows + rowDelta, resize.startCols + colDelta);
    };
    const onUp = () => {
      const resize = tableResizeRef.current;
      if (!resize) return;
      tableResizeRef.current = null;
      void persistInlineTable(resize.blockId);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  useEffect(() => {
    const loadViewer = async () => {
      const response = await fetch("/api/me");
      if (!response.ok) return;
      const data = await response.json();
      const userId = data?.user?.id;
      if (typeof userId === "string") {
        setViewerUserId(userId);
      }
    };
    void loadViewer();
  }, []);

  useEffect(() => {
    const loadMentionCandidates = async () => {
      const response = await fetch(`/api/pages/${pageId}/permissions`);
      if (!response.ok) return;
      const data = await response.json();
      const members = Array.isArray(data?.members) ? data.members : [];
      const permissions = Array.isArray(data?.permissions) ? data.permissions : [];
      const source =
        permissions.length > 0
          ? permissions.map((permission: { user?: { id?: string; email?: string } }) => ({ user: permission.user }))
          : members;
      const next = source
        .map((member: { user?: { id?: string; email?: string } }) => ({
          id: String(member?.user?.id ?? ""),
          email: String(member?.user?.email ?? ""),
        }))
        .filter((member: MentionCandidate) => member.id.length > 0 && member.email.length > 0);
      const deduped = Array.from(
        new Map<string, MentionCandidate>(next.map((item: MentionCandidate) => [item.id, item])).values()
      );
      setMentionCandidates(deduped);
    };
    void loadMentionCandidates();
  }, [pageId]);

  useEffect(() => {
    let cancelled = false;

    const syncLinkedReferenceTitles = async () => {
      const currentBlocks = orderedBlocksRef.current;
      const linkedBlocks = currentBlocks
        .map((block) => {
          const meta = getLinkedPageMeta(block);
          if (!meta) return null;
          return { block, meta };
        })
        .filter(
          (item): item is { block: Block; meta: { id: string; type: "database" | "document"; href: string; view: LinkedPageView } } =>
            Boolean(item)
        );

      if (linkedBlocks.length === 0) return;

      const response = await fetch("/api/pages");
      if (!response.ok || cancelled) return;
      const data = await response.json();
      const pages = Array.isArray(data?.pages) ? data.pages : [];
      const pageTitleMap = new Map<string, string>(
        pages
          .map((page: { id?: unknown; title?: unknown }) => [String(page?.id ?? ""), String(page?.title ?? "")] as const)
          .filter((item: readonly [string, string]) => item[0].length > 0)
      );

      const updates = linkedBlocks
        .map((item) => {
          const latestTitle = pageTitleMap.get(item.meta.id);
          if (!latestTitle || latestTitle === (item.block.contentText ?? "")) return null;
          return {
            blockId: item.block.id,
            title: latestTitle,
            href: item.meta.href,
          };
        })
        .filter((item): item is { blockId: string; title: string; href: string } => Boolean(item));

      if (updates.length === 0 || cancelled) return;

      const updateMap = new Map(updates.map((item) => [item.blockId, item]));
      setBlocks((prev) =>
        prev.map((block) => {
          const next = updateMap.get(block.id);
          if (!next) return block;
          return {
            ...block,
            contentText: next.title,
            richTextJson: {
              marks: [{ start: 0, end: next.title.length, link: next.href }],
            },
          };
        })
      );

      await Promise.all(
        updates.map((item) =>
          fetch(`/api/blocks/${item.blockId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contentText: item.title,
              richTextJson: { marks: [{ start: 0, end: item.title.length, link: item.href }] },
            }),
          })
        )
      );
    };

    void syncLinkedReferenceTitles();
    window.addEventListener("pages:refresh", syncLinkedReferenceTitles);
    return () => {
      cancelled = true;
      window.removeEventListener("pages:refresh", syncLinkedReferenceTitles);
    };
  }, [pageId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!editable) return;
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "z") {
        const target = event.target as HTMLElement | null;
        const tag = target?.tagName?.toLowerCase();
        if (tag === "textarea" || tag === "input" || tag === "select" || target?.isContentEditable) {
          return;
        }
        event.preventDefault();
        void undoLastChange();
      }
      if (event.key === "Backspace" || event.key === "Delete") {
        const selectedIds = [...selectedBlockIdsRef.current];
        if (selectedIds.length > 0) {
          event.preventDefault();
          void deleteMultipleBlocks(selectedIds);
          return;
        }
        const target = event.target as HTMLElement | null;
        const tag = target?.tagName?.toLowerCase();
        if (tag === "textarea" || tag === "input" || tag === "select" || target?.isContentEditable) {
          return;
        }
      }
      if (event.key === "Escape") {
        setSelectedBlockIds(new Set());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pageId, editable]);

  useEffect(() => {
    if (selectedBlockIds.size === 0) return;
    const active = document.activeElement as HTMLElement | null;
    if (active && (active.tagName === "TEXTAREA" || active.tagName === "INPUT")) {
      active.blur();
    }
    setFocusedBlockId(null);
  }, [selectedBlockIds]);

  useEffect(() => {
    function isDescBById(blockId: string, ancestorId: string, bMap: Map<string, Block>): boolean {
      const b = bMap.get(blockId);
      if (!b) return false;
      let pid = b.parentBlockId;
      while (pid) {
        if (pid === ancestorId) return true;
        const p = bMap.get(pid);
        if (!p) break;
        pid = p.parentBlockId;
      }
      return false;
    }

    function findBlockAtPoint(x: number, y: number, excludeIds: Set<string>): Block | null {
      const bMap = blockMapRef.current;
      // Primary: exact hit via elementsFromPoint
      const elements = document.elementsFromPoint(x, y);
      for (const el of elements) {
        const bid = (el as HTMLElement).getAttribute?.("data-block-id");
        if (bid && !excludeIds.has(bid)) {
          const block = bMap.get(bid);
          if (block && [...excludeIds].every((excludeId) => !isDescBById(bid, excludeId, bMap))) return block;
        }
      }
      // Fallback: find nearest block by vertical midpoint distance
      // (handles gaps between blocks and overshooting past the last block)
      let closest: Block | null = null;
      let closestDist = Infinity;
      for (const [bid, block] of bMap) {
        if (excludeIds.has(bid)) continue;
        if ([...excludeIds].some((excludeId) => isDescBById(bid, excludeId, bMap))) continue;
        const el = document.querySelector(`[data-block-id="${bid}"]`);
        if (!el) continue;
        const rect = el.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        const dist = Math.abs(y - midY);
        if (dist < closestDist) {
          closestDist = dist;
          closest = block;
        }
      }
      return closest;
    }

    function onMouseMove(e: MouseEvent) {
      const drag = pointerDragRef.current;
      if (drag) {
        if (!drag.isDragging) {
          const dist = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
          if (dist >= 5) {
            drag.isDragging = true;
            draggingBlockIdRef.current = drag.blockId;
            dragStartXRef.current = drag.startX;
            const selIds = selectedBlockIdsRef.current;
            const idsToMove = selIds.has(drag.blockId) && selIds.size > 1 ? [...selIds] : [drag.blockId];
            draggingBlockIdsRef.current = new Set(idsToMove);
            justDraggedRef.current = true;
            setDraggingBlockId(drag.blockId);
          }
        }

        if (drag.isDragging) {
          const target = findBlockAtPoint(e.clientX, e.clientY, draggingBlockIdsRef.current);
          if (target) {
            setDropIndicator({ overId: target.id, parentBlockId: target.parentBlockId });
          } else {
            setDropIndicator(null);
          }
        }
      }

      const marquee = marqueePointerRef.current;
      if (!marquee) return;
      const dist = Math.hypot(e.clientX - marquee.startX, e.clientY - marquee.startY);
      if (!marquee.isSelecting && dist < 5) return;
      marquee.isSelecting = true;

      const left = Math.min(marquee.startX, e.clientX);
      const top = Math.min(marquee.startY, e.clientY);
      const right = Math.max(marquee.startX, e.clientX);
      const bottom = Math.max(marquee.startY, e.clientY);
      setMarqueeRect({
        left,
        top,
        width: right - left,
        height: bottom - top,
      });

      const nextSelection = new Set<string>();
      const blockElements = Array.from(document.querySelectorAll<HTMLElement>("[data-block-id]"));
      for (const blockElement of blockElements) {
        const blockId = blockElement.getAttribute("data-block-id");
        if (!blockId) continue;
        const rect = blockElement.getBoundingClientRect();
        const intersects = !(rect.right < left || rect.left > right || rect.bottom < top || rect.top > bottom);
        if (intersects) {
          nextSelection.add(blockId);
        }
      }
      setSelectedBlockIds(nextSelection);
    }

    function onMouseUp(e: MouseEvent) {
      const drag = pointerDragRef.current;
      if (drag) {
        pointerDragRef.current = null;

        if (!drag.isDragging) {
          draggingBlockIdRef.current = null;
          draggingBlockIdsRef.current = new Set();
          justDraggedRef.current = false;
        } else {
          const indicator = dropIndicatorRef.current;
          const dragBlockId = drag.blockId;
          const movingIds = new Set(draggingBlockIdsRef.current);
          const multiIds = draggingBlockIdsRef.current.size > 1 ? [...draggingBlockIdsRef.current] : null;

          draggingBlockIdRef.current = null;
          draggingBlockIdsRef.current = new Set();
          setDraggingBlockId(null);
          setDropIndicator(null);

          // Check if mouse is over delete zone
          const deleteZoneEl = deleteZoneRef.current;
          if (deleteZoneEl) {
            const rect = deleteZoneEl.getBoundingClientRect();
            if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
              deleteActionRef.current?.(dragBlockId, multiIds);
              return;
            }
          }

          if (indicator) {
            dropActionRef.current?.(dragBlockId, indicator.overId, indicator.parentBlockId, multiIds);
          } else {
            const ordered = orderedBlocksRef.current;
            const remaining = ordered.filter((item) => !movingIds.has(item.id));
            if (remaining.length > 0) {
              const fallbackTarget =
                e.clientY < window.innerHeight / 2 ? remaining[0] : remaining[remaining.length - 1];
              dropActionRef.current?.(dragBlockId, fallbackTarget.id, fallbackTarget.parentBlockId, multiIds);
            }
          }

          window.setTimeout(() => {
            justDraggedRef.current = false;
          }, 120);
        }
      }

      const marquee = marqueePointerRef.current;
      if (marquee) {
        marqueePointerRef.current = null;
        if (marquee.isSelecting) {
          setMarqueeRect(null);
        } else {
          setMarqueeRect(null);
        }
      }
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  // Cursor feedback during pointer drag
  useEffect(() => {
    if (draggingBlockId) {
      document.body.style.cursor = "grabbing";
      document.body.style.userSelect = "none";
    } else {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [draggingBlockId]);

  const filteredSlashCommands = useMemo(() => {
    if (!slash) return [];
    const q = slash.query.trim().toLowerCase();
    if (!q) return SLASH_COMMANDS;
    return SLASH_COMMANDS.filter((item) => `${item.label} ${item.keywords}`.toLowerCase().includes(q));
  }, [slash]);

  const filteredTurnInto = useMemo(() => {
    const q = menuState?.query?.trim().toLowerCase() ?? "";
    if (!q) return TURN_INTO_TYPES;
    return TURN_INTO_TYPES.filter((item) => item.label.toLowerCase().includes(q));
  }, [menuState]);

  function isHiddenByCollapsedAncestor(block: Block) {
    let parentId = block.parentBlockId;
    while (parentId) {
      const parent = blockMap.get(parentId);
      if (!parent) return false;
      if (parent.type === "toggle" && parent.propsJson?.collapsed) {
        return true;
      }
      parentId = parent.parentBlockId;
    }
    return false;
  }

  function getDepth(block: Block) {
    let depth = 0;
    let parentId = block.parentBlockId;
    while (parentId && depth < 6) {
      const parent = blockMap.get(parentId);
      if (!parent) break;
      depth += 1;
      parentId = parent.parentBlockId;
    }
    return depth;
  }

  function getDepthById(id: string) {
    const target = blockMap.get(id);
    if (!target) return 0;
    return getDepth(target);
  }

  const visibleBlocks = useMemo(
    () => orderedBlocks.filter((block) => !isHiddenByCollapsedAncestor(block)),
    [orderedBlocks, blockMap]
  );

  const parsedComments = useMemo(() => {
    const parsed = comments.map((comment) => {
      const anchor = parseAnchoredContent(comment.content ?? "");
      return {
        ...comment,
        ...anchor,
      } as ParsedComment;
    });

    const parsedMap = new Map(parsed.map((item) => [item.id, item]));
    for (const item of parsed) {
      if (item.anchorBlockId) continue;
      if (!item.parentCommentId) continue;
      const parent = parsedMap.get(item.parentCommentId);
      if (!parent?.anchorBlockId) continue;
      item.anchorBlockId = parent.anchorBlockId;
      item.anchorQuote = parent.anchorQuote;
    }

    for (const item of parsed) {
      if (item.anchorBlockId) continue;
      item.anchorBlockId = PAGE_COMMENT_ANCHOR;
    }

    return parsed;
  }, [comments]);

  const repliesByParentId = useMemo(() => {
    const map = new Map<string, ParsedComment[]>();
    for (const comment of parsedComments) {
      if (!comment.parentCommentId) continue;
      const parent = parsedComments.find((item) => item.id === comment.parentCommentId);
      if (!parent?.anchorBlockId) continue;
      const list = map.get(comment.parentCommentId) ?? [];
      list.push(comment);
      map.set(comment.parentCommentId, list);
    }
    return map;
  }, [parsedComments]);

  const commentThreadsByBlockId = useMemo(() => {
    const map = new Map<string, ParsedComment[]>();
    const parsedMap = new Map(parsedComments.map((item) => [item.id, item]));
    for (const comment of parsedComments) {
      if (!comment.anchorBlockId) continue;
      if (comment.parentCommentId) {
        const parent = parsedMap.get(comment.parentCommentId);
        if (parent?.anchorBlockId) continue;
      }
      const list = map.get(comment.anchorBlockId) ?? [];
      list.push(comment);
      map.set(comment.anchorBlockId, list);
    }
    return map;
  }, [parsedComments]);

  async function toggleCommentReaction(thread: ParsedComment, emoji: string) {
    const viewerId = viewerUserId || "viewer-self";
    const current = (thread.uiMeta.reactions ?? []).map((item) => ({
      emoji: item.emoji,
      userIds: [...item.userIds],
    }));
    const reaction = current.find((item) => item.emoji === emoji);
    if (!reaction) {
      current.push({ emoji, userIds: [viewerId] });
    } else if (reaction.userIds.includes(viewerId)) {
      reaction.userIds = reaction.userIds.filter((id) => id !== viewerId);
    } else {
      reaction.userIds.push(viewerId);
    }

    const nextReactions = current.filter((item) => item.userIds.length > 0);
    const content = buildCommentContent({
      blockId: thread.anchorBlockId,
      quote: thread.anchorQuote,
      text: thread.displayContent,
      uiMeta: { reactions: nextReactions },
    });
    await updateCommentContent(thread.id, content);
  }

  async function saveEditedComment(thread: ParsedComment, nextText: string) {
    const trimmed = nextText.trim();
    if (!trimmed) return;
    const content = buildCommentContent({
      blockId: thread.anchorBlockId,
      quote: thread.anchorQuote,
      text: trimmed,
      uiMeta: thread.uiMeta,
    });
    const ok = await updateCommentContent(thread.id, content);
    if (ok) {
      setEditingComment(null);
      setCommentMenuId(null);
    }
  }

  function cloneBlocksSnapshot(source: Block[]) {
    return source.map((item) => ({
      ...item,
      propsJson: item.propsJson ? JSON.parse(JSON.stringify(item.propsJson)) : null,
      richTextJson: item.richTextJson ? JSON.parse(JSON.stringify(item.richTextJson)) : null,
    }));
  }

  function snapshotSignature(snapshot: Block[]) {
    return snapshot
      .map((item) => `${item.id}:${item.position}:${item.parentBlockId ?? ""}:${item.type}:${item.contentText ?? ""}`)
      .join("|");
  }

  function pushUndoSnapshot(snapshot?: Block[], options?: { force?: boolean }) {
    if (isRestoringRef.current) return;
    const source = snapshot ?? blocks;
    const now = Date.now();
    if (!options?.force && now - lastUndoAtRef.current < UNDO_COALESCE_MS) return;
    const candidate = cloneBlocksSnapshot(source);
    const last = undoStackRef.current[undoStackRef.current.length - 1];
    if (last && snapshotSignature(last) === snapshotSignature(candidate)) return;
    undoStackRef.current.push(candidate);
    if (undoStackRef.current.length > MAX_UNDO_STACK) {
      undoStackRef.current.shift();
    }
    lastUndoAtRef.current = now;
  }

  async function replaceBlocks(nextBlocks: Block[]) {
    await fetch(`/api/pages/${pageId}/blocks`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blocks: nextBlocks }),
    });
  }

  async function undoLastChange() {
    const snapshot = undoStackRef.current.pop();
    if (!snapshot) return;
    isRestoringRef.current = true;
    setBlocks(snapshot);
    try {
      await replaceBlocks(snapshot);
    } finally {
      isRestoringRef.current = false;
    }
  }

  function beginEditSession(blockId: string) {
    if (editSessionSnapshotRef.current[blockId]) return;
    editSessionSnapshotRef.current[blockId] = cloneBlocksSnapshot(blocks);
  }

  function endEditSession(blockId: string, changed: boolean) {
    const snapshot = editSessionSnapshotRef.current[blockId];
    delete editSessionSnapshotRef.current[blockId];
    if (!snapshot || !changed) return;
    pushUndoSnapshot(snapshot, { force: true });
  }

  function didContentChangeFromSession(blockId: string, nextValue: string) {
    const snapshot = editSessionSnapshotRef.current[blockId];
    if (!snapshot) return false;
    const previousBlock = snapshot.find((item) => item.id === blockId);
    const previousValue = previousBlock?.contentText ?? "";
    return previousValue !== nextValue;
  }

  function getNumberedListOrder(block: Block) {
    const ordered = orderedBlocks;
    let order = 0;
    for (const item of ordered) {
      if (item.parentBlockId === block.parentBlockId && item.type === "numbered_list_item") {
        order += 1;
      }
      if (item.id === block.id) {
        break;
      }
    }
    return Math.max(1, order);
  }

  function toAlpha(value: number) {
    let n = Math.max(1, value);
    let output = "";
    while (n > 0) {
      const remainder = (n - 1) % 26;
      output = String.fromCharCode(97 + remainder) + output;
      n = Math.floor((n - 1) / 26);
    }
    return output;
  }

  function toRoman(value: number) {
    const romanTable: Array<[number, string]> = [
      [1000, "m"],
      [900, "cm"],
      [500, "d"],
      [400, "cd"],
      [100, "c"],
      [90, "xc"],
      [50, "l"],
      [40, "xl"],
      [10, "x"],
      [9, "ix"],
      [5, "v"],
      [4, "iv"],
      [1, "i"],
    ];
    let n = Math.max(1, value);
    let output = "";
    for (const [unit, roman] of romanTable) {
      while (n >= unit) {
        output += roman;
        n -= unit;
      }
    }
    return output;
  }

  function getOrderedListStyle(depth: number) {
    const normalized = Math.max(0, depth % 3);
    if (normalized === 1) return "alpha";
    if (normalized === 2) return "roman";
    return "number";
  }

  function formatNumberedMarker(order: number, depth: number) {
    const style = getOrderedListStyle(depth);
    if (style === "alpha") return `${toAlpha(order)}.`;
    if (style === "roman") return `${toRoman(order)}.`;
    return `${order}.`;
  }

  function getBulletMarker(depth: number) {
    const markers = ["•", "◦", "▪"];
    return markers[Math.max(0, depth) % markers.length];
  }

  function getInlineMarks(block: Block): InlineMark[] {
    const raw = block.richTextJson;
    if (!raw || typeof raw !== "object" || !Array.isArray((raw as any).marks)) return [];
    return (raw as any).marks
      .map((mark: any) => ({
        start: Number(mark?.start ?? 0),
        end: Number(mark?.end ?? 0),
        bold: Boolean(mark?.bold),
        italic: Boolean(mark?.italic),
        underline: Boolean(mark?.underline),
        strikethrough: Boolean(mark?.strikethrough),
        code: Boolean(mark?.code),
        equation: Boolean(mark?.equation),
        link: typeof mark?.link === "string" ? mark.link : undefined,
        color: typeof mark?.color === "string" ? mark.color : undefined,
        backgroundColor: typeof mark?.backgroundColor === "string" ? mark.backgroundColor : undefined,
      }))
      .filter((mark: InlineMark) => Number.isInteger(mark.start) && Number.isInteger(mark.end) && mark.end > mark.start);
  }

  function normalizeInlineStyle(style: InlineStyle): InlineStyle {
    return {
      bold: Boolean(style.bold) || undefined,
      italic: Boolean(style.italic) || undefined,
      underline: Boolean(style.underline) || undefined,
      strikethrough: Boolean(style.strikethrough) || undefined,
      code: Boolean(style.code) || undefined,
      equation: Boolean(style.equation) || undefined,
      link: typeof style.link === "string" && style.link.trim().length > 0 ? style.link.trim() : undefined,
      color: typeof style.color === "string" && style.color.trim().length > 0 ? style.color.trim() : undefined,
      backgroundColor:
        typeof style.backgroundColor === "string" && style.backgroundColor.trim().length > 0
          ? style.backgroundColor.trim()
          : undefined,
    };
  }

  function styleKey(style: InlineStyle) {
    const normalized = normalizeInlineStyle(style);
    return [
      normalized.bold ? "1" : "0",
      normalized.italic ? "1" : "0",
      normalized.underline ? "1" : "0",
      normalized.strikethrough ? "1" : "0",
      normalized.code ? "1" : "0",
      normalized.equation ? "1" : "0",
      normalized.link ?? "",
      normalized.color ?? "",
      normalized.backgroundColor ?? "",
    ].join("|");
  }

  function hasAnyInlineStyle(style: InlineStyle) {
    const normalized = normalizeInlineStyle(style);
    return Boolean(
      normalized.bold ||
        normalized.italic ||
        normalized.underline ||
        normalized.strikethrough ||
        normalized.code ||
        normalized.equation ||
        normalized.link ||
        normalized.color ||
        normalized.backgroundColor
    );
  }

  function getStyleAtRange(marks: InlineMark[], start: number, end: number): InlineStyle {
    const active = marks.filter((mark) => mark.start < end && mark.end > start);
    return normalizeInlineStyle({
      bold: active.some((mark) => mark.bold),
      italic: active.some((mark) => mark.italic),
      underline: active.some((mark) => mark.underline),
      strikethrough: active.some((mark) => mark.strikethrough),
      code: active.some((mark) => mark.code),
      equation: active.some((mark) => mark.equation),
      link: active.find((mark) => mark.link)?.link,
      color: [...active].reverse().find((mark) => mark.color)?.color,
      backgroundColor: [...active].reverse().find((mark) => mark.backgroundColor)?.backgroundColor,
    });
  }

  function toInlineSegments(textLength: number, marks: InlineMark[]) {
    if (textLength <= 0) return [] as Array<{ start: number; end: number; style: InlineStyle }>;
    const points = new Set<number>([0, textLength]);
    for (const mark of marks) {
      points.add(Math.max(0, Math.min(textLength, mark.start)));
      points.add(Math.max(0, Math.min(textLength, mark.end)));
    }
    const sorted = [...points].sort((a, b) => a - b);
    const segments: Array<{ start: number; end: number; style: InlineStyle }> = [];
    for (let index = 0; index < sorted.length - 1; index += 1) {
      const start = sorted[index];
      const end = sorted[index + 1];
      if (end <= start) continue;
      segments.push({
        start,
        end,
        style: getStyleAtRange(marks, start, end),
      });
    }
    return segments;
  }

  function fromInlineSegments(segments: Array<{ start: number; end: number; style: InlineStyle }>) {
    if (segments.length === 0) return [] as InlineMark[];
    const merged: Array<{ start: number; end: number; style: InlineStyle }> = [];
    for (const segment of segments) {
      const normalizedStyle = normalizeInlineStyle(segment.style);
      const last = merged[merged.length - 1];
      if (last && styleKey(last.style) === styleKey(normalizedStyle) && last.end === segment.start) {
        last.end = segment.end;
      } else {
        merged.push({ start: segment.start, end: segment.end, style: normalizedStyle });
      }
    }
    return merged
      .filter((segment) => hasAnyInlineStyle(segment.style))
      .map((segment): InlineMark => ({
        start: segment.start,
        end: segment.end,
        ...segment.style,
      }));
  }

  function getSelectionRangeForBlock(blockId: string) {
    const textarea = textareaRefs.current[blockId];
    if (textarea) {
      const start = textarea.selectionStart ?? 0;
      const end = textarea.selectionEnd ?? 0;
      if (end > start) return { start, end };
    }
    if (inlineToolbar?.blockId === blockId && inlineToolbar.end > inlineToolbar.start) {
      return { start: inlineToolbar.start, end: inlineToolbar.end };
    }
    return null;
  }

  async function updateInlineMarks(
    block: Block,
    range: { start: number; end: number },
    mutator: (style: InlineStyle) => InlineStyle
  ) {
    const textLength = (block.contentText ?? "").length;
    if (textLength === 0) return;
    const start = Math.max(0, Math.min(textLength, range.start));
    const end = Math.max(0, Math.min(textLength, range.end));
    if (end <= start) return;

    const marks = getInlineMarks(block).map((mark) => ({
      ...mark,
      start: Math.max(0, Math.min(textLength, mark.start)),
      end: Math.max(0, Math.min(textLength, mark.end)),
    }));
    const segments = toInlineSegments(textLength, marks).map((segment) => {
      if (segment.end <= start || segment.start >= end) return segment;
      return {
        ...segment,
        style: normalizeInlineStyle(mutator(segment.style)),
      };
    });
    const nextMarks = fromInlineSegments(segments);
    await updateBlock(
      block.id,
      { richTextJson: nextMarks.length > 0 ? { marks: nextMarks } : null },
      { trackUndo: true }
    );
    const textarea = textareaRefs.current[block.id];
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(start, end);
    }
  }

  function renderRichText(block: Block): ReactNode {
    const text = block.contentText ?? "";
    const marks = getInlineMarks(block);
    if (!text.length) return text;
    if (marks.length === 0) {
      const trimmed = text.trim();
      const isPathLink = /^\/(app|share)\//.test(trimmed);
      const isAbsoluteLink = /^https?:\/\/\S+$/i.test(trimmed);
      if (!isPathLink && !isAbsoluteLink) return text;

      let href = trimmed;
      let isInternal = isPathLink;
      if (isAbsoluteLink) {
        try {
          const parsed = new URL(trimmed);
          if (typeof window !== "undefined" && parsed.origin === window.location.origin) {
            href = `${parsed.pathname}${parsed.search}${parsed.hash}`;
            isInternal = true;
          }
        } catch {
          return text;
        }
      }

      return (
        <a
          href={href}
          data-inline-link="1"
          target={isInternal ? undefined : "_blank"}
          rel={isInternal ? undefined : "noreferrer"}
          onClick={(event) => {
            if (!isInternal) return;
            event.preventDefault();
            router.push(href);
          }}
          className="text-[#175cd3] underline underline-offset-2"
        >
          {text}
        </a>
      );
    }

    const points = new Set<number>([0, text.length]);
    for (const mark of marks) {
      points.add(Math.max(0, Math.min(text.length, mark.start)));
      points.add(Math.max(0, Math.min(text.length, mark.end)));
    }
    const sorted = [...points].sort((a, b) => a - b);
    const segments: ReactNode[] = [];

    for (let i = 0; i < sorted.length - 1; i += 1) {
      const start = sorted[i];
      const end = sorted[i + 1];
      if (end <= start) continue;
      const content = text.slice(start, end);
      const active = marks.filter((mark) => mark.start < end && mark.end > start);
      const bold = active.some((mark) => mark.bold);
      const italic = active.some((mark) => mark.italic);
      const underline = active.some((mark) => mark.underline);
      const strike = active.some((mark) => mark.strikethrough);
      const code = active.some((mark) => mark.code);
      const equation = active.some((mark) => mark.equation);
      const link = active.find((mark) => mark.link)?.link;
      const color = [...active].reverse().find((mark) => mark.color)?.color;
      const backgroundColor = [...active].reverse().find((mark) => mark.backgroundColor)?.backgroundColor;
      const className = [
        bold ? "font-semibold" : "",
        italic ? "italic" : "",
        underline ? "underline underline-offset-2" : "",
        strike ? "line-through" : "",
        code ? "rounded bg-[var(--surface)] px-1 font-mono text-[#d63d3d]" : "",
        equation ? "font-mono italic" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const span = (
        <span
          key={`${start}-${end}`}
          className={className || undefined}
          style={{
            color: color || undefined,
            backgroundColor: backgroundColor || undefined,
          }}
        >
          {content}
        </span>
      );
      if (link) {
        const isInternal = link.startsWith("/");
        segments.push(
          <a
            key={`l-${start}-${end}`}
            href={link}
            data-inline-link="1"
            target={isInternal ? undefined : "_blank"}
            rel={isInternal ? undefined : "noreferrer"}
            onClick={(event) => {
              if (!isInternal) return;
              event.preventDefault();
              router.push(link);
            }}
            className="text-[#175cd3] underline underline-offset-2"
          >
            {span}
          </a>
        );
      } else {
        segments.push(span);
      }
    }

    return segments;
  }

  function getFocusedTextareaColor(block: Block) {
    const text = block.contentText ?? "";
    if (!text.length) return block.propsJson?.color ? String(block.propsJson.color) : undefined;

    const marks = getInlineMarks(block);
    if (marks.length === 0) return block.propsJson?.color ? String(block.propsJson.color) : undefined;

    const segments = toInlineSegments(text.length, marks);
    if (segments.length === 0) return block.propsJson?.color ? String(block.propsJson.color) : undefined;

    const firstColor = segments[0].style.color ?? null;
    const isUniform = segments.every((segment) => (segment.style.color ?? null) === firstColor);
    if (isUniform && firstColor) {
      return firstColor;
    }
    return block.propsJson?.color ? String(block.propsJson.color) : undefined;
  }

  function getLinkedPageMeta(block: Block): { id: string; type: "database" | "document"; href: string; view: LinkedPageView } | null {
    const props = block.propsJson;
    if (!props || typeof props !== "object") return null;
    const linkedPageId = typeof props.linkedPageId === "string" ? props.linkedPageId.trim() : "";
    const linkedPageType = props.linkedPageType === "database" ? "database" : props.linkedPageType === "document" ? "document" : null;
    if (!linkedPageId || !linkedPageType) return null;
    const linkedPageView: LinkedPageView = props.linkedPageView === "link" ? "link" : "inline";
    return {
      id: linkedPageId,
      type: linkedPageType,
      href: linkedPageType === "database" ? `/app/database/${linkedPageId}` : `/app/page/${linkedPageId}`,
      view: linkedPageView,
    };
  }

  function isDescendantOf(block: Block, ancestorId: string) {
    let parentId = block.parentBlockId;
    while (parentId) {
      if (parentId === ancestorId) return true;
      const parent = blockMap.get(parentId);
      if (!parent) break;
      parentId = parent.parentBlockId;
    }
    return false;
  }

  function getDepthFromParent(parentId: string | null) {
    if (!parentId) return 0;
    const parent = blockMap.get(parentId);
    if (!parent) return 0;
    return getDepth(parent) + 1;
  }



  function getSubtreeIds(rootId: string) {
    const ordered = orderedBlocks;
    const descendants = ordered.filter((item) => isDescendantOf(item, rootId)).map((item) => item.id);
    return [rootId, ...descendants];
  }

  function getSubtreeTailPosition(rootId: string) {
    const root = blockMap.get(rootId);
    if (!root) return 0;
    let maxPosition = root.position;
    for (const item of orderedBlocks) {
      if (item.id === rootId || isDescendantOf(item, rootId)) {
        maxPosition = Math.max(maxPosition, item.position);
      }
    }
    return maxPosition;
  }

  async function persistLayout(nextBlocks: Block[], previousBlocks: Block[]) {
    const previousMap = new Map(previousBlocks.map((item) => [item.id, item]));
    const changed = nextBlocks.filter((item) => {
      const prev = previousMap.get(item.id);
      if (!prev) return false;
      return prev.position !== item.position || prev.parentBlockId !== item.parentBlockId;
    });

    if (changed.length === 0) return;

    await Promise.all(
      changed.map((item) =>
        fetch(`/api/blocks/${item.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position: item.position, parentBlockId: item.parentBlockId }),
        })
      )
    );
  }

  async function moveBlockWithHierarchy(blockId: string, overId: string, projectedParentId: string | null) {
    if (blockId === overId) return;

    const ordered = orderedBlocks;
    const movingIds = new Set(getSubtreeIds(blockId));
    if (movingIds.has(overId)) return;

    const moving = ordered.filter((item) => movingIds.has(item.id));
    const remaining = ordered.filter((item) => !movingIds.has(item.id));
    if (moving.length === 0 || remaining.length === 0) return;

    const overIndex = remaining.findIndex((item) => item.id === overId);
    if (overIndex === -1) return;

    const safeParentId = projectedParentId && !movingIds.has(projectedParentId) ? projectedParentId : remaining[overIndex].parentBlockId;
    const movedRoot = { ...moving[0], parentBlockId: safeParentId ?? null };
    const insertionIndex = overIndex + 1;

    const reordered = [
      ...remaining.slice(0, insertionIndex),
      movedRoot,
      ...moving.slice(1),
      ...remaining.slice(insertionIndex),
    ].map((item, position) => ({ ...item, position }));

    const previous = cloneBlocksSnapshot(blocks);
    pushUndoSnapshot(previous, { force: true });
    setBlocks(reordered);
    await persistLayout(reordered, previous);
  }

  async function moveMultipleBlocks(blockIds: string[], overId: string) {
    const ordered = orderedBlocks;
    const blockIdSet = new Set(blockIds);
    const rootSelected = blockIds.filter((id) => {
      const candidate = blockMap.get(id);
      if (!candidate) return false;
      let parentId = candidate.parentBlockId;
      while (parentId) {
        if (blockIdSet.has(parentId)) return false;
        const parent = blockMap.get(parentId);
        if (!parent) break;
        parentId = parent.parentBlockId;
      }
      return true;
    });
    const allMovingIds = new Set<string>();
    for (const id of rootSelected) {
      if (id === overId) continue;
      for (const subId of getSubtreeIds(id)) allMovingIds.add(subId);
    }
    if (allMovingIds.has(overId)) return;
    const moving = ordered.filter((item) => allMovingIds.has(item.id));
    const remaining = ordered.filter((item) => !allMovingIds.has(item.id));
    const overIndex = remaining.findIndex((item) => item.id === overId);
    if (overIndex === -1) return;
    const reordered = [
      ...remaining.slice(0, overIndex + 1),
      ...moving,
      ...remaining.slice(overIndex + 1),
    ].map((item, position) => ({ ...item, position }));
    const previous = cloneBlocksSnapshot(blocks);
    pushUndoSnapshot(previous, { force: true });
    setBlocks(reordered);
    await persistLayout(reordered, previous);
    setSelectedBlockIds(new Set());
  }

  async function createBlock(options: {
    type: BlockType;
    afterBlockId?: string;
    position?: number;
    contentText?: string;
    parentBlockId?: string | null;
    propsJson?: Record<string, any> | null;
    trackUndo?: boolean;
  }) {
    const response = await fetch(`/api/pages/${pageId}/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
    const data = await response.json();
    if (!response.ok) return null;
    if (options.trackUndo !== false) {
      pushUndoSnapshot(undefined, { force: true });
    }
    setBlocks((prev) => {
      const insertPosition = Number(data.block?.position ?? prev.length);
      const shifted = prev.map((item) =>
        item.position >= insertPosition ? { ...item, position: item.position + 1 } : item
      );
      const next = [...shifted.filter((item) => item.id !== data.block.id), data.block];
      next.sort((a, b) => a.position - b.position);
      return next;
    });
    return data.block as Block;
  }

  async function updateBlock(id: string, updates: Partial<Block>, options?: { trackUndo?: boolean }) {
    if (options?.trackUndo) {
      pushUndoSnapshot(undefined, { force: true });
    }
    setBlocks((prev) => prev.map((block) => (block.id === id ? { ...block, ...updates } : block)));
    await fetch(`/api/blocks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
  }

  async function deleteBlock(id: string) {
    const subtreeIds = getSubtreeIds(id);
    if (subtreeIds.length === 0) return;

    const previous = cloneBlocksSnapshot(blocks);
    pushUndoSnapshot(undefined, { force: true });
    const removed = new Set(subtreeIds);
    const next = previous
      .filter((block) => !removed.has(block.id))
      .sort((a, b) => a.position - b.position)
      .map((block, position) => ({ ...block, position }));

    setBlocks(next);
    setSelectedBlockIds((prev) => {
      const selected = new Set(prev);
      for (const removedId of removed) selected.delete(removedId);
      return selected;
    });

    try {
      const response = await fetch(`/api/pages/${pageId}/blocks`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          blocks: next.map((block) => ({
            id: block.id,
            type: block.type,
            contentText: block.contentText,
            checked: block.checked,
            imageUrl: block.imageUrl,
            position: block.position,
            parentBlockId: block.parentBlockId,
            propsJson: block.propsJson,
            richTextJson: block.richTextJson,
          })),
        }),
      });
      if (!response.ok) {
        setBlocks(previous);
      }
    } catch {
      setBlocks(previous);
    }
  }

  async function deleteBlockPromoteChildren(id: string) {
    const target = blockMap.get(id);
    if (!target) return;

    const directChildren = orderedBlocks
      .filter((item) => item.parentBlockId === id)
      .sort((a, b) => a.position - b.position);

    if (directChildren.length === 0) {
      await deleteBlock(id);
      return;
    }

    pushUndoSnapshot(undefined, { force: true });

    const nextParentId = target.parentBlockId ?? null;

    setBlocks((prev) =>
      prev
        .filter((item) => item.id !== id)
        .map((item) => (item.parentBlockId === id ? { ...item, parentBlockId: nextParentId } : item))
    );

    await Promise.all(
      directChildren.map((child) =>
        fetch(`/api/blocks/${child.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ parentBlockId: nextParentId }),
        })
      )
    );
    await fetch(`/api/blocks/${id}`, { method: "DELETE" });

    requestFocusBlock(directChildren[0]?.id ?? null);
  }

  async function deleteMultipleBlocks(ids: string[]) {
    if (ids.length === 0) return;
    const idSet = new Set(ids);
    const rootSelected = ids.filter((id) => {
      const candidate = blockMap.get(id);
      if (!candidate) return false;
      let parentId = candidate.parentBlockId;
      while (parentId) {
        if (idSet.has(parentId)) return false;
        const parent = blockMap.get(parentId);
        if (!parent) break;
        parentId = parent.parentBlockId;
      }
      return true;
    });
    const allIds = new Set<string>();
    for (const id of rootSelected) {
      for (const subtreeId of getSubtreeIds(id)) {
        allIds.add(subtreeId);
      }
    }
    if (allIds.size === 0) {
      setSelectedBlockIds(new Set());
      return;
    }

    const previous = cloneBlocksSnapshot(blocks);
    pushUndoSnapshot(undefined, { force: true });
    const remaining = previous
      .filter((block) => !allIds.has(block.id))
      .sort((a, b) => a.position - b.position)
      .map((block, position) => ({ ...block, position }));
    setBlocks(remaining);
    setSelectedBlockIds(new Set());

    try {
      const response = await fetch(`/api/pages/${pageId}/blocks`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          blocks: remaining.map((block) => ({
            id: block.id,
            type: block.type,
            contentText: block.contentText,
            checked: block.checked,
            imageUrl: block.imageUrl,
            position: block.position,
            parentBlockId: block.parentBlockId,
            propsJson: block.propsJson,
            richTextJson: block.richTextJson,
          })),
        }),
      });
      if (!response.ok) {
        setBlocks(previous);
      }
    } catch {
      setBlocks(previous);
    }
  }

  async function duplicateBlock(id: string) {
    const response = await fetch(`/api/blocks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "duplicate" }),
    });
    const data = await response.json();
    if (!response.ok) return;
    pushUndoSnapshot(undefined, { force: true });
    setBlocks((prev) => {
      const insertPosition = Number(data.block?.position ?? prev.length);
      const shifted = prev.map((item) =>
        item.position >= insertPosition ? { ...item, position: item.position + 1 } : item
      );
      const next = [...shifted.filter((item) => item.id !== data.block.id), data.block];
      next.sort((a, b) => a.position - b.position);
      return next;
    });
    requestFocusBlock(data.block.id);
    setMenuState(null);
    setTurnIntoHoverBlockId(null);
  }

  async function copyBlockLink(blockId: string) {
    const url = `${window.location.origin}/app/page/${pageId}#block-${blockId}`;
    await navigator.clipboard.writeText(url);
    setMenuState(null);
    setTurnIntoHoverBlockId(null);
  }

  async function uploadFile(file: File) {
    setUploadProgress(0);

    return await new Promise<string>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/pages/${pageId}/attachments`);
      xhr.responseType = "json";

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const progress = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(progress);
      };

      xhr.onload = () => {
        const ok = xhr.status >= 200 && xhr.status < 300;
        if (!ok) {
          setUploadProgress(null);
          reject(new Error("upload failed"));
          return;
        }

        const fileUrl = xhr.response?.attachment?.fileUrl;
        if (!fileUrl) {
          setUploadProgress(null);
          reject(new Error("missing fileUrl"));
          return;
        }

        setUploadProgress(null);
        resolve(fileUrl);
      };

      xhr.onerror = () => {
        setUploadProgress(null);
        reject(new Error("upload failed"));
      };

      const formData = new FormData();
      formData.append("file", file);
      xhr.send(formData);
    });
  }

  async function addImageFromFile(file: File, afterBlockId?: string) {
    const imageBlock = await createBlock({ type: "image", afterBlockId, contentText: file.name });
    if (!imageBlock) return;

    try {
      const fileUrl = await uploadFile(file);
      await updateBlock(imageBlock.id, { imageUrl: fileUrl, contentText: file.name });
      requestFocusBlock(imageBlock.id);
    } catch {
      await updateBlock(imageBlock.id, { contentText: "Upload failed" });
    }
  }

  function openSlash(blockId: string, value: string) {
    const query = value.slice(1);
    setSlash({ blockId, query });
    setSlashIndex(0);
  }

  async function runSlashCommand(block: Block, command: SlashCommand) {
    setSlash(null);
    suppressNextBlurSaveRef.current.add(block.id);
    setInlineToolbar(null);
    setInlineColorOpen(false);

    if (command.action === "image_upload") {
      uploadTargetBlockIdRef.current = block.id;
      fileInputRef.current?.click();
      return;
    }

    if (command.action === "create_inline_table") {
      await updateBlock(
        block.id,
        {
          type: "paragraph",
          contentText: "",
          propsJson: {
            ...(block.propsJson ?? {}),
            inlineTable: createInlineTable(2, 3),
          },
        },
        { trackUndo: true }
      );
      setFocusedBlockId(null);
      setPendingFocusBlockId(null);
      return;
    }

    if (command.action === "create_inline_database") {
      const response = await fetch("/api/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Untitled database",
          type: "database",
          accessLevel: "workspace",
          parentPageId: pageId,
          createMode: "inline",
          createLinkInParent: false,
        }),
      });
      const data = await response.json();
      if (response.ok && data?.page?.id) {
        window.dispatchEvent(new Event("pages:refresh"));
        const title = String(data.page.title || "New database");
        const href = `/app/database/${data.page.id}`;
        await updateBlock(
          block.id,
          {
            type: "paragraph",
            contentText: title,
            propsJson: {
              ...(block.propsJson ?? {}),
              linkedPageId: data.page.id,
              linkedPageType: "database",
              linkedPageView: "inline",
              linkedPageAuto: true,
            },
            richTextJson: {
              marks: [{ start: 0, end: title.length, link: href }],
            },
          },
          { trackUndo: true }
        );
        setFocusedBlockId(null);
        setPendingFocusBlockId(null);
      }
      return;
    }

    if (command.action === "create_full_database") {
      const response = await fetch("/api/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "New database",
          type: "database",
          accessLevel: "workspace",
          parentPageId: pageId,
          createMode: "full_page",
          createLinkInParent: false,
        }),
      });
      const data = await response.json();
      if (response.ok && data?.page?.id) {
        window.dispatchEvent(new Event("pages:refresh"));
        const title = String(data.page.title || "New database");
        const href = `/app/database/${data.page.id}`;
        await updateBlock(
          block.id,
          {
            type: "paragraph",
            contentText: title,
            propsJson: {
              ...(block.propsJson ?? {}),
              linkedPageId: data.page.id,
              linkedPageType: "database",
              linkedPageView: "link",
              linkedPageAuto: true,
            },
            richTextJson: {
              marks: [{ start: 0, end: title.length, link: href }],
            },
          },
          { trackUndo: true }
        );
        setFocusedBlockId(null);
        setPendingFocusBlockId(null);
      }
      return;
    }

    if (command.action === "create_child_page") {
      const response = await fetch("/api/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "New page",
          type: "document",
          accessLevel: "workspace",
          parentPageId: pageId,
          createMode: "inline",
          createLinkInParent: false,
        }),
      });
      const data = await response.json();
      if (response.ok && data?.page?.id) {
        window.dispatchEvent(new Event("pages:refresh"));
        const title = String(data.page.title || "New page");
        const href = `/app/page/${data.page.id}`;
        await updateBlock(
          block.id,
          {
            type: "paragraph",
            contentText: title,
            propsJson: {
              ...(block.propsJson ?? {}),
              linkedPageId: data.page.id,
              linkedPageType: "document",
              linkedPageView: "link",
              linkedPageAuto: true,
            },
            richTextJson: {
              marks: [{ start: 0, end: title.length, link: href }],
            },
          },
          { trackUndo: true }
        );
        setFocusedBlockId(null);
        setPendingFocusBlockId(null);
      }
      return;
    }

    if (command.type) {
      await updateBlock(block.id, {
        type: command.type,
        contentText: command.type === "divider" ? null : "",
        checked: command.type === "todo" ? false : null,
      }, { trackUndo: true });
      requestFocusBlock(block.id);
    }
  }

  function updateInlineToolbarFromTextarea(blockId: string, textarea: HTMLTextAreaElement | null) {
    if (!textarea) return;
    const start = textarea.selectionStart ?? 0;
    const end = textarea.selectionEnd ?? 0;
    if (start === end) {
      setInlineToolbar(null);
      setInlineColorOpen(false);
      return;
    }

    const rect = textarea.getBoundingClientRect();
    const desiredX = rect.left + rect.width / 2;
    const desiredY = rect.top - 8;
    const viewportPadding = 12;
    const clampedX = Math.max(viewportPadding + 180, Math.min(window.innerWidth - (viewportPadding + 180), desiredX));
    const clampedY = desiredY < 56 ? rect.top + 44 : desiredY;
    setInlineToolbar({
      blockId,
      start,
      end,
      x: clampedX,
      y: clampedY,
    });
  }

  async function applyInlineFormat(markKey: ToggleInlineMarkKey, options?: { showRenderedImmediately?: boolean }) {
    const blockId = inlineToolbar?.blockId ?? focusedBlockId;
    if (!blockId) return;
    const block = blocks.find((item) => item.id === blockId);
    if (!block) return;

    const range = getSelectionRangeForBlock(block.id);
    if (!range) return;

    const existingMarks = getInlineMarks(block);
    const selectedSegments = toInlineSegments((block.contentText ?? "").length, existingMarks).filter(
      (segment) => segment.end > range.start && segment.start < range.end
    );
    const allApplied =
      selectedSegments.length > 0 &&
      selectedSegments.every((segment) => {
        if (markKey === "bold") return Boolean(segment.style.bold);
        if (markKey === "italic") return Boolean(segment.style.italic);
        if (markKey === "underline") return Boolean(segment.style.underline);
        if (markKey === "strikethrough") return Boolean(segment.style.strikethrough);
        if (markKey === "code") return Boolean(segment.style.code);
        return Boolean(segment.style.equation);
      });
    const nextValue = !allApplied;

    const mutator = (style: InlineStyle): InlineStyle => {
      if (markKey === "bold") return { ...style, bold: nextValue };
      if (markKey === "italic") return { ...style, italic: nextValue };
      if (markKey === "underline") return { ...style, underline: nextValue };
      if (markKey === "strikethrough") return { ...style, strikethrough: nextValue };
      if (markKey === "code") return { ...style, code: nextValue };
      return { ...style, equation: nextValue };
    };

    if (options?.showRenderedImmediately) {
      setInlineToolbar(null);
      setFocusedBlockId(null);
      void updateInlineMarks(block, range, mutator);
      return;
    }

    await updateInlineMarks(block, range, mutator);
    setInlineToolbar((prev) => (prev ? { ...prev, start: range.start, end: range.end } : prev));
  }

  function insertLink(options?: { showRenderedImmediately?: boolean }) {
    const blockId = inlineToolbar?.blockId ?? focusedBlockId;
    if (!blockId) return;
    const block = blocks.find((item) => item.id === blockId);
    if (!block) return;
    const range = getSelectionRangeForBlock(block.id);
    if (!range) return;

    setLinkPopupValue("");
    setLinkPopup({
      blockId: block.id,
      start: range.start,
      end: range.end,
      x: inlineToolbar?.x ?? 0,
      y: inlineToolbar?.y ?? 0,
      showRenderedImmediately: options?.showRenderedImmediately,
    });
  }

  async function confirmLinkPopup() {
    if (!linkPopup) return;
    const url = linkPopupValue.trim();
    if (!url) { setLinkPopup(null); return; }
    const block = blocks.find((item) => item.id === linkPopup.blockId);
    if (!block) { setLinkPopup(null); return; }
    const range = { start: linkPopup.start, end: linkPopup.end };

    if (linkPopup.showRenderedImmediately) {
      setLinkPopup(null);
      setInlineToolbar(null);
      setFocusedBlockId(null);
      void updateInlineMarks(block, range, (style) => ({ ...style, link: url }));
      return;
    }

    setLinkPopup(null);
    await updateInlineMarks(block, range, (style) => ({ ...style, link: url }));
    setInlineToolbar((prev) => (prev ? { ...prev, start: range.start, end: range.end } : prev));
  }

  async function addCommentFromSelection() {
    if (!inlineToolbar) return;
    const block = blocks.find((item) => item.id === inlineToolbar.blockId);
    if (!block) return;

    const text = block.contentText ?? "";
    const selected = text.slice(inlineToolbar.start, inlineToolbar.end);
    setCommentComposer({
      blockId: block.id,
      quote: selected.trim(),
      text: "",
      parentCommentId: null,
    });
    setInlineToolbar(null);
  }

  function formatCommentTime(value: string) {
    return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function blinkReferencedBlock(blockId: string) {
    setHighlightedBlockId(blockId);
    window.setTimeout(() => setHighlightedBlockId(null), 260);
  }

  function isImageAttachmentUrl(url: string) {
    const clean = url.split("?")[0].toLowerCase();
    return /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/.test(clean);
  }

  function renderCommentContent(text: string, mode: "thread" | "reply") {
    const lines = text.split("\n");
    return (
      <div className={mode === "thread" ? "space-y-2" : "space-y-1.5"}>
        {lines.map((line, index) => {
          const trimmed = line.trim();
          const match = trimmed.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
          if (match) {
            const label = match[1];
            const url = match[2];
            if (isImageAttachmentUrl(url)) {
              return (
                <img
                  key={`${mode}-image-${index}-${url}`}
                  src={url}
                  alt={label}
                  className="max-h-[260px] w-full rounded-lg border border-[var(--line)] object-contain"
                />
              );
            }
            return (
              <a
                key={`${mode}-file-${index}-${url}`}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="block truncate rounded bg-[var(--surface)] px-2 py-1 text-sm text-[var(--blue)] underline"
              >
                {label}
              </a>
            );
          }

          if (trimmed.length === 0) {
            return <div key={`${mode}-empty-${index}`} className="h-2" />;
          }

          return (
            <p
              key={`${mode}-text-${index}`}
              className={mode === "thread" ? "whitespace-pre-wrap text-[15px] leading-6" : "whitespace-pre-wrap text-sm"}
            >
              {line}
            </p>
          );
        })}
      </div>
    );
  }

  async function onTextareaKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>, block: Block) {
    const isModKey = event.metaKey || event.ctrlKey;
    const key = event.key.toLowerCase();
    const value = block.contentText ?? "";
    const selectionStart = event.currentTarget.selectionStart ?? 0;
    const selectionEnd = event.currentTarget.selectionEnd ?? 0;
    const hasSelection = selectionStart !== selectionEnd;
    const visibleIndex = visibleBlocks.findIndex((item) => item.id === block.id);

    if (isModKey && key === "z") {
      event.preventDefault();
      if (event.shiftKey) return;
      const editingSnapshot = editSessionSnapshotRef.current[block.id];
      if (editingSnapshot && didContentChangeFromSession(block.id, value)) {
        delete editSessionSnapshotRef.current[block.id];
        isRestoringRef.current = true;
        setBlocks(editingSnapshot);
        requestFocusBlock(block.id);
        try {
          await replaceBlocks(editingSnapshot);
        } finally {
          isRestoringRef.current = false;
        }
        return;
      }
      await undoLastChange();
      return;
    }

    if (isModKey && !event.altKey) {
      if (key === "b") {
        event.preventDefault();
        await applyInlineFormat("bold");
        return;
      }
      if (key === "i") {
        event.preventDefault();
        await applyInlineFormat("italic");
        return;
      }
      if (key === "u") {
        event.preventDefault();
        await applyInlineFormat("underline");
        return;
      }
      if (key === "e") {
        event.preventDefault();
        await applyInlineFormat("code");
        return;
      }
      if (key === "k") {
        event.preventDefault();
        await insertLink();
        return;
      }
      if (event.shiftKey && key === "s") {
        event.preventDefault();
        await applyInlineFormat("strikethrough");
        return;
      }
    }

    if (slash && slash.blockId === block.id) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSlashIndex((prev) => {
          if (filteredSlashCommands.length === 0) return 0;
          return Math.min(filteredSlashCommands.length - 1, prev + 1);
        });
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSlashIndex((prev) => Math.max(0, prev - 1));
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const command = filteredSlashCommands[slashIndex];
        if (command) {
          await runSlashCommand(block, command);
        }
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setSlash(null);
        return;
      }
    }

    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      if (selectionStart === selectionEnd) {
        if (event.key === "ArrowUp" && selectionStart === 0 && visibleIndex > 0) {
          event.preventDefault();
          requestFocusBlock(visibleBlocks[visibleIndex - 1].id);
          return;
        }
        if (event.key === "ArrowDown" && selectionEnd === value.length && visibleIndex >= 0 && visibleIndex < visibleBlocks.length - 1) {
          event.preventDefault();
          requestFocusBlock(visibleBlocks[visibleIndex + 1].id);
          return;
        }
      }
    }

    if (event.key === "Tab") {
      event.preventDefault();
      if (event.shiftKey) {
        if (!block.parentBlockId) return;
        const parent = blockMap.get(block.parentBlockId);
        const nextParentId = parent?.parentBlockId ?? null;
        await updateBlock(block.id, { parentBlockId: nextParentId }, { trackUndo: true });
      } else {
        const ordered = orderedBlocks;
        const index = ordered.findIndex((item) => item.id === block.id);
        const currentDepth = getDepth(block);
        // Find the nearest previous block at the same depth — that becomes our new parent
        // (e.g. block at depth 0 looks for the previous depth-0 block, not depth-1 child)
        let target: Block | null = null;
        for (let i = index - 1; i >= 0; i--) {
          const candidate = ordered[i];
          const candidateDepth = getDepth(candidate);
          if (candidateDepth === currentDepth) {
            if (!isDescendantOf(candidate, block.id)) target = candidate;
            break;
          }
          if (candidateDepth < currentDepth) break; // went above our level
        }
        if (target) {
          await updateBlock(block.id, { parentBlockId: target.id }, { trackUndo: true });
        }
      }
      return;
    }

    if (
      (event.key === "Backspace" || event.key === "Delete") &&
      !hasSelection &&
      value.trim().length === 0 &&
      (block.type === "bulleted_list_item" ||
        block.type === "numbered_list_item" ||
        block.type === "todo" ||
        block.type === "toggle")
    ) {
      event.preventDefault();
      await updateBlock(block.id, {
        type: "paragraph",
        checked: null,
      }, { trackUndo: true });
      return;
    }

    if (event.key === "Backspace" && !hasSelection && selectionStart === 0 && visibleIndex > 0) {
      event.preventDefault();
      const previous = visibleBlocks[visibleIndex - 1];
      const currentText = value;
      const previousText = previous.contentText ?? "";
      const canMerge =
        TEXT_MERGE_BLOCK_TYPES.includes(previous.type) &&
        TEXT_MERGE_BLOCK_TYPES.includes(block.type);

      if (!currentText.length || !canMerge) {
        const hasDirectChildren = orderedBlocks.some((item) => item.parentBlockId === block.id);
        if (!currentText.length && hasDirectChildren) {
          await deleteBlockPromoteChildren(block.id);
          return;
        }
        await deleteBlock(block.id);
        requestFocusBlock(previous.id);
        return;
      }

      const merged = previousText.length && currentText.length ? `${previousText} ${currentText}` : `${previousText}${currentText}`;
      await updateBlock(previous.id, { contentText: merged });
      await deleteBlock(block.id);
      requestFocusBlock(previous.id);
      return;
    }

    if (event.key === " " && !hasSelection) {
      const shortcut = value.trim();
      const numberedShortcut = /^\d+\.$/.test(shortcut) ? "numbered_list_item" : null;
      const nextType = numberedShortcut ?? MARKDOWN_SHORTCUTS[shortcut];
      if (nextType) {
        event.preventDefault();
        await updateBlock(block.id, {
          type: nextType,
          contentText: "",
          checked: nextType === "todo" ? false : null,
          propsJson: nextType === "toggle" ? { ...(block.propsJson ?? {}), collapsed: true } : block.propsJson,
        }, { trackUndo: true });
        return;
      }
    }

    if (event.key === " " && value.trim() === "\\page") {
      event.preventDefault();
      await runSlashCommand(block, {
        id: "page",
        label: "Page",
        description: "Create a sub-page",
        action: "create_child_page",
        keywords: "page subpage",
        icon: Type,
      });
      return;
    }

    if (block.type === "code" && event.key === "Enter" && !event.shiftKey) {
      return;
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      const isEmpty = value.trim().length === 0;
      const isAtEnd = selectionStart === selectionEnd && selectionEnd === value.length;
      const before = value.slice(0, selectionStart);
      const after = value.slice(selectionEnd);
      const isListLike =
        block.type === "bulleted_list_item" ||
        block.type === "numbered_list_item" ||
        block.type === "todo" ||
        block.type === "toggle";

      if (isListLike && isEmpty) {
        await updateBlock(
          block.id,
          {
            type: "paragraph",
            checked: null,
            propsJson: block.type === "toggle" ? { ...(block.propsJson ?? {}), collapsed: false } : block.propsJson,
          },
          { trackUndo: true }
        );
        return;
      }

      const shouldSplitText = !hasSelection && !isAtEnd && block.type !== "divider" && block.type !== "image";
      if (shouldSplitText) {
        await updateBlock(block.id, { contentText: before }, { trackUndo: true });
      }

      let nextType: BlockType = "paragraph";
      if (block.type === "bulleted_list_item" || block.type === "numbered_list_item") nextType = block.type;
      if (block.type === "todo") nextType = "todo";
      if (block.type === "toggle") nextType = "toggle";
      if (block.type === "quote") nextType = "quote";
      if (block.type === "callout") nextType = "callout";

      const directChildren = orderedBlocks
        .filter((item) => item.parentBlockId === block.id)
        .sort((a, b) => a.position - b.position);
      const shouldCarryChildren =
        !shouldSplitText && isAtEnd && block.type !== "toggle" && directChildren.length > 0;
      const insertPosition = shouldCarryChildren ? getSubtreeTailPosition(block.id) + 1 : block.position + 1;

      const newBlock = await createBlock({
        type: nextType,
        parentBlockId: block.parentBlockId,
        position: insertPosition,
        contentText: shouldSplitText ? after : "",
        propsJson: nextType === "toggle" ? { collapsed: true } : null,
        trackUndo: !shouldSplitText,
      });

      if (newBlock && shouldCarryChildren) {
        await Promise.all(directChildren.map((child) => updateBlock(child.id, { parentBlockId: newBlock.id })));
      }

      if (newBlock) {
        requestFocusBlock(newBlock.id);
      }
      return;
    }

    if ((event.key === "Backspace" || event.key === "Delete") && value.trim().length === 0 && blocks.length > 1) {
      event.preventDefault();
      const hasDirectChildren = orderedBlocks.some((item) => item.parentBlockId === block.id);
      if (hasDirectChildren) {
        await deleteBlockPromoteChildren(block.id);
        return;
      }
      const previous = visibleIndex > 0 ? visibleBlocks[visibleIndex - 1] : null;
      const fallback = previous ?? (visibleIndex >= 0 ? visibleBlocks[visibleIndex + 1] : null);
      await deleteBlock(block.id);
      if (fallback) {
        requestFocusBlock(fallback.id);
      }
    }
  }

  async function applyInlineColor(
    key: "color" | "backgroundColor",
    value: string | null,
    options?: { showRenderedImmediately?: boolean }
  ) {
    const blockId = inlineToolbar?.blockId ?? focusedBlockId;
    if (!blockId) return;
    const block = blocks.find((item) => item.id === blockId);
    if (!block) return;
    const range = getSelectionRangeForBlock(block.id);
    if (!range) return;

    await updateInlineMarks(block, range, (style) => ({ ...style, [key]: value ?? undefined }));

    if (options?.showRenderedImmediately) {
      setInlineToolbar(null);
      setInlineColorOpen(false);
      setFocusedBlockId(null);
    } else {
      setInlineToolbar((prev) => (prev ? { ...prev, start: range.start, end: range.end } : prev));
    }
  }

  function textClassName(block: Block) {
    if (block.type === "heading_1") return "w-full resize-none overflow-hidden border-0 bg-transparent px-0 py-0.5 text-4xl font-semibold tracking-[-0.02em] leading-tight outline-none";
    if (block.type === "heading_2") return "w-full resize-none overflow-hidden border-0 bg-transparent px-0 py-0.5 text-2xl font-semibold leading-tight outline-none";
    if (block.type === "heading_3") return "w-full resize-none overflow-hidden border-0 bg-transparent px-0 py-0.5 text-xl font-semibold leading-tight outline-none";
    if (block.type === "code") return "w-full resize-none overflow-hidden rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 font-mono text-sm leading-6 outline-none";
    if (block.type === "quote") return "w-full resize-none overflow-hidden border-l-2 border-[var(--line-strong)] bg-transparent px-3 py-0.5 text-[15px] italic leading-6 outline-none";
    if (block.type === "callout") return "w-full resize-none overflow-hidden rounded-md bg-[var(--surface)] px-3 py-1.5 text-[15px] leading-6 outline-none";
    return "w-full resize-none overflow-hidden border-0 bg-transparent px-0 py-0.5 text-[15px] leading-6 outline-none";
  }

  function autoResize(el: HTMLTextAreaElement | null) {
    if (!el) return;
    el.style.height = "auto";
    const nextHeight = Math.min(320, Math.max(28, el.scrollHeight));
    el.style.height = `${nextHeight}px`;
    el.style.overflowY = el.scrollHeight > 320 ? "auto" : "hidden";
  }

  function scheduleAutoResize(el: HTMLTextAreaElement | null) {
    if (!el) return;
    requestAnimationFrame(() => {
      autoResize(el);
    });
  }

  function displayTextClassName(block: Block) {
    if (block.type === "heading_1") return "w-full px-0 py-0.5 text-4xl font-semibold tracking-[-0.02em] leading-tight whitespace-pre-wrap break-words";
    if (block.type === "heading_2") return "w-full px-0 py-0.5 text-2xl font-semibold leading-tight whitespace-pre-wrap break-words";
    if (block.type === "heading_3") return "w-full px-0 py-0.5 text-xl font-semibold leading-tight whitespace-pre-wrap break-words";
    if (block.type === "quote") return "w-full border-l-2 border-[var(--line-strong)] bg-transparent px-3 py-0.5 text-[15px] italic leading-6 whitespace-pre-wrap break-words";
    if (block.type === "callout") return "w-full rounded-md bg-[var(--surface)] px-3 py-1.5 text-[15px] leading-6 whitespace-pre-wrap break-words";
    return "w-full px-0 py-0.5 text-[15px] leading-6 whitespace-pre-wrap break-words";
  }

  const hasCommentRail = parsedComments.length > 0 || commentComposer !== null;
  const commentThreadGroups = useMemo<CommentThreadGroup[]>(() => {
    const groups: CommentThreadGroup[] = [];
    const pageThreads = (commentThreadsByBlockId.get(PAGE_COMMENT_ANCHOR) ?? []).filter((item) => !item.parentCommentId);
    const pageComposer =
      commentComposer && commentComposer.blockId === PAGE_COMMENT_ANCHOR && !commentComposer.parentCommentId
        ? commentComposer
        : null;

    if (pageThreads.length > 0 || pageComposer) {
      groups.push({
        blockId: PAGE_COMMENT_ANCHOR,
        blockQuote: "",
        threads: pageThreads,
        composer: pageComposer,
      });
    }

    groups.push(
      ...visibleBlocks.map((block) => {
        const threads = (commentThreadsByBlockId.get(block.id) ?? []).filter((item) => !item.parentCommentId);
        const composer =
          commentComposer && commentComposer.blockId === block.id && !commentComposer.parentCommentId
            ? commentComposer
            : null;
        if (threads.length === 0 && !composer) return null;
        return {
          blockId: block.id,
          blockQuote: (block.contentText ?? "").trim().slice(0, 180),
          threads,
          composer,
        };
      }).filter((item): item is CommentThreadGroup => Boolean(item))
    );
    return groups;
  }, [visibleBlocks, commentThreadsByBlockId, commentComposer]);
  const pageCommentGroup = commentThreadGroups.find((group) => group.blockId === PAGE_COMMENT_ANCHOR) ?? null;
  const showCommentRail = commentThreadGroups.some((group) => group.blockId !== PAGE_COMMENT_ANCHOR);

  function renderPageCommentGroup(group: CommentThreadGroup) {
    const composerForBlock = group.composer;
    const hasTopLevelComposer = Boolean(composerForBlock && !composerForBlock.parentCommentId);

    return (
      <div data-page-comment-panel="1" className="mb-6 space-y-3">
        {group.threads.map((thread) => {
          const replies = repliesByParentId.get(thread.id) ?? [];
          const replyComposer =
            commentComposer &&
            commentComposer.blockId === group.blockId &&
            commentComposer.parentCommentId === thread.id
              ? commentComposer
              : null;
          const isEditingThread = editingComment?.id === thread.id;
          const reactions = thread.uiMeta.reactions ?? [];
          const menuOpen = commentMenuId === thread.id;
          const reactionPickerOpen = reactionPickerForCommentId === thread.id;

          return (
            <div key={thread.id} className="rounded-2xl border-b border-[var(--line)] bg-transparent px-0 pb-4 pt-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--selected)] text-sm font-semibold text-[var(--text)]">
                    {(thread.author.email.split("@")[0] ?? "U").slice(0, 2).toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-[15px] font-semibold">{thread.author.email}</p>
                      <p className="text-sm text-[var(--muted)]">{formatCommentTime(thread.createdAt)}</p>
                    </div>
                  </div>
                </div>
                <div className="inline-flex items-center gap-1 text-[var(--muted)]" data-comment-menu="1">
                  <div className="relative">
                    <button
                      onClick={() => setReactionPickerForCommentId((prev) => (prev === thread.id ? null : thread.id))}
                      className="rounded p-1 hover:bg-[var(--hover)]"
                      title="Add reaction"
                    >
                      <SmilePlus className="h-4 w-4" />
                    </button>
                    {reactionPickerOpen ? (
                      <div className="absolute right-0 top-[110%] z-30 flex rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                        {COMMENT_REACTION_EMOJIS.map((emoji) => (
                          <button
                            key={`${thread.id}-${emoji}`}
                            className="rounded px-1.5 py-1 text-base hover:bg-[var(--hover)]"
                            onClick={() => {
                              void toggleCommentReaction(thread, emoji);
                              setReactionPickerForCommentId(null);
                            }}
                          >
                            {emoji}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <button onClick={() => void resolveComment(thread.id)} className="rounded p-1 hover:bg-[var(--hover)]" title="Resolve">
                    <Check className="h-4 w-4" />
                  </button>
                  <div className="relative">
                    <button
                      onClick={() => setCommentMenuId((prev) => (prev === thread.id ? null : thread.id))}
                      className="rounded p-1 hover:bg-[var(--hover)]"
                      title="More"
                    >
                      <Ellipsis className="h-4 w-4" />
                    </button>
                    {menuOpen ? (
                      <div className="absolute right-0 top-[110%] z-30 w-36 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                        <button
                          className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                          onClick={() => {
                            setEditingComment({ id: thread.id, text: thread.displayContent });
                            setCommentMenuId(null);
                          }}
                        >
                          Edit comment
                        </button>
                        <button
                          className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                          onClick={() => {
                            void resolveComment(thread.id);
                            setCommentMenuId(null);
                          }}
                        >
                          Delete comment
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>

              {isEditingThread ? (
                <div className="space-y-2">
                  <textarea
                    value={editingComment.text}
                    onChange={(event) =>
                      setEditingComment((prev) => (prev && prev.id === thread.id ? { ...prev, text: event.target.value } : prev))
                    }
                    rows={3}
                    className="w-full resize-none rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm outline-none"
                  />
                  <div className="flex items-center justify-end gap-2">
                    <button className="rounded px-2 py-1 text-xs hover:bg-[var(--hover)]" onClick={() => setEditingComment(null)}>
                      Cancel
                    </button>
                    <button
                      className="rounded bg-[var(--text)] px-2 py-1 text-xs text-[var(--bg)]"
                      onClick={() => void saveEditedComment(thread, editingComment.text)}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                renderCommentContent(thread.displayContent, "thread")
              )}

              {reactions.length > 0 ? (
                <div className="mt-2 flex flex-wrap items-center gap-1">
                  {reactions.map((reaction) => (
                    <button
                      key={`${thread.id}-${reaction.emoji}`}
                      className="rounded-full border border-[var(--line)] px-2 py-0.5 text-xs hover:bg-[var(--hover)]"
                      onClick={() => void toggleCommentReaction(thread, reaction.emoji)}
                    >
                      {reaction.emoji} {reaction.userIds.length}
                    </button>
                  ))}
                </div>
              ) : null}

              {replies.length > 0 ? (
                <div className="mt-3 space-y-2 border-t border-[var(--line)] pt-2">
                  {replies.map((reply) => {
                    const isEditingReply = editingComment?.id === reply.id;
                    const replyMenuOpen = commentMenuId === reply.id;
                    return (
                      <div key={reply.id} className="rounded-lg bg-[var(--surface)] px-2 py-1.5">
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-xs text-[var(--muted)]">{reply.author.email}</p>
                            <p className="text-xs text-[var(--muted)]">{formatCommentTime(reply.createdAt)}</p>
                          </div>
                          <div className="relative" data-comment-menu="1">
                            <button
                              className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                              onClick={() => setCommentMenuId((prev) => (prev === reply.id ? null : reply.id))}
                            >
                              <Ellipsis className="h-3.5 w-3.5" />
                            </button>
                            {replyMenuOpen ? (
                              <div className="absolute right-0 top-[110%] z-30 w-36 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                <button
                                  className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                  onClick={() => {
                                    setEditingComment({ id: reply.id, text: reply.displayContent });
                                    setCommentMenuId(null);
                                  }}
                                >
                                  Edit comment
                                </button>
                                <button
                                  className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                                  onClick={() => {
                                    void resolveComment(reply.id);
                                    setCommentMenuId(null);
                                  }}
                                >
                                  Delete comment
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </div>

                        {isEditingReply ? (
                          <div className="space-y-2">
                            <textarea
                              value={editingComment.text}
                              onChange={(event) =>
                                setEditingComment((prev) =>
                                  prev && prev.id === reply.id ? { ...prev, text: event.target.value } : prev
                                )
                              }
                              rows={2}
                              className="w-full resize-none rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm outline-none"
                            />
                            <div className="flex items-center justify-end gap-2">
                              <button className="rounded px-2 py-1 text-xs hover:bg-[var(--hover)]" onClick={() => setEditingComment(null)}>
                                Cancel
                              </button>
                              <button
                                className="rounded bg-[var(--text)] px-2 py-1 text-xs text-[var(--bg)]"
                                onClick={() =>
                                  void saveEditedComment(
                                    reply,
                                    editingComment && editingComment.id === reply.id ? editingComment.text : reply.displayContent
                                  )
                                }
                              >
                                Save
                              </button>
                            </div>
                          </div>
                        ) : (
                          renderCommentContent(reply.displayContent, "reply")
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}

              <div className="mt-3 rounded-xl border border-[var(--line)] px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <input
                    value={replyComposer?.text ?? ""}
                    onChange={(event) =>
                      updateCommentComposerText({
                        blockId: group.blockId,
                        quote: "",
                        parentCommentId: thread.id,
                        nextText: event.target.value,
                      })
                    }
                    onKeyDown={(event) => {
                      if ((event.nativeEvent as KeyboardEvent).isComposing) return;
                      if (event.key !== "Enter") return;
                      event.preventDefault();
                      void submitReply(group.blockId, thread, replyComposer?.text ?? "");
                    }}
                    placeholder="Reply..."
                    className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none"
                  />
                  <button
                    className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                    onClick={() =>
                      openCommentFilePicker({
                        key: `reply-${thread.id}`,
                        blockId: group.blockId,
                        quote: "",
                        parentCommentId: thread.id,
                      })
                    }
                    title="Attach file"
                  >
                    <Paperclip className="h-4 w-4" />
                  </button>
                  <div className="relative" data-comment-menu="1">
                    <button
                      className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                      onClick={() => setMentionPickerKey((prev) => (prev === `reply-${thread.id}` ? null : `reply-${thread.id}`))}
                      title="Mention member"
                    >
                      <AtSign className="h-4 w-4" />
                    </button>
                    {mentionPickerKey === `reply-${thread.id}` ? (
                      <div className="absolute bottom-[calc(100%+8px)] right-0 z-30 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                        {mentionCandidates.length === 0 ? (
                          <p className="px-2 py-1.5 text-xs text-[var(--muted)]">No members available</p>
                        ) : (
                          mentionCandidates.map((candidate) => (
                            <button
                              key={`reply-${thread.id}-${candidate.id}`}
                              className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                              onClick={() =>
                                insertMentionInComposer({
                                  blockId: group.blockId,
                                  quote: "",
                                  parentCommentId: thread.id,
                                  candidate,
                                })
                              }
                            >
                              @{candidate.email}
                            </button>
                          ))
                        )}
                      </div>
                    ) : null}
                  </div>
                  <button
                    className="rounded-full p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                    onClick={() => void submitReply(group.blockId, thread, replyComposer?.text ?? "")}
                  >
                    <ArrowUpCircle className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {hasTopLevelComposer ? (
          <div className="rounded-xl border-b border-[var(--line)] bg-transparent px-0 pb-4 pt-2">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--selected)] text-sm font-semibold text-[var(--text)]">
                ME
              </span>
              <input
                value={composerForBlock?.text ?? ""}
                onChange={(event) =>
                  updateCommentComposerText({
                    blockId: group.blockId,
                    quote: "",
                    parentCommentId: null,
                    nextText: event.target.value,
                  })
                }
                onKeyDown={(event) => {
                  if ((event.nativeEvent as KeyboardEvent).isComposing) return;
                  if (event.key !== "Enter") return;
                  event.preventDefault();
                  void submitTopLevelComment(group.blockId, "", composerForBlock?.text ?? "");
                }}
                placeholder="Add a comment..."
                className="min-w-0 flex-1 border-0 bg-transparent text-[15px] outline-none"
              />
              <button
                className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                onClick={() =>
                  openCommentFilePicker({
                    key: `top-${group.blockId}`,
                    blockId: group.blockId,
                    quote: "",
                    parentCommentId: null,
                  })
                }
                title="Attach file"
              >
                <Paperclip className="h-4 w-4" />
              </button>
              <div className="relative" data-comment-menu="1">
                <button
                  className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                  onClick={() => setMentionPickerKey((prev) => (prev === `top-${group.blockId}` ? null : `top-${group.blockId}`))}
                  title="Mention member"
                >
                  <AtSign className="h-4 w-4" />
                </button>
                {mentionPickerKey === `top-${group.blockId}` ? (
                  <div className="absolute bottom-[calc(100%+8px)] right-0 z-30 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                    {mentionCandidates.length === 0 ? (
                      <p className="px-2 py-1.5 text-xs text-[var(--muted)]">No members available</p>
                    ) : (
                      mentionCandidates.map((candidate) => (
                        <button
                          key={`top-${group.blockId}-${candidate.id}`}
                          className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                          onClick={() =>
                            insertMentionInComposer({
                              blockId: group.blockId,
                              quote: "",
                              parentCommentId: null,
                              candidate,
                            })
                          }
                        >
                          @{candidate.email}
                        </button>
                      ))
                    )}
                  </div>
                ) : null}
              </div>
              <button
                className="rounded-full p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                onClick={() => void submitTopLevelComment(group.blockId, "", composerForBlock?.text ?? "")}
              >
                <ArrowUpCircle className="h-5 w-5" />
              </button>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={showCommentRail ? "lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start lg:gap-8" : ""}>
      <div
        className="relative min-w-0 space-y-0.5 overflow-x-clip"
        onMouseDownCapture={beginMarqueeSelection}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("Files")) event.preventDefault();
        }}
        onDrop={(event) => {
          const file = event.dataTransfer.files?.[0];
          if (file) {
            event.preventDefault();
            void addImageFromFile(file, focusedBlockId ?? undefined);
          }
        }}
        onPaste={(event) => {
          const file = event.clipboardData.files?.[0];
          if (file) {
            event.preventDefault();
            void addImageFromFile(file, focusedBlockId ?? undefined);
          }
        }}
      >
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (!file) return;
          const targetId = uploadTargetBlockIdRef.current;
          if (targetId) {
            void (async () => {
              try {
                const fileUrl = await uploadFile(file);
                await updateBlock(targetId, { type: "image", imageUrl: fileUrl, contentText: file.name });
              } catch {
                await updateBlock(targetId, { contentText: "Upload failed" });
              }
              uploadTargetBlockIdRef.current = null;
            })();
          } else {
            void addImageFromFile(file, focusedBlockId ?? undefined);
          }
          event.currentTarget.value = "";
        }}
      />
      <input
        ref={commentFileInputRef}
        type="file"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          const target = commentUploadTargetRef.current;
          if (!file || !target) {
            event.currentTarget.value = "";
            return;
          }
          void (async () => {
            try {
              const fileUrl = await uploadFile(file);
              appendToComposer({
                blockId: target.blockId,
                quote: target.quote,
                parentCommentId: target.parentCommentId,
                textToAppend: `\n[${file.name}](${fileUrl})`,
              });
            } catch {}
          })();
          commentUploadTargetRef.current = null;
          event.currentTarget.value = "";
        }}
      />

      {uploadProgress !== null ? (
        <div className="mb-2 rounded-md border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-xs text-[var(--muted)]">
          Uploading... {uploadProgress}%
        </div>
      ) : null}

      {inlineToolbar ? (
        <div
          ref={toolbarRef}
          className="fixed z-40 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl"
          style={{ top: inlineToolbar.y, left: inlineToolbar.x, transform: "translate(-50%, -100%)" }}
        >
          <div className="relative">
            <div className="flex items-center gap-1">
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => setInlineColorOpen((prev) => !prev)} className={`rounded p-1 hover:bg-[var(--hover)] ${inlineColorOpen ? "bg-[var(--hover)]" : ""}`} title="Color"><Palette className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => applyInlineFormat("bold", { showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Bold className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => applyInlineFormat("italic", { showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Italic className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => applyInlineFormat("underline", { showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Underline className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => applyInlineFormat("strikethrough", { showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Strikethrough className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => insertLink({ showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Link2 className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => applyInlineFormat("code", { showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Code2 className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => applyInlineFormat("equation", { showRenderedImmediately: true })} className="rounded p-1 hover:bg-[var(--hover)]"><Sigma className="h-4 w-4" /></button>
              <button onMouseDown={(event) => event.preventDefault()} onClick={() => addCommentFromSelection()} className="rounded p-1 hover:bg-[var(--hover)]"><MessageSquare className="h-4 w-4" /></button>
            </div>

            {inlineColorOpen ? (
              <div className="absolute left-0 top-[calc(100%+8px)] z-50 w-[330px] rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-3 shadow-xl">
                <p className="mb-2 text-xs font-medium text-[var(--muted)]">Text color</p>
                <div className="mb-3 grid grid-cols-5 gap-2">
                  {INLINE_TEXT_COLORS.map((option) => (
                    <button
                      key={`text-${option.id}`}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        void applyInlineColor("color", option.value, { showRenderedImmediately: true });
                      }}
                      className="flex h-9 items-center justify-center rounded-lg border border-[var(--line)] text-base hover:bg-[var(--hover)]"
                      title={option.label}
                      style={{ color: option.value ?? "var(--text)" }}
                    >
                      A
                    </button>
                  ))}
                </div>

                <p className="mb-2 text-xs font-medium text-[var(--muted)]">Background color</p>
                <div className="grid grid-cols-5 gap-2">
                  {INLINE_BG_COLORS.map((option) => (
                    <button
                      key={`bg-${option.id}`}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => {
                        void applyInlineColor("backgroundColor", option.value, { showRenderedImmediately: true });
                      }}
                      className="h-9 rounded-lg border border-[var(--line)] hover:opacity-90"
                      title={option.label}
                      style={{ backgroundColor: option.value ?? "transparent" }}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {linkPopup ? (
        <div
          className="fixed z-50 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl"
          style={{ top: linkPopup.y + 6, left: linkPopup.x, transform: "translateX(-50%)" }}
          data-link-popup="1"
        >
          <form
            className="flex items-center gap-1"
            onSubmit={(event) => { event.preventDefault(); void confirmLinkPopup(); }}
          >
            <input
              autoFocus
              type="text"
              placeholder="Paste link URL…"
              value={linkPopupValue}
              onChange={(event) => setLinkPopupValue(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Escape") { setLinkPopup(null); } }}
              className="w-[220px] rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-sm outline-none focus:border-[var(--blue)]"
            />
            <button type="submit" className="rounded bg-[var(--blue)] px-2 py-1 text-sm text-white hover:opacity-90">
              Link
            </button>
          </form>
        </div>
      ) : null}

      {pageCommentGroup ? renderPageCommentGroup(pageCommentGroup) : null}
      {draggingBlockId ? (
        <div
          ref={deleteZoneRef}
          className="fixed bottom-6 right-8 z-40 flex h-14 min-w-[260px] items-center justify-center rounded-xl border-2 border-dashed border-[#cf2338]/55 bg-[#cf2338]/12 px-4 text-sm font-semibold text-[#cf2338] shadow-lg"
        >
          {selectedBlockIds.has(draggingBlockId ?? "") && selectedBlockIds.size > 1
            ? `Drop here to delete ${selectedBlockIds.size} blocks`
            : "Drop here to delete block"}
        </div>
      ) : null}

      {marqueeRect ? (
        <div
          className="pointer-events-none fixed z-50 rounded border border-[#2f76ff]/70 bg-[#2f76ff]/15"
          style={{
            left: marqueeRect.left,
            top: marqueeRect.top,
            width: marqueeRect.width,
            height: marqueeRect.height,
          }}
        />
      ) : null}

      {visibleBlocks.map((block, visualIndex) => {
        const depth = getDepth(block);
        const isToggle = block.type === "toggle";
        const isBulleted = block.type === "bulleted_list_item";
        const isNumbered = block.type === "numbered_list_item";
        const collapsed = Boolean(block.propsJson?.collapsed);
        const dropGuideDepth =
          dropIndicator?.overId === block.id ? getDepthFromParent(dropIndicator.parentBlockId) : depth;
        const inlineTable = parseInlineTableModel(block.propsJson);
        const commentThreads = commentThreadsByBlockId.get(block.id) ?? [];
        const composerForBlock =
          commentComposer?.blockId === block.id
            ? commentComposer
            : {
                blockId: block.id,
                quote: (block.contentText ?? "").trim().slice(0, 180),
                text: "",
                parentCommentId: null as string | null,
              };
        const hasCommentsOnBlock = commentThreads.length > 0 || commentComposer?.blockId === block.id;

        return (
          <div
            id={`block-${block.id}`}
            data-block-id={block.id}
            key={block.id}
            className="relative"
          >
            <div
              className={`group relative self-start rounded-md px-1 py-0.5 ${
                highlightedBlockId === block.id
                  ? "bg-[#ffe58f] ring-1 ring-[#facc15]/70"
                  : selectedBlockIds.has(block.id)
                  ? "bg-[#2f76ff]/10"
                  : hasCommentsOnBlock
                  ? "bg-[#fff7cc]/70 ring-1 ring-[#facc15]/55"
                  : "hover:bg-[var(--surface)]"
              }`}
              style={{ marginLeft: depth * INDENT_SIZE }}
            >
            {depth > 0 ? <div className="pointer-events-none absolute bottom-0 left-[-8px] top-0 w-px bg-[var(--line)]/60" /> : null}
            {dropIndicator?.overId === block.id ? (
              <div
                className="pointer-events-none absolute -bottom-[2px] right-1 z-10 h-[2px] rounded bg-[#2f76ff]"
                style={{ left: 44 + dropGuideDepth * INDENT_SIZE }}
              />
            ) : null}

            <div className="flex items-start gap-2">
              <div
                className={`mt-0.5 flex w-10 shrink-0 items-center justify-center gap-1 transition-opacity ${
                  editable
                    ? draggingBlockId === block.id
                      ? "opacity-100 visible"
                      : "opacity-0 invisible group-hover:opacity-100 group-hover:visible"
                    : "pointer-events-none invisible opacity-0"
                }`}
              >
                <button
                  data-no-marquee="1"
                  disabled={!editable}
                  onClick={async () => {
                    if (!editable) return;
                    const newBlock = await createBlock({
                      type: "paragraph",
                      afterBlockId: block.id,
                      parentBlockId: block.parentBlockId,
                      position: block.position + 1,
                    });
                    if (newBlock) requestFocusBlock(newBlock.id);
                  }}
                  className="rounded p-0.5 text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--text)]"
                  title="Add block"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
                <div
                  data-no-marquee="1"
                  role="button"
                  tabIndex={-1}
                  onMouseDown={(e) => {
                    if (!editable) return;
                    if (e.button !== 0) return;
                    e.preventDefault();
                    if (e.metaKey || e.ctrlKey || e.shiftKey) {
                      toggleBlockSelection(block.id);
                    } else if (!selectedBlockIdsRef.current.has(block.id)) {
                      setSelectedBlockIds(new Set([block.id]));
                    }
                    pointerDragRef.current = { blockId: block.id, startX: e.clientX, startY: e.clientY, isDragging: false };
                  }}
                  onClick={(event) => {
                    if (!editable) return;
                    if (pointerDragRef.current?.isDragging || justDraggedRef.current) return;
                    openBlockActionMenu(block.id, event.currentTarget as HTMLElement);
                  }}
                  className="cursor-grab rounded p-0.5 text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--text)] active:cursor-grabbing select-none"
                  title="Block actions"
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </div>
              </div>

              <div className="min-w-0 flex-1">
                {menuState?.blockId === block.id ? (
                  <div
                    ref={menuRef}
                    className="fixed z-40 w-[320px] max-w-[calc(100vw-24px)] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-2 text-sm shadow-xl"
                    style={{ left: menuPosition.left, top: menuPosition.top }}
                  >
                    <input
                      value={menuState.query}
                      onChange={(event) => setMenuState({ blockId: block.id, query: event.target.value })}
                      placeholder="Search actions..."
                      className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                    />

                    <div className="relative mb-2 rounded border border-[var(--line)] bg-[var(--surface)] p-1">
                      <button
                        className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                        onMouseEnter={() => setTurnIntoHoverBlockId(block.id)}
                        onFocus={() => setTurnIntoHoverBlockId(block.id)}
                        onClick={() => setTurnIntoHoverBlockId((prev) => (prev === block.id ? null : block.id))}
                      >
                        <span className="text-xs text-[var(--muted)]">Turn into</span>
                        <ChevronRight className="h-3.5 w-3.5 text-[var(--muted)]" />
                      </button>
                      {turnIntoHoverBlockId === block.id ? (
                        <div className="absolute left-[calc(100%+8px)] top-0 z-40 w-[240px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-1 shadow-xl">
                          <div className="max-h-[260px] space-y-1 overflow-y-auto scrollbar-thin">
                            {filteredTurnInto.map((item) => {
                              const Icon = item.icon;
                              return (
                                <button
                                  key={item.value}
                                  onClick={() => {
                                    void updateBlock(block.id, { type: item.value }, { trackUndo: true });
                                    setMenuState(null);
                                    setTurnIntoHoverBlockId(null);
                                  }}
                                  className="flex w-full items-center justify-between rounded px-2 py-1.5 hover:bg-[var(--hover)]"
                                >
                                  <span className="inline-flex items-center gap-2">
                                    <Icon className="h-4 w-4 text-[var(--muted)]" />
                                    {item.label}
                                  </span>
                                  {block.type === item.value ? <span>✓</span> : null}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ) : null}
                    </div>

                    <div className="mb-2 rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-2">
                      <p className="mb-1 text-xs text-[var(--muted)]">Color</p>
                      <button
                        onClick={() => openInlineColorPaletteForBlock(block.id)}
                        className="inline-flex items-center gap-2 rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]"
                      >
                        <Palette className="h-3.5 w-3.5" />
                        Open color palette
                      </button>
                    </div>

                    <div className="space-y-1">
                      <button onClick={() => copyBlockLink(block.id)} className="flex w-full items-center rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]">Copy link to block</button>
                      <button onClick={() => duplicateBlock(block.id)} className="flex w-full items-center rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]">Duplicate</button>
                      <button onClick={() => deleteBlock(block.id)} className="flex w-full items-center rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]">Delete</button>
                      <button
                        className="flex w-full items-center rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                        onClick={() => {
                          setCommentComposer({
                            blockId: block.id,
                            quote: (block.contentText ?? "").trim().slice(0, 180),
                            text: "",
                            parentCommentId: null,
                          });
                          setMenuState(null);
                        }}
                      >
                        Comment
                      </button>
                    </div>
                  </div>
                ) : null}

                {block.type === "divider" ? (
                  <div className="py-3">
                    <div className="h-px w-full bg-[var(--line-strong)]" />
                  </div>
                ) : block.type === "image" ? (
                  <div className="space-y-2">
                    <input
                      value={block.imageUrl ?? ""}
                      readOnly={!editable}
                      onChange={(event) =>
                        editable
                          ? setBlocks((prev) => prev.map((item) => (item.id === block.id ? { ...item, imageUrl: event.target.value } : item)))
                          : undefined
                      }
                      onBlur={(event) => {
                        if (!editable) return;
                        updateBlock(block.id, { imageUrl: event.target.value });
                      }}
                      placeholder="Paste image URL or use /image upload"
                      className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
                    />
                    <button
                      disabled={!editable}
                      onClick={() => {
                        if (!editable) return;
                        uploadTargetBlockIdRef.current = block.id;
                        fileInputRef.current?.click();
                      }}
                      className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)] disabled:opacity-50"
                    >
                      Upload file
                    </button>
                    {block.imageUrl ? (
                      <img
                        src={block.imageUrl}
                        alt={block.contentText ?? "image"}
                        className="max-h-[420px] w-full rounded-md border border-[var(--line)] object-contain"
                      />
                    ) : null}
                    <input
                      value={block.contentText ?? ""}
                      readOnly={!editable}
                      onChange={(event) =>
                        editable
                          ? setBlocks((prev) => prev.map((item) => (item.id === block.id ? { ...item, contentText: event.target.value } : item)))
                          : undefined
                      }
                      onBlur={(event) => {
                        if (!editable) return;
                        updateBlock(block.id, { contentText: event.target.value });
                      }}
                      placeholder="Caption"
                      className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
                    />
                  </div>
                ) : inlineTable ? (
                  <div className="space-y-2">
                    <div className="inline-block rounded-md border border-[var(--line)] bg-[var(--panel)] p-2">
                      <table className="border-collapse">
                        <tbody>
                          {inlineTable.cells.map((row, rowIndex) => (
                            <tr key={`${block.id}-row-${rowIndex}`}>
                              {row.map((cell, colIndex) => (
                                <td key={`${block.id}-cell-${rowIndex}-${colIndex}`} className="border border-[var(--line)] p-0">
                                  <input
                                    value={cell}
                                    readOnly={!editable}
                                    onFocus={() => {
                                      if (!editable) return;
                                      setFocusedBlockId(block.id);
                                      setSelectedBlockIds(new Set());
                                    }}
                                    onChange={(event) => {
                                      if (!editable) return;
                                      setInlineTableCell(block.id, rowIndex, colIndex, event.target.value);
                                    }}
                                    onBlur={() => {
                                      if (!editable) return;
                                      void persistInlineTable(block.id);
                                    }}
                                    className="h-9 min-w-[120px] border-0 bg-transparent px-2 py-1 text-sm outline-none"
                                  />
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                      <button
                        disabled={!editable}
                        onClick={() => {
                          if (!editable) return;
                          const nextTable: InlineTableModel = {
                            rows: Math.max(1, Math.min(20, Math.trunc(inlineTable.rows + 1))),
                            cols: Math.max(1, Math.min(20, Math.trunc(inlineTable.cols))),
                            cells: Array.from({ length: Math.max(1, Math.min(20, Math.trunc(inlineTable.rows + 1))) }, (_, rowIndex) =>
                              Array.from({ length: Math.max(1, Math.min(20, Math.trunc(inlineTable.cols))) }, (_, colIndex) =>
                                inlineTable.cells[rowIndex]?.[colIndex] ?? ""
                              )
                            ),
                          };
                          resizeInlineTable(block.id, nextTable.rows, nextTable.cols);
                          void persistInlineTable(block.id, nextTable);
                        }}
                        className="rounded border border-[var(--line)] px-2 py-1 hover:bg-[var(--hover)] disabled:opacity-50"
                      >
                        + Row
                      </button>
                      <button
                        disabled={!editable}
                        onClick={() => {
                          if (!editable) return;
                          const nextTable: InlineTableModel = {
                            rows: Math.max(1, Math.min(20, Math.trunc(inlineTable.rows))),
                            cols: Math.max(1, Math.min(20, Math.trunc(inlineTable.cols + 1))),
                            cells: Array.from({ length: Math.max(1, Math.min(20, Math.trunc(inlineTable.rows))) }, (_, rowIndex) =>
                              Array.from({ length: Math.max(1, Math.min(20, Math.trunc(inlineTable.cols + 1))) }, (_, colIndex) =>
                                inlineTable.cells[rowIndex]?.[colIndex] ?? ""
                              )
                            ),
                          };
                          resizeInlineTable(block.id, nextTable.rows, nextTable.cols);
                          void persistInlineTable(block.id, nextTable);
                        }}
                        className="rounded border border-[var(--line)] px-2 py-1 hover:bg-[var(--hover)] disabled:opacity-50"
                      >
                        + Column
                      </button>
                      <button
                        disabled={!editable}
                        className="cursor-nwse-resize rounded border border-[var(--line)] px-2 py-1 hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-50"
                        onMouseDown={(event) => {
                          if (!editable) return;
                          event.preventDefault();
                          tableResizeRef.current = {
                            blockId: block.id,
                            startX: event.clientX,
                            startY: event.clientY,
                            startRows: inlineTable.rows,
                            startCols: inlineTable.cols,
                          };
                        }}
                        title="Drag to resize"
                      >
                        Resize
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    {isToggle ? (
                      <button
                        onClick={async () => {
                          const willExpand = collapsed;
                          await updateBlock(block.id, { propsJson: { ...(block.propsJson ?? {}), collapsed: !collapsed } });
                          if (willExpand) {
                            const hasChildren = blocks.some((b) => b.parentBlockId === block.id);
                            if (!hasChildren) {
                              const child = await createBlock({ type: "paragraph", parentBlockId: block.id, position: block.position + 1 });
                              if (child) requestFocusBlock(child.id);
                            }
                          }
                        }}
                        className="mt-1 w-5 text-xs text-[var(--muted)]"
                      >
                        <ChevronRight className={`h-3.5 w-3.5 transition ${collapsed ? "" : "rotate-90"}`} />
                      </button>
                    ) : null}

                    {isBulleted ? <span className="mt-1 w-5 text-center text-sm text-[var(--muted)]">{getBulletMarker(depth)}</span> : null}
                    {isNumbered ? (
                      <span className="mt-1 min-w-[1.5rem] text-right text-sm text-[var(--muted)]">
                        {formatNumberedMarker(getNumberedListOrder(block), depth)}
                      </span>
                    ) : null}

                    {block.type === "todo" ? (
                      <input
                        type="checkbox"
                        checked={Boolean(block.checked)}
                        disabled={!editable}
                        onChange={(event) => {
                          if (!editable) return;
                          updateBlock(block.id, { checked: event.target.checked });
                        }}
                        className="mt-1.5"
                      />
                    ) : null}

                    {block.type === "code" ? (
                      <div className="w-full overflow-hidden rounded-md border border-[var(--line)] bg-[var(--surface)]">
                        <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)]">
                          <span>Code</span>
                          <select
                            value={(block.propsJson?.language as string) ?? "plain"}
                            disabled={!editable}
                            onChange={(event) =>
                              void (editable
                                ? updateBlock(block.id, {
                                    propsJson: { ...(block.propsJson ?? {}), language: event.target.value },
                                  })
                                : Promise.resolve())
                            }
                            className="rounded border border-[var(--line)] bg-[var(--panel)] px-1.5 py-0.5 text-xs"
                          >
                            {CODE_LANGUAGES.map((lang) => (
                              <option key={lang} value={lang}>
                                {lang}
                              </option>
                            ))}
                          </select>
                        </div>
                        {editable ? (
                          <textarea
                            ref={(element) => {
                              textareaRefs.current[block.id] = element;
                              scheduleAutoResize(element);
                            }}
                            value={block.contentText ?? ""}
                            onFocus={() => {
                              setFocusedBlockId(block.id);
                              beginEditSession(block.id);
                              scheduleAutoResize(textareaRefs.current[block.id]);
                            }}
                            onChange={(event) => {
                              const value = event.target.value;
                              setBlocks((prev) => prev.map((item) => (item.id === block.id ? { ...item, contentText: value } : item)));
                            }}
                            onInput={(event) => autoResize(event.currentTarget)}
                            onBlur={(event) => {
                              if (suppressNextBlurSaveRef.current.has(block.id)) {
                                suppressNextBlurSaveRef.current.delete(block.id);
                                endEditSession(block.id, false);
                                setFocusedBlockId((current) => (current === block.id ? null : current));
                                return;
                              }
                              const changed = didContentChangeFromSession(block.id, event.target.value);
                              endEditSession(block.id, changed);
                              void updateBlock(block.id, { contentText: event.target.value });
                              setFocusedBlockId((current) => (current === block.id ? null : current));
                            }}
                            onMouseUp={(event) => updateInlineToolbarFromTextarea(block.id, event.currentTarget)}
                            onSelect={(event) => updateInlineToolbarFromTextarea(block.id, event.currentTarget)}
                            onDoubleClick={(event) => {
                              const textarea = event.currentTarget;
                              window.requestAnimationFrame(() => updateInlineToolbarFromTextarea(block.id, textarea));
                            }}
                            onKeyUp={(event) => updateInlineToolbarFromTextarea(block.id, event.currentTarget)}
                            onKeyDown={(event) => {
                              void onTextareaKeyDown(event, block);
                            }}
                            placeholder="Write code..."
                            className="w-full resize-none border-0 bg-transparent px-3 py-2 font-mono text-sm leading-6 outline-none"
                          />
                        ) : (
                          <pre className="whitespace-pre-wrap px-3 py-2 font-mono text-sm leading-6">{block.contentText ?? ""}</pre>
                        )}
                      </div>
                    ) : (
                      editable && focusedBlockId === block.id ? (
                        <textarea
                          ref={(element) => {
                            textareaRefs.current[block.id] = element;
                            scheduleAutoResize(element);
                          }}
                          value={block.contentText ?? ""}
                          onFocus={() => {
                            setFocusedBlockId(block.id);
                            beginEditSession(block.id);
                            scheduleAutoResize(textareaRefs.current[block.id]);
                          }}
                          onChange={(event) => {
                            const value = event.target.value;
                            setBlocks((prev) => prev.map((item) => (item.id === block.id ? { ...item, contentText: value } : item)));
                            if (value.startsWith("/") && !value.includes("\n")) {
                              openSlash(block.id, value);
                            } else if (slash?.blockId === block.id) {
                              setSlash(null);
                            }
                          }}
                          onInput={(event) => autoResize(event.currentTarget)}
                          onBlur={(event) => {
                            if (suppressNextBlurSaveRef.current.has(block.id)) {
                              suppressNextBlurSaveRef.current.delete(block.id);
                              endEditSession(block.id, false);
                              setFocusedBlockId((current) => (current === block.id ? null : current));
                              return;
                            }
                            const changed = didContentChangeFromSession(block.id, event.target.value);
                            endEditSession(block.id, changed);
                            void updateBlock(block.id, { contentText: event.target.value });
                            setFocusedBlockId((current) => (current === block.id ? null : current));
                          }}
                          onMouseUp={(event) => updateInlineToolbarFromTextarea(block.id, event.currentTarget)}
                          onSelect={(event) => updateInlineToolbarFromTextarea(block.id, event.currentTarget)}
                          onDoubleClick={(event) => {
                            const textarea = event.currentTarget;
                            window.requestAnimationFrame(() => updateInlineToolbarFromTextarea(block.id, textarea));
                          }}
                          onKeyUp={(event) => updateInlineToolbarFromTextarea(block.id, event.currentTarget)}
                          onKeyDown={(event) => {
                            void onTextareaKeyDown(event, block);
                          }}
                          rows={1}
                          placeholder={
                            (focusedBlockId === block.id || visualIndex === visibleBlocks.length - 1) && (block.contentText ?? "").length === 0
                              ? "Type '/' for commands"
                              : ""
                          }
                          className={textClassName(block)}
                          style={(() => {
                            const color = getFocusedTextareaColor(block);
                            return color ? { color } : undefined;
                          })()}
                        />
                      ) : (
                        <div
                          role="button"
                          tabIndex={0}
                          onMouseDown={(event) => {
                            if (!editable) return;
                            if (event.button !== 0) return;
                            const target = event.target as HTMLElement | null;
                            if (target?.closest("a,button,input,select,textarea,[data-inline-db='1']")) return;
                            event.preventDefault();
                            if (event.shiftKey || event.metaKey || event.ctrlKey) {
                              toggleBlockSelection(block.id);
                              return;
                            }
                            setSelectedBlockIds(new Set());
                            requestFocusBlock(block.id);
                          }}
                          onKeyDown={(event) => {
                            if (!editable) return;
                            if (event.key !== "Enter" && event.key !== " ") return;
                            event.preventDefault();
                            setSelectedBlockIds(new Set());
                            requestFocusBlock(block.id);
                          }}
                          className={`m-0 min-h-[1.75rem] w-full border-0 bg-transparent p-0 text-left outline-none ${editable ? "cursor-text" : "cursor-default"} ${displayTextClassName(block)}`}
                          style={block.propsJson?.color ? { color: String(block.propsJson.color) } : undefined}
                        >
                          {(block.contentText ?? "").length === 0 ? (
                            <span className="text-[var(--muted)]">
                              {(visualIndex === visibleBlocks.length - 1) ? "Type '/' for commands" : ""}
                            </span>
                          ) : (
                            (() => {
                              const linkedPageMeta = getLinkedPageMeta(block);
                              if (!linkedPageMeta) return renderRichText(block);
                              if (linkedPageMeta.type === "database" && linkedPageMeta.view === "inline") {
                                return (
                                  <InlineDatabaseEmbed
                                    databasePageId={linkedPageMeta.id}
                                    title={block.contentText ?? "New database"}
                                    editable={editable}
                                    onRename={async (nextTitle) => {
                                      await updateBlock(block.id, {
                                        contentText: nextTitle,
                                        richTextJson: {
                                          marks: [{ start: 0, end: nextTitle.length, link: linkedPageMeta.href }],
                                        },
                                      });
                                    }}
                                  />
                                );
                              }
                              return (
                                <a
                                  href={linkedPageMeta.href}
                                  data-inline-link="1"
                                  onClick={(event) => {
                                    event.preventDefault();
                                    router.push(linkedPageMeta.href);
                                  }}
                                  className="inline-flex max-w-full items-center gap-2 rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[14px] hover:bg-[var(--hover)]"
                                >
                                  <span className="text-[var(--muted)]">{linkedPageMeta.type === "database" ? "🗄️" : "📄"}</span>
                                  <span className="truncate underline underline-offset-2">{block.contentText}</span>
                                </a>
                              );
                            })()
                          )}
                        </div>
                      )
                    )}
                  </div>
                )}

                {isToggle && !collapsed && !orderedBlocks.some((b) => b.parentBlockId === block.id) ? (
                  <div className="py-1 pl-7 text-sm text-[var(--muted)]">
                    Empty toggle. Click or drop blocks inside.
                  </div>
                ) : null}

                {slash && slash.blockId === block.id ? (
                  <div className="mt-1 w-[420px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                    <input
                      value={slash.query}
                      onChange={(event) => {
                        setSlash({ ...slash, query: event.target.value });
                        setSlashIndex(0);
                      }}
                      placeholder="Type to search"
                      className="mb-1 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                    />
                    <div className="max-h-[280px] overflow-y-auto scrollbar-thin">
                      {filteredSlashCommands.map((command, index) => {
                        const Icon = command.icon;
                        return (
                          <button
                            key={command.id}
                            onMouseDown={(event) => {
                              event.preventDefault();
                              void runSlashCommand(block, command);
                            }}
                            className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left ${index === slashIndex ? "bg-[var(--selected)]" : "hover:bg-[var(--hover)]"}`}
                          >
                            <Icon className="h-4 w-4 text-[var(--muted)]" />
                            <span>
                              <span className="block text-sm">{command.label}</span>
                              <span className="block text-xs text-[var(--muted)]">{command.description}</span>
                            </span>
                          </button>
                        );
                      })}
                      {filteredSlashCommands.length === 0 ? <p className="px-2 py-2 text-sm text-[var(--muted)]">No commands found.</p> : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

            {false ? (
              <div className="self-start">
                {false ? (
                  <div className="relative z-20 mt-1 w-[360px] space-y-2">
                    {commentThreads.map((thread) => {
                      const replies = repliesByParentId.get(thread.id) ?? [];
                      const isReplyingHere =
                        composerForBlock &&
                        composerForBlock.parentCommentId === thread.id &&
                        composerForBlock.blockId === block.id;

                      const isEditingThread = editingComment?.id === thread.id;
                      const reactions = thread.uiMeta.reactions ?? [];
                      const menuOpen = commentMenuId === thread.id;
                      const reactionPickerOpen = reactionPickerForCommentId === thread.id;
                      return (
                        <div
                          key={thread.id}
                          className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-3 shadow-sm"
                          onClick={(event) => {
                            const target = event.target as HTMLElement;
                            if (target.closest("button,input,textarea,a,select,[data-no-blink='1']")) return;
                            if (thread.anchorBlockId) {
                              blinkReferencedBlock(thread.anchorBlockId);
                            }
                          }}
                        >
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--selected)] text-xs font-semibold text-[var(--text)]">
                                {(thread.author.email.split("@")[0] ?? "U").slice(0, 2).toUpperCase()}
                              </span>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium">{thread.author.email}</p>
                                <p className="text-xs text-[var(--muted)]">{formatCommentTime(thread.createdAt)}</p>
                              </div>
                            </div>
                            <div className="inline-flex items-center gap-1 text-[var(--muted)]" data-comment-menu="1">
                              <div className="relative">
                                <button
                                  onClick={() =>
                                    setReactionPickerForCommentId((prev) => (prev === thread.id ? null : thread.id))
                                  }
                                  className="rounded p-1 hover:bg-[var(--hover)]"
                                  title="Add reaction"
                                >
                                  <SmilePlus className="h-4 w-4" />
                                </button>
                                {reactionPickerOpen ? (
                                  <div className="absolute right-0 top-[110%] z-30 flex rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                    {COMMENT_REACTION_EMOJIS.map((emoji) => (
                                      <button
                                        key={`${thread.id}-${emoji}`}
                                        className="rounded px-1.5 py-1 text-base hover:bg-[var(--hover)]"
                                        onClick={() => {
                                          void toggleCommentReaction(thread, emoji);
                                          setReactionPickerForCommentId(null);
                                        }}
                                      >
                                        {emoji}
                                      </button>
                                    ))}
                                  </div>
                                ) : null}
                              </div>
                              <button
                                onClick={() => {
                                  void resolveComment(thread.id);
                                }}
                                className="rounded p-1 hover:bg-[var(--hover)]"
                                title="Resolve"
                              >
                                <Check className="h-4 w-4" />
                              </button>
                              <div className="relative">
                                <button
                                  onClick={() => setCommentMenuId((prev) => (prev === thread.id ? null : thread.id))}
                                  className="rounded p-1 hover:bg-[var(--hover)]"
                                  title="More"
                                >
                                  <Ellipsis className="h-4 w-4" />
                                </button>
                                {menuOpen ? (
                                  <div className="absolute right-0 top-[110%] z-30 w-36 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                    <button
                                      className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                      onClick={() => {
                                        setEditingComment({ id: thread.id, text: thread.displayContent });
                                        setCommentMenuId(null);
                                      }}
                                    >
                                      Edit comment
                                    </button>
                                    <button
                                      className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                                      onClick={() => {
                                        void resolveComment(thread.id);
                                        setCommentMenuId(null);
                                      }}
                                    >
                                      Delete comment
                                    </button>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </div>

                          {thread.anchorQuote ? (
                            <p className="mb-2 line-clamp-2 rounded bg-[var(--surface)] px-2 py-1 text-xs text-[var(--muted)]" data-no-blink="1">
                              {thread.anchorQuote}
                            </p>
                          ) : null}

                          {isEditingThread ? (
                            <div className="space-y-2">
                              <textarea
                                value={editingComment.text}
                                onChange={(event) =>
                                  setEditingComment((prev) => (prev && prev.id === thread.id ? { ...prev, text: event.target.value } : prev))
                                }
                                rows={3}
                                className="w-full resize-none rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm outline-none"
                              />
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  className="rounded px-2 py-1 text-xs hover:bg-[var(--hover)]"
                                  onClick={() => setEditingComment(null)}
                                >
                                  Cancel
                                </button>
                                <button
                                  className="rounded bg-[var(--text)] px-2 py-1 text-xs text-[var(--bg)]"
                                  onClick={() => void saveEditedComment(thread, editingComment.text)}
                                >
                                  Save
                                </button>
                              </div>
                            </div>
                          ) : renderCommentContent(thread.displayContent, "thread")}

                          {reactions.length > 0 ? (
                            <div className="mt-2 flex items-center justify-between">
                              <div className="flex flex-wrap items-center gap-1">
                                {reactions.map((reaction) => (
                                  <button
                                    key={`${thread.id}-${reaction.emoji}`}
                                    className="rounded-full border border-[var(--line)] px-2 py-0.5 text-xs hover:bg-[var(--hover)]"
                                    onClick={() => void toggleCommentReaction(thread, reaction.emoji)}
                                  >
                                    {reaction.emoji} {reaction.userIds.length}
                                  </button>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          {replies.length > 0 ? (
                            <div className="mt-3 space-y-2 border-t border-[var(--line)] pt-2">
                              {replies.map((reply) => {
                                const isEditingReply = editingComment?.id === reply.id;
                                const replyMenuOpen = commentMenuId === reply.id;
                                return (
                                  <div
                                    key={reply.id}
                                    className="rounded-lg bg-[var(--surface)] px-2 py-1.5"
                                    onClick={(event) => {
                                      const target = event.target as HTMLElement;
                                      if (target.closest("button,input,textarea,a,select,[data-no-blink='1']")) return;
                                      if (thread.anchorBlockId) {
                                        blinkReferencedBlock(thread.anchorBlockId);
                                      }
                                    }}
                                  >
                                    <div className="mb-1 flex items-center justify-between gap-2">
                                      <div className="min-w-0">
                                        <p className="truncate text-xs text-[var(--muted)]">{reply.author.email}</p>
                                        <p className="text-xs text-[var(--muted)]">{formatCommentTime(reply.createdAt)}</p>
                                      </div>
                                      <div className="relative" data-comment-menu="1">
                                        <button
                                          className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                                          onClick={() => setCommentMenuId((prev) => (prev === reply.id ? null : reply.id))}
                                        >
                                          <Ellipsis className="h-3.5 w-3.5" />
                                        </button>
                                        {replyMenuOpen ? (
                                          <div className="absolute right-0 top-[110%] z-30 w-36 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                            <button
                                              className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                              onClick={() => {
                                                setEditingComment({ id: reply.id, text: reply.displayContent });
                                                setCommentMenuId(null);
                                              }}
                                            >
                                              Edit comment
                                            </button>
                                            <button
                                              className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                                              onClick={() => {
                                                void resolveComment(reply.id);
                                                setCommentMenuId(null);
                                              }}
                                            >
                                              Delete comment
                                            </button>
                                          </div>
                                        ) : null}
                                      </div>
                                    </div>

                                    {isEditingReply ? (
                                      <div className="space-y-2">
                                        <textarea
                                          value={editingComment.text}
                                          onChange={(event) =>
                                            setEditingComment((prev) =>
                                              prev && prev.id === reply.id ? { ...prev, text: event.target.value } : prev
                                            )
                                          }
                                          rows={2}
                                          className="w-full resize-none rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm outline-none"
                                        />
                                        <div className="flex items-center justify-end gap-2">
                                          <button
                                            className="rounded px-2 py-1 text-xs hover:bg-[var(--hover)]"
                                            onClick={() => setEditingComment(null)}
                                          >
                                            Cancel
                                          </button>
                                          <button
                                            className="rounded bg-[var(--text)] px-2 py-1 text-xs text-[var(--bg)]"
                                            onClick={() =>
                                              void saveEditedComment(
                                                reply,
                                                editingComment && editingComment.id === reply.id ? editingComment.text : reply.displayContent
                                              )
                                            }
                                          >
                                            Save
                                          </button>
                                        </div>
                                      </div>
                                    ) : (
                                      renderCommentContent(reply.displayContent, "reply")
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : null}

                          <div className="mt-3 rounded-xl border border-[var(--line)] px-2 py-1.5">
                            <div className="flex items-center gap-2">
                              <input
                                value={isReplyingHere ? composerForBlock.text : ""}
                                onChange={(event) =>
                                  updateCommentComposerText({
                                    blockId: block.id,
                                    quote: thread.anchorQuote ?? "",
                                    parentCommentId: thread.id,
                                    nextText: event.target.value,
                                  })
                                }
                                onKeyDown={(event) => {
                                  if ((event.nativeEvent as KeyboardEvent).isComposing) return;
                                  if (event.key !== "Enter") return;
                                  event.preventDefault();
                                  void submitReply(block.id, thread, isReplyingHere ? composerForBlock.text : "");
                                }}
                                placeholder="Reply..."
                                className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none"
                              />
                              <button
                                className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                                onClick={() =>
                                  openCommentFilePicker({
                                    key: `reply-${thread.id}`,
                                    blockId: block.id,
                                    quote: thread.anchorQuote ?? "",
                                    parentCommentId: thread.id,
                                  })
                                }
                                title="Attach file"
                              >
                                <Paperclip className="h-4 w-4" />
                              </button>
                              <div className="relative" data-comment-menu="1">
                                <button
                                  className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                                  onClick={() =>
                                    setMentionPickerKey((prev) => (prev === `reply-${thread.id}` ? null : `reply-${thread.id}`))
                                  }
                                  title="Mention member"
                                >
                                  <AtSign className="h-4 w-4" />
                                </button>
                                {mentionPickerKey === `reply-${thread.id}` ? (
                                  <div className="absolute bottom-[calc(100%+8px)] right-0 z-30 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                    {mentionCandidates.length === 0 ? (
                                      <p className="px-2 py-1.5 text-xs text-[var(--muted)]">No members available</p>
                                    ) : (
                                      mentionCandidates.map((candidate) => (
                                        <button
                                          key={`reply-${thread.id}-${candidate.id}`}
                                          className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                          onClick={() =>
                                            insertMentionInComposer({
                                              blockId: block.id,
                                              quote: thread.anchorQuote ?? "",
                                              parentCommentId: thread.id,
                                              candidate,
                                            })
                                          }
                                        >
                                          @{candidate.email}
                                        </button>
                                      ))
                                    )}
                                  </div>
                                ) : null}
                              </div>
                              <button
                                className="rounded-full p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                                onClick={() => void submitReply(block.id, thread, isReplyingHere ? composerForBlock.text : "")}
                              >
                                <ArrowUpCircle className="h-5 w-5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    {composerForBlock && !composerForBlock.parentCommentId ? (
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 shadow-sm">
                        <div className="flex items-center gap-2">
                          <input
                            value={composerForBlock.text}
                            onChange={(event) =>
                              updateCommentComposerText({
                                blockId: block.id,
                                quote: composerForBlock.quote,
                                parentCommentId: null,
                                nextText: event.target.value,
                              })
                            }
                            onKeyDown={(event) => {
                              if ((event.nativeEvent as KeyboardEvent).isComposing) return;
                              if (event.key !== "Enter") return;
                              event.preventDefault();
                              void submitTopLevelComment(block.id, composerForBlock.quote, composerForBlock.text);
                            }}
                            placeholder="Add a comment..."
                            className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none"
                          />
                          <button
                            className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                            onClick={() =>
                              openCommentFilePicker({
                                key: `top-${block.id}`,
                                blockId: block.id,
                                quote: composerForBlock.quote,
                                parentCommentId: null,
                              })
                            }
                            title="Attach file"
                          >
                            <Paperclip className="h-4 w-4" />
                          </button>
                          <div className="relative" data-comment-menu="1">
                            <button
                              className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                              onClick={() =>
                                setMentionPickerKey((prev) => (prev === `top-${block.id}` ? null : `top-${block.id}`))
                              }
                              title="Mention member"
                            >
                              <AtSign className="h-4 w-4" />
                            </button>
                            {mentionPickerKey === `top-${block.id}` ? (
                              <div className="absolute bottom-[calc(100%+8px)] right-0 z-30 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                {mentionCandidates.length === 0 ? (
                                  <p className="px-2 py-1.5 text-xs text-[var(--muted)]">No members available</p>
                                ) : (
                                  mentionCandidates.map((candidate) => (
                                    <button
                                      key={`top-${block.id}-${candidate.id}`}
                                      className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                      onClick={() =>
                                        insertMentionInComposer({
                                          blockId: block.id,
                                          quote: composerForBlock.quote,
                                          parentCommentId: null,
                                          candidate,
                                        })
                                      }
                                    >
                                      @{candidate.email}
                                    </button>
                                  ))
                                )}
                              </div>
                            ) : null}
                          </div>
                          <button
                            className="rounded-full p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                            onClick={() => void submitTopLevelComment(block.id, composerForBlock.quote, composerForBlock.text)}
                          >
                            <ArrowUpCircle className="h-5 w-5" />
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}

      </div>

      {showCommentRail ? (
        <aside data-comment-panel="1" className="pointer-events-auto mt-6 space-y-3 lg:sticky lg:top-24 lg:mt-0 lg:w-[360px]">
          {commentThreadGroups
            .filter((group) => group.blockId !== PAGE_COMMENT_ANCHOR)
            .map((group) => {
            const composerForBlock = group.composer;
            const hasTopLevelComposer = Boolean(composerForBlock && !composerForBlock.parentCommentId);

            return (
              <div key={`comment-group-${group.blockId}`} className="space-y-2">
                {group.threads.map((thread) => {
                  const replies = repliesByParentId.get(thread.id) ?? [];
                  const replyComposer =
                    commentComposer &&
                    commentComposer.blockId === group.blockId &&
                    commentComposer.parentCommentId === thread.id
                      ? commentComposer
                      : null;
                  const isEditingThread = editingComment?.id === thread.id;
                  const reactions = thread.uiMeta.reactions ?? [];
                  const menuOpen = commentMenuId === thread.id;
                  const reactionPickerOpen = reactionPickerForCommentId === thread.id;

                  return (
                    <div
                      key={thread.id}
                      className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-3 shadow-sm"
                      onClick={(event) => {
                        const target = event.target as HTMLElement;
                        if (target.closest("button,input,textarea,a,select,[data-no-blink='1']")) return;
                        if (thread.anchorBlockId && thread.anchorBlockId !== PAGE_COMMENT_ANCHOR) blinkReferencedBlock(thread.anchorBlockId);
                      }}
                    >
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--selected)] text-xs font-semibold text-[var(--text)]">
                            {(thread.author.email.split("@")[0] ?? "U").slice(0, 2).toUpperCase()}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">{thread.author.email}</p>
                            <p className="text-xs text-[var(--muted)]">{formatCommentTime(thread.createdAt)}</p>
                          </div>
                        </div>
                        <div className="inline-flex items-center gap-1 text-[var(--muted)]" data-comment-menu="1">
                          <div className="relative">
                            <button
                              onClick={() => setReactionPickerForCommentId((prev) => (prev === thread.id ? null : thread.id))}
                              className="rounded p-1 hover:bg-[var(--hover)]"
                              title="Add reaction"
                            >
                              <SmilePlus className="h-4 w-4" />
                            </button>
                            {reactionPickerOpen ? (
                              <div className="absolute right-0 top-[110%] z-30 flex rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                {COMMENT_REACTION_EMOJIS.map((emoji) => (
                                  <button
                                    key={`${thread.id}-${emoji}`}
                                    className="rounded px-1.5 py-1 text-base hover:bg-[var(--hover)]"
                                    onClick={() => {
                                      void toggleCommentReaction(thread, emoji);
                                      setReactionPickerForCommentId(null);
                                    }}
                                  >
                                    {emoji}
                                  </button>
                                ))}
                              </div>
                            ) : null}
                          </div>
                          <button
                            onClick={() => {
                              void resolveComment(thread.id);
                            }}
                            className="rounded p-1 hover:bg-[var(--hover)]"
                            title="Resolve"
                          >
                            <Check className="h-4 w-4" />
                          </button>
                          <div className="relative">
                            <button
                              onClick={() => setCommentMenuId((prev) => (prev === thread.id ? null : thread.id))}
                              className="rounded p-1 hover:bg-[var(--hover)]"
                              title="More"
                            >
                              <Ellipsis className="h-4 w-4" />
                            </button>
                            {menuOpen ? (
                              <div className="absolute right-0 top-[110%] z-30 w-36 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                <button
                                  className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                  onClick={() => {
                                    setEditingComment({ id: thread.id, text: thread.displayContent });
                                    setCommentMenuId(null);
                                  }}
                                >
                                  Edit comment
                                </button>
                                <button
                                  className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                                  onClick={() => {
                                    void resolveComment(thread.id);
                                    setCommentMenuId(null);
                                  }}
                                >
                                  Delete comment
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>

                      {thread.anchorQuote ? (
                        <p className="mb-2 line-clamp-2 rounded bg-[var(--surface)] px-2 py-1 text-xs text-[var(--muted)]" data-no-blink="1">
                          {thread.anchorQuote}
                        </p>
                      ) : null}

                      {isEditingThread ? (
                        <div className="space-y-2">
                          <textarea
                            value={editingComment.text}
                            onChange={(event) =>
                              setEditingComment((prev) => (prev && prev.id === thread.id ? { ...prev, text: event.target.value } : prev))
                            }
                            rows={3}
                            className="w-full resize-none rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm outline-none"
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button className="rounded px-2 py-1 text-xs hover:bg-[var(--hover)]" onClick={() => setEditingComment(null)}>
                              Cancel
                            </button>
                            <button
                              className="rounded bg-[var(--text)] px-2 py-1 text-xs text-[var(--bg)]"
                              onClick={() => void saveEditedComment(thread, editingComment.text)}
                            >
                              Save
                            </button>
                          </div>
                        </div>
                      ) : (
                        renderCommentContent(thread.displayContent, "thread")
                      )}

                      {reactions.length > 0 ? (
                        <div className="mt-2 flex items-center justify-between">
                          <div className="flex flex-wrap items-center gap-1">
                            {reactions.map((reaction) => (
                              <button
                                key={`${thread.id}-${reaction.emoji}`}
                                className="rounded-full border border-[var(--line)] px-2 py-0.5 text-xs hover:bg-[var(--hover)]"
                                onClick={() => void toggleCommentReaction(thread, reaction.emoji)}
                              >
                                {reaction.emoji} {reaction.userIds.length}
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {replies.length > 0 ? (
                        <div className="mt-3 space-y-2 border-t border-[var(--line)] pt-2">
                          {replies.map((reply) => {
                            const isEditingReply = editingComment?.id === reply.id;
                            const replyMenuOpen = commentMenuId === reply.id;
                            return (
                              <div
                                key={reply.id}
                                className="rounded-lg bg-[var(--surface)] px-2 py-1.5"
                                onClick={(event) => {
                                  const target = event.target as HTMLElement;
                                  if (target.closest("button,input,textarea,a,select,[data-no-blink='1']")) return;
                                  if (thread.anchorBlockId && thread.anchorBlockId !== PAGE_COMMENT_ANCHOR) blinkReferencedBlock(thread.anchorBlockId);
                                }}
                              >
                                <div className="mb-1 flex items-center justify-between gap-2">
                                  <div className="min-w-0">
                                    <p className="truncate text-xs text-[var(--muted)]">{reply.author.email}</p>
                                    <p className="text-xs text-[var(--muted)]">{formatCommentTime(reply.createdAt)}</p>
                                  </div>
                                  <div className="relative" data-comment-menu="1">
                                    <button
                                      className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                                      onClick={() => setCommentMenuId((prev) => (prev === reply.id ? null : reply.id))}
                                    >
                                      <Ellipsis className="h-3.5 w-3.5" />
                                    </button>
                                    {replyMenuOpen ? (
                                      <div className="absolute right-0 top-[110%] z-30 w-36 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                        <button
                                          className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                          onClick={() => {
                                            setEditingComment({ id: reply.id, text: reply.displayContent });
                                            setCommentMenuId(null);
                                          }}
                                        >
                                          Edit comment
                                        </button>
                                        <button
                                          className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                                          onClick={() => {
                                            void resolveComment(reply.id);
                                            setCommentMenuId(null);
                                          }}
                                        >
                                          Delete comment
                                        </button>
                                      </div>
                                    ) : null}
                                  </div>
                                </div>

                                {isEditingReply ? (
                                  <div className="space-y-2">
                                    <textarea
                                      value={editingComment.text}
                                      onChange={(event) =>
                                        setEditingComment((prev) =>
                                          prev && prev.id === reply.id ? { ...prev, text: event.target.value } : prev
                                        )
                                      }
                                      rows={2}
                                      className="w-full resize-none rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm outline-none"
                                    />
                                    <div className="flex items-center justify-end gap-2">
                                      <button className="rounded px-2 py-1 text-xs hover:bg-[var(--hover)]" onClick={() => setEditingComment(null)}>
                                        Cancel
                                      </button>
                                      <button
                                        className="rounded bg-[var(--text)] px-2 py-1 text-xs text-[var(--bg)]"
                                        onClick={() =>
                                          void saveEditedComment(
                                            reply,
                                            editingComment && editingComment.id === reply.id ? editingComment.text : reply.displayContent
                                          )
                                        }
                                      >
                                        Save
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  renderCommentContent(reply.displayContent, "reply")
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : null}

                      <div className="mt-3 rounded-xl border border-[var(--line)] px-2 py-1.5">
                        <div className="flex items-center gap-2">
                          <input
                            value={replyComposer?.text ?? ""}
                            onChange={(event) =>
                              updateCommentComposerText({
                                blockId: group.blockId,
                                quote: thread.anchorQuote ?? "",
                                parentCommentId: thread.id,
                                nextText: event.target.value,
                              })
                            }
                            onKeyDown={(event) => {
                              if ((event.nativeEvent as KeyboardEvent).isComposing) return;
                              if (event.key !== "Enter") return;
                              event.preventDefault();
                              void submitReply(group.blockId, thread, replyComposer?.text ?? "");
                            }}
                            placeholder="Reply..."
                            className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none"
                          />
                          <button
                            className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                            onClick={() =>
                              openCommentFilePicker({
                                key: `reply-${thread.id}`,
                                blockId: group.blockId,
                                quote: thread.anchorQuote ?? "",
                                parentCommentId: thread.id,
                              })
                            }
                            title="Attach file"
                          >
                            <Paperclip className="h-4 w-4" />
                          </button>
                          <div className="relative" data-comment-menu="1">
                            <button
                              className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                              onClick={() => setMentionPickerKey((prev) => (prev === `reply-${thread.id}` ? null : `reply-${thread.id}`))}
                              title="Mention member"
                            >
                              <AtSign className="h-4 w-4" />
                            </button>
                            {mentionPickerKey === `reply-${thread.id}` ? (
                              <div className="absolute bottom-[calc(100%+8px)] right-0 z-30 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                                {mentionCandidates.length === 0 ? (
                                  <p className="px-2 py-1.5 text-xs text-[var(--muted)]">No members available</p>
                                ) : (
                                  mentionCandidates.map((candidate) => (
                                    <button
                                      key={`reply-${thread.id}-${candidate.id}`}
                                      className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                      onClick={() =>
                                        insertMentionInComposer({
                                          blockId: group.blockId,
                                          quote: thread.anchorQuote ?? "",
                                          parentCommentId: thread.id,
                                          candidate,
                                        })
                                      }
                                    >
                                      @{candidate.email}
                                    </button>
                                  ))
                                )}
                              </div>
                            ) : null}
                          </div>
                          <button
                            className="rounded-full p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                            onClick={() => void submitReply(group.blockId, thread, replyComposer?.text ?? "")}
                          >
                            <ArrowUpCircle className="h-5 w-5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {hasTopLevelComposer ? (
                  <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 shadow-sm">
                    <div className="flex items-center gap-2">
                      <input
                        value={composerForBlock?.text ?? ""}
                        onChange={(event) =>
                          updateCommentComposerText({
                            blockId: group.blockId,
                            quote: composerForBlock?.quote ?? group.blockQuote,
                            parentCommentId: null,
                            nextText: event.target.value,
                          })
                        }
                        onKeyDown={(event) => {
                          if ((event.nativeEvent as KeyboardEvent).isComposing) return;
                          if (event.key !== "Enter") return;
                          event.preventDefault();
                          void submitTopLevelComment(group.blockId, composerForBlock?.quote ?? group.blockQuote, composerForBlock?.text ?? "");
                        }}
                        placeholder="Add a comment..."
                        className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none"
                      />
                      <button
                        className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                        onClick={() =>
                          openCommentFilePicker({
                            key: `top-${group.blockId}`,
                            blockId: group.blockId,
                            quote: composerForBlock?.quote ?? group.blockQuote,
                            parentCommentId: null,
                          })
                        }
                        title="Attach file"
                      >
                        <Paperclip className="h-4 w-4" />
                      </button>
                      <div className="relative" data-comment-menu="1">
                        <button
                          className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                          onClick={() => setMentionPickerKey((prev) => (prev === `top-${group.blockId}` ? null : `top-${group.blockId}`))}
                          title="Mention member"
                        >
                          <AtSign className="h-4 w-4" />
                        </button>
                        {mentionPickerKey === `top-${group.blockId}` ? (
                          <div className="absolute bottom-[calc(100%+8px)] right-0 z-30 w-64 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                            {mentionCandidates.length === 0 ? (
                              <p className="px-2 py-1.5 text-xs text-[var(--muted)]">No members available</p>
                            ) : (
                              mentionCandidates.map((candidate) => (
                                <button
                                  key={`top-${group.blockId}-${candidate.id}`}
                                  className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                  onClick={() =>
                                    insertMentionInComposer({
                                      blockId: group.blockId,
                                      quote: composerForBlock?.quote ?? group.blockQuote,
                                      parentCommentId: null,
                                      candidate,
                                    })
                                  }
                                >
                                  @{candidate.email}
                                </button>
                              ))
                            )}
                          </div>
                        ) : null}
                      </div>
                      <button
                        className="rounded-full p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                        onClick={() =>
                          void submitTopLevelComment(group.blockId, composerForBlock?.quote ?? group.blockQuote, composerForBlock?.text ?? "")
                        }
                      >
                        <ArrowUpCircle className="h-5 w-5" />
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </aside>
      ) : null}
    </div>
  );
}

type InlineDatabasePayload = {
  id: string;
  pageId: string;
  properties: Array<{
    id: string;
    name: string;
    type: "title" | "text" | "select" | "multi_select" | "checkbox" | "date";
    position: number;
    configJson: unknown;
  }>;
  rows: Array<{
    id: string;
    databaseId: string;
    pageId?: string;
    title: string;
    position: number;
    createdAt: string;
    updatedAt: string;
    cells: Array<{
      id: string;
      rowId: string;
      propertyId: string;
      valueJson: unknown;
    }>;
  }>;
};

function InlineDatabaseEmbed({
  databasePageId,
  title,
  editable = true,
  onRename,
}: {
  databasePageId: string;
  title: string;
  editable?: boolean;
  onRename?: (nextTitle: string) => void | Promise<void>;
}) {
  const [payload, setPayload] = useState<InlineDatabasePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [editableTitle, setEditableTitle] = useState(title || "New database");

  useEffect(() => {
    setEditableTitle(title || "New database");
  }, [title]);

  async function load() {
    setLoading(true);
    try {
      const [databaseRes, rowsRes] = await Promise.all([
        fetch(`/api/databases/${databasePageId}`),
        fetch(`/api/databases/${databasePageId}/rows`),
      ]);
      if (!databaseRes.ok || !rowsRes.ok) return;
      const dbData = await databaseRes.json();
      const rowData = await rowsRes.json();
      const database = dbData?.database;
      const rows = Array.isArray(rowData?.rows) ? rowData.rows : [];
      if (!database || typeof database !== "object") return;
      setPayload({
        id: String(database.id),
        pageId: String(database.pageId),
        properties: Array.isArray(database.properties) ? (database.properties as InlineDatabasePayload["properties"]) : [],
        rows: rows as InlineDatabasePayload["rows"],
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [databasePageId]);

  return (
    <div data-inline-db="1" className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-2">
      <input
        value={editableTitle}
        readOnly={!editable}
        onChange={(event) => setEditableTitle(event.target.value)}
        onBlur={() => {
          if (!editable) return;
          const normalized = editableTitle.trim() || "New database";
          setEditableTitle(normalized);
          void fetch(`/api/pages/${databasePageId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: normalized }),
          }).then(() => {
            window.dispatchEvent(new Event("pages:refresh"));
            if (onRename) return Promise.resolve(onRename(normalized));
            return Promise.resolve();
          });
        }}
        className="mb-2 w-full rounded border border-transparent bg-transparent px-1 py-1 text-sm font-medium text-[var(--muted)] outline-none hover:border-[var(--line)] focus:border-[var(--line)]"
      />
      {loading || !payload ? (
        <p className="px-1 py-2 text-xs text-[var(--muted)]">Loading database…</p>
      ) : (
        <DatabaseTable database={payload} editable={editable} />
      )}
    </div>
  );
}
