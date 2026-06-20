import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteDocument,
  getDocument,
  listDocuments,
  updateDocumentClassification,
  uploadDocument,
} from "@/lib/api/documents";
import type { DocumentClassificationUpdate, Uuid } from "@/lib/api/types";

export const documentsKeys = {
  list: (projectId: Uuid) => ["documents", projectId] as const,
  detail: (documentId: Uuid) => ["documents", "detail", documentId] as const,
};

/** List a project's documents (newest first). */
export function useDocuments(projectId: Uuid | undefined) {
  return useQuery({
    queryKey: projectId ? documentsKeys.list(projectId) : ["documents", "none"],
    queryFn: () => listDocuments(projectId as Uuid),
    enabled: Boolean(projectId),
  });
}

/** Fetch one document's metadata + signed download URL. */
export function useDocument(documentId: Uuid | undefined) {
  return useQuery({
    queryKey: documentId
      ? documentsKeys.detail(documentId)
      : ["documents", "detail", "none"],
    queryFn: () => getDocument(documentId as Uuid),
    enabled: Boolean(documentId),
  });
}

/** Upload a single source file to a project. */
export function useUploadDocument(projectId: Uuid) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadDocument(projectId, file),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: documentsKeys.list(projectId) }),
  });
}

/** Override a document's classification (sets source = manual). */
export function useUpdateDocumentClassification(projectId: Uuid) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentId,
      update,
    }: {
      documentId: Uuid;
      update: DocumentClassificationUpdate;
    }) => updateDocumentClassification(documentId, update),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: documentsKeys.list(projectId) }),
  });
}

/** Delete a document (row + storage object). */
export function useDeleteDocument(projectId: Uuid) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: Uuid) => deleteDocument(documentId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: documentsKeys.list(projectId) }),
  });
}
