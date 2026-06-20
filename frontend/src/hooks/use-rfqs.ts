import { useMutation, useQueryClient } from "@tanstack/react-query";

import { generateRfq } from "@/lib/api/rfqs";
import { documentsKeys } from "@/hooks/use-documents";
import type { Uuid } from "@/lib/api/types";

/**
 * Generate an RFQ datasheet. Long-running: the POST stays open for the whole
 * map-reduce LLM run (minutes). On success a new Document row with
 * doc_type = "RFQ Package" is created, so the project's document list is
 * invalidated to pick it up.
 */
export function useGenerateRfq(projectId: Uuid) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, equipment }: { file: File; equipment: string }) =>
      generateRfq(projectId, file, equipment),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: documentsKeys.list(projectId) }),
  });
}
