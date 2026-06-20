import { apiClient } from "./client";
import type { RfqGenerationResponse, Uuid } from "./types";

/**
 * POST /api/v1/projects/{projectId}/rfqs — generate a populated RFQ datasheet.
 *
 * Multipart: `file` = the RFQ template (.xlsx/.xls/.pdf/.docx) plus a form
 * field `equipment` naming the equipment. The backend runs map-reduce LLM
 * extraction over the project's source documents, renders a fresh .xlsx, and
 * persists it as a Document row (doc_type = "RFQ Package").
 *
 * This call is SYNCHRONOUS and long-running — several LLM calls in series can
 * take 5–30 minutes (backend LLM_TIMEOUT_S ceiling is 1800s). There is no
 * background-job endpoint yet, so the request stays open for the whole run.
 */
export function generateRfq(
  projectId: Uuid,
  file: File,
  equipment: string,
): Promise<RfqGenerationResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("equipment", equipment);
  return apiClient.post<RfqGenerationResponse>(
    `/projects/${projectId}/rfqs`,
    form,
  );
}
