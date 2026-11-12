"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { DollarSign, Handshake, Target, CalendarCheck, Phone, Mail, Calendar, CheckSquare, StickyNote, Filter, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const PIE_COLORS = ["#22c55e", "#ef4444"];

const typeIcons: Record<string, React.ElementType> = {
  call: Phone,
  email: Mail,
  meeting: Calendar,
  task: CheckSquare,
  note: StickyNote,
};

const PERIOD_OPTIONS = [
  { value: "all", label: "All time" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "6m", label: "Last 6 months" },
  { value: "1y", label: "Last year" },
];

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [period, setPeriod] = useState("all");
  const [stageId, setStageId] = useState("all");

  const load = useCallback(() => {
    const params = new URLSearchParams({ period });
    if (stageId !== "all") params.set("stageId", stageId);
    fetch(`/api/dashboard?${params}`)
      .then((r) => r.ok && r.json())
      .then((d) => d && setData(d));
  }, [period, stageId]);

  useEffect(() => { load(); }, [load]);

  const hasActiveFilters = period !== "all" || stageId !== "all";

  function clearFilters() {
    setPeriod("all");
    setStageId("all");
  }

  if (!data) return <div className="p-6 text-muted-foreground">Loading dashboard...</div>;

  const { summary, dealsByStage, forecast, wonLost, recentActivities, stages } = data;

  const periodLabel = PERIOD_OPTIONS.find((o) => o.value === period)?.label ?? "All time";
  const stageLabel = stageId !== "all"
    ? (stages as { id: number; name: string }[]).find((s) => String(s.id) === stageId)?.name
    : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>

        {/* Filter bar */}
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />

          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-40 h-8 text-sm">
              <SelectValue placeholder="Period" />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={stageId} onValueChange={setStageId}>
            <SelectTrigger className="w-40 h-8 text-sm">
              <SelectValue placeholder="All stages" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All stages</SelectItem>
              {(stages as { id: number; name: string }[]).map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {hasActiveFilters && (
            <Button variant="ghost" size="sm" className="h-8 px-2 text-muted-foreground" onClick={clearFilters}>
              <X className="h-3 w-3 mr-1" />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Active filter badges */}
      {hasActiveFilters && (
        <div className="flex gap-2 mb-4">
          {period !== "all" && (
            <Badge variant="secondary" className="text-xs gap-1">
              {periodLabel}
              <button onClick={() => setPeriod("all")} className="ml-1 hover:text-foreground">×</button>
            </Badge>
          )}
          {stageLabel && (
            <Badge variant="secondary" className="text-xs gap-1">
              Stage: {stageLabel}
              <button onClick={() => setStageId("all")} className="ml-1 hover:text-foreground">×</button>
            </Badge>
          )}
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Handshake className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Open Deals</p>
                <p className="text-2xl font-bold">{summary.openDeals}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <DollarSign className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Pipeline Value</p>
                <p className="text-2xl font-bold">{formatCurrency(summary.totalOpenValue)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-100 rounded-lg">
                <Target className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Win Rate</p>
                <p className="text-2xl font-bold">{summary.winRate}%</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-orange-100 rounded-lg">
                <CalendarCheck className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Activities This Week</p>
                <p className="text-2xl font-bold">{summary.activitiesThisWeek}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Deals by Stage</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={dealsByStage}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="stage" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip formatter={(value) => formatCurrency(Number(value))} />
                <Bar
                  dataKey="value"
                  radius={[4, 4, 0, 0]}
                >
                  {dealsByStage.map((entry: any) => (
                    <Cell
                      key={entry.stageId}
                      fill={stageId !== "all" && String(entry.stageId) === stageId ? "#2563eb" : "#3b82f6"}
                      opacity={stageId !== "all" && String(entry.stageId) !== stageId ? 0.35 : 1}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Revenue Forecast</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={forecast}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip formatter={(value) => formatCurrency(Number(value))} />
                <Area type="monotone" dataKey="total" stroke="#94a3b8" fill="#f1f5f9" name="Total" />
                <Area type="monotone" dataKey="weighted" stroke="#3b82f6" fill="#dbeafe" name="Weighted" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Won vs Lost</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={wonLost}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {wonLost.map((_: any, idx: number) => (
                    <Cell key={idx} fill={PIE_COLORS[idx]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentActivities.map((a: any) => {
                const Icon = typeIcons[a.type] || StickyNote;
                return (
                  <div key={a.id} className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className={`text-sm flex-1 ${a.isDone ? "line-through text-muted-foreground" : ""}`}>
                      {a.subject}
                    </span>
                    <Badge variant="outline" className="text-xs shrink-0">{a.type}</Badge>
                  </div>
                );
              })}
              {recentActivities.length === 0 && (
                <p className="text-sm text-muted-foreground">No recent activities</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
