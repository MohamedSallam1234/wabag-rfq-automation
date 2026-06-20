/**
 * Types mirroring the backend Pydantic schemas (backend/src/app/schemas/*).
 * Field names and nullability match the JSON the API returns — these are the
 * source of truth for the frontend's view of the data model.
 *
 * Backend has only two real tables (Project, Document). "RFQ Package" is a
 * Document row with doc_type = "RFQ Package"; per-field confidence/audit data
 * lives inside the generated .xlsx, not a JSON endpoint.
 */

/** ISO 8601 timestamp string, e.g. "2026-06-20T10:30:00Z". */
export type IsoTimestamp = string;

/** UUID string. */
export type Uuid = string;

/** POST /api/v1/projects request body. */
export interface ProjectCreate {
  name: string;
  location?: string | null;
  client?: string | null;
  consultant?: string | null;
  project_number?: string | null;
  capacity_m3d?: number | null;
}

/** Project as returned by GET/POST /api/v1/projects. */
export interface ProjectRead {
  id: Uuid;
  name: string;
  location: string | null;
  client: string | null;
  consultant: string | null;
  project_number: string | null;
  capacity_m3d: number | null;
  created_at: IsoTimestamp;
  updated_at: IsoTimestamp;
}

/** How a document's classification was set (backend models/document.py enum). */
export type DocTypeSource = "auto" | "manual";

/** Retention policy for the stored artifact (backend models/document.py enum). */
export type RetentionPolicy = "persistent" | "transient";

/**
 * Controlled vocabulary for document classification
 * (backend services/ingestion/classifier.py DocType enum). The backend stores
 * doc_type as a free-form string, so unclassified docs are null and generated
 * RFQs carry the runtime-only "RFQ Package" value (kept here for filtering).
 */
export const DOC_TYPES = [
  "Employer Technical Specifications",
  "Process Engineering Profile",
  "RFQ Template",
  "Hydraulic Calculation Profile",
  "Equipment List",
  "General Motor Specifications",
  "General Mechanical Works Specs",
  "Local Control Panel DataSheet",
  "RFQ Authorization Letter",
  "Equipment DataSheet",
  "Equipment Specification Document",
] as const;

export type DocType = (typeof DOC_TYPES)[number];

/** Runtime-only doc_type stamped on generated RFQ outputs (not in the enum). */
export const GENERATED_DOC_TYPE = "RFQ Package" as const;

/** A single field's lifecycle status (backend schemas/rfq.py FieldStatus). */
export type FieldStatus = "extracted" | "conflict" | "tbd" | "vtf";

/** Document metadata as returned by document list/create/patch endpoints. */
export interface DocumentRead {
  id: Uuid;
  project_id: Uuid;
  original_filename: string;
  content_type: string;
  size_bytes: number | null;
  doc_type: string | null;
  doc_type_source: DocTypeSource;
  revision_label: string | null;
  revision_number: number | null;
  page_count: number | null;
  sheet_names: string[] | null;
  retention: RetentionPolicy;
  created_at: IsoTimestamp;
  updated_at: IsoTimestamp;
}

/** DocumentRead plus a short-lived signed download URL (GET /documents/:id). */
export interface DocumentDetail extends DocumentRead {
  download_url: string;
}

/** PATCH /documents/:id request body. */
export interface DocumentClassificationUpdate {
  doc_type: DocType;
}

/** Aggregate counts for a generated RFQ (backend schemas/rfq.py RFQSummary). */
export interface RfqSummary {
  fields_total: number;
  extracted: number;
  conflict: number;
  tbd: number;
  vtf: number;
}

/** POST /api/v1/projects/:id/rfqs response. */
export interface RfqGenerationResponse {
  document: DocumentRead;
  summary: RfqSummary;
}
