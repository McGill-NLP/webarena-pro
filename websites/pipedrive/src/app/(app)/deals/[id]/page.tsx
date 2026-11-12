"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { formatCurrency, formatDate } from "@/lib/utils";
import { ActivityForm } from "@/components/activities/activity-form";
import { ActivityItem } from "@/components/activities/activity-item";
import {
  ArrowLeft,
  Trophy,
  XCircle,
  Building2,
  User,
  Calendar,
  DollarSign,
  Target,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

export default function DealDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [deal, setDeal] = useState<any>(null);
  const [showActivityForm, setShowActivityForm] = useState(false);

  async function loadDeal() {
    const res = await fetch(`/api/deals/${id}`);
    if (res.ok) setDeal(await res.json());
  }

  useEffect(() => { loadDeal(); }, [id]);

  async function markStatus(status: "won" | "lost") {
    const res = await fetch(`/api/deals/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (res.ok) {
      toast.success(`Deal marked as ${status}`);
      loadDeal();
    }
  }

  if (!deal) return <div className="p-6">Loading...</div>;

  const statusColors: Record<string, string> = {
    open: "bg-blue-100 text-blue-800",
    won: "bg-green-100 text-green-800",
    lost: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-4xl">
      <Button variant="ghost" size="sm" onClick={() => router.back()} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Deals
      </Button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{deal.title}</h1>
          <Badge className={`mt-2 ${statusColors[deal.status]}`}>
            {deal.status.toUpperCase()}
          </Badge>
        </div>
        {deal.status === "open" && (
          <div className="flex gap-2">
            <Button variant="outline" className="text-green-600" onClick={() => markStatus("won")}>
              <Trophy className="h-4 w-4 mr-2" />
              Mark Won
            </Button>
            <Button variant="outline" className="text-red-600" onClick={() => markStatus("lost")}>
              <XCircle className="h-4 w-4 mr-2" />
              Mark Lost
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Deal Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <span className="font-semibold">{formatCurrency(deal.value)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Target className="h-4 w-4 text-muted-foreground" />
              <span>{deal.stageName} ({deal.stageProbability}%)</span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <span>{formatDate(deal.expectedCloseDate) || "No close date"}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Related</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {deal.contactFirstName && (
              <Link href={`/contacts/${deal.contactId}`} className="flex items-center gap-2 hover:underline">
                <User className="h-4 w-4 text-muted-foreground" />
                <span>{deal.contactFirstName} {deal.contactLastName}</span>
              </Link>
            )}
            {deal.companyName && (
              <Link href={`/companies/${deal.companyId}`} className="flex items-center gap-2 hover:underline">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span>{deal.companyName}</span>
              </Link>
            )}
          </CardContent>
        </Card>
      </div>

      <Separator className="my-6" />

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Activities</h2>
        <Button size="sm" onClick={() => setShowActivityForm(true)}>Add Activity</Button>
      </div>

      {showActivityForm && (
        <div className="mb-4">
          <ActivityForm
            dealId={deal.id}
            contactId={deal.contactId}
            companyId={deal.companyId}
            onSuccess={() => {
              setShowActivityForm(false);
              loadDeal();
              toast.success("Activity added");
            }}
            onCancel={() => setShowActivityForm(false)}
          />
        </div>
      )}

      <div className="space-y-2">
        {deal.activities?.length === 0 && (
          <p className="text-sm text-muted-foreground">No activities yet.</p>
        )}
        {deal.activities?.map((activity: any) => (
          <ActivityItem
            key={activity.id}
            activity={activity}
            onToggle={async () => {
              await fetch(`/api/activities/${activity.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ isDone: !activity.isDone }),
              });
              loadDeal();
            }}
          />
        ))}
      </div>
    </div>
  );
}
