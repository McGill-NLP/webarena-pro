"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Check, X } from "lucide-react";

type PropertyType = "title" | "text" | "select" | "multi_select" | "checkbox" | "date";
type DisplayPropertyType = PropertyType | "number" | "person" | "email" | "status";

type RowPropertyItem = {
  id: string;
  name: string;
  type: PropertyType;
  configJson: unknown;
  value: unknown;
};

type PropertyOption = {
  id: string;
  label: string;
  color: string;
  group?: string;
};

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
  const source = input as { id?: unknown; label?: unknown; name?: unknown; color?: unknown; group?: unknown };
  const labelRaw = typeof source.label === "string" ? source.label : typeof source.name === "string" ? source.name : "";
  const label = labelRaw.trim();
  if (!label) return null;
  return {
    id: typeof source.id === "string" && source.id.trim() ? source.id : label.toLowerCase().replace(/\s+/g, "_"),
    label,
    color: typeof source.color === "string" && source.color.trim() ? source.color : "default",
    group: typeof source.group === "string" && source.group.trim() ? source.group : undefined,
  };
}

function optionsOf(item: RowPropertyItem) {
  if (!item.configJson || typeof item.configJson !== "object") return [];
  const raw = (item.configJson as { options?: unknown }).options;
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeOption).filter((entry): entry is PropertyOption => Boolean(entry));
}

function subtypeOf(item: RowPropertyItem): string | null {
  if (!item.configJson || typeof item.configJson !== "object") return null;
  const subtype = (item.configJson as { subtype?: unknown }).subtype;
  return typeof subtype === "string" && subtype.trim().length > 0 ? subtype : null;
}

function displayTypeOf(item: RowPropertyItem): DisplayPropertyType {
  const subtype = subtypeOf(item);
  if (item.type === "text" && subtype === "number") return "number";
  if (item.type === "text" && subtype === "email") return "email";
  if (item.type === "multi_select" && subtype === "person") return "person";
  if (item.type === "select" && subtype === "status") return "status";
  return item.type;
}

function normalizeArrayValue(input: unknown) {
  if (!Array.isArray(input)) return [];
  return input.map((entry) => String(entry)).filter((entry) => entry.length > 0);
}

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

function SelectLikePropertyEditor({
  item,
  value,
  disabled,
  onChange,
}: {
  item: RowPropertyItem;
  value: unknown;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const pickerRef = useRef<HTMLDivElement | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const displayType = displayTypeOf(item);
  const options = optionsOf(item);
  const selected = typeof value === "string" ? value : "";
  const filtered = options.filter((option) => option.label.toLowerCase().includes(draft.trim().toLowerCase()));
  const statusGroups = ["To-do", "In progress", "Complete"];
  const groupedFiltered =
    displayType === "status"
      ? statusGroups.map((group) => ({
          group,
          items: filtered.filter((option) => (option.group || "To-do") === group),
        }))
      : [];

  useEffect(() => {
    if (!pickerOpen) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (pickerRef.current?.contains(target)) return;
      setPickerOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [pickerOpen]);

  return (
    <div ref={pickerRef} className="relative min-w-[200px]">
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          if (disabled) return;
          setPickerOpen((prev) => !prev);
          setDraft("");
        }}
        onKeyDown={(event) => {
          if ((event.key === "Backspace" || event.key === "Delete") && !pickerOpen) {
            event.preventDefault();
            onChange("");
          }
        }}
        className="inline-flex min-h-8 w-full items-center justify-between rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-left text-xs hover:bg-[var(--hover)] disabled:cursor-default disabled:opacity-70"
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
        <div className="absolute left-0 top-[calc(100%+8px)] z-[90] w-[260px] rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Find or create option"
            onKeyDown={(event) => {
              if ((event.key === "Backspace" || event.key === "Delete") && draft.length === 0) {
                event.preventDefault();
                onChange("");
                return;
              }
              if (event.key !== "Enter") return;
              event.preventDefault();
              const next = draft.trim();
              if (!next) return;
              onChange(next);
              setDraft("");
              setPickerOpen(false);
            }}
            className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-xs"
          />
          <div className="max-h-[220px] space-y-1 overflow-y-auto">
            {(displayType === "status"
              ? groupedFiltered.flatMap(({ group, items }) =>
                  items.map((entry, index) => ({ ...entry, __group: group, __first: index === 0 }))
                )
              : filtered
            ).map((option: PropertyOption & { __group?: string; __first?: boolean }) => (
              <div key={`${item.id}-${option.id}`}>
                {displayType === "status" && option.__first ? (
                  <p className="px-2 pb-1 pt-1 text-[11px] font-medium text-[var(--muted)]">{option.__group}</p>
                ) : null}
                <button
                  type="button"
                  className="inline-flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                  onClick={() => {
                    onChange(option.label);
                    setPickerOpen(false);
                  }}
                >
                  <span className="inline-flex max-w-full truncate rounded-full border px-2 py-0.5 text-xs" style={optionColorStyle(option.color)}>
                    {option.label}
                  </span>
                  {selected === option.label ? <Check className="h-3.5 w-3.5 text-[var(--muted)]" /> : null}
                </button>
              </div>
            ))}
            {filtered.length === 0 ? <p className="px-2 py-1 text-xs text-[var(--muted)]">No options</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MultiValuePropertyEditor({
  item,
  value,
  disabled,
  onChange,
}: {
  item: RowPropertyItem;
  value: unknown;
  disabled: boolean;
  onChange: (value: string[]) => void;
}) {
  const pickerRef = useRef<HTMLDivElement | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const displayType = displayTypeOf(item);
  const options = optionsOf(item);
  const selected = normalizeArrayValue(value);
  const suggestions = Array.from(new Set([...options.map((option) => option.label), ...selected]));
  const filtered = suggestions.filter((option) => option.toLowerCase().includes(draft.trim().toLowerCase()));
  const shouldCloseAfterAssign = displayType === "person";

  useEffect(() => {
    if (!pickerOpen) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (pickerRef.current?.contains(target)) return;
      setPickerOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [pickerOpen]);

  const commitValue = (label: string, closeAfter = shouldCloseAfterAssign) => {
    const normalized = label.trim();
    if (!normalized) return;
    const next = Array.from(new Set([...selected, normalized]));
    onChange(next);
    setDraft("");
    if (closeAfter) setPickerOpen(false);
  };

  const removeValue = (label: string) => {
    onChange(selected.filter((entry) => entry !== label));
  };

  return (
    <div ref={pickerRef} className="relative min-w-[220px]">
      <div className="flex min-h-8 flex-wrap items-center gap-1 rounded border border-[var(--line)] bg-[var(--panel)] px-1.5 py-1">
        {selected.map((label) => (
          <button
            key={`${item.id}-${label}`}
            type="button"
            disabled={disabled}
            onClick={() => removeValue(label)}
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs hover:brightness-95 disabled:cursor-default disabled:opacity-70"
            style={optionColorStyle(options.find((option) => option.label === label)?.color ?? "default")}
          >
            {label}
            <X className="h-3 w-3" />
          </button>
        ))}
        <input
          value={draft}
          disabled={disabled}
          onFocus={() => {
            if (disabled) return;
            setPickerOpen(true);
          }}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event: ReactKeyboardEvent<HTMLInputElement>) => {
            if ((event.key === "Backspace" || event.key === "Delete") && draft.length === 0 && selected.length > 0) {
              event.preventDefault();
              removeValue(selected[selected.length - 1] ?? "");
              return;
            }
            if (event.key !== "Enter" && event.key !== ",") return;
            event.preventDefault();
            commitValue(draft);
          }}
          placeholder={displayType === "person" ? "Mention members" : "Add option"}
          className="min-w-[96px] flex-1 border-0 bg-transparent py-0.5 text-xs outline-none"
        />
      </div>

      {pickerOpen ? (
        <div className="absolute left-0 top-[calc(100%+8px)] z-[90] w-[260px] rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2 shadow-xl">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault();
              commitValue(draft);
            }}
            placeholder={displayType === "person" ? "Mention members" : "Find or create option"}
            className="mb-2 w-full rounded border border-[var(--line)] bg-[var(--panel)] px-2 py-1.5 text-xs"
          />
          <div className="max-h-[220px] space-y-1 overflow-y-auto">
            {filtered.map((label) => {
              const selectedNow = selected.includes(label);
              const option = options.find((entry) => entry.label === label);
              return (
                <button
                  key={`${item.id}-suggestion-${label}`}
                  type="button"
                  className="inline-flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-[var(--hover)]"
                  onClick={() => {
                    if (selectedNow) {
                      removeValue(label);
                      if (shouldCloseAfterAssign) setPickerOpen(false);
                    } else {
                      commitValue(label);
                    }
                  }}
                >
                  <span
                    className="inline-flex max-w-full truncate rounded-full border px-2 py-0.5 text-xs"
                    style={optionColorStyle(option?.color ?? "default")}
                  >
                    {label}
                  </span>
                  {selectedNow ? <Check className="h-3.5 w-3.5 text-[var(--muted)]" /> : null}
                </button>
              );
            })}
            {filtered.length === 0 ? (
              <button
                type="button"
                className="w-full rounded px-2 py-1.5 text-left text-xs text-[var(--muted)] hover:bg-[var(--hover)]"
                onClick={() => commitValue(draft)}
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

export default function RowPropertiesPanel({
  databasePageId,
  rowId,
  title,
  items,
  editable = true,
}: {
  databasePageId: string;
  rowId: string;
  title: string;
  items: RowPropertyItem[];
  editable?: boolean;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(
    Object.fromEntries(items.map((item) => [item.id, item.value ?? (item.type === "checkbox" ? false : "")]))
  );
  const [busyId, setBusyId] = useState<string | null>(null);

  const itemMap = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);

  async function updateCell(propertyId: string, value: unknown) {
    if (!editable) return;
    setBusyId(propertyId);
    setValues((prev) => ({ ...prev, [propertyId]: value }));
    try {
      await fetch(`/api/databases/${databasePageId}/cells`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rowId, propertyId, value }),
      });
    } finally {
      setBusyId((current) => (current === propertyId ? null : current));
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
      <p className="mb-2 text-xs text-[var(--muted)]">In {title}</p>
      <div className="flex flex-wrap gap-2">
        {items.length === 0 ? <p className="text-xs text-[var(--muted)]">No properties</p> : null}
        {items.map((item) => {
          const raw = values[item.id];
          const options = optionsOf(item);
          const subtype = subtypeOf(item);
          const displayType = displayTypeOf(item);
          const disabled = !editable || busyId === item.id;

          if (item.type === "checkbox") {
            return (
              <label
                key={item.id}
                className="inline-flex items-center gap-2 rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs"
              >
                <span className="text-[var(--muted)]">{item.name}</span>
                <input
                  type="checkbox"
                  checked={Boolean(raw)}
                  disabled={disabled}
                  onChange={(event) => {
                    void updateCell(item.id, event.target.checked);
                  }}
                />
              </label>
            );
          }

          if (item.type === "date") {
            return (
              <label key={item.id} className="inline-flex items-center gap-2 rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs">
                <span className="text-[var(--muted)]">{item.name}</span>
                <input
                  type="date"
                  value={typeof raw === "string" ? raw : ""}
                  disabled={disabled}
                  onChange={(event) => {
                    void updateCell(item.id, event.target.value);
                  }}
                  className="rounded border border-[var(--line)] bg-[var(--panel)] px-1 py-0.5 text-xs"
                />
              </label>
            );
          }

          if (displayType === "select" || displayType === "status") {
            return (
              <label key={item.id} className="inline-flex items-center gap-2 rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs">
                <span className="text-[var(--muted)]">{item.name}</span>
                <SelectLikePropertyEditor
                  item={item}
                  value={raw}
                  disabled={disabled}
                  onChange={(next) => {
                    void updateCell(item.id, next);
                  }}
                />
              </label>
            );
          }

          if (item.type === "multi_select") {
            return (
              <label key={item.id} className="inline-flex items-center gap-2 rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs">
                <span className="text-[var(--muted)]">{item.name}</span>
                <MultiValuePropertyEditor
                  item={item}
                  value={raw}
                  disabled={disabled}
                  onChange={(next) => {
                    setValues((prev) => ({ ...prev, [item.id]: next }));
                    void updateCell(item.id, next);
                  }}
                />
              </label>
            );
          }

          const inputType = subtype === "email" ? "email" : subtype === "number" ? "number" : "text";
          const display = raw == null ? "" : String(raw);
          return (
            <label key={item.id} className="inline-flex items-center gap-2 rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs">
              <span className="text-[var(--muted)]">{item.name}</span>
              <input
                type={inputType}
                value={display}
                disabled={disabled}
                onChange={(event) => setValues((prev) => ({ ...prev, [item.id]: event.target.value }))}
                onBlur={(event) => {
                  const current = itemMap.get(item.id);
                  if (current && subtypeOf(current) === "number") {
                    const numeric = Number(event.target.value);
                    void updateCell(item.id, Number.isFinite(numeric) ? String(numeric) : "");
                    return;
                  }
                  void updateCell(item.id, event.target.value.trim());
                }}
                className="min-w-[140px] rounded border border-[var(--line)] bg-[var(--panel)] px-1 py-0.5 text-xs"
              />
            </label>
          );
        })}
      </div>
    </div>
  );
}
