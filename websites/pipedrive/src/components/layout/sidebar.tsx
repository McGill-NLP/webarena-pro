"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Handshake,
  Users,
  Building2,
  CalendarCheck,
  Settings,
  ChevronLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

const navItems = [
  { href: "/deals", label: "Deals", icon: Handshake },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/activities", label: "Activities", icon: CalendarCheck },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col bg-zinc-900 text-zinc-100 transition-all duration-200 h-screen sticky top-0",
        collapsed ? "w-16" : "w-60"
      )}
    >
      <div className="flex items-center justify-between px-4 h-14 border-b border-zinc-800">
        {!collapsed && (
          <Link href="/deals" className="text-lg font-bold tracking-tight">
            PipeCRM
          </Link>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 ml-auto"
          onClick={() => setCollapsed(!collapsed)}
        >
          <ChevronLeft
            className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")}
          />
        </Button>
      </div>
      <nav className="flex-1 py-4 space-y-1 px-2">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-100"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
