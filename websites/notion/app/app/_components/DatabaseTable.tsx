"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpDown,
  Check,
  Columns3,
  Copy,
  Database,
  Eye,
  ExternalLink,
  Filter,
  Group,
  MoreHorizontal,
  Pencil,
  Plus,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { pageIdForDatabaseRow } from "@/lib/database-row-page";

type StoredPropertyType = "title" | "text" | "select" | "multi_select" | "checkbox" | "date";
type DisplayPropertyType = StoredPropertyType | "number" | "person" | "email" | "status";

type PropertyOption = {
  id: string;
  label: string;
  color: string;
  group?: string;
};

type DatabaseProperty = {
  id: string;
  name: string;
  type: StoredPropertyType;
  position: number;
  configJson: unknown;
};

type DatabaseCell = {
  id: string;
  rowId: string;
  propertyId: string;
  valueJson: unknown;
};

type DatabaseRow = {
  id: string;
  databaseId: string;
  pageId?: string;
  title: string;
  position: number;
  createdAt: string;
  updatedAt: string;
  cells: DatabaseCell[];
};

type DatabasePayload = {
  id: string;
  pageId: string;
  properties: DatabaseProperty[];
  rows: DatabaseRow[];
};

type DatabaseViewLayout = "table" | "board";

type DatabaseFilterOperator =
  | "contains"
  | "is"
  | "is_not"
  | "before"
  | "after"
  | "on"
  | "on_or_before"
  | "on_or_after"
  | "is_checked"
  | "is_not_checked"
  | "contains_current_user";

type DatabaseFilterRule = {
  id: string;
  propertyId: string;
  operator: DatabaseFilterOperator;
  value: string;
};

type DatabaseViewState = {
  id: string;
  name: string;
  layout: DatabaseViewLayout;
  hiddenPropertyIds: string[];
  groupByPropertyId: string;
  sortByPropertyId: string;
  sortDirection: "asc" | "desc";
  filters: DatabaseFilterRule[];
};

function viewStorageKey(databaseId: string) {
  return `database:${databaseId}:views`;
}

function defaultView(): DatabaseViewState {
  return {
    id: "view_table",
    name: "Table",
    layout: "table",
    hiddenPropertyIds: [],
    groupByPropertyId: "",
    sortByPropertyId: "",
    sortDirection: "asc",
    filters: [],
  };
}

function makeFilterId() {
  return `filter_${Math.random().toString(36).slice(2, 9)}`;
}

function readViews(databaseId: string): DatabaseViewState[] {
  if (typeof window === "undefined") return [defaultView()];
  const raw = window.localStorage.getItem(viewStorageKey(databaseId));
  if (!raw) return [defaultView()];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return [defaultView()];
    const views: DatabaseViewState[] = parsed
      .map((item): DatabaseViewState => ({
        id: typeof item?.id === "string" && item.id.trim() ? item.id : `view_${Math.random().toString(36).slice(2, 8)}`,
        name: typeof item?.name === "string" && item.name.trim() ? item.name : "View",
        layout: item?.layout === "board" ? "board" : "table",
        hiddenPropertyIds: Array.isArray(item?.hiddenPropertyIds) ? item.hiddenPropertyIds.map((id: unknown) => String(id)) : [],
        groupByPropertyId: typeof item?.groupByPropertyId === "string" ? item.groupByPropertyId : "",
        sortByPropertyId: typeof item?.sortByPropertyId === "string" ? item.sortByPropertyId : "",
        sortDirection: item?.sortDirection === "desc" ? "desc" : "asc",
        filters: Array.isArray(item?.filters)
          ? item.filters
              .map((filter: unknown): DatabaseFilterRule | null => {
                if (!filter || typeof filter !== "object") return null;
                return {
                  id:
                    typeof (filter as { id?: unknown }).id === "string" && String((filter as { id?: string }).id).trim()
                      ? String((filter as { id?: string }).id)
                      : makeFilterId(),
                  propertyId:
                    typeof (filter as { propertyId?: unknown }).propertyId === "string"
                      ? String((filter as { propertyId?: string }).propertyId)
                      : "",
                  operator:
                    typeof (filter as { operator?: unknown }).operator === "string"
                      ? (String((filter as { operator?: string }).operator) as DatabaseFilterOperator)
                      : "contains",
                  value:
                    typeof (filter as { value?: unknown }).value === "string"
                      ? String((filter as { value?: string }).value)
                      : "",
                };
              })
              .filter((filter: DatabaseFilterRule | null): filter is DatabaseFilterRule => Boolean(filter))
          : typeof item?.filterPropertyId === "string" && typeof item?.filterQuery === "string" && item.filterPropertyId.trim()
          ? [
              {
                id: makeFilterId(),
                propertyId: item.filterPropertyId,
                operator: "contains",
                value: item.filterQuery,
              },
            ]
          : [],
      }))
      .filter((item) => item.id.length > 0);
    return views.length > 0 ? views : [defaultView()];
  } catch {
    return [defaultView()];
  }
}

function persistViews(databaseId: string, views: DatabaseViewState[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(viewStorageKey(databaseId), JSON.stringify(views));
}

function normalizeIdList(ids: Iterable<string>): string[] {
  return Array.from(
    new Set(
      Array.from(ids)
        .map((item) => item.trim())
        .filter((item) => item.length > 0)
    )
  ).sort();
}

const PROPERTY_TYPES: Array<{ value: DisplayPropertyType; label: string }> = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "select", label: "Select" },
  { value: "multi_select", label: "Multi-select" },
  { value: "status", label: "Status" },
  { value: "checkbox", label: "Checkbox" },
  { value: "person", label: "Person" },
  { value: "email", label: "Email" },
  { value: "date", label: "Date" },
];

const OPTION_COLORS = ["default", "gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red"];

function optionColorStyle(color: string) {
  switch (color) {
    case "gray":
      return { backgroundColor: "#f1f1ef", color: "#5f5e5a", borderColor: "#e2e2de" };
    case "brown":
      return { backgroundColor: "#f4eeee", color: "#8d5e47", borderColor: "#eadfd8" };
    case "orange":
      return { backgroundColor: "#fbeedd", color: "#b76208", borderColor: "#f4dbbf" };
    case "yellow":
      return { backgroundColor: "#fbf3db", color: "#9a6f24", borderColor: "#f0e2b8" };
    case "green":
      return { backgroundColor: "#edf3ec", color: "#3f7a59", borderColor: "#d7e6d4" };
    case "blue":
      return { backgroundColor: "#e7f3f8", color: "#2e6f95", borderColor: "#cfe3ef" };
    case "purple":
      return { backgroundColor: "#f6f3f8", color: "#7f58a2", borderColor: "#e5dbef" };
    case "pink":
      return { backgroundColor: "#faeff4", color: "#a94a78", borderColor: "#efd8e4" };
    case "red":
      return { backgroundColor: "#fdebec", color: "#be4b48", borderColor: "#f3d3d6" };
    default:
      return { backgroundColor: "#f7f7f6", color: "var(--text)", borderColor: "var(--line)" };
  }
}

function readSubtype(property: DatabaseProperty): string | null {
  if (!property.configJson || typeof property.configJson !== "object") return null;
  const subtype = (property.configJson as { subtype?: unknown }).subtype;
  if (typeof subtype !== "string" || !subtype.trim()) return null;
  return subtype.trim();
}

function displayTypeOf(property: DatabaseProperty): DisplayPropertyType {
  const subtype = readSubtype(property);
  if (property.type === "text" && subtype === "number") return "number";
  if (property.type === "text" && subtype === "email") return "email";
  if (property.type === "multi_select" && subtype === "person") return "person";
  if (property.type === "select" && subtype === "status") return "status";
  return property.type;
}

function normalizeOption(input: unknown): PropertyOption | null {
  if (typeof input === "string") {
    const label = input.trim();
    if (!label) return null;
    return {
      id: `opt_${label.toLowerCase().replace(/\s+/g, "_")}`,
      label,
      color: "default",
    };
  }
  if (!input || typeof input !== "object") return null;
  const source = input as {
    id?: unknown;
    label?: unknown;
    name?: unknown;
    color?: unknown;
    group?: unknown;
  };
  const labelRaw = typeof source.label === "string" ? source.label : typeof source.name === "string" ? source.name : "";
  const label = labelRaw.trim();
  if (!label) return null;
  return {
    id: typeof source.id === "string" && source.id.trim() ? source.id.trim() : `opt_${label.toLowerCase().replace(/\s+/g, "_")}`,
    label,
    color: typeof source.color === "string" && source.color.trim() ? source.color.trim() : "default",
    group: typeof source.group === "string" && source.group.trim() ? source.group.trim() : undefined,
  };
}

function optionsOf(property: DatabaseProperty): PropertyOption[] {
  if (!property.configJson || typeof property.configJson !== "object") return [];
  const raw = (property.configJson as { options?: unknown }).options;
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeOption).filter((item): item is PropertyOption => Boolean(item));
}

function getCellValue(row: DatabaseRow, property: DatabaseProperty): unknown {
  if (property.type === "title") return row.title;
  return row.cells.find((cell) => cell.propertyId === property.id)?.valueJson;
}

function normalizeNumber(input: string) {
  const trimmed = input.trim();
  if (!trimmed) return "";
  const asNumber = Number(trimmed);
  if (!Number.isFinite(asNumber)) return "";
  return asNumber.toString();
}

function valueToComparable(value: unknown, property: DatabaseProperty): number | string {
  const displayType = displayTypeOf(property);
  if (displayType === "number") {
    const numeric = Number(value ?? 0);
    return Number.isFinite(numeric) ? numeric : 0;
  }
  if (displayType === "checkbox") return value ? 1 : 0;
  if (Array.isArray(value)) return value.join(",").toLowerCase();
  if (typeof value === "string") return value.toLowerCase();
  if (value == null) return "";
  return String(value).toLowerCase();
}

function includesFilter(value: unknown, query: string): boolean {
  if (!query.trim()) return true;
  const normalized = query.trim().toLowerCase();
  if (Array.isArray(value)) return value.some((item) => String(item).toLowerCase().includes(normalized));
  if (typeof value === "boolean") return String(value).toLowerCase().includes(normalized);
  if (value == null) return false;
  return String(value).toLowerCase().includes(normalized);
}

function normalizeDateValue(value: unknown) {
  if (typeof value !== "string" || value.trim().length === 0) return null;
  const [year, month, day] = value.split("-").map((part) => Number(part));
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

function defaultOperatorForProperty(property: DatabaseProperty | null): DatabaseFilterOperator {
  const displayType = property ? displayTypeOf(property) : "text";
  if (displayType === "date") return "on";
  if (displayType === "checkbox") return "is_checked";
  if (displayType === "person") return "contains_current_user";
  if (displayType === "select" || displayType === "status") return "is";
  return "contains";
}

function matchesFilterRule(
  value: unknown,
  property: DatabaseProperty,
  rule: DatabaseFilterRule,
  currentUserEmail: string
): boolean {
  const displayType = displayTypeOf(property);
  const normalizedValue = rule.value.trim();

  if (displayType === "checkbox") {
    return rule.operator === "is_not_checked" ? !Boolean(value) : Boolean(value);
  }

  if (displayType === "date") {
    const left = normalizeDateValue(value);
    const right = normalizeDateValue(normalizedValue);
    if (!left || !right) return false;
    if (rule.operator === "before") return left < right;
    if (rule.operator === "after") return left > right;
    if (rule.operator === "on_or_before") return left <= right;
    if (rule.operator === "on_or_after") return left >= right;
    return left === right;
  }

  if (rule.operator === "contains_current_user") {
    if (!currentUserEmail) return false;
    if (Array.isArray(value)) return value.map((item) => String(item).toLowerCase()).includes(currentUserEmail.toLowerCase());
    return String(value ?? "").toLowerCase() === currentUserEmail.toLowerCase();
  }

  if (Array.isArray(value)) {
    const normalizedArray = value.map((item) => String(item).toLowerCase());
    if (rule.operator === "is") return normalizedArray.includes(normalizedValue.toLowerCase());
    if (rule.operator === "is_not") return !normalizedArray.includes(normalizedValue.toLowerCase());
    return normalizedArray.some((item) => item.includes(normalizedValue.toLowerCase()));
  }

  const normalizedCell = String(value ?? "").toLowerCase();
  const normalizedRule = normalizedValue.toLowerCase();
  if (rule.operator === "is") return normalizedCell === normalizedRule;
  if (rule.operator === "is_not") return normalizedCell !== normalizedRule;
  return normalizedCell.includes(normalizedRule);
}

function propertyGlyph(property: DatabaseProperty) {
  const displayType = displayTypeOf(property);
  if (displayType === "title") return "Aa";
  if (displayType === "number") return "#";
  if (displayType === "select") return "◉";
  if (displayType === "multi_select") return "◉◉";
  if (displayType === "status") return "●";
  if (displayType === "checkbox") return "☑";
  if (displayType === "person") return "@";
  if (displayType === "email") return "✉";
  if (displayType === "date") return "🗓";
  return "Aa";
}

export default function DatabaseTable({ database, editable = true }: { database: DatabasePayload; editable?: boolean }) {
  const router = useRouter();
  const [rows, setRows] = useState<DatabaseRow[]>(database.rows);
  const [properties, setProperties] = useState<DatabaseProperty[]>(database.properties);
  const [draggingRowId, setDraggingRowId] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [views, setViews] = useState<DatabaseViewState[]>([defaultView()]);
  const [activeViewId, setActiveViewId] = useState("view_table");
  const [viewCreateMenuOpen, setViewCreateMenuOpen] = useState(false);
  const [viewTabMenu, setViewTabMenu] = useState<{ viewId: string; x: number; y: number } | null>(null);
  const [propertyMenuId, setPropertyMenuId] = useState<string | null>(null);
  const [addPropertyMenuOpen, setAddPropertyMenuOpen] = useState(false);
  const [pendingPropertyType, setPendingPropertyType] = useState<DisplayPropertyType | null>(null);
  const [newPropertyName, setNewPropertyName] = useState("");
  const [addPropertyMenuPosition, setAddPropertyMenuPosition] = useState<{ top: number; left: number; maxHeight: number } | null>(null);
  const [propertyMenuPosition, setPropertyMenuPosition] = useState<{ top: number; left: number; maxHeight: number } | null>(null);
  const [insertRef, setInsertRef] = useState<{ propertyId: string; side: "left" | "right" } | null>(null);
  const [visibilityMenuOpen, setVisibilityMenuOpen] = useState(false);
  const [members, setMembers] = useState<string[]>([]);
  const [currentUserEmail, setCurrentUserEmail] = useState("");
  const [savingPropertyId, setSavingPropertyId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const addPropertyButtonRef = useRef<HTMLButtonElement | null>(null);
  const propertyButtonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const fallbackView = useMemo(() => defaultView(), []);

  const activeView = useMemo(
    () => views.find((view) => view.id === activeViewId) ?? views[0] ?? fallbackView,
    [activeViewId, views, fallbackView]
  );
  const viewName = activeView?.name ?? "Table";
  const hiddenPropertyIds = useMemo(() => new Set(normalizeIdList(activeView.hiddenPropertyIds ?? [])), [activeView.hiddenPropertyIds]);
  const groupByPropertyId = activeView.groupByPropertyId || "";
  const sortByPropertyId = activeView.sortByPropertyId || "";
  const sortDirection: "asc" | "desc" = activeView.sortDirection === "desc" ? "desc" : "asc";
  const filters = Array.isArray(activeView.filters) ? activeView.filters : [];

  useEffect(() => {
    const loadMembers = async () => {
      const response = await fetch(`/api/pages/${database.pageId}/permissions`);
      if (!response.ok) return;
      const data = await response.json();
      const list = Array.isArray(data?.members)
        ? data.members
            .map((item: { user?: { email?: unknown } }) => (typeof item?.user?.email === "string" ? item.user.email : ""))
            .filter((email: string) => email.length > 0)
        : [];
      setMembers(Array.from(new Set(list)));
    };
    void loadMembers();
  }, [database.pageId]);

  useEffect(() => {
    const loadCurrentUser = async () => {
      const response = await fetch("/api/me");
      if (!response.ok) return;
      const data = await response.json();
      const email = typeof data?.user?.email === "string" ? data.user.email : "";
      setCurrentUserEmail(email);
    };
    void loadCurrentUser();
  }, []);

  useEffect(() => {
    const loaded = readViews(database.id);
    setViews(loaded);
    setActiveViewId(loaded[0]?.id ?? "view_table");
  }, [database.id]);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-db-menu='1']")) return;
      setPropertyMenuId(null);
      setPropertyMenuPosition(null);
      setAddPropertyMenuOpen(false);
      setVisibilityMenuOpen(false);
      setViewCreateMenuOpen(false);
      setViewTabMenu(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setPropertyMenuId(null);
      setPropertyMenuPosition(null);
      setAddPropertyMenuOpen(false);
      setVisibilityMenuOpen(false);
      setViewCreateMenuOpen(false);
      setViewTabMenu(null);
      setShowSettings(false);
    };
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  function updateAddPropertyMenuPosition(nextPendingType: DisplayPropertyType | null = pendingPropertyType) {
    const anchor = addPropertyButtonRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const menuWidth = 280;
    const estimatedHeight = nextPendingType ? 230 : 420;
    const margin = 12;
    const availableAbove = rect.top - margin - 6;
    const availableBelow = window.innerHeight - rect.bottom - margin - 6;
    const openAbove = availableBelow < estimatedHeight && availableAbove > availableBelow;
    const rawMaxHeight = openAbove ? availableAbove : availableBelow;
    const maxHeight = Math.max(200, Math.floor(rawMaxHeight));
    const desiredHeight = Math.min(estimatedHeight, maxHeight);
    const left = Math.max(margin, Math.min(window.innerWidth - menuWidth - margin, rect.left));
    const top = openAbove ? Math.max(margin, rect.top - desiredHeight - 6) : rect.bottom + 6;
    setAddPropertyMenuPosition({ top, left, maxHeight });
  }

  function updatePropertyMenuPosition(propertyId: string | null = propertyMenuId) {
    if (!propertyId) return;
    const anchor = propertyButtonRefs.current[propertyId];
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const menuWidth = 360;
    const estimatedHeight = 520;
    const margin = 12;
    const availableAbove = rect.top - margin - 6;
    const availableBelow = window.innerHeight - rect.bottom - margin - 6;
    const openAbove = availableBelow < estimatedHeight && availableAbove > availableBelow;
    const rawMaxHeight = openAbove ? availableAbove : availableBelow;
    const maxHeight = Math.max(240, Math.floor(rawMaxHeight));
    const desiredHeight = Math.min(estimatedHeight, maxHeight);
    const left = Math.max(margin, Math.min(window.innerWidth - menuWidth - margin, rect.left));
    const top = openAbove ? Math.max(margin, rect.top - desiredHeight - 6) : rect.bottom + 6;
    setPropertyMenuPosition({ top, left, maxHeight });
  }

  useEffect(() => {
    if (!addPropertyMenuOpen) return;
    const reposition = () => updateAddPropertyMenuPosition();
    reposition();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [addPropertyMenuOpen, pendingPropertyType]);

  useEffect(() => {
    if (!propertyMenuId) return;
    const reposition = () => updatePropertyMenuPosition(propertyMenuId);
    reposition();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [propertyMenuId]);

  const sortedProperties = useMemo(() => [...properties].sort((a, b) => a.position - b.position), [properties]);
  const visibleProperties = useMemo(
    () => sortedProperties.filter((property) => !hiddenPropertyIds.has(property.id)),
    [sortedProperties, hiddenPropertyIds]
  );

  const processedRows = useMemo(() => {
    let nextRows = [...rows].sort((a, b) => a.position - b.position);

    const activeFilters = filters.filter((filter) => filter.propertyId.trim().length > 0);
    if (activeFilters.length > 0) {
      nextRows = nextRows.filter((row) =>
        activeFilters.every((filter) => {
          const filterProperty = properties.find((item) => item.id === filter.propertyId);
          if (!filterProperty) return true;
          const operatorNeedsValue = !["contains_current_user", "is_checked", "is_not_checked"].includes(filter.operator);
          if (operatorNeedsValue && filter.value.trim().length === 0) return true;
          return matchesFilterRule(getCellValue(row, filterProperty), filterProperty, filter, currentUserEmail);
        })
      );
    }

    if (sortByPropertyId) {
      const sortProperty = properties.find((item) => item.id === sortByPropertyId);
      if (sortProperty) {
        nextRows = nextRows.sort((a, b) => {
          const va = valueToComparable(getCellValue(a, sortProperty), sortProperty);
          const vb = valueToComparable(getCellValue(b, sortProperty), sortProperty);
          if (va < vb) return sortDirection === "asc" ? -1 : 1;
          if (va > vb) return sortDirection === "asc" ? 1 : -1;
          return 0;
        });
      }
    }

    return nextRows;
  }, [rows, properties, filters, currentUserEmail, sortByPropertyId, sortDirection]);

  const groupedRows = useMemo(() => {
    if (!groupByPropertyId) {
      return [{ key: "All", rows: processedRows }];
    }
    const groupProperty = properties.find((item) => item.id === groupByPropertyId);
    if (!groupProperty) return [{ key: "All", rows: processedRows }];
    const map = new Map<string, DatabaseRow[]>();
    for (const row of processedRows) {
      const value = getCellValue(row, groupProperty);
      const key = Array.isArray(value) ? value.join(", ") : value == null || value === "" ? "Empty" : String(value);
      const list = map.get(key) ?? [];
      list.push(row);
      map.set(key, list);
    }
    return Array.from(map.entries()).map(([key, value]) => ({ key, rows: value }));
  }, [groupByPropertyId, properties, processedRows]);

  async function refreshDatabase() {
    const [databaseRes, rowsRes] = await Promise.all([fetch(`/api/databases/${database.id}`), fetch(`/api/databases/${database.id}/rows`)]);
    if (!databaseRes.ok || !rowsRes.ok) return;
    const databaseData = await databaseRes.json();
    const rowsData = await rowsRes.json();
    const nextProperties = Array.isArray(databaseData?.database?.properties)
      ? (databaseData.database.properties as DatabaseProperty[])
      : [];
    const nextRows = Array.isArray(rowsData?.rows) ? (rowsData.rows as DatabaseRow[]) : [];
    setProperties(nextProperties);
    setRows(nextRows);
  }

  async function patchDatabase(payload: Record<string, unknown>) {
    const response = await fetch(`/api/databases/${database.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response;
  }

  async function addRow() {
    if (!editable) return;
    const response = await fetch(`/api/databases/${database.id}/rows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New page" }),
    });
    if (!response.ok) return;
    const data = await response.json();
    setRows((prev) => [...prev, data.row as DatabaseRow]);
  }

  async function updateRowTitle(rowId: string, title: string) {
    if (!editable) return;
    setRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, title } : row)));
    const response = await fetch(`/api/databases/${database.id}/rows/${rowId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) {
      await refreshDatabase();
    }
  }

  async function updateCell(rowId: string, propertyId: string, value: unknown) {
    if (!editable) return;
    setRows((prev) =>
      prev.map((row) => {
        if (row.id !== rowId) return row;
        const existing = row.cells.find((cell) => cell.propertyId === propertyId);
        if (existing) {
          return {
            ...row,
            cells: row.cells.map((cell) => (cell.propertyId === propertyId ? { ...cell, valueJson: value } : cell)),
          };
        }
        return {
          ...row,
          cells: [...row.cells, { id: `temp_${propertyId}_${rowId}`, rowId, propertyId, valueJson: value }],
        };
      })
    );

    const response = await fetch(`/api/databases/${database.id}/cells`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rowId, propertyId, value }),
    });
    if (!response.ok) {
      await refreshDatabase();
    }
  }

  async function moveRow(rowId: string, targetIndex: number) {
    if (!editable) return;
    const sourceIndex = processedRows.findIndex((row) => row.id === rowId);
    if (sourceIndex === -1) return;
    const clamped = Math.max(0, Math.min(processedRows.length - 1, targetIndex));
    if (sourceIndex === clamped) return;

    const reordered = [...processedRows];
    const [moved] = reordered.splice(sourceIndex, 1);
    reordered.splice(clamped, 0, moved);
    setRows(reordered.map((row, index) => ({ ...row, position: index })));

    const response = await fetch(`/api/databases/${database.id}/rows/${rowId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetIndex: clamped }),
    });
    if (!response.ok) {
      await refreshDatabase();
    }
  }

  async function applyPropertyOptions(property: DatabaseProperty, nextOptions: PropertyOption[]) {
    if (!editable) return;
    setSavingPropertyId(property.id);
    try {
      const response = await patchDatabase({
        action: "update_property",
        propertyId: property.id,
        options: nextOptions,
      });
      if (!response.ok) return;
      await refreshDatabase();
    } finally {
      setSavingPropertyId(null);
    }
  }

  async function ensureOption(property: DatabaseProperty, label: string, group?: string) {
    const normalized = label.trim();
    if (!normalized) return;
    const current = optionsOf(property);
    if (current.some((item) => item.label.toLowerCase() === normalized.toLowerCase())) return;
    const isStatus = displayTypeOf(property) === "status";
    const nextOptions = [
      ...current,
      {
        id: `opt_${Date.now()}`,
        label: normalized,
        color: "default",
        group: isStatus ? group || "To-do" : undefined,
      },
    ];
    await applyPropertyOptions(property, nextOptions);
  }

  async function updateOptionColor(property: DatabaseProperty, optionId: string, color: string) {
    const next = optionsOf(property).map((item) => (item.id === optionId ? { ...item, color } : item));
    await applyPropertyOptions(property, next);
  }

  async function updateOptionGroup(property: DatabaseProperty, optionId: string, group: string) {
    const next = optionsOf(property).map((item) => (item.id === optionId ? { ...item, group } : item));
    await applyPropertyOptions(property, next);
  }

  async function deleteOptionFromProperty(property: DatabaseProperty, option: PropertyOption) {
    const nextOptions = optionsOf(property).filter((item) => item.id !== option.id);
    await applyPropertyOptions(property, nextOptions);

    const valueToRemove = option.label;
    const affectedRows = rows.filter((row) => {
      const raw = getCellValue(row, property);
      if (typeof raw === "string") return raw === valueToRemove;
      if (Array.isArray(raw)) return raw.map((item) => String(item)).includes(valueToRemove);
      return false;
    });

    await Promise.all(
      affectedRows.map(async (row) => {
        const raw = getCellValue(row, property);
        if (typeof raw === "string") {
          await updateCell(row.id, property.id, "");
          return;
        }
        if (Array.isArray(raw)) {
          const next = raw.map((item) => String(item)).filter((item) => item !== valueToRemove);
          await updateCell(row.id, property.id, next);
        }
      })
    );
  }

  function openRowPage(row: DatabaseRow) {
    const targetPageId = row.pageId ?? pageIdForDatabaseRow(row.id);
    router.push(`/app/page/${targetPageId}`);
  }

  function addView(layout: DatabaseViewLayout) {
    const nextView: DatabaseViewState = {
      ...defaultView(),
      id: `view_${Math.random().toString(36).slice(2, 9)}`,
      name: layout === "board" ? "Board" : "Table",
      layout,
    };
    setViews((prev) => {
      const next = [...prev, nextView];
      persistViews(database.id, next);
      return next;
    });
    setActiveViewId(nextView.id);
  }

  function duplicateView(viewId: string) {
    const source = views.find((v) => v.id === viewId);
    if (!source) return;
    const nextView: DatabaseViewState = {
      ...JSON.parse(JSON.stringify(source)),
      id: `view_${Math.random().toString(36).slice(2, 9)}`,
      name: `${source.name} (copy)`,
    };
    setViews((prev) => {
      const next = [...prev, nextView];
      persistViews(database.id, next);
      return next;
    });
    setActiveViewId(nextView.id);
  }

  function deleteView(viewId: string) {
    if (views.length <= 1) return;
    setViews((prev) => {
      const next = prev.filter((v) => v.id !== viewId);
      persistViews(database.id, next);
      if (activeViewId === viewId) {
        setActiveViewId(next[0]?.id ?? "view_table");
      }
      return next;
    });
  }

  function switchToLayoutView(layout: DatabaseViewLayout) {
    if (activeView.layout === layout) return;
    updateActiveView({ layout });
  }

  function updateActiveView(patch: Partial<DatabaseViewState>) {
    setViews((prev) => {
      const targetIndex = prev.findIndex((view) => view.id === activeViewId);
      if (targetIndex === -1) return prev;
      const current = prev[targetIndex];
      const nextView: DatabaseViewState = {
        ...current,
        ...patch,
        hiddenPropertyIds:
          patch.hiddenPropertyIds !== undefined
            ? normalizeIdList(patch.hiddenPropertyIds)
            : normalizeIdList(current.hiddenPropertyIds ?? []),
      };
      const changed =
        current.name !== nextView.name ||
        current.layout !== nextView.layout ||
        current.groupByPropertyId !== nextView.groupByPropertyId ||
        current.sortByPropertyId !== nextView.sortByPropertyId ||
        current.sortDirection !== nextView.sortDirection ||
        JSON.stringify(current.filters ?? []) !== JSON.stringify(nextView.filters ?? []) ||
        JSON.stringify(normalizeIdList(current.hiddenPropertyIds ?? [])) !== JSON.stringify(nextView.hiddenPropertyIds);
      if (!changed) return prev;

      const next = [...prev];
      next[targetIndex] = nextView;
      persistViews(database.id, next);
      return next;
    });
  }

  function addFilterRule() {
    const firstProperty = sortedProperties.find((property) => property.type !== "title") ?? sortedProperties[0] ?? null;
    updateActiveView({
      filters: [
        ...(activeView.filters ?? []),
        {
          id: makeFilterId(),
          propertyId: firstProperty?.id ?? "",
          operator: defaultOperatorForProperty(firstProperty),
          value: "",
        },
      ],
    });
  }

  function updateFilterRule(filterId: string, patch: Partial<DatabaseFilterRule>) {
    const nextFilters = (activeView.filters ?? []).map((filter) => {
      if (filter.id !== filterId) return filter;
      const nextProperty =
        patch.propertyId !== undefined
          ? sortedProperties.find((property) => property.id === patch.propertyId) ?? null
          : sortedProperties.find((property) => property.id === filter.propertyId) ?? null;
      const nextOperator =
        patch.propertyId !== undefined && patch.operator === undefined
          ? defaultOperatorForProperty(nextProperty)
          : patch.operator ?? filter.operator;
      const nextValue =
        ["contains_current_user", "is_checked", "is_not_checked"].includes(nextOperator)
          ? ""
          : patch.value ?? filter.value;
      return {
        ...filter,
        ...patch,
        operator: nextOperator,
        value: nextValue,
      };
    });
    updateActiveView({ filters: nextFilters });
  }

  function removeFilterRule(filterId: string) {
    updateActiveView({
      filters: (activeView.filters ?? []).filter((filter) => filter.id !== filterId),
    });
  }

  async function addProperty(type: DisplayPropertyType, customName?: string, target?: { propertyId: string; side: "left" | "right" }) {
    if (!editable) return;
    const name = customName?.trim() || PROPERTY_TYPES.find((item) => item.value === type)?.label || "Property";
    const response = await patchDatabase({
      action: target ? "insert_property" : "add_property",
      type,
      name,
      referencePropertyId: target?.propertyId,
      side: target?.side,
    });
    if (!response.ok) return;
    await refreshDatabase();
  }

  async function updateProperty(propertyId: string, patch: { name?: string; type?: DisplayPropertyType; options?: PropertyOption[] }) {
    if (!editable) return;
    const response = await patchDatabase({
      action: "update_property",
      propertyId,
      ...patch,
    });
    if (!response.ok) return;
    await refreshDatabase();
  }

  async function duplicateProperty(propertyId: string) {
    if (!editable) return;
    const response = await patchDatabase({
      action: "duplicate_property",
      propertyId,
    });
    if (!response.ok) return;
    await refreshDatabase();
  }

  async function deleteProperty(propertyId: string) {
    if (!editable) return;
    const response = await patchDatabase({
      action: "delete_property",
      propertyId,
    });
    if (!response.ok) return;
    updateActiveView({
      hiddenPropertyIds: activeView.hiddenPropertyIds.filter((id) => id !== propertyId),
    });
    await refreshDatabase();
  }

  const editingProperty = propertyMenuId ? sortedProperties.find((item) => item.id === propertyMenuId) ?? null : null;

  return (
    <div ref={rootRef} className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-1">
          {views.map((view) => (
            <div key={view.id} className="relative">
              <button
                onClick={() => {
                  if (view.id === activeViewId) {
                    setViewTabMenu((prev) => prev?.viewId === view.id ? null : { viewId: view.id, x: 0, y: 0 });
                  } else {
                    setActiveViewId(view.id);
                  }
                }}
                className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium ${
                  view.id === activeViewId ? "bg-[var(--hover)]" : "hover:bg-[var(--hover)]"
                }`}
              >
                <Database className="h-4 w-4" />
                <span>{view.name}</span>
              </button>
              {viewTabMenu?.viewId === view.id ? (
                <div className="absolute left-0 top-[calc(100%+4px)] z-[80] w-[200px] rounded-lg border border-[var(--line)] bg-[var(--panel)] p-1 shadow-xl" data-db-menu="1">
                  <button
                    onClick={() => { setViewTabMenu(null); setShowSettings(true); }}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                  >
                    <Pencil className="h-4 w-4" />
                    Rename
                  </button>
                  <button
                    onClick={() => { setViewTabMenu(null); setShowSettings(true); }}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                  >
                    <SlidersHorizontal className="h-4 w-4" />
                    Edit view
                  </button>
                  <div className="my-1 border-t border-[var(--line)]" />
                  <button
                    onClick={() => { setViewTabMenu(null); duplicateView(view.id); }}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                  >
                    <Copy className="h-4 w-4" />
                    Duplicate view
                  </button>
                  <button
                    onClick={() => { setViewTabMenu(null); deleteView(view.id); }}
                    disabled={views.length <= 1}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-[#b42318] hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-40 disabled:text-[var(--muted)]"
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete view
                  </button>
                </div>
              ) : null}
            </div>
          ))}
          <div className="relative" data-db-menu="1">
            <button
              onClick={() => setViewCreateMenuOpen((prev) => !prev)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] bg-[var(--panel)] hover:bg-[var(--hover)]"
              title="Create view"
            >
              <Plus className="h-4 w-4" />
            </button>
            {viewCreateMenuOpen ? (
              <div className="absolute left-0 top-[calc(100%+8px)] z-[80] w-[180px] rounded-md border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                <button
                  onClick={() => {
                    setViewCreateMenuOpen(false);
                    addView("table");
                  }}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                >
                  Table view
                </button>
                <button
                  onClick={() => {
                    setViewCreateMenuOpen(false);
                    addView("board");
                  }}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                >
                  Board view
                </button>
              </div>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings((prev) => !prev)}
            disabled={!editable}
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-[var(--line)] bg-[var(--panel)] hover:bg-[var(--hover)]"
            title="View settings"
          >
            <SlidersHorizontal className="h-4 w-4" />
          </button>
          <button
            onClick={addRow}
            disabled={!editable}
            className="inline-flex items-center gap-2 rounded-md bg-[var(--blue)] px-4 py-2 text-sm font-semibold text-white hover:brightness-95 disabled:cursor-default disabled:opacity-60"
          >
            <Plus className="h-4 w-4" />
            New
          </button>
        </div>
      </div>

      {activeView.layout === "board" ? (
        <div className="grid gap-3 overflow-auto rounded-xl border border-[var(--line)] bg-[var(--panel)] p-3 shadow-[0_1px_0_rgba(15,15,15,0.02)] md:grid-cols-3">
          {groupedRows.map((grouped) => (
            <div key={`board-${grouped.key}`} className="min-w-0 rounded-lg border border-[var(--line)] bg-[var(--surface)]">
              <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2">
                <p className="truncate text-sm font-semibold">{grouped.key}</p>
                <span className="rounded bg-[var(--panel)] px-2 py-0.5 text-xs text-[var(--muted)]">{grouped.rows.length}</span>
              </div>
              <div className="space-y-2 p-2">
                {grouped.rows.map((row) => (
                  <button
                    key={`board-row-${row.id}`}
                    onClick={() => openRowPage(row)}
                    className="w-full rounded-md border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-left hover:bg-[var(--hover)]"
                  >
                    <p className="truncate text-sm font-medium">{row.title || "Untitled"}</p>
                    <div className="mt-1 space-y-1">
                      {visibleProperties
                        .filter((property) => property.type !== "title")
                        .slice(0, 3)
                        .map((property) => {
                          const value = getCellValue(row, property);
                          const text = Array.isArray(value) ? value.join(", ") : value == null || value === "" ? "Empty" : String(value);
                          return (
                            <p key={`board-cell-${row.id}-${property.id}`} className="truncate text-xs text-[var(--muted)]">
                              {property.name}: {text}
                            </p>
                          );
                        })}
                    </div>
                  </button>
                ))}
                <button
                  onClick={addRow}
                  disabled={!editable}
                  className="w-full rounded-md border border-dashed border-[var(--line)] px-3 py-2 text-left text-sm text-[var(--muted)] hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-60"
                >
                  + New
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className={`overflow-visible rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_1px_0_rgba(15,15,15,0.02)] ${activeView.layout === "board" ? "hidden" : ""}`}>
        <div className="overflow-x-auto">
        {groupedRows.map((grouped, groupedIndex) => {
          const interactiveHeader = groupedIndex === 0 && editable;
          return (
          <div key={grouped.key} className="border-b border-[var(--line)] last:border-b-0">
            {groupByPropertyId ? (
              <div className="flex items-center justify-between bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--muted)]">
                <span>{grouped.key}</span>
                <span>{grouped.rows.length}</span>
              </div>
            ) : null}
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--line)] bg-[var(--surface)]">
                  {visibleProperties.map((property) => {
                    const displayType = displayTypeOf(property);
                    return (
                      <th key={property.id} className="relative px-3 py-2 text-left text-sm font-semibold tracking-normal text-[var(--muted)]">
                        {interactiveHeader ? (
                          <button
                            ref={(node) => {
                              propertyButtonRefs.current[property.id] = node;
                            }}
                            onClick={() => {
                              const next = propertyMenuId === property.id ? null : property.id;
                              setPropertyMenuId(next);
                              if (!next) {
                                setPropertyMenuPosition(null);
                                return;
                              }
                              window.requestAnimationFrame(() => updatePropertyMenuPosition(property.id));
                            }}
                            className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-[var(--hover)]"
                            data-db-menu="1"
                          >
                            <span className="text-[11px] uppercase text-[var(--muted)]">{propertyGlyph(property)}</span>
                            <span>{property.name}</span>
                          </button>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-1 py-0.5">
                            <span className="text-[11px] uppercase text-[var(--muted)]">{propertyGlyph(property)}</span>
                            <span>{property.name}</span>
                          </span>
                        )}
                        {interactiveHeader && propertyMenuId === property.id ? (
                          <div
                            className="fixed z-[90] w-[360px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl"
                            style={{
                              top: propertyMenuPosition?.top ?? 80,
                              left: propertyMenuPosition?.left ?? 40,
                              maxHeight: propertyMenuPosition?.maxHeight ?? 520,
                              overflowY: "auto",
                            }}
                            data-db-menu="1"
                          >
                            <input
                              value={editingProperty?.name ?? ""}
                              onChange={(event) => {
                                const next = event.target.value;
                                setProperties((prev) =>
                                  prev.map((item) => (item.id === property.id ? { ...item, name: next } : item))
                                );
                              }}
                              onBlur={() => {
                                const next = properties.find((item) => item.id === property.id)?.name ?? property.name;
                                void updateProperty(property.id, { name: next });
                              }}
                              className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
                            />
                            <select
                              value={displayType}
                              onChange={(event) => {
                                void updateProperty(property.id, { type: event.target.value as DisplayPropertyType });
                              }}
                              className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
                            >
                              {PROPERTY_TYPES.filter((item) => item.value !== "title").map((item) => (
                                <option key={`${property.id}-${item.value}`} value={item.value}>
                                  {item.label}
                                </option>
                              ))}
                            </select>

                            {(displayType === "select" || displayType === "multi_select" || displayType === "status") && (
                              <div className="mb-2 rounded border border-[var(--line)] p-2">
                                <p className="mb-1 text-xs font-medium text-[var(--muted)]">Options</p>
                                <div className="space-y-1">
                                  {optionsOf(property).map((option) => (
                                    <div key={option.id} className="flex items-center gap-1">
                                      <input
                                        value={option.label}
                                        onChange={(event) => {
                                          const next = optionsOf(property).map((item) =>
                                            item.id === option.id ? { ...item, label: event.target.value } : item
                                          );
                                          void applyPropertyOptions(property, next);
                                        }}
                                        className="min-w-0 flex-1 rounded border border-[var(--line)] bg-[var(--panel)] px-1.5 py-1 text-xs"
                                      />
                                      <select
                                        value={option.color}
                                        onChange={(event) => {
                                          const next = optionsOf(property).map((item) =>
                                            item.id === option.id ? { ...item, color: event.target.value } : item
                                          );
                                          void applyPropertyOptions(property, next);
                                        }}
                                        className="rounded border border-[var(--line)] bg-[var(--panel)] px-1 py-1 text-xs"
                                      >
                                        {OPTION_COLORS.map((color) => (
                                          <option key={`${option.id}-${color}`} value={color}>
                                            {color}
                                          </option>
                                        ))}
                                      </select>
                                      <button
                                        className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                                        onClick={() => {
                                          const next = optionsOf(property).filter((item) => item.id !== option.id);
                                          void applyPropertyOptions(property, next);
                                        }}
                                      >
                                        <Trash2 className="h-3.5 w-3.5" />
                                      </button>
                                    </div>
                                  ))}
                                </div>
                                <button
                                  className="mt-2 rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]"
                                  onClick={() => {
                                    const next = [...optionsOf(property), { id: `opt_${Date.now()}`, label: "Option", color: "default" }];
                                    void applyPropertyOptions(property, next);
                                  }}
                                  disabled={savingPropertyId === property.id}
                                >
                                  + Add option
                                </button>
                              </div>
                            )}

                            <div className="space-y-1">
                              <button
                                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                onClick={() => {
                                  setInsertRef({ propertyId: property.id, side: "left" });
                                  setPendingPropertyType("text");
                                  setAddPropertyMenuOpen(true);
                                  setPropertyMenuId(null);
                                }}
                              >
                                <Columns3 className="h-3.5 w-3.5" />
                                Insert left
                              </button>
                              <button
                                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                onClick={() => {
                                  setInsertRef({ propertyId: property.id, side: "right" });
                                  setPendingPropertyType("text");
                                  setAddPropertyMenuOpen(true);
                                  setPropertyMenuId(null);
                                }}
                              >
                                <Columns3 className="h-3.5 w-3.5" />
                                Insert right
                              </button>
                              <button
                                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                onClick={() => {
                                  void duplicateProperty(property.id);
                                  setPropertyMenuId(null);
                                }}
                              >
                                <Copy className="h-3.5 w-3.5" />
                                Duplicate property
                              </button>
                              <button
                                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-[var(--hover)]"
                                onClick={() => {
                                  updateActiveView({
                                    hiddenPropertyIds: [...new Set([...activeView.hiddenPropertyIds, property.id])],
                                  });
                                  setPropertyMenuId(null);
                                }}
                              >
                                <Eye className="h-3.5 w-3.5" />
                                Hide column
                              </button>
                              <button
                                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                                onClick={() => {
                                  void deleteProperty(property.id);
                                  setPropertyMenuId(null);
                                }}
                                disabled={property.type === "title"}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                Delete property
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </th>
                    );
                  })}
                  <th className="px-3 py-2 text-left">
                    {interactiveHeader ? (
                      <div className="relative inline-block" data-db-menu="1">
                        <button
                          ref={addPropertyButtonRef}
                          onClick={() => {
                            const next = !addPropertyMenuOpen;
                            if (!next) {
                              setAddPropertyMenuOpen(false);
                              setPendingPropertyType(null);
                              setInsertRef(null);
                              return;
                            }
                            setPropertyMenuId(null);
                            setPropertyMenuPosition(null);
                            setPendingPropertyType(null);
                            setInsertRef(null);
                            setAddPropertyMenuOpen(true);
                            window.requestAnimationFrame(() => updateAddPropertyMenuPosition(null));
                          }}
                          className="inline-flex items-center gap-1 rounded px-1 py-1 text-sm text-[var(--muted)] hover:bg-[var(--hover)]"
                        >
                          <Plus className="h-4 w-4" />
                          Add property
                        </button>

                        {addPropertyMenuOpen ? (
                          <div
                            className="fixed z-[90] w-[280px] rounded-md border border-[var(--line)] bg-[var(--panel)] p-2 shadow-lg"
                            style={{
                              top: addPropertyMenuPosition?.top ?? 80,
                              left: addPropertyMenuPosition?.left ?? 40,
                              maxHeight: addPropertyMenuPosition?.maxHeight ?? 420,
                              overflowY: "auto",
                            }}
                            data-db-menu="1"
                          >
                          {!pendingPropertyType ? (
                            <div className="space-y-1">
                              <p className="px-1 pb-1 text-xs font-medium text-[var(--muted)]">Property type</p>
                              {PROPERTY_TYPES.map((item) => (
                                <button
                                  key={`add-type-${item.value}`}
                                  className="flex w-full items-center rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)]"
                                  onClick={() => {
                                    setPendingPropertyType(item.value);
                                    setNewPropertyName(item.label);
                                    window.requestAnimationFrame(() => updateAddPropertyMenuPosition(item.value));
                                  }}
                                >
                                  {item.label}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <div className="space-y-2">
                              <p className="text-xs text-[var(--muted)]">
                                Type: <span className="font-medium">{PROPERTY_TYPES.find((item) => item.value === pendingPropertyType)?.label}</span>
                              </p>
                              <input
                                value={newPropertyName}
                                onChange={(event) => setNewPropertyName(event.target.value)}
                                placeholder="Property name"
                                className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
                              />
                              <div className="flex justify-end gap-2">
                                <button
                                  onClick={() => {
                                    setPendingPropertyType(null);
                                    setNewPropertyName("");
                                    window.requestAnimationFrame(() => updateAddPropertyMenuPosition(null));
                                  }}
                                  className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]"
                                >
                                  Back
                                </button>
                                <button
                                  onClick={async () => {
                                    if (!pendingPropertyType) return;
                                    await addProperty(pendingPropertyType, newPropertyName, insertRef ?? undefined);
                                    setAddPropertyMenuOpen(false);
                                    setPendingPropertyType(null);
                                    setNewPropertyName("");
                                    setInsertRef(null);
                                  }}
                                  className="rounded border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]"
                                >
                                  Create
                                </button>
                              </div>
                            </div>
                          )}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </th>
                </tr>
              </thead>
              <tbody>
                {grouped.rows.map((row) => (
                  <tr
                    key={row.id}
                    draggable={!groupByPropertyId && editable}
                    onDoubleClick={(event) => {
                      const target = event.target as HTMLElement;
                      if (target.closest("input,textarea,button,select,a")) return;
                      openRowPage(row);
                    }}
                    onDragStart={() => {
                      if (!editable) return;
                      setDraggingRowId(row.id);
                    }}
                    onDragEnd={() => {
                      if (!editable) return;
                      setDraggingRowId(null);
                    }}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (!draggingRowId || draggingRowId === row.id || groupByPropertyId) return;
                      const targetIndex = processedRows.findIndex((candidate) => candidate.id === row.id);
                      if (targetIndex >= 0) {
                        void moveRow(draggingRowId, targetIndex);
                      }
                    }}
                    className="border-b border-[var(--line)] hover:bg-[var(--hover)]"
                  >
                    {visibleProperties.map((property) => (
                      <td key={property.id} className="px-3 py-2 align-top">
                        <CellEditor
                          row={row}
                          property={property}
                          memberEmails={members}
                          updateRowTitle={updateRowTitle}
                  updateCell={updateCell}
                  ensureOption={ensureOption}
                  updateOptionColor={updateOptionColor}
                  updateOptionGroup={updateOptionGroup}
                  deleteOptionFromProperty={deleteOptionFromProperty}
                          openRowPage={openRowPage}
                          readOnly={!editable}
                />
                      </td>
                    ))}
                    <td className="px-3 py-2" />
                  </tr>
                ))}
                {!groupByPropertyId ? (
                  <tr>
                    <td colSpan={visibleProperties.length + 1} className="px-3 py-2">
                      <button onClick={addRow} disabled={!editable} className="inline-flex items-center gap-2 text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-60">
                        <Plus className="h-4 w-4" />
                        New page
                      </button>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        );})}
        </div>
      </div>

      {showSettings ? (
        <div className="fixed inset-0 z-[70] flex justify-end bg-black/20 p-6" data-db-menu="1" onClick={(e) => { if (e.target === e.currentTarget) setShowSettings(false); }}>
          <aside className="h-fit w-[420px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-2xl font-semibold">View settings</p>
              <button onClick={() => setShowSettings(false)} className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mb-3 flex items-center gap-2 rounded-md border border-[var(--line)] px-3 py-2">
              <Database className="h-4 w-4 text-[var(--muted)]" />
              <input
                value={viewName}
                onChange={(event) => updateActiveView({ name: event.target.value })}
                onBlur={(event) => { if (!event.target.value.trim()) updateActiveView({ name: "View" }); }}
                className="w-full border-0 bg-transparent outline-none"
                placeholder="View name"
              />
            </div>

            <div className="space-y-2">
              <div className="rounded-md border border-[var(--line)] p-2">
                <p className="mb-1 inline-flex items-center gap-2 text-sm">
                  <Database className="h-4 w-4 text-[var(--muted)]" />
                  Layout
                </p>
                <select
                  value={activeView.layout}
                  onChange={(event) => switchToLayoutView(event.target.value === "board" ? "board" : "table")}
                  className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                >
                  <option value="table">Table</option>
                  <option value="board">Board</option>
                </select>
              </div>
              <div className="rounded-md border border-[var(--line)] p-2">
                <button
                  onClick={() => setVisibilityMenuOpen((prev) => !prev)}
                  className="flex w-full items-center justify-between rounded px-1 py-1.5 text-left hover:bg-[var(--hover)]"
                >
                  <span className="inline-flex items-center gap-2">
                    <Eye className="h-4 w-4 text-[var(--muted)]" />
                    <span>Property visibility</span>
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    {visibleProperties.length}/{sortedProperties.length}
                  </span>
                </button>
                {visibilityMenuOpen ? (
                  <div className="mt-2 max-h-44 space-y-1 overflow-y-auto rounded border border-[var(--line)] p-2">
                    {sortedProperties.map((property) => {
                      const checked = !hiddenPropertyIds.has(property.id);
                      return (
                        <label key={`visibility-${property.id}`} className="flex items-center justify-between gap-2 rounded px-1 py-1 text-sm hover:bg-[var(--hover)]">
                          <span className="truncate">{property.name}</span>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) => {
                              const next = new Set(activeView.hiddenPropertyIds);
                              if (event.target.checked) next.delete(property.id);
                              else next.add(property.id);
                              updateActiveView({ hiddenPropertyIds: [...next] });
                            }}
                          />
                        </label>
                      );
                    })}
                  </div>
                ) : null}
              </div>

              <div className="rounded-md border border-[var(--line)] p-2">
                <p className="mb-1 inline-flex items-center gap-2 text-sm">
                  <Filter className="h-4 w-4 text-[var(--muted)]" />
                  Filter
                </p>
                <div className="space-y-2">
                  {filters.length === 0 ? <p className="text-sm text-[var(--muted)]">No filters applied</p> : null}
                  {filters.map((filter) => {
                    const filterProperty = sortedProperties.find((property) => property.id === filter.propertyId) ?? null;
                    const filterDisplayType = filterProperty ? displayTypeOf(filterProperty) : "text";
                    const operatorOptions: Array<{ value: DatabaseFilterOperator; label: string }> =
                      filterDisplayType === "date"
                        ? [
                            { value: "on", label: "On" },
                            { value: "before", label: "Before" },
                            { value: "after", label: "After" },
                            { value: "on_or_before", label: "On or before" },
                            { value: "on_or_after", label: "On or after" },
                          ]
                        : filterDisplayType === "checkbox"
                        ? [
                            { value: "is_checked", label: "Is checked" },
                            { value: "is_not_checked", label: "Is not checked" },
                          ]
                        : filterDisplayType === "person"
                        ? [
                            { value: "contains_current_user", label: "Assigned to me" },
                            { value: "contains", label: "Contains" },
                            { value: "is", label: "Is" },
                            { value: "is_not", label: "Is not" },
                          ]
                        : filterDisplayType === "select" || filterDisplayType === "status"
                        ? [
                            { value: "is", label: "Is" },
                            { value: "is_not", label: "Is not" },
                            { value: "contains", label: "Contains" },
                          ]
                        : [
                            { value: "contains", label: "Contains" },
                            { value: "is", label: "Is" },
                            { value: "is_not", label: "Is not" },
                          ];
                    const valuePlaceholder =
                      filterDisplayType === "date"
                        ? ""
                        : filterDisplayType === "person"
                        ? "Enter member"
                        : "Value";
                    const hideValueInput = ["contains_current_user", "is_checked", "is_not_checked"].includes(filter.operator);

                    return (
                      <div key={filter.id} className="rounded border border-[var(--line)] p-2">
                        <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                          <select
                            value={filter.propertyId}
                            onChange={(event) => updateFilterRule(filter.id, { propertyId: event.target.value })}
                            className="rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                          >
                            <option value="">Property</option>
                            {sortedProperties.map((property) => (
                              <option key={`filter-${filter.id}-${property.id}`} value={property.id}>
                                {property.name}
                              </option>
                            ))}
                          </select>
                          <select
                            value={filter.operator}
                            onChange={(event) => updateFilterRule(filter.id, { operator: event.target.value as DatabaseFilterOperator })}
                            className="rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                          >
                            {operatorOptions.map((option) => (
                              <option key={`${filter.id}-${option.value}`} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <button
                            onClick={() => removeFilterRule(filter.id)}
                            className="inline-flex items-center justify-center rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]"
                            title="Remove filter"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        {!hideValueInput ? (
                          filterDisplayType === "date" ? (
                            <input
                              type="date"
                              value={filter.value}
                              onChange={(event) => updateFilterRule(filter.id, { value: event.target.value })}
                              className="mt-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                            />
                          ) : (
                            <input
                              value={filter.value}
                              onChange={(event) => updateFilterRule(filter.id, { value: event.target.value })}
                              placeholder={valuePlaceholder}
                              className="mt-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                            />
                          )
                        ) : null}
                      </div>
                    );
                  })}
                  <button
                    onClick={addFilterRule}
                    className="inline-flex items-center gap-2 rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add filter
                  </button>
                </div>
              </div>

              <div className="rounded-md border border-[var(--line)] p-2">
                <p className="mb-1 inline-flex items-center gap-2 text-sm">
                  <ArrowUpDown className="h-4 w-4 text-[var(--muted)]" />
                  Sort
                </p>
                <div className="flex gap-2">
                  <select
                    value={sortByPropertyId}
                    onChange={(event) => updateActiveView({ sortByPropertyId: event.target.value })}
                    className="min-w-0 flex-1 rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                  >
                    <option value="">None</option>
                    {sortedProperties.map((property) => (
                      <option key={`sort-${property.id}`} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={sortDirection}
                    onChange={(event) => updateActiveView({ sortDirection: event.target.value === "desc" ? "desc" : "asc" })}
                    className="w-[110px] rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                  >
                    <option value="asc">Ascending</option>
                    <option value="desc">Descending</option>
                  </select>
                </div>
              </div>

              <div className="rounded-md border border-[var(--line)] p-2">
                <p className="mb-1 inline-flex items-center gap-2 text-sm">
                  <Group className="h-4 w-4 text-[var(--muted)]" />
                  Group
                </p>
                <select
                  value={groupByPropertyId}
                  onChange={(event) => updateActiveView({ groupByPropertyId: event.target.value })}
                  className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-sm"
                >
                  <option value="">None</option>
                  {sortedProperties
                    .filter((property) => property.type !== "title")
                    .map((property) => (
                      <option key={`group-${property.id}`} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                </select>
              </div>

              <button
                onClick={() => router.push(`/app/database/${database.pageId}`)}
                className="flex w-full items-center justify-between rounded-md border border-[var(--line)] px-2 py-2 text-left hover:bg-[var(--hover)]"
              >
                <span className="inline-flex items-center gap-2">
                  <ExternalLink className="h-4 w-4 text-[var(--muted)]" />
                  Open as full page
                </span>
                <span className="text-xs text-[var(--muted)]">Open</span>
              </button>
            </div>

            <div className="my-4 border-t border-[var(--line)]" />
            <p className="mb-2 text-sm font-semibold text-[var(--muted)]">Edit properties</p>
            <div className="flex flex-wrap gap-2">
              {PROPERTY_TYPES.map((item) => (
                <button
                  key={`settings-add-${item.value}`}
                  onClick={() => void addProperty(item.value)}
                  className="rounded-md border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--hover)]"
                >
                  + {item.label}
                </button>
              ))}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function CellEditor({
  row,
  property,
  memberEmails,
  updateRowTitle,
  updateCell,
  ensureOption,
  updateOptionColor,
  updateOptionGroup,
  deleteOptionFromProperty,
  openRowPage,
  readOnly = false,
}: {
  row: DatabaseRow;
  property: DatabaseProperty;
  memberEmails: string[];
  updateRowTitle: (rowId: string, title: string) => Promise<void>;
  updateCell: (rowId: string, propertyId: string, value: unknown) => Promise<void>;
  ensureOption: (property: DatabaseProperty, label: string, group?: string) => Promise<void>;
  updateOptionColor: (property: DatabaseProperty, optionId: string, color: string) => Promise<void>;
  updateOptionGroup: (property: DatabaseProperty, optionId: string, group: string) => Promise<void>;
  deleteOptionFromProperty: (property: DatabaseProperty, option: PropertyOption) => Promise<void>;
  openRowPage: (row: DatabaseRow) => void;
  readOnly?: boolean;
}) {
  const displayType = displayTypeOf(property);
  const rawValue = getCellValue(row, property);
  const pickerRef = useRef<HTMLDivElement | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [optionMenuId, setOptionMenuId] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>(() => {
    if (Array.isArray(rawValue)) return "";
    if (rawValue == null) return "";
    return String(rawValue);
  });

  useEffect(() => {
    if (Array.isArray(rawValue)) {
      setDraft("");
      return;
    }
    setDraft(rawValue == null ? "" : String(rawValue));
  }, [rawValue]);

  useEffect(() => {
    if (!pickerOpen) {
      setOptionMenuId(null);
      return;
    }
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (pickerRef.current?.contains(target)) return;
      setPickerOpen(false);
      setOptionMenuId(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [pickerOpen]);

  if (readOnly) {
    if (property.type === "title") {
      return <span className="block truncate py-1">{row.title || "Untitled"}</span>;
    }
    if (displayType === "checkbox") {
      return <input type="checkbox" checked={Boolean(rawValue)} disabled className="h-4 w-4" />;
    }
    if (displayType === "select" || displayType === "status") {
      const options = optionsOf(property);
      const selected = typeof rawValue === "string" ? rawValue : "";
      if (!selected) return <span className="text-[var(--muted)]">Empty</span>;
      return (
        <span
          className="inline-flex max-w-full truncate rounded-full border px-2 py-0.5 text-xs"
          style={optionColorStyle(options.find((option) => option.label === selected)?.color ?? "default")}
        >
          {selected}
        </span>
      );
    }
    if (displayType === "multi_select" || displayType === "person") {
      const selected = Array.isArray(rawValue) ? rawValue.map((item) => String(item)) : [];
      const propertyOptions = optionsOf(property);
      if (selected.length === 0) return <span className="text-[var(--muted)]">Empty</span>;
      return (
        <div className="flex flex-wrap gap-1">
          {selected.map((label) => (
            <span
              key={`${row.id}-${property.id}-readonly-${label}`}
              className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs"
              style={optionColorStyle(propertyOptions.find((option) => option.label === label)?.color ?? "default")}
            >
              {label}
            </span>
          ))}
        </div>
      );
    }
    if (displayType === "date") {
      return <span>{typeof rawValue === "string" && rawValue ? rawValue : "Empty"}</span>;
    }
    if (displayType === "number") {
      return <span>{typeof rawValue === "string" && rawValue ? rawValue : "0"}</span>;
    }
    if (displayType === "email") {
      return <span>{typeof rawValue === "string" && rawValue ? rawValue : "Empty"}</span>;
    }
    return <span>{rawValue == null || rawValue === "" ? "Empty" : String(rawValue)}</span>;
  }

  if (property.type === "title") {
    return (
      <div className="group flex items-center gap-1">
        <input
          value={row.title}
          onChange={(event) => {
            void updateRowTitle(row.id, event.target.value);
          }}
          className="min-w-0 flex-1 border-0 bg-transparent px-0 py-1 outline-none"
        />
        <button
          className="rounded p-1 text-[var(--muted)] opacity-0 transition group-hover:opacity-100 hover:bg-[var(--hover)]"
          onClick={() => openRowPage(row)}
          title="Open row page"
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  if (displayType === "checkbox") {
    return (
      <input
        type="checkbox"
        checked={Boolean(rawValue)}
        onChange={(event) => {
          void updateCell(row.id, property.id, event.target.checked);
        }}
        className="h-4 w-4"
      />
    );
  }

  if (displayType === "date") {
    return (
      <input
        type="date"
        value={typeof rawValue === "string" ? rawValue : ""}
        onChange={(event) => {
          void updateCell(row.id, property.id, event.target.value);
        }}
        className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1"
      />
    );
  }

  if (displayType === "number") {
    return (
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value.replace(/[^\d.-]/g, ""))}
        onBlur={() => {
          const normalized = normalizeNumber(draft);
          setDraft(normalized);
          void updateCell(row.id, property.id, normalized);
        }}
        placeholder="0"
        className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1"
      />
    );
  }

  if (displayType === "email") {
    const value = typeof rawValue === "string" ? rawValue : "";
    return (
      <div className="group flex items-center gap-1">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => {
            void updateCell(row.id, property.id, draft.trim());
          }}
          placeholder="name@example.com"
          className="min-w-0 flex-1 rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1"
        />
        <button
          className="rounded p-1 text-[var(--muted)] opacity-0 transition group-hover:opacity-100 hover:bg-[var(--hover)]"
          title="Copy email"
          onClick={() => {
            if (value) void navigator.clipboard.writeText(value);
          }}
        >
          <Copy className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  if (displayType === "select" || displayType === "status") {
    const options = optionsOf(property);
    const selected = typeof rawValue === "string" ? rawValue : "";
    const filtered = options.filter((option) => option.label.toLowerCase().includes(draft.trim().toLowerCase()));
    const statusGroups = ["To-do", "In progress", "Complete"];
    const groupedFiltered =
      displayType === "status"
        ? statusGroups.map((group) => ({
            group,
            items: filtered.filter((option) => (option.group || "To-do") === group),
          }))
        : [];
    return (
      <div ref={pickerRef} className="relative">
        <button
          onClick={() => {
            setPickerOpen((prev) => !prev);
            setDraft("");
          }}
          onKeyDown={(event) => {
            if ((event.key === "Backspace" || event.key === "Delete") && !pickerOpen) {
              event.preventDefault();
              void updateCell(row.id, property.id, "");
            }
          }}
          className="inline-flex min-h-7 w-full items-center justify-between rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-left text-sm hover:bg-[var(--hover)]"
        >
          {selected ? (
            <span
              className="inline-flex max-w-full truncate rounded-full border px-2 py-0.5 text-xs"
              style={optionColorStyle(options.find((option) => option.label === selected)?.color ?? "default")}
            >
              {selected}
            </span>
          ) : (
            <span className="text-[var(--muted)]">Select</span>
          )}
          <span className="text-xs text-[var(--muted)]">▾</span>
        </button>

        {pickerOpen ? (
          <div className="absolute left-0 top-[calc(100%+8px)] z-[80] w-[250px] rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Find or create option"
              onKeyDown={(event) => {
                if ((event.key === "Backspace" || event.key === "Delete") && draft.length === 0) {
                  event.preventDefault();
                  void updateCell(row.id, property.id, "");
                  return;
                }
                if (event.key !== "Enter") return;
                event.preventDefault();
                const next = draft.trim();
                if (!next) return;
                void (async () => {
                  await ensureOption(property, next);
                  await updateCell(row.id, property.id, next);
                  setDraft("");
                  setPickerOpen(false);
                })();
              }}
              className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
            />

            <div className="max-h-[220px] space-y-1 overflow-y-auto">
              {(displayType === "status"
                ? groupedFiltered.flatMap(({ group, items }) =>
                    items.map((item, index) => ({ ...item, __group: group, __first: index === 0 }))
                  )
                : filtered
              ).map((option: PropertyOption & { __group?: string; __first?: boolean }) => {
                const menuOpen = optionMenuId === option.id;
                return (
                  <div key={`${row.id}-${property.id}-${option.id}`} className="relative">
                    {displayType === "status" && option.__first ? (
                      <p className="px-2 pb-1 pt-1 text-[11px] font-medium text-[var(--muted)]">{option.__group}</p>
                    ) : null}
                    <div className="relative flex items-center gap-1">
                    <button
                      className="inline-flex min-w-0 flex-1 items-center justify-between rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                      onClick={() => {
                        void updateCell(row.id, property.id, option.label);
                        setPickerOpen(false);
                        setOptionMenuId(null);
                      }}
                    >
                      <span className="inline-flex max-w-full truncate rounded-full border px-2 py-0.5 text-xs" style={optionColorStyle(option.color)}>
                        {option.label}
                      </span>
                      {selected === option.label ? <Check className="h-3.5 w-3.5 text-[var(--muted)]" /> : null}
                    </button>
                    <button
                      className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                      onClick={() => setOptionMenuId((prev) => (prev === option.id ? null : option.id))}
                    >
                      <MoreHorizontal className="h-3.5 w-3.5" />
                    </button>
                    {menuOpen ? (
                      <div className="absolute right-0 top-[calc(100%+8px)] z-[90] w-44 rounded-md border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                        {displayType === "status" ? (
                          <select
                            value={option.group || "To-do"}
                            onChange={(event) => {
                              void updateOptionGroup(property, option.id, event.target.value);
                              setOptionMenuId(null);
                            }}
                            className="mb-1 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs"
                          >
                            {statusGroups.map((group) => (
                              <option key={`status-group-option-${group}`} value={group}>
                                {group}
                              </option>
                            ))}
                          </select>
                        ) : null}
                        <p className="px-2 py-1 text-[11px] text-[var(--muted)]">Color</p>
                        <div className="mb-1 grid grid-cols-5 gap-1 px-1">
                          {OPTION_COLORS.map((color) => (
                            <button
                              key={`${option.id}-${color}`}
                              className="h-5 w-5 rounded border"
                              style={optionColorStyle(color)}
                              onClick={() => {
                                void updateOptionColor(property, option.id, color);
                                setOptionMenuId(null);
                              }}
                            />
                          ))}
                        </div>
                        <button
                          className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                          onClick={() => {
                            void deleteOptionFromProperty(property, option);
                            setOptionMenuId(null);
                          }}
                        >
                          Delete option
                        </button>
                      </div>
                    ) : null}
                  </div>
                  </div>
                );
              })}
              {filtered.length === 0 ? <p className="px-2 py-1 text-xs text-[var(--muted)]">No options</p> : null}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  if (displayType === "multi_select" || displayType === "person") {
    const selected = Array.isArray(rawValue) ? rawValue.map((item) => String(item)) : [];
    const propertyOptions = optionsOf(property);
    const optionLabels = propertyOptions.map((item) => item.label);
    const suggestions = displayType === "person" ? Array.from(new Set([...memberEmails, ...optionLabels])) : optionLabels;
    const filteredSuggestions = suggestions.filter((item) => item.toLowerCase().includes(draft.trim().toLowerCase()));

    const removeValue = (label: string) => {
      const next = selected.filter((item) => item !== label);
      void updateCell(row.id, property.id, next);
    };

    const addValue = (label: string, closeAfter = displayType === "person") => {
      const normalized = label.trim();
      if (!normalized) return;
      const next = Array.from(new Set([...selected, normalized]));
      void (async () => {
        if (!suggestions.some((item) => item.toLowerCase() === normalized.toLowerCase())) {
          await ensureOption(property, normalized);
        }
        await updateCell(row.id, property.id, next);
      })();
      setDraft("");
      if (closeAfter) {
        setPickerOpen(false);
      }
    };

    return (
      <div ref={pickerRef} className="relative space-y-1">
        <div className="flex min-h-7 flex-wrap items-center gap-1 rounded border border-[var(--line)] bg-[var(--panel)] px-1.5 py-1">
          {selected.map((label) => (
            <button
              key={`${row.id}-${property.id}-${label}`}
              onClick={() => removeValue(label)}
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs hover:brightness-95"
              style={optionColorStyle(propertyOptions.find((option) => option.label === label)?.color ?? "default")}
            >
              {label}
              <X className="h-3 w-3" />
            </button>
          ))}
          <input
            value={draft}
            onFocus={() => setPickerOpen(true)}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
              if (event.key === "Backspace" && draft.length === 0 && selected.length > 0) {
                event.preventDefault();
                removeValue(selected[selected.length - 1] ?? "");
                return;
              }
              if (event.key !== "Enter" && event.key !== ",") return;
              event.preventDefault();
              addValue(draft);
            }}
            placeholder={displayType === "person" ? "Mention members" : "Add option"}
            className="min-w-[92px] flex-1 border-0 bg-transparent py-0.5 text-sm outline-none"
          />
        </div>

        {pickerOpen ? (
          <div className="absolute left-0 top-[calc(100%+6px)] z-[80] w-[260px] rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                addValue(draft);
              }}
              placeholder={displayType === "person" ? "Mention members" : "Find or create option"}
              className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-sm"
            />
            <div className="max-h-[220px] space-y-1 overflow-y-auto">
              {filteredSuggestions.map((label) => {
                const option = propertyOptions.find((item) => item.label === label) ?? null;
                const selectedNow = selected.includes(label);
                const menuOpen = optionMenuId === option?.id;
                return (
                  <div key={`${row.id}-${property.id}-pick-${label}`} className="relative flex items-center gap-1">
                    <button
                      className="inline-flex min-w-0 flex-1 items-center justify-between rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                      onClick={() => {
                        if (selectedNow) {
                          removeValue(label);
                          if (displayType === "person") {
                            setPickerOpen(false);
                          }
                        } else {
                          addValue(label);
                        }
                      }}
                    >
                      <span className="inline-flex max-w-full truncate rounded-full border px-2 py-0.5 text-xs" style={optionColorStyle(option?.color ?? "default")}>
                        {label}
                      </span>
                      {selectedNow ? <Check className="h-3.5 w-3.5 text-[var(--muted)]" /> : null}
                    </button>
                    {option && displayType !== "person" ? (
                      <>
                        <button
                          className="rounded p-1 text-[var(--muted)] hover:bg-[var(--hover)]"
                          onClick={() => setOptionMenuId((prev) => (prev === option.id ? null : option.id))}
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </button>
                        {menuOpen ? (
                          <div className="absolute right-0 top-[calc(100%+8px)] z-[90] w-44 rounded-md border border-[var(--line)] bg-[var(--panel)] p-1 shadow-lg">
                            <p className="px-2 py-1 text-[11px] text-[var(--muted)]">Color</p>
                            <div className="mb-1 grid grid-cols-5 gap-1 px-1">
                              {OPTION_COLORS.map((color) => (
                                <button
                                  key={`${option.id}-${color}`}
                                  className="h-5 w-5 rounded border"
                                  style={optionColorStyle(color)}
                                  onClick={() => {
                                    void updateOptionColor(property, option.id, color);
                                    setOptionMenuId(null);
                                  }}
                                />
                              ))}
                            </div>
                            <button
                              className="w-full rounded px-2 py-1.5 text-left text-xs text-[#b42318] hover:bg-[var(--hover)]"
                              onClick={() => {
                                void deleteOptionFromProperty(property, option);
                                setOptionMenuId(null);
                              }}
                            >
                              Delete option
                            </button>
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                );
              })}
              {filteredSuggestions.length === 0 ? (
                <button
                  className="w-full rounded px-2 py-1.5 text-left text-xs text-[var(--muted)] hover:bg-[var(--hover)]"
                  onClick={() => addValue(draft)}
                >
                  Create "{draft.trim() || "option"}"
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <input
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        void updateCell(row.id, property.id, draft);
      }}
      className="w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1"
    />
  );
}
