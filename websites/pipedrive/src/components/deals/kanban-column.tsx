"use client";

import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { KanbanCard } from "./kanban-card";
import { formatCurrency } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Deal, Stage } from "./kanban-board";

type Props = {
  stage: Stage;
  deals: Deal[];
  totalValue: number;
  onEdit: (deal: Deal) => void;
  onDelete: (dealId: number) => void;
};

export function KanbanColumn({ stage, deals, totalValue, onEdit, onDelete }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col w-72 min-w-72 rounded-lg bg-muted/50 ${
        isOver ? "ring-2 ring-primary/50" : ""
      }`}
    >
      <div className="p-3 border-b">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm">{stage.name}</h3>
          <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">
            {deals.length}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {formatCurrency(totalValue)}
        </p>
      </div>
      <ScrollArea className="flex-1 p-2" style={{ maxHeight: "calc(100vh - 240px)" }}>
        <SortableContext
          items={deals.map((d) => d.id)}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-2 min-h-[40px]">
            {deals.map((deal) => (
              <KanbanCard
                key={deal.id}
                deal={deal}
                onEdit={() => onEdit(deal)}
                onDelete={() => onDelete(deal.id)}
              />
            ))}
          </div>
        </SortableContext>
      </ScrollArea>
    </div>
  );
}
