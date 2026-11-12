"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ActivityItem } from "@/components/activities/activity-item";
import { ActivityForm } from "@/components/activities/activity-form";
import { Plus, Phone, Mail, Calendar, CheckSquare, StickyNote } from "lucide-react";
import { toast } from "sonner";

const typeFilters = [
  { value: "", label: "All", icon: null },
  { value: "call", label: "Calls", icon: Phone },
  { value: "email", label: "Emails", icon: Mail },
  { value: "meeting", label: "Meetings", icon: Calendar },
  { value: "task", label: "Tasks", icon: CheckSquare },
  { value: "note", label: "Notes", icon: StickyNote },
];

export default function ActivitiesPage() {
  const [activities, setActivities] = useState<any[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [doneFilter, setDoneFilter] = useState<string>("");
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (typeFilter) params.set("type", typeFilter);
    if (doneFilter !== "") params.set("isDone", doneFilter);
    const res = await fetch(`/api/activities?${params}`);
    if (res.ok) setActivities(await res.json());
  }, [typeFilter, doneFilter]);

  useEffect(() => { load(); }, [load]);

  // Group by date
  const grouped = activities.reduce<Record<string, any[]>>((acc, a) => {
    const date = a.dueDate || "No date";
    if (!acc[date]) acc[date] = [];
    acc[date].push(a);
    return acc;
  }, {});

  const sortedDates = Object.keys(grouped).sort((a, b) => {
    if (a === "No date") return 1;
    if (b === "No date") return -1;
    return b.localeCompare(a);
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Activities</h1>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add Activity
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {typeFilters.map((f) => (
          <Button
            key={f.value}
            variant={typeFilter === f.value ? "default" : "outline"}
            size="sm"
            onClick={() => setTypeFilter(f.value)}
          >
            {f.icon && <f.icon className="h-3 w-3 mr-1" />}
            {f.label}
          </Button>
        ))}
        <div className="w-px bg-border mx-1" />
        <Button
          variant={doneFilter === "" ? "default" : "outline"}
          size="sm"
          onClick={() => setDoneFilter("")}
        >
          All
        </Button>
        <Button
          variant={doneFilter === "false" ? "default" : "outline"}
          size="sm"
          onClick={() => setDoneFilter("false")}
        >
          Pending
        </Button>
        <Button
          variant={doneFilter === "true" ? "default" : "outline"}
          size="sm"
          onClick={() => setDoneFilter("true")}
        >
          Done
        </Button>
      </div>

      {showForm && (
        <div className="mb-6">
          <ActivityForm
            onSuccess={() => {
              setShowForm(false);
              load();
              toast.success("Activity created");
            }}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      <div className="space-y-6">
        {sortedDates.map((date) => (
          <div key={date}>
            <h3 className="text-sm font-medium text-muted-foreground mb-2">
              {date === "No date"
                ? "No date"
                : new Date(date + "T00:00:00").toLocaleDateString("en-US", {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
            </h3>
            <div className="space-y-2">
              {grouped[date].map((a: any) => (
                <ActivityItem
                  key={a.id}
                  activity={a}
                  onToggle={async () => {
                    await fetch(`/api/activities/${a.id}`, {
                      method: "PATCH",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ isDone: !a.isDone }),
                    });
                    load();
                    toast.success(a.isDone ? "Marked as pending" : "Marked as done");
                  }}
                />
              ))}
            </div>
          </div>
        ))}
        {activities.length === 0 && (
          <p className="text-center text-muted-foreground py-8">No activities found.</p>
        )}
      </div>
    </div>
  );
}
