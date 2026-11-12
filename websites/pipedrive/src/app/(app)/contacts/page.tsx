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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Search, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

type Contact = {
  id: number;
  firstName: string;
  lastName: string;
  email: string | null;
  phone: string | null;
  jobTitle: string | null;
  companyId: number | null;
  companyName: string | null;
  createdAt: string;
};

export default function ContactsPage() {
  const router = useRouter();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [companies, setCompanies] = useState<{ id: number; name: string }[]>([]);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Contact | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Contact | null>(null);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    const res = await fetch(`/api/contacts?search=${encodeURIComponent(search)}&limit=100`);
    if (res.ok) {
      const data = await res.json();
      setContacts(data.data);
    }
  }, [search]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetch("/api/companies?limit=100").then((r) => r.ok && r.json()).then((d) => setCompanies(d?.data || []));
  }, []);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setFormError("");
    const form = new FormData(e.currentTarget);
    const companyIdVal = form.get("companyId") as string;
    const phone = (form.get("phone") as string) || null;

    if (phone && !/^\+?[\d\s\-().]{7,20}$/.test(phone)) {
      setFormError("Invalid phone number");
      setLoading(false);
      return;
    }

    const data = {
      firstName: form.get("firstName") as string,
      lastName: form.get("lastName") as string,
      email: (form.get("email") as string) || null,
      phone,
      jobTitle: (form.get("jobTitle") as string) || null,
      companyId: companyIdVal && companyIdVal !== "none" ? parseInt(companyIdVal) : null,
    };

    const url = editing ? `/api/contacts/${editing.id}` : "/api/contacts";
    const method = editing ? "PATCH" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    setLoading(false);
    if (res.ok) {
      toast.success(editing ? "Contact updated" : "Contact created");
      setShowForm(false);
      setEditing(null);
      load();
    } else {
      const err = await res.json().catch(() => null);
      toast.error(err?.error?.fieldErrors?.phone?.[0] || "Failed to save contact");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    await fetch(`/api/contacts/${deleteTarget.id}`, { method: "DELETE" });
    toast.success("Contact deleted");
    load();
    setDeleteTarget(null);
  }

  const columns: ColumnDef<Contact>[] = [
    {
      id: "name",
      header: "Name",
      accessorFn: (row) => `${row.firstName} ${row.lastName}`,
    },
    { accessorKey: "email", header: "Email" },
    { accessorKey: "phone", header: "Phone" },
    { accessorKey: "jobTitle", header: "Job Title" },
    { accessorKey: "companyName", header: "Company" },
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
        <h1 className="text-2xl font-bold">Contacts</h1>
        <Button onClick={() => { setEditing(null); setFormError(""); setShowForm(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add Contact
        </Button>
      </div>

      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search contacts..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      <DataTable
        columns={columns}
        data={contacts}
        onRowClick={(row) => router.push(`/contacts/${row.id}`)}
      />

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Contact" : "New Contact"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="firstName">First Name</Label>
                <Input id="firstName" name="firstName" defaultValue={editing?.firstName} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lastName">Last Name</Label>
                <Input id="lastName" name="lastName" defaultValue={editing?.lastName} required />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" name="email" type="email" defaultValue={editing?.email || ""} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">Phone</Label>
              <Input id="phone" name="phone" defaultValue={editing?.phone || ""} placeholder="+1-555-0100" />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="jobTitle">Job Title</Label>
              <Input id="jobTitle" name="jobTitle" defaultValue={editing?.jobTitle || ""} />
            </div>
            <div className="space-y-2">
              <Label>Company</Label>
              <Select name="companyId" defaultValue={editing?.companyId ? String(editing.companyId) : "none"}>
                <SelectTrigger>
                  <SelectValue placeholder="Select company..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No company</SelectItem>
                  {companies.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
        title="Delete Contact"
        description={`Are you sure you want to delete "${deleteTarget?.firstName} ${deleteTarget?.lastName}"?`}
        onConfirm={handleDelete}
        destructive
      />
    </div>
  );
}
