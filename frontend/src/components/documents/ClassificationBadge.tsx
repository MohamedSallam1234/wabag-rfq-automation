import { Badge } from "@/components/ui/badge";
import { GENERATED_DOC_TYPE } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface ClassificationBadgeProps {
  docType: string | null;
  source: "auto" | "manual";
  className?: string;
}

/**
 * Shows the document's classification with a semantic pill + an auto/manual
 * tag. Generated RFQ outputs (doc_type = "RFQ Package") use the success tone
 * so they stand out from source documents.
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
      <Badge variant={isGenerated ? "success" : "outline"}>{docType}</Badge>
      {!isGenerated && (
        <Badge
          variant={source === "manual" ? "warning" : "outline"}
          className="text-[10px]"
        >
          {source}
        </Badge>
      )}
    </span>
  );
}
