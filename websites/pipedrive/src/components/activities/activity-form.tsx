"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Phone, Mail, Calendar, CheckSquare, StickyNote } from "lucide-react";
import { cn } from "@/lib/utils";

const activityTypes = [
  { value: "call", label: "Call", icon: Phone },
  { value: "email", label: "Email", icon: Mail },
  { value: "meeting", label: "Meeting", icon: Calendar },
  { value: "task", label: "Task", icon: CheckSquare },
  { value: "note", label: "Note", icon: StickyNote },
];

type Props = {
  dealId?: number | null;
  contactId?: number | null;
  companyId?: number | null;
  onSuccess: () => void;
  onCancel: () => void;
};

export function ActivityForm({ dealId, contactId, companyId, onSuccess, onCancel }: Props) {
  const [type, setType] = useState("call");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);

    const form = new FormData(e.currentTarget);
    const data = {
      type,
      subject: form.get("subject") as string,
      description: (form.get("description") as string) || null,
      dueDate: (form.get("dueDate") as string) || null,
      isDone: false,
      dealId: dealId || null,
      contactId: contactId || null,
      companyId: companyId || null,
    };

    const res = await fetch("/api/activities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    setLoading(false);
    if (res.ok) onSuccess();
  }

  return (
    <Card>
      <CardContent className="pt-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex gap-2">
            {activityTypes.map((t) => (
              <Button
                key={t.value}
                type="button"
                variant={type === t.value ? "default" : "outline"}
                size="sm"
                onClick={() => setType(t.value)}
                className="gap-1"
              >
                <t.icon className="h-3 w-3" />
                {t.label}
              </Button>
            ))}
          </div>
          <div className="space-y-2">
            <Label htmlFor="subject">Subject</Label>
            <Input id="subject" name="subject" required placeholder="What needs to be done?" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" name="description" placeholder="Optional details..." rows={2} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="dueDate">Due Date</Label>
            <Input id="dueDate" name="dueDate" type="date" defaultValue={new Date().toISOString().split("T")[0]} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={loading}>
              {loading ? "Adding..." : "Add Activity"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
