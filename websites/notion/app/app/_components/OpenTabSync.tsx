"use client";

import { useEffect, useRef } from "react";

export default function OpenTabSync({ pageId }: { pageId: string }) {
  const syncedRef = useRef<string | null>(null);

  useEffect(() => {
    if (syncedRef.current === pageId) return;
    syncedRef.current = pageId;

    const run = async () => {
      await fetch("/api/tabs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pageId }),
      });
      window.dispatchEvent(new Event("tabs:refresh"));
    };
    void run();
  }, [pageId]);

  return null;
}
