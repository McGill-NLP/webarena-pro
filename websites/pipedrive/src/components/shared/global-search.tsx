"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { Search, Handshake, Users, Building2 } from "lucide-react";

type SearchResult = {
  id: number;
  type: "deal" | "contact" | "company";
  title: string;
  subtitle: string;
};

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  useEffect(() => {
    if (!query || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setResults([]);
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        setResults(res.ok ? await res.json() : []);
      } catch (error) {
        if ((error as Error).name !== "AbortError") setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 200);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query]);

  function handleSelect(result: SearchResult) {
    setOpen(false);
    setQuery("");
    const paths = {
      deal: `/deals/${result.id}`,
      contact: `/contacts/${result.id}`,
      company: `/companies/${result.id}`,
    };
    router.push(paths[result.type]);
  }

  const icons = {
    deal: Handshake,
    contact: Users,
    company: Building2,
  };

  return (
    <>
      <Button
        variant="outline"
        className="relative h-9 w-full max-w-sm justify-start text-sm text-muted-foreground"
        onClick={() => setOpen(true)}
      >
        <Search className="mr-2 h-4 w-4" />
        Search...
        <kbd className="pointer-events-none ml-auto inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100">
          <span className="text-xs">&#8984;</span>K
        </kbd>
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen} commandProps={{ shouldFilter: false }}>
        <CommandInput
          placeholder="Search deals, contacts, companies..."
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>{loading ? "Searching..." : "No results found."}</CommandEmpty>
          {results.length > 0 && (
            <CommandGroup heading="Results">
              {results.map((r) => {
                const Icon = icons[r.type];
                return (
                  <CommandItem
                    key={`${r.type}-${r.id}`}
                    value={`${r.type}-${r.id}-${r.title}-${r.subtitle}`}
                    onSelect={() => handleSelect(r)}
                  >
                    <Icon className="mr-2 h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="text-sm font-medium">{r.title}</div>
                      <div className="text-xs text-muted-foreground">{r.subtitle}</div>
                    </div>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
