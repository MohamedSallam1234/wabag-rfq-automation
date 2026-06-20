import { useQueries } from "@tanstack/react-query";

import { listDocuments } from "@/lib/api/documents";
import { documentsKeys } from "@/hooks/use-documents";
import type { DocumentRead, ProjectRead, Uuid } from "@/lib/api/types";

/**
 * Fetch documents for every project in parallel.
 *
 * Tradeoff: the backend exposes no bulk or summary endpoint, so deriving a
 * per-project document count and RFQ status requires one
 * `GET /projects/{id}/documents` call per project (N+1). Acceptable for modest
 * project counts; revisit if a summary endpoint is added. Reuses the same
 * query keys as `useDocuments`, so the project detail page shares this cache.
 */
export function useProjectsDocuments(projects: ProjectRead[] | undefined) {
  const queries = useQueries({
    queries: (projects ?? []).map((project) => ({
      queryKey: documentsKeys.list(project.id),
      queryFn: () => listDocuments(project.id),
    })),
  });

  const docsByProject = queries.reduce<Record<Uuid, DocumentRead[]>>(
    (acc, result, index) => {
      const project = projects?.[index];
      if (project && result.data) {
        acc[project.id] = result.data;
      }
      return acc;
    },
    {},
  );

  return {
    docsByProject,
    isLoading: queries.some((q) => q.isLoading),
    isError: queries.some((q) => q.isError),
  };
}
