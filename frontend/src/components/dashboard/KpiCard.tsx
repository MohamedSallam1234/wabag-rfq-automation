import type { LucideIcon } from "lucide-react";
import { Building2, FileText, PackageCheck } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Semantic tone — maps to a soft-tint tile bg + solid icon/number color. */
export type KpiTone = "info" | "success" | "extraction";

const TONE_CLASSES: Record<
  KpiTone,
  { tile: string; icon: string; value: string }
> = {
  info: {
    tile: "bg-info-soft",
    icon: "text-info",
    value: "text-text-primary",
  },
  success: {
    tile: "bg-success-soft",
    icon: "text-success",
    value: "text-text-primary",
  },
  extraction: {
    tile: "bg-extraction-soft",
    icon: "text-extraction",
    value: "text-text-primary",
  },
};

export interface KpiCardProps {
  tone: KpiTone;
  icon: LucideIcon;
  label: string;
  value: number | string;
  caption?: string;
  isLoading?: boolean;
  className?: string;
}

/** Single stat card (DESIGN.md §8.4). No trend line — no historical data. */
export function KpiCard({
  tone,
  icon: Icon,
  label,
  value,
  caption,
  isLoading,
  className,
}: KpiCardProps) {
  const toneClasses = TONE_CLASSES[tone];
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardContent className="flex items-start gap-4 p-6">
        <div
          className={cn(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-tile",
            toneClasses.tile,
          )}
          aria-hidden="true"
        >
          <Icon className={cn("h-5 w-5", toneClasses.icon)} />
        </div>
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[13px] font-medium text-text-secondary">
            {label}
          </span>
          {isLoading ? (
            <Skeleton className="mt-1 h-8 w-16" />
          ) : (
            <span
              className={cn(
                "text-[30px] font-bold leading-tight tabular-nums",
                toneClasses.value,
              )}
            >
              {value}
            </span>
          )}
          {caption && !isLoading && (
            <span className="text-xs text-text-muted">{caption}</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/** Convenience exports for the three derivable KPIs. */
export const ACTIVE_PROJECTS_ICON = Building2;
export const DOCUMENTS_UPLOADED_ICON = FileText;
export const RFQ_PACKAGES_ICON = PackageCheck;
