import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, HelpCircle, Wrench } from "lucide-react";

import type { RfqSummary } from "@/lib/api/types";

const STATS: {
  key: keyof RfqSummary;
  label: string;
  icon: typeof CheckCircle2;
  className: string;
}[] = [
  {
    key: "extracted",
    label: "Extracted",
    icon: CheckCircle2,
    className: "text-emerald-600",
  },
  {
    key: "conflict",
    label: "Conflicts",
    icon: AlertTriangle,
    className: "text-amber-600",
  },
  {
    key: "tbd",
    label: "TBD",
    icon: HelpCircle,
    className: "text-muted-foreground",
  },
  {
    key: "vtf",
    label: "VTF",
    icon: Wrench,
    className: "text-blue-600",
  },
];

/**
 * Aggregate result of a generated RFQ. Shows the field-level confidence counts
 * (per F-04 status: extracted / conflict / tbd / vtf) so the engineer can gauge
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
          {STATS.map(({ key, label, icon: Icon, className }) => (
            <div
              key={key}
              className="flex flex-col items-center rounded-md border p-3"
            >
              <Icon className={`h-5 w-5 ${className}`} />
              <span className="mt-1 text-2xl font-bold tabular-nums">
                {summary[key]}
              </span>
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          The populated datasheet is saved as a document — download it from the
          documents table below.
        </p>
      </CardContent>
    </Card>
  );
}
