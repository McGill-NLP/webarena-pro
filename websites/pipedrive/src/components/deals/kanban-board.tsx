"use client";

import { useState, useCallback, useEffect } from "react";
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragStartEvent,
  DragEndEvent,
  DragOverEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { KanbanColumn } from "./kanban-column";
import { KanbanCard } from "./kanban-card";
import { DealFormDialog } from "./deal-form";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { toast } from "sonner";

export type Deal = {
  id: number;
  title: string;
  value: number;
  status: string;
  position: number;
  expectedCloseDate: string | null;
  stageId: number;
  stageName: string | null;
  contactId: number | null;
  contactFirstName: string | null;
  contactLastName: string | null;
  companyId: number | null;
  companyName: string | null;
  pipelineId: number;
};

export type Stage = {
  id: number;
  name: string;
  position: number;
  probability: number;
  pipelineId: number;
};

type Props = {
  initialDeals: Deal[];
  stages: Stage[];
  pipelineId: number;
  contacts: { id: number; firstName: string; lastName: string; companyId: number | null }[];
  companies: { id: number; name: string }[];
};

export function KanbanBoard({ initialDeals, stages, pipelineId, contacts, companies }: Props) {
  const [deals, setDeals] = useState<Deal[]>(initialDeals);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingDeal, setEditingDeal] = useState<Deal | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const activeDeal = deals.find((d) => d.id === activeId);

  function getDealsByStage(stageId: number) {
    return deals
      .filter((d) => d.stageId === stageId && d.status !== "lost")
      .sort((a, b) => a.position - b.position);
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as number);
  }

  function handleDragOver(event: DragOverEvent) {
    const { active, over } = event;
    if (!over) return;

    const activeId = active.id as number;
    const overId = over.id;

    const activeDeal = deals.find((d) => d.id === activeId);
    if (!activeDeal) return;

    // Determine target stage
    let targetStageId: number;
    const overDeal = deals.find((d) => d.id === overId);
    if (overDeal) {
      targetStageId = overDeal.stageId;
    } else {
      // Over a column
      targetStageId = overId as number;
    }

    if (activeDeal.stageId !== targetStageId) {
      setDeals((prev) => {
        const updated = prev.map((d) =>
          d.id === activeId ? { ...d, stageId: targetStageId } : d
        );
        return updated;
      });
    }
  }

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    const activeId = active.id as number;
    const overId = over.id;

    const activeDeal = deals.find((d) => d.id === activeId);
    if (!activeDeal) return;

    let targetStageId = activeDeal.stageId;
    let newPosition = 0;

    const overDeal = deals.find((d) => d.id === overId);
    if (overDeal) {
      targetStageId = overDeal.stageId;
      const stageDeals = getDealsByStage(targetStageId).filter((d) => d.id !== activeId);
      const overIndex = stageDeals.findIndex((d) => d.id === overId);
      newPosition = overIndex >= 0 ? overIndex : stageDeals.length;
    } else {
      targetStageId = overId as number;
      newPosition = getDealsByStage(targetStageId).filter((d) => d.id !== activeId).length;
    }

    // Optimistic update
    setDeals((prev) => {
      const updated = prev.map((d) =>
        d.id === activeId ? { ...d, stageId: targetStageId, position: newPosition } : d
      );
      // Re-index positions
      const stageDeals = updated
        .filter((d) => d.stageId === targetStageId && d.id !== activeId)
        .sort((a, b) => a.position - b.position);
      stageDeals.splice(newPosition, 0, { ...activeDeal, stageId: targetStageId });
      const reindexed = stageDeals.map((d, i) => ({ ...d, position: i }));

      return updated.map((d) => {
        const reindexedDeal = reindexed.find((r) => r.id === d.id);
        return reindexedDeal || d;
      });
    });

    try {
      await fetch("/api/deals/reorder", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dealId: activeId, newStageId: targetStageId, newPosition }),
      });
    } catch {
      toast.error("Failed to reorder deal");
    }
  }

  async function handleDealCreated() {
    const res = await fetch(`/api/deals?pipelineId=${pipelineId}`);
    if (res.ok) setDeals(await res.json());
    setShowForm(false);
    setEditingDeal(null);
    toast.success("Deal saved");
  }

  async function handleDealDeleted(dealId: number) {
    await fetch(`/api/deals/${dealId}`, { method: "DELETE" });
    setDeals((prev) => prev.filter((d) => d.id !== dealId));
    toast.success("Deal deleted");
  }

  const stageValue = (stageId: number) =>
    deals
      .filter((d) => d.stageId === stageId)
      .reduce((sum, d) => sum + d.value, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Deals</h1>
        <Button onClick={() => { setEditingDeal(null); setShowForm(true); }}>
          <Plus className="h-4 w-4 mr-2" />
          Add Deal
        </Button>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-4 overflow-x-auto pb-4">
          {stages
            .sort((a, b) => a.position - b.position)
            .map((stage) => (
              <KanbanColumn
                key={stage.id}
                stage={stage}
                deals={getDealsByStage(stage.id)}
                totalValue={stageValue(stage.id)}
                onEdit={(deal) => { setEditingDeal(deal); setShowForm(true); }}
                onDelete={handleDealDeleted}
              />
            ))}
        </div>

        <DragOverlay>
          {activeDeal ? <KanbanCard deal={activeDeal} isOverlay /> : null}
        </DragOverlay>
      </DndContext>

      <DealFormDialog
        open={showForm}
        onOpenChange={setShowForm}
        deal={editingDeal}
        stages={stages}
        contacts={contacts}
        companies={companies}
        pipelineId={pipelineId}
        onSuccess={handleDealCreated}
      />
    </div>
  );
}
