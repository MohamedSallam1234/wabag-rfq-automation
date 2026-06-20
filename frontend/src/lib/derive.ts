import { GENERATED_DOC_TYPE, type DocumentRead, type Uuid } from "@/lib/api/types";

/** Subset of badge variants used for derived status pills. */
export type StatusVariant = "info" | "success" | "warning" | "outline";

/** True for a generated RFQ package document (runtime-only doc_type). */
export function isRfqPackageDoc(doc: DocumentRead): boolean {
  return doc.doc_type === GENERATED_DOC_TYPE;
}

/** Number of documents attached to a project (0 when unknown/loading). */
export function projectDocCount(docs: DocumentRead[] | undefined): number {
  return docs?.length ?? 0;
}

export interface RfqStatus {
  label: string;
  variant: StatusVariant;
}

/**
 * Derive a project's RFQ status purely from its documents.
 *
 * The backend has no `rfq_status` field — this is a client-side approximation:
 * any generated "RFQ Package" document ⇒ Ready; any documents at all ⇒ In
 * Progress; otherwise none.
 */
export function projectRfqStatus(docs: DocumentRead[] | undefined): RfqStatus {
  if (!docs || docs.length === 0) {
    return { label: "No documents", variant: "outline" };
  }
  if (docs.some(isRfqPackageDoc)) {
    return { label: "RFQ Ready", variant: "success" };
  }
  return { label: "In Progress", variant: "info" };
}

/** Total generated RFQ packages across the supplied per-project document map. */
export function totalRfqPackages(
  docsByProject: Record<Uuid, DocumentRead[]>,
): number {
  return Object.values(docsByProject).reduce(
    (sum, docs) => sum + docs.filter(isRfqPackageDoc).length,
    0,
  );
}

/** Total documents uploaded across the supplied per-project document map. */
export function totalDocuments(
  docsByProject: Record<Uuid, DocumentRead[]>,
): number {
  return Object.values(docsByProject).reduce(
    (sum, docs) => sum + docs.length,
    0,
  );
}
