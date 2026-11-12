"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal, Pencil, Trash2, Calendar, User, Building2 } from "lucide-react";
import { formatCurrency, formatDate } from "@/lib/utils";
import Link from "next/link";
import type { Deal } from "./kanban-board";

type Props = {
  deal: Deal;
  isOverlay?: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
};

export function KanbanCard({ deal, isOverlay, onEdit, onDelete }: Props) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: deal.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={`p-3 cursor-grab active:cursor-grabbing ${
        isOverlay ? "shadow-lg ring-2 ring-primary" : ""
      }`}
    >
      <div className="flex items-start justify-between">
        <Link href={`/deals/${deal.id}`} className="hover:underline flex-1" onClick={(e) => e.stopPropagation()}>
          <h4 className="text-sm font-medium leading-tight">{deal.title}</h4>
        </Link>
        {!isOverlay && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreHorizontal className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onEdit}>
                <Pencil className="h-3 w-3 mr-2" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onDelete} className="text-destructive">
                <Trash2 className="h-3 w-3 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      <p className="text-sm font-semibold text-primary mt-1">
        {formatCurrency(deal.value)}
      </p>
      <div className="flex flex-wrap gap-1 mt-2 text-xs text-muted-foreground">
        {deal.contactFirstName && (
          <span className="flex items-center gap-1">
            <User className="h-3 w-3" />
            {deal.contactFirstName} {deal.contactLastName}
          </span>
        )}
        {deal.companyName && (
          <span className="flex items-center gap-1">
            <Building2 className="h-3 w-3" />
            {deal.companyName}
          </span>
        )}
        {deal.expectedCloseDate && (
          <span className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {formatDate(deal.expectedCloseDate)}
          </span>
        )}
      </div>
    </Card>
  );
}
