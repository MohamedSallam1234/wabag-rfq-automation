import { apiClient } from "./client";
import type {
  DocumentClassificationUpdate,
  DocumentDetail,
  DocumentRead,
  Uuid,
} from "./types";

/**
 * POST /api/v1/projects/{projectId}/documents — upload a single source file.
 * Backend validates extension (.pdf/.docx/.xlsx/.xls), classifies by filename,
 * normalizes to Markdown, and stores the artifact. 415/422/413 on bad input.
 */
export function uploadDocument(
  projectId: Uuid,
  file: File,
): Promise<DocumentRead> {
  const form = new FormData();
  form.append("file", file);
  return apiClient.post<DocumentRead>(`/projects/${projectId}/documents`, form);
}

/** GET /api/v1/projects/{projectId}/documents — list a project's documents. */
export function listDocuments(projectId: Uuid): Promise<DocumentRead[]> {
  return apiClient.get<DocumentRead[]>(`/projects/${projectId}/documents`);
}

/**
 * GET /api/v1/documents/{documentId} — fetch document metadata plus a
 * short-lived signed download URL (DocumentDetail.download_url).
 */
export function getDocument(documentId: Uuid): Promise<DocumentDetail> {
  return apiClient.get<DocumentDetail>(`/documents/${documentId}`);
}

/**
 * PATCH /api/v1/documents/{documentId} — override a document's classification.
 * Marks doc_type_source as "manual".
 */
export function updateDocumentClassification(
  documentId: Uuid,
  update: DocumentClassificationUpdate,
): Promise<DocumentRead> {
  return apiClient.patch<DocumentRead>(`/documents/${documentId}`, update);
}

/** DELETE /api/v1/documents/{documentId} — remove the row + storage object. */
export function deleteDocument(documentId: Uuid): Promise<void> {
  return apiClient.delete<void>(`/documents/${documentId}`);
}
