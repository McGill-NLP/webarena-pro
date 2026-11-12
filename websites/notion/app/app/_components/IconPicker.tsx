"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import EmojiPicker, { Theme } from "emoji-picker-react";
import { Smile, X } from "lucide-react";
import { getCustomEmojis, resolveIcon, type CustomEmoji } from "@/lib/workspace-ui";

type IconPickerProps = {
  icon: string | null;
  onChange: (icon: string) => void;
  onRemove?: () => void;
  workspaceId?: string | null;
};

export default function IconPicker({ icon, onChange, onRemove, workspaceId }: IconPickerProps) {
  const [open, setOpen] = useState(false);
  const [customEmojis, setCustomEmojis] = useState<CustomEmoji[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      setCustomEmojis([]);
      return;
    }
    setCustomEmojis(getCustomEmojis(workspaceId));
  }, [workspaceId]);

  useEffect(() => {
    const onWorkspaceUiChanged = () => {
      if (!workspaceId) return;
      setCustomEmojis(getCustomEmojis(workspaceId));
    };
    window.addEventListener("workspace-ui:changed", onWorkspaceUiChanged);
    return () => window.removeEventListener("workspace-ui:changed", onWorkspaceUiChanged);
  }, [workspaceId]);

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    window.addEventListener("mousedown", handleOutsideClick);
    return () => window.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const resolved = useMemo(() => resolveIcon(icon, customEmojis), [icon, customEmojis]);

  return (
    <div ref={containerRef} className="relative inline-flex items-center gap-1">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className={`inline-flex items-center justify-center rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 hover:bg-[var(--hover)] ${icon ? "h-9 min-w-9 text-lg" : "h-8 gap-1 text-sm text-[var(--muted)]"}`}
        title="Pick icon"
      >
        {resolved ? (
          resolved.type === "image" ? <img src={resolved.value} alt="icon" className="h-6 w-6 rounded object-cover" /> : <span>{resolved.value}</span>
        ) : (
          <>
            <Smile className="h-4 w-4" />
            <span>Add icon</span>
          </>
        )}
      </button>

      {icon && onRemove ? (
        <button
          onClick={onRemove}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--line)] bg-[var(--panel)] hover:bg-[var(--hover)]"
          title="Remove icon"
        >
          <X className="h-3.5 w-3.5 text-[var(--muted)]" />
        </button>
      ) : null}

      {open ? (
        <div className="absolute left-0 top-[110%] z-40 w-[320px] rounded-md border border-[var(--line)] bg-[var(--panel)] p-2 shadow-lg">
          {customEmojis.length > 0 ? (
            <div className="mb-2 rounded-md border border-[var(--line)] bg-[var(--surface)] p-2">
              <p className="mb-1 text-xs font-medium text-[var(--muted)]">Custom emoji</p>
              <div className="grid grid-cols-8 gap-1">
                {customEmojis.slice(0, 24).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      onChange(`custom:${item.id}`);
                      setOpen(false);
                    }}
                    className="inline-flex h-8 w-8 items-center justify-center overflow-hidden rounded border border-[var(--line)] bg-[var(--panel)] hover:bg-[var(--hover)]"
                    title={item.name}
                  >
                    {item.value.startsWith("data:") || item.value.startsWith("http") || item.value.startsWith("/") ? (
                      <img src={item.value} alt={item.name} className="h-full w-full object-cover" />
                    ) : (
                      <span className="text-base leading-none">{item.value}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <EmojiPicker
            height={360}
            width={304}
            theme={Theme.LIGHT}
            onEmojiClick={(data) => {
              onChange(data.emoji);
              setOpen(false);
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
