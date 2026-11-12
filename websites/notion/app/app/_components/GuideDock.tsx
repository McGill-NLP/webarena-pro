"use client";

import { useState } from "react";
import { BookOpen, X } from "lucide-react";

export default function GuideDock() {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-4 left-4 z-40">
      {open ? (
        <div className="mb-2 w-[320px] rounded-xl border border-[var(--line)] bg-[var(--panel)] p-3 text-sm shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <p className="font-semibold">Guide</p>
            <button onClick={() => setOpen(false)} className="rounded p-1 hover:bg-[var(--hover)]">
              <X className="h-4 w-4" />
            </button>
          </div>
          <ul className="space-y-1 text-[13px] text-[var(--muted)]">
            <li>`/` : open slash commands</li>
            <li>`Cmd/Ctrl + \\` : toggle sidebar</li>
            <li>`Tab / Shift+Tab` : indent / outdent block</li>
            <li>Empty block + Delete/Backspace: remove block</li>
          </ul>
        </div>
      ) : null}

      <button
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm shadow-md hover:bg-[var(--hover)]"
      >
        <BookOpen className="h-4 w-4" />
        Guide
      </button>
    </div>
  );
}
