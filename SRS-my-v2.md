# SOFTWARE REQUIREMENTS SPECIFICATION

## RFQ Automation System

### Water & Wastewater Treatment Plant Engineering

**Document Version:** 4.0
**Date:** April 2026
**Prepared for:** Momen Yasser by Mohamed Sallam
**Classification:** Internal Use

---

## TABLE OF CONTENTS

1. Introduction
2. System Overview
3. Functional Requirements
4. Non-Functional Requirements
5. Future Phases

---

## 1. INTRODUCTION

### 1.1 Purpose

This document defines the requirements for the RFQ Automation System. The system uses AI to automate the generation of Request for Quotation (RFQ) documents for water and wastewater treatment plant equipment — a process that currently takes a senior technical engineer 2–3 days per RFQ to complete manually.

### 1.2 Glossary

| Term     | Definition                                                       |
| :------- | :--------------------------------------------------------------- |
| **RFQ**  | Request for Quotation — formal document requesting vendor pricing |
| **P&ID** | Piping and Instrumentation Diagram                               |
| **MLLM** | Multimodal Large Language Model                                  |
| **HITL** | Human-in-the-Loop                                                |
| **FAT**  | Factory Acceptance Testing                                       |
| **NPSH** | Net Positive Suction Head                                        |
| **VFD**  | Variable Frequency Drive                                         |

### 1.3 Scope

**Phase 1 (this document):** Automated RFQ generation from source engineering documents, with engineer review and approval.

**Phase 2 (future):** Compliance Matrix — AI-assisted comparison of vendor offers against the issued RFQ.

---

## 2. SYSTEM OVERVIEW

### 2.1 What the System Does

The system accepts a set of engineering documents for a project, extracts and cross-correlates equipment data across them using an AI agent governed by engineered prompts, and produces a populated RFQ datasheet for each equipment item. The engineer reviews, corrects if needed, and approves the output.

### 2.2 Input Documents

The system requires five source document types to generate an RFQ:

1. **Employer Technical Specifications** — standard codes and client requirements
2. **Process Engineering Profile** — design data
3. **Hydraulic Profile** — calculations and CAD-generated drawings
4. **Equipment List** — itemized equipment register
5. **RFQ Template** — the Excel datasheet to be populated

### 2.3 System Flow

```
Upload Documents
      │
      ▼
AI Extraction & Cross-Correlation
      │
      ▼
Validation & Confidence Scoring
      │
      ▼
Engineer Review & Approval
      │
      ▼
Generated RFQ (Excel / PDF)
```

### 2.4 Users

| User                    | Role                                                |
| :---------------------- | :-------------------------------------------------- |
| **Project Engineer**    | Uploads documents, reviews and approves RFQs        |
| **Senior Engineer**     | Resolves discrepancies, approves complex RFQs       |
| **Procurement Officer** | Receives final RFQ packages for vendor distribution |
| **System Admin**        | Manages users, projects, and system settings        |

---

## 3. FUNCTIONAL REQUIREMENTS

### 3.1 Document Ingestion

- System shall accept batch upload of the five source document types
- System shall support PDF, DOCX, XLSX, and CAD-generated PDF formats
- System shall auto-classify uploaded documents by type using filename and content analysis
- System shall detect document revision (Rev A, Rev B, Rev C, etc.)
- System shall reject corrupted files with a clear error message

### 3.2 AI Extraction & Cross-Correlation

The AI agent must be capable of reading and ingesting all supported document types, running extraction and word search across them, and cross-checking data for verification. This is the core capability of the system.

- System shall extract equipment master data per item: tag number, category, process parameters, materials, motor data, testing requirements, and vendor scope
- System shall cross-reference values across documents and flag discrepancies:
  - **Critical** (>20% difference): blocks generation, requires engineer resolution
  - **Warning** (10–20%): flagged for review
  - **Info** (<10%): auto-resolved using primary source
- System shall apply Egyptian Code motor service factors automatically:
  - Motors < 40 kW → +25%
  - Motors 40–100 kW → +20%
  - Motors > 100 kW → +15%
- System shall resolve "same as" references (e.g., "P-102 same as P-101")
- System shall normalize units to metric

### 3.3 Validation

- System shall validate that all required fields are present and correctly typed
- System shall verify equipment tags exist across documents consistently
- System shall check engineering logic (e.g., NPSH margins, efficiency ranges, motor power vs. calculated load)
- System shall calculate a Confidence Score (0.0–1.0) for each equipment extraction

### 3.4 Engineer Review

- System shall route extractions to review based on Confidence Score:
  - ≥ 0.95: auto-approved, proceeds to generation
  - 0.85–0.95: standard review queue
  - < 0.85 or discrepancies found: detailed review queue
- System shall provide a three-panel Review Workbench: Source Document | Extracted Data | RFQ Preview
- System shall allow the engineer to click any field and edit it inline
- System shall link each field to its source location in the original document
- System shall allow the engineer to issue a prompt to modify a field or section (e.g., "change all motor efficiency class to IE3")
- System shall allow the engineer to upload an additional document and trigger re-extraction
- System shall track all changes with timestamp and user

### 3.5 RFQ Generation

There is one RFQ template — a standard Equipment Datasheet in Excel format. It covers all equipment types used in water and wastewater treatment projects.

**Template sections:**

- **Header:** Project, client, consultant, document number
- **Process Data:** Fluid, quantity, capacity, head, pressure, temperature, duty
- **Performance Data:** Type, speed, efficiency, power, shut-off head
- **Materials:** Impeller, casing, shaft, seal, fasteners, bearings
- **Drive Motor:** Rating, speed, starting method, efficiency class, IP rating, insulation, sensors
- **Vendor Scope:** Checklist of items the vendor is required to supply

**Generation requirements:**

- System shall populate all template sections from validated extraction data
- System shall preserve Excel formulas, conditional formatting, and data validation dropdowns
- System shall output in Excel (.xlsx) for editing and PDF for distribution
- System shall group equipment items into packages with a cover sheet summary

### 3.6 Project Archive

- System shall store all projects, documents, extractions, and generated RFQs
- System shall enforce project-scoped access: users see only their assigned projects
- System shall maintain revision history for all generated RFQs
- System shall support search by equipment tag, project name, or client

---

## 4. NON-FUNCTIONAL REQUIREMENTS

| Requirement      | Target                                                        |
| :--------------- | :------------------------------------------------------------ |
| Extraction speed | < 10 minutes for a 200-page document set                      |
| RFQ generation   | < 30 seconds per package                                      |
| Availability     | 99.5% uptime                                                  |
| Scalability      | Support 50+ concurrent users across 10+ simultaneous projects |
| Data encryption  | AES-256 at rest, TLS 1.3 in transit                           |
| Audit logging    | Immutable logs of all actions per ISO 9001:2015               |
| Data residency   | Configurable per project (Middle East, Egypt, EU)             |
| Deployment       | Containerized (Docker / Kubernetes), cloud or on-premise      |

---

## 5. FUTURE PHASES

### Phase 2 — Compliance Matrix

After an RFQ is issued to vendors and offers are received, the engineer evaluates each offer against the RFQ requirements. Phase 2 will automate this through a Compliance Matrix.

**How it works:**

1. Engineer uploads the issued RFQ and all received vendor offers
2. System maps each vendor's values to the corresponding RFQ fields
3. System scores each line item: Compliant / Deviation / Non-Compliant / Not Provided
4. System generates a per-vendor summary and a consolidated multi-vendor comparison sheet
5. Engineer reviews, annotates, and exports for management decision-making

**Phase 2 depends on Phase 1** — specifically the structured RFQ data model and the document ingestion pipeline, which will be reused for parsing vendor offers.

---

**END OF DOCUMENT**
