"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, GripVertical, Trash2, Save } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";

type Stage = {
  id: number;
  name: string;
  position: number;
  probability: number;
  pipelineId: number;
};

export default function SettingsPage() {
  const [stages, setStages] = useState<Stage[]>([]);
  const [pipelineId, setPipelineId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Stage | null>(null);
  const [newStageName, setNewStageName] = useState("");

  async function loadStages() {
    const pipRes = await fetch("/api/pipelines");
    if (!pipRes.ok) return;
    const pips = await pipRes.json();
    if (pips.length === 0) return;
    setPipelineId(pips[0].id);

    const stagesRes = await fetch(`/api/stages?pipelineId=${pips[0].id}`);
    if (stagesRes.ok) setStages(await stagesRes.json());
  }

  useEffect(() => { loadStages(); }, []);

  async function addStage() {
    if (!newStageName.trim() || !pipelineId) return;
    const maxPos = stages.length > 0 ? Math.max(...stages.map((s) => s.position)) + 1 : 0;
    const res = await fetch("/api/stages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newStageName.trim(),
        position: maxPos,
        probability: 0,
        pipelineId,
      }),
    });
    if (res.ok) {
      toast.success("Stage added");
      setNewStageName("");
      loadStages();
    }
  }

  async function updateStage(stage: Stage, updates: Partial<Stage>) {
    const res = await fetch(`/api/stages/${stage.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (res.ok) {
      toast.success("Stage updated");
      loadStages();
    }
  }

  async function deleteStage() {
    if (!deleteTarget) return;
    const res = await fetch(`/api/stages/${deleteTarget.id}`, { method: "DELETE" });
    if (res.ok) {
      toast.success("Stage deleted");
      loadStages();
    } else {
      const data = await res.json();
      toast.error(data.error || "Failed to delete stage");
    }
    setDeleteTarget(null);
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pipeline Stages</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {stages
            .sort((a, b) => a.position - b.position)
            .map((stage) => (
              <div key={stage.id} className="flex items-center gap-3 p-2 border rounded-md">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
                <Input
                  defaultValue={stage.name}
                  className="flex-1"
                  onBlur={(e) => {
                    if (e.target.value !== stage.name) {
                      updateStage(stage, { name: e.target.value });
                    }
                  }}
                />
                <div className="flex items-center gap-1">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    defaultValue={stage.probability}
                    className="w-20"
                    onBlur={(e) => {
                      const val = parseInt(e.target.value);
                      if (val !== stage.probability) {
                        updateStage(stage, { probability: val });
                      }
                    }}
                  />
                  <span className="text-sm text-muted-foreground">%</span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive"
                  onClick={() => setDeleteTarget(stage)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}

          <div className="flex gap-2 pt-2">
            <Input
              placeholder="New stage name..."
              value={newStageName}
              onChange={(e) => setNewStageName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addStage()}
            />
            <Button onClick={addStage} disabled={!newStageName.trim()}>
              <Plus className="h-4 w-4 mr-2" />
              Add Stage
            </Button>
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title="Delete Stage"
        description={`Delete "${deleteTarget?.name}"? This only works if no deals are in this stage.`}
        onConfirm={deleteStage}
        destructive
      />
    </div>
  );
}
