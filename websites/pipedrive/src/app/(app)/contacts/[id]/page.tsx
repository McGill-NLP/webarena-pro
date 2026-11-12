"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Mail, Phone, Briefcase, Building2, Handshake } from "lucide-react";
import { formatCurrency } from "@/lib/utils";
import { ActivityForm } from "@/components/activities/activity-form";
import { ActivityItem } from "@/components/activities/activity-item";
import Link from "next/link";
import { toast } from "sonner";

export default function ContactDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [contact, setContact] = useState<any>(null);
  const [deals, setDeals] = useState<any[]>([]);
  const [activities, setActivities] = useState<any[]>([]);
  const [showActivityForm, setShowActivityForm] = useState(false);

  function loadData() {
    fetch(`/api/contacts/${id}`).then((r) => r.ok && r.json()).then(setContact);
    fetch(`/api/deals`).then((r) => r.ok && r.json()).then((d) =>
      setDeals((d || []).filter((deal: any) => deal.contactId === parseInt(id as string)))
    );
    fetch(`/api/activities?contactId=${id}`).then((r) => r.ok && r.json()).then(setActivities);
  }

  useEffect(() => { loadData(); }, [id]);

  if (!contact) return <div>Loading...</div>;

  return (
    <div className="max-w-4xl">
      <Button variant="ghost" size="sm" onClick={() => router.back()} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back
      </Button>

      <h1 className="text-2xl font-bold mb-6">
        {contact.firstName} {contact.lastName}
      </h1>

      <Card className="mb-6">
        <CardContent className="pt-6 space-y-3">
          {contact.email && (
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span>{contact.email}</span>
            </div>
          )}
          {contact.phone && (
            <div className="flex items-center gap-2">
              <Phone className="h-4 w-4 text-muted-foreground" />
              <span>{contact.phone}</span>
            </div>
          )}
          {contact.jobTitle && (
            <div className="flex items-center gap-2">
              <Briefcase className="h-4 w-4 text-muted-foreground" />
              <span>{contact.jobTitle}</span>
            </div>
          )}
          {contact.companyName && (
            <Link href={`/companies/${contact.companyId}`} className="flex items-center gap-2 hover:underline">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <span>{contact.companyName}</span>
            </Link>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Handshake className="h-4 w-4" />
              Deals ({deals.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {deals.length === 0 ? (
              <p className="text-sm text-muted-foreground">No deals</p>
            ) : (
              <div className="space-y-2">
                {deals.map((d: any) => (
                  <Link
                    key={d.id}
                    href={`/deals/${d.id}`}
                    className="flex items-center justify-between p-2 rounded hover:bg-muted"
                  >
                    <div>
                      <p className="text-sm font-medium">{d.title}</p>
                      <p className="text-xs text-muted-foreground">{d.stageName}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold">{formatCurrency(d.value)}</p>
                      <Badge variant="outline" className="text-xs">{d.status}</Badge>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Activities</CardTitle>
            <Button size="sm" onClick={() => setShowActivityForm(true)}>Add</Button>
          </CardHeader>
          <CardContent>
            {showActivityForm && (
              <div className="mb-4">
                <ActivityForm
                  contactId={parseInt(id as string)}
                  onSuccess={() => {
                    setShowActivityForm(false);
                    loadData();
                    toast.success("Activity added");
                  }}
                  onCancel={() => setShowActivityForm(false)}
                />
              </div>
            )}
            {activities.length === 0 ? (
              <p className="text-sm text-muted-foreground">No activities</p>
            ) : (
              <div className="space-y-2">
                {activities.map((a: any) => (
                  <ActivityItem
                    key={a.id}
                    activity={a}
                    onToggle={async () => {
                      await fetch(`/api/activities/${a.id}`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ isDone: !a.isDone }),
                      });
                      loadData();
                    }}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
