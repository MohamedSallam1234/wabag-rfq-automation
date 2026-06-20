import { Badge } from "@/components/ui/badge";
import { GENERATED_DOC_TYPE } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface ClassificationBadgeProps {
  docType: string | null;
  source: "auto" | "manual";
  className?: string;
}

/**
 * Shows the document's classification with a color hint + an auto/manual tag.
 * Generated RFQ outputs (doc_type = "RFQ Package") get a distinct color so
 * they stand out from source documents.
 */
export function ClassificationBadge({
  docType,
  source,
  className,
}: ClassificationBadgeProps) {
  if (!docType) {
    return (
      <span className={cn("inline-flex items-center gap-1", className)}>
        <Badge variant="outline">Unclassified</Badge>
      </span>
    );
  }

  const isGenerated = docType === GENERATED_DOC_TYPE;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <Badge variant={isGenerated ? "secondary" : "outline"}>{docType}</Badge>
      {!isGenerated && (
        <Badge
          variant="outline"
          className={cn(
            "text-[10px]",
            source === "manual"
              ? "border-amber-400 text-amber-700"
              : "text-muted-foreground",
          )}
        >
          {source}
        </Badge>
      )}
    </span>
  );
}
