import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, HelpCircle, Wrench } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RfqSummary } from "@/lib/api/types";

type Tone = "success" | "danger" | "warning" | "info";

const STATS: {
  key: keyof RfqSummary;
  label: string;
  icon: typeof CheckCircle2;
  tone: Tone;
}[] = [
  { key: "extracted", label: "Extracted", icon: CheckCircle2, tone: "success" },
  { key: "conflict", label: "Conflicts", icon: AlertTriangle, tone: "danger" },
  { key: "tbd", label: "TBD", icon: HelpCircle, tone: "warning" },
  { key: "vtf", label: "VTF", icon: Wrench, tone: "info" },
];

const TONE_TILE: Record<Tone, string> = {
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
};

/**
 * Aggregate result of a generated RFQ. Shows the field-level status counts
 * (per F-04: extracted / conflict / tbd / vtf) so the engineer can gauge
 * output quality at a glance. Full per-field detail lives in the .xlsx file.
 */
export function RfqSummaryCard({ summary }: { summary: RfqSummary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Generation summary · {summary.fields_total} fields
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {STATS.map(({ key, label, icon: Icon, tone }) => (
            <div
              key={key}
              className="flex flex-col items-center rounded-control border border-border p-3"
            >
              <div
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-tile",
                  TONE_TILE[tone],
                )}
                aria-hidden="true"
              >
                <Icon className="h-5 w-5" />
              </div>
              <span className="mt-2 text-2xl font-bold tabular-nums text-text-primary">
                {summary[key]}
              </span>
              <span className="text-xs text-text-muted">{label}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-text-muted">
          The populated datasheet is saved as a document — download it from the
          documents table below.
        </p>
      </CardContent>
    </Card>
  );
}
