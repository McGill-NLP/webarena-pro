"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/shared/data-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Search, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

type Company = {
  id: number;
  name: string;
  domain: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  createdAt: string;
};

export default function CompaniesPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Company | null>(null);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    const res = await fetch(`/api/companies?search=${encodeURIComponent(search)}&limit=100`);
    if (res.ok) {
      const data = await res.json();
      setCompanies(data.data);
    }
  }, [search]);

  useEffect(() => { load(); }, [load]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setFormError("");
    const form = new FormData(e.currentTarget);
    const phone = (form.get("phone") as string) || null;

    if (phone && !/^\+?[\d\s\-().]{7,20}$/.test(phone)) {
      setFormError("Invalid phone number");
      setLoading(false);
      return;
    }

    const data = {
      name: form.get("name") as string,
      domain: (form.get("domain") as string) || null,
      phone,
      address: (form.get("address") as string) || null,
      notes: (form.get("notes") as string) || null,
    };

    const url = editing ? `/api/companies/${editing.id}` : "/api/companies";
    const method = editing ? "PATCH" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    setLoading(false);
    if (res.ok) {
      toast.success(editing ? "Company updated" : "Company created");
      setShowForm(false);
      setEditing(null);
      load();
    } else {
      const err = await res.json().catch(() => null);
      toast.error(err?.error?.fieldErrors?.phone?.[0] || "Failed to save company");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    const res = await fetch(`/api/companies/${deleteTarget.id}`, { method: "DELETE" });
    if (res.ok) {
      toast.success("Company deleted");
      load();
    } else {
      const err = await res.json().catch(() => null);
      toast.error(err?.error || "Failed to delete company");
    }
    setDeleteTarget(null);
  }

  const columns: ColumnDef<Company>[] = [
    { accessorKey: "name", header: "Name" },
    { accessorKey: "domain", header: "Domain" },
    { accessorKey: "phone", header: "Phone" },
    {
      id: "actions",
      cell: ({ row }) => (
        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => { setEditing(row.original); setShowForm(true); }}
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-destructive"
            onClick={() => setDeleteTarget(row.original)}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Companies</h1>
        <Button onClick={() => { setEditing(null); setFormError(""); setShowForm(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add Company
        </Button>
      </div>

      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search companies..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      <DataTable
        columns={columns}
        data={companies}
        onRowClick={(row) => router.push(`/companies/${row.id}`)}
      />

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Company" : "New Company"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" name="name" defaultValue={editing?.name} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="domain">Domain</Label>
              <Input id="domain" name="domain" defaultValue={editing?.domain || ""} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">Phone</Label>
              <Input id="phone" name="phone" defaultValue={editing?.phone || ""} placeholder="+1-555-0100" />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="address">Address</Label>
              <Input id="address" name="address" defaultValue={editing?.address || ""} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="notes">Notes</Label>
              <Textarea id="notes" name="notes" defaultValue={editing?.notes || ""} />
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? "Saving..." : editing ? "Update" : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title="Delete Company"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This cannot be undone.`}
        onConfirm={handleDelete}
        destructive
      />
    </div>
  );
}
