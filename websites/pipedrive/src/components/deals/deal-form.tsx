"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Deal, Stage } from "./kanban-board";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deal: Deal | null;
  stages: Stage[];
  contacts: { id: number; firstName: string; lastName: string; companyId: number | null }[];
  companies: { id: number; name: string }[];
  pipelineId: number;
  onSuccess: () => void;
};

export function DealFormDialog({
  open,
  onOpenChange,
  deal,
  stages,
  contacts,
  companies,
  pipelineId,
  onSuccess,
}: Props) {
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);

    const form = new FormData(e.currentTarget);
    const data = {
      title: form.get("title") as string,
      value: parseFloat(form.get("value") as string) || 0,
      stageId: parseInt(form.get("stageId") as string),
      contactId: form.get("contactId") ? parseInt(form.get("contactId") as string) : null,
      companyId: form.get("companyId") ? parseInt(form.get("companyId") as string) : null,
      expectedCloseDate: (form.get("expectedCloseDate") as string) || null,
      pipelineId,
    };

    const url = deal ? `/api/deals/${deal.id}` : "/api/deals";
    const method = deal ? "PATCH" : "POST";

    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    setLoading(false);
    if (res.ok) onSuccess();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{deal ? "Edit Deal" : "New Deal"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input id="title" name="title" defaultValue={deal?.title} required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="value">Value ($)</Label>
            <Input
              id="value"
              name="value"
              type="number"
              step="0.01"
              defaultValue={deal?.value || ""}
            />
          </div>
          <div className="space-y-2">
            <Label>Stage</Label>
            <Select name="stageId" defaultValue={String(deal?.stageId || stages[0]?.id)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {stages
                  .sort((a, b) => a.position - b.position)
                  .map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Contact</Label>
            <Select name="contactId" defaultValue={deal?.contactId ? String(deal.contactId) : ""}>
              <SelectTrigger>
                <SelectValue placeholder="Select contact..." />
              </SelectTrigger>
              <SelectContent>
                {contacts.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.firstName} {c.lastName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Company</Label>
            <Select name="companyId" defaultValue={deal?.companyId ? String(deal.companyId) : ""}>
              <SelectTrigger>
                <SelectValue placeholder="Select company..." />
              </SelectTrigger>
              <SelectContent>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="expectedCloseDate">Expected Close Date</Label>
            <Input
              id="expectedCloseDate"
              name="expectedCloseDate"
              type="date"
              defaultValue={deal?.expectedCloseDate || ""}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Saving..." : deal ? "Update" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
