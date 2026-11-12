"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";
import { Phone, Mail, Calendar, CheckSquare, StickyNote } from "lucide-react";
import Link from "next/link";

const typeIcons = {
  call: Phone,
  email: Mail,
  meeting: Calendar,
  task: CheckSquare,
  note: StickyNote,
};

const typeColors: Record<string, string> = {
  call: "bg-blue-100 text-blue-800",
  email: "bg-purple-100 text-purple-800",
  meeting: "bg-orange-100 text-orange-800",
  task: "bg-green-100 text-green-800",
  note: "bg-gray-100 text-gray-800",
};

type Props = {
  activity: {
    id: number;
    type: string;
    subject: string;
    dueDate: string | null;
    isDone: boolean;
    dealId?: number | null;
    dealTitle?: string | null;
    contactId?: number | null;
    contactFirstName?: string | null;
    contactLastName?: string | null;
    companyId?: number | null;
    companyName?: string | null;
  };
  onToggle: () => void;
};

export function ActivityItem({ activity, onToggle }: Props) {
  const Icon = typeIcons[activity.type as keyof typeof typeIcons] || StickyNote;

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border">
      <Checkbox
        checked={activity.isDone}
        onCheckedChange={onToggle}
        className="mt-0.5"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className={`text-sm font-medium ${activity.isDone ? "line-through text-muted-foreground" : ""}`}>
            {activity.subject}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className={`text-xs ${typeColors[activity.type]}`}>
            {activity.type}
          </Badge>
          {activity.dueDate && (
            <span className="text-xs text-muted-foreground">
              {formatDate(activity.dueDate)}
            </span>
          )}
          {activity.dealTitle && (
            <Link href={`/deals/${activity.dealId}`} className="text-xs text-primary hover:underline">
              {activity.dealTitle}
            </Link>
          )}
          {activity.contactFirstName && (
            <Link href={`/contacts/${activity.contactId}`} className="text-xs text-primary hover:underline">
              {activity.contactFirstName} {activity.contactLastName}
            </Link>
          )}
          {activity.companyName && (
            <Link href={`/companies/${activity.companyId}`} className="text-xs text-primary hover:underline">
              {activity.companyName}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
