# SOFTWARE REQUIREMENTS SPECIFICATION

## RFQ Automation System

### Water & Wastewater Treatment Plant Engineering

**Document Version:** 3.0
**Date:** April 2026
**Prepared for:** Mohamed Sallam by Momen Yasser
**Document Type:** Software Requirements Specification (SRS)
**Classification:** Internal Use

---

## TABLE OF CONTENTS

1. Introduction
2. Overall Description
3. System Features & Requirements
4. External Interface Requirements
5. Non-Functional Requirements
6. Data Requirements
7. Future Phases
8. Appendices

---

## 1. INTRODUCTION

### 1.1 Purpose

This SRS document defines the complete requirements for the RFQ Automation System designed for water and wastewater treatment plant engineering. The system automates the transformation of multi-source engineering documents into structured Request for Quotation (RFQ) packages using multimodal Large Language Models (LLMs), governed by a set of engineered prompts that dictate the accuracy and flow of the generation process.

### 1.2 Document Conventions

| Term      | Definition                                                        |
| :-------- | :---------------------------------------------------------------- |
| **RFQ**   | Request for Quotation - formal document requesting vendor pricing |
| **P&ID**  | Piping and Instrumentation Diagram                                |
| **BOQ**   | Bill of Quantities                                                |
| **EPC**   | Engineering, Procurement, Construction                            |
| **MLLM**  | Multimodal Large Language Model                                   |
| **HITL**  | Human-in-the-Loop                                                 |
| **RAS**   | Return Activated Sludge                                           |
| **TC-CS** | Technical Clearance - Coarse Screens                              |

### 1.3 Intended Audience

- Software Architects and Developers
- Engineering Managers
- Project Managers and Procurement Teams
- Quality Assurance Officers

### 1.4 Project Scope

**Phase 1 (This Document) — In Scope:**

- Automated extraction from 5 source document types
- Generation of a single standardized RFQ template (Equipment Datasheet)
- Human review workflow with confidence-based routing
- Project-scoped archive and access control

**Phase 2 (Future — See Section 7):**

- Compliance Matrix generation: AI-assisted comparison of vendor offers against the issued RFQ

**Out of Scope (All Phases):**

- SAP ERP integration
- Vendor portal integration
- Tender/bidding phase (pre-award)
- Vendor selection algorithms
- Post-PO manufacturing tracking

### 1.5 References

1. IEEE Std 830-1998 — Recommended Practice for Software Requirements Specifications
2. ISO/IEC/IEEE 29148:2018 — Systems and software engineering requirements engineering
3. Internal Document Standards (Project Execution Process Flow v2.1)
4. In-house RFQ AI-Enhanced System Overview (internal briefing document)

---

## 2. OVERALL DESCRIPTION

### 2.1 Product Perspective

The RFQ Automation System is a standalone web application that supports the post-tender phase of EPC projects, bridging the gap between engineering design completion and procurement initiation. It replicates and accelerates the work of a senior technical engineer who would typically spend 2–3 days preparing a single RFQ manually.

The system accepts a set of project documents, runs AI-driven extraction and cross-correlation across them, and produces a fully populated RFQ datasheet ready for engineer review and distribution to vendors.

**System Context Diagram:**

```
┌──────────────────────────────────────────────────────────┐
│                   INPUT DOCUMENTS                         │
│  Employer Specs │ Process Eng. │ Hydraulic │ Equip. List │
│                     RFQ Template                         │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│                 RFQ AUTOMATION SYSTEM                     │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │  Document  │  │  AI          │  │  Review           │ │
│  │  Ingestion │  │  Extraction  │  │  Workbench        │ │
│  └────────────┘  └──────────────┘  └───────────────────┘ │
│  ┌────────────┐  ┌──────────────┐                        │
│  │  Prompt    │  │  Archive     │                        │
│  │  Engine    │  │  System      │                        │
│  └────────────┘  └──────────────┘                        │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│               RFQ OUTPUT (Excel / PDF)                    │
│         Reviewed & Approved by Technical Engineer         │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Product Functions

**Major Functions:**

1. **F-01: Multi-Document Ingestion** — Accept batch uploads of source document types
2. **F-02: Intelligent Document Classification** — Auto-detect document type and revision
3. **F-03: Cross-Document Extraction** — Extract equipment data with cross-referencing and conflict detection
4. **F-04: Validation & Verification** — Multi-layer validation with discrepancy detection
5. **F-05: Human Review Workflow** — Confidence-based routing with side-by-side editing and adaptive prompt-based revision
6. **F-06: RFQ Generation** — Single standardized template population with full data traceability
7. **F-07: Project Archive** — Scoped storage with access control per project

### 2.3 User Classes and Characteristics

| User Class                      | Role                                          | Technical Skill      | Usage Frequency | Key Needs                                      |
| :------------------------------ | :-------------------------------------------- | :------------------- | :-------------- | :--------------------------------------------- |
| **UC-01: Project Engineer**     | Creates RFQs, reviews extractions             | High (domain expert) | Daily           | Accuracy, speed, source traceability           |
| **UC-02: Senior Engineer**      | Approves complex RFQs, resolves discrepancies | Very High            | Weekly          | Oversight, exception handling                  |
| **UC-03: Project Manager**      | Monitors progress, manages timelines          | Medium               | Weekly          | Dashboards, status tracking                    |
| **UC-04: Procurement Officer**  | Receives RFQs, distributes to vendors         | Medium               | Daily           | Format compliance, completeness checks         |
| **UC-05: System Administrator** | Manages templates, users, audit logs          | High                 | Monthly         | Governance, security, performance              |

### 2.4 Operating Environment

**Server Environment:**

- Cloud (AWS/Azure/GCP) or On-premise Kubernetes
- OS: Linux (Ubuntu 22.04 LTS)
- Container Orchestration: Kubernetes 1.28+
- Database: PostgreSQL 16, Redis 7

**Client Environment:**

- Modern web browsers (Chrome 120+, Firefox 121+, Edge 120+)
- Minimum resolution: 1920×1080 (optimized for dual-monitor setups)
- PDF viewer integration for source document display

### 2.5 Design and Implementation Constraints

**C-01: Data Residency:** Projects may require data storage within regional boundaries (UAE, Saudi Arabia, Egypt)

**C-02: LLM Provider:** Primary: Claude Opus 4.6 (1M token context). Fallback: Kimi 2.5 (2M token context) for cost optimization

**C-03: Compliance:** All actions must generate immutable audit logs per ISO 9001:2015 requirements

**C-04: Accessibility:** System must support intermittent connectivity (offline review mode for field use)

---

## 3. SYSTEM FEATURES & REQUIREMENTS

### 3.1 Feature: Multi-Document Ingestion (F-01)

#### 3.1.1 Description

Enable batch upload of all project source documents with automatic format detection and validation. The system must handle the five core document types that together constitute the prerequisites for generating an accurate RFQ.

#### 3.1.2 Functional Requirements

**F-01-01:** System shall accept simultaneous upload of up to 20 files (total size ≤ 500 MB)

**F-01-02:** System shall support the following formats: PDF, DOCX, XLSX, XLS, DWG (with converter), PNG, JPG

**F-01-03:** System shall auto-classify uploaded documents into the following types using filename patterns and content analysis:

- Employer Technical Specifications (Standard Codes)
- Process Engineering Profile (Design Data)
- Hydraulic Profile (including CAD-generated PDFs)
- Equipment List
- RFQ Template

**F-01-04:** System shall detect document revision from headers/footers (Rev A, Rev B, Rev C, Rev 1, Rev 2)

**F-01-05:** System shall validate file integrity (checksum) and reject corrupted files with specific error messages

**F-01-06:** System shall extract document metadata: page count, author, creation date, last modified date

#### 3.1.3 Use Case: Upload Project Documents

**Primary Actor:** Project Engineer (UC-01)

**Preconditions:** User authenticated, project created in system

**Main Flow:**

1. Engineer navigates to project workspace
2. Clicks "Upload Documents"
3. System displays dropzone with document type indicators
4. Engineer uploads the five source document types
5. System validates files and displays a classification preview
6. Engineer confirms or corrects document type assignments
7. System initiates the processing pipeline
8. Engineer receives notification when extraction is complete

**Alternative Flows:**

- 5a. File corrupted: System highlights the specific file and requests re-upload
- 5b. Revision conflict detected: System warns "Rev C detected but project has Rev B — continue?"
- 6a. Engineer reassigns document type: System reprocesses classification

---

### 3.2 Feature: Intelligent Document Classification (F-02)

#### 3.2.1 Description

Automatically identify document structure, extract layout elements, and prepare content for MLLM processing. The system must handle a variety of file types including native PDFs, scanned drawings, spreadsheets, and CAD-generated outputs.

#### 3.2.2 Functional Requirements

**F-02-01:** System shall detect document structure per type:

- Text-based PDF: Extract native text with bounding boxes
- Scanned/image PDF: Apply OCR (PaddleOCR for multi-language support)
- DOCX: Extract structured XML with heading hierarchy
- XLSX/XLS: Identify sheet types (data tables, charts, calculations)

**F-02-02:** System shall identify and extract tables with preservation of merged cells and formulas

**F-02-03:** System shall detect P&ID diagrams using computer vision (symbol detection for pumps, valves, tanks)

**F-02-04:** System shall identify equipment tags using regex patterns: `[A-Z]{1,2}-\d{2,4}[A-Z]?` (e.g., P-101, TK-201, B-100A)

**F-02-05:** System shall create a document map: an index of all pages with content type classification

**F-02-06:** System shall handle Arabic and other RTL text present in source documentation

---

### 3.3 Feature: Cross-Document Extraction (F-03)

#### 3.3.1 Description

Extract equipment specifications across all source documents with cross-referencing and conflict detection. This mirrors the work a senior technical engineer performs when correlating data across engineering documents — a process that currently takes 2–3 days per RFQ.

#### 3.3.2 Functional Requirements

**F-03-01:** System shall extract equipment master data including:

- Tag number (primary identifier)
- Equipment category (pump, blower, valve, tank, instrument, screen, conveyor)
- Description
- Process parameters (capacity, head, temperature, pressure)
- Material specifications (impeller, casing, shaft, seal)
- Performance data (efficiency, power, speed)
- Testing requirements (FAT, NDT, certifications)
- Scope of supply (vendor deliverables)

**F-03-02:** System shall perform cross-document validation per the following reference matrix:

| RFQ Field             | Primary Source           | Secondary Source        | Validation Rule                    |
| :-------------------- | :----------------------- | :---------------------- | :--------------------------------- |
| Capacity (m³/hr)      | Hydraulic Profile        | Process Engineering     | Values must be within ±10%         |
| Differential Head (m) | Hydraulic Profile        | Process Engineering     | Values must be within ±5%          |
| Material Grade        | Employer Specifications  | Internal material list  | Must exist in approved list        |
| Motor Power (kW)      | Hydraulic Profile        | Egyptian Code SF        | Apply 25%/20%/15% service factor   |
| Quantity              | Equipment List           | P&ID tag count          | Must match                         |
| Testing Requirements  | Employer Specifications  | Client-specific clauses | Must include all mandatory tests   |

**F-03-03:** System shall detect and flag discrepancies between sources with severity levels:

- **Critical:** Values differ by >20% (blocks RFQ generation pending engineer review)
- **Warning:** Values differ by 10–20% (requires engineer review)
- **Info:** Values differ by <10% (auto-resolved using primary source)

**F-03-04:** System shall resolve "same as" references (e.g., "P-102 same as P-101") by copying validated specifications

**F-03-05:** System shall extract and normalize units (convert to metric, standardize notation)

**F-03-06:** System shall identify and apply client-specific requirements from Employer Specifications to all relevant equipment

---

### 3.4 Feature: Validation & Verification (F-04)

#### 3.4.1 Description

Multi-layer validation system ensuring extracted data meets engineering standards and business rules before proceeding to RFQ generation.

#### 3.4.2 Functional Requirements

**F-04-01:** System shall perform Schema Validation (L1):

- All required fields present per equipment category
- Data types correct (numeric fields contain numbers)
- Enumerated values valid (category must be in approved list)

**F-04-02:** System shall perform Cross-Reference Validation (L2):

- Verify P&ID tags exist in Equipment List
- Check hydraulic calculations reference valid equipment tags

**F-04-03:** System shall perform Standards Validation (L3):

- Verify ISO, ASTM, API, DIN standard numbers are current
- Flag deprecated standards and suggest current equivalents

**F-04-04:** System shall perform Engineering Logic Validation (L4):

- NPSH_available > NPSH_required + 0.5 m safety margin
- Pump efficiency within 40–85% range
- Motor power matches calculated hydraulic power plus service factor
- Temperature ratings exceed maximum process temperature

**F-04-05:** System shall calculate a composite Confidence Score (0.0–1.0) based on:

- LLM token probabilities (30%)
- Schema compliance (25%)
- Cross-reference consistency (25%)
- Engineering logic checks (20%)

---

### 3.5 Feature: Human Review Workflow (F-05)

#### 3.5.1 Description

Intelligent routing of extractions to engineers based on confidence scores, with specialized UI for validation, correction, and adaptive prompt-based revision. Engineers may request changes to any field via prompt or by uploading additional documents; the system adapts accordingly.

#### 3.5.2 Functional Requirements

**F-05-01:** System shall route extractions based on Confidence Score:

- **Auto-Approve:** Confidence ≥ 0.95 AND no critical fields → Direct to RFQ generation
- **Quick Review:** 0.85 ≤ Confidence < 0.95 OR contains critical field → Standard review queue
- **Detailed Review:** Confidence < 0.85 OR discrepancies detected → Expert review queue

**F-05-02:** System shall provide a Review Workbench UI with:

- Three-panel layout: Source Documents | Extracted Data | RFQ Preview
- Synchronized scrolling between source and extracted data
- Color-coded confidence indicators (green ≥0.95, yellow 0.85–0.95, red <0.85)

**F-05-03:** System shall support inline editing:

- Click any field to edit
- Auto-save drafts
- Track all changes with timestamp and user
- Show "original | modified" diff view

**F-05-04:** System shall support source linking:

- Click "View Source" on any field to jump to the exact page/location in the source PDF
- Highlight relevant text in source document

**F-05-05:** System shall support adaptive revision via prompt:

- Engineer can issue a natural-language prompt to modify a field or section (e.g., "Change all motor ratings to IE3")
- Engineer can upload a supplementary document and trigger re-extraction
- System tracks all prompt-driven changes in audit log

**F-05-06:** System shall support discrepancy resolution:

- Side-by-side comparison of conflicting sources
- Engineer selects which source to trust
- Resolution logged for future reference

**F-05-07:** System shall support comment threads:

- @mention colleagues
- Attach supporting files
- Mark as resolved/unresolved
- Email notifications for mentions

---

### 3.6 Feature: RFQ Generation (F-06)

#### 3.6.1 Description

Populate the standard equipment datasheet template with extracted and validated data. There is one unified RFQ template format used across all equipment types. The template structure accommodates all major equipment categories found in water and wastewater treatment projects.

#### 3.6.2 RFQ Template Structure

The single RFQ template is an Excel-based Equipment Datasheet organized into the following sections:

**Section: Header**

- Project, Location, Client, Consultant
- Internal Document No., Client Document No.

**Section: Process Data**

- Fluid Handled, Quantity (Nos.)
- Capacity (m³/hr), Ambient Temperature (°C)
- Solid Handling Size (mm), Suction Pressure (bar)
- Differential Head (mwc), Head Range (min/max, mwc)
- Service Duty

**Section: Performance Data**

- Type, Impeller Type, Design Standard
- Full Load Speed (rpm), No. of Stages
- Pump/Equipment Efficiency (%), Power at Duty Point (kW)
- Shut-Off Head (m)

**Section: Material of Construction**

- Impeller, Casing, Shaft, Seal Type
- Fasteners, Foundation Bolts, Bearing
- Guide Rail, Lifting Chain (where applicable)

**Section: Drive Motor**

- Type, Rating (kW), Speed (rpm)
- Starting Method (DOL, Star-Delta, VFD)
- Motor Efficiency Class (IE2, IE3, IE4)
- Power Supply (V/Ph/Hz), Ingress Protection
- Insulation Class, Mounting/Frame Size
- Sensors: Moisture, Thermal (3×PTC), Bearing PT100, Vibration
- Cooling Method

**Section: Vendor Scope Checklist**

- Equipment (boolean), Motor (boolean)
- Cables, Guide Rails, Pedestal Coupling, Lifting Chain with Shackles
- Spare Parts (array)

#### 3.6.3 Functional Requirements

**F-06-01:** System shall use a single unified Equipment Datasheet template for all equipment types

**F-06-02:** System shall auto-populate all template sections from validated extraction data

**F-06-03:** System shall apply Egyptian Code service factors to motor ratings:
- Motors < 40 kW: +25%
- Motors 40–100 kW: +20%
- Motors > 100 kW: +15%

**F-06-04:** System shall preserve Excel features:

- Formulas (e.g., auto-calculate efficiency from power/flow/head)
- Conditional formatting (flag values outside norms)
- Data validation dropdowns (material selection lists)
- Protected cells for calculated fields

**F-06-05:** System shall generate output in the following formats:

- Excel (.xlsx) — primary editable format
- PDF — for distribution to vendors

**F-06-06:** System shall support package grouping:

- Auto-group equipment items by category
- Allow manual reassignment
- Generate cover sheet with package summary

---

### 3.7 Feature: Project Archive (F-07)

#### 3.7.1 Description

Maintain a structured archive of all project documents, extracted data, and generated RFQs. The system must support the company's consistent undertaking of multiple concurrent projects, each requiring multiple RFQs across project lifetime.

#### 3.7.2 Functional Requirements

**F-07-01:** System shall organize all data under a project hierarchy (Project → Equipment → RFQ Packages)

**F-07-02:** System shall enforce project-scoped access control: users see only projects they are assigned to

**F-07-03:** System shall maintain revision history for all generated RFQ documents

**F-07-04:** System shall link generated RFQs to their source documents for full audit trail

**F-07-05:** System shall support search across all projects by equipment tag, project name, or client

---

## 4. EXTERNAL INTERFACE REQUIREMENTS

### 4.1 User Interfaces

**UI-01: Project Dashboard**

- List view with filters (client, status, date range)
- Kanban board view (Uploading → Processing → Reviewing → Completed)
- Quick stats: active projects, pending reviews, accuracy trend

**UI-02: Upload Wizard**

- Drag-and-drop with visual feedback
- Document type icons and descriptions
- Progress bars for upload and processing
- Error display with retry options

**UI-03: Review Workbench**

- Three-panel responsive layout (collapsible panels)
- PDF viewer with annotation tools
- Spreadsheet-like data editor
- Prompt input box for adaptive revisions

**UI-04: Admin Dashboard**

- User management
- Template viewer/editor
- System health monitoring
- LLM usage and cost tracking

### 4.2 Software Interfaces

| Interface           | Protocol   | Data Format | Purpose                            |
| :------------------ | :--------- | :---------- | :--------------------------------- |
| Claude Opus 4.6 API | HTTPS/REST | JSON        | Primary extraction engine          |
| Kimi 2.5 API        | HTTPS/REST | JSON        | Fallback/cost-optimized extraction |
| Document Storage    | REST API   | JSON/Binary | File storage and retrieval         |

### 4.3 Communications Interfaces

- WebSocket for real-time updates (processing progress, notifications)
- Server-Sent Events (SSE) for long-running extraction jobs

---

## 5. NON-FUNCTIONAL REQUIREMENTS

### 5.1 Performance Requirements

**PR-01:** Upload to extraction completion: < 10 minutes for a 200-page document set

**PR-02:** Review workbench load time: < 2 seconds for 100 equipment items

**PR-03:** RFQ generation time: < 30 seconds per package

**PR-04:** Concurrent users: Support 50+ engineers across 10+ simultaneous projects

**PR-05:** API response time: < 500 ms for 95% of requests

### 5.2 Security Requirements

**SR-01:** Data encryption at rest: AES-256

**SR-02:** Data encryption in transit: TLS 1.3

**SR-03:** Authentication: Role-based login with access control per project

**SR-04:** Authorization: Project-based access control (engineer sees only assigned projects)

**SR-05:** Audit logging: Immutable logs of all data access and modifications

**SR-06:** Data residency: Configurable storage region per project (Middle East, Egypt, EU)

### 5.3 Software Quality Attributes

**QA-01: Availability:** 99.5% uptime (scheduled maintenance windows excluded)

**QA-02: Maintainability:** Modular architecture, comprehensive API documentation

**QA-03: Portability:** Docker containerization, Kubernetes orchestration

**QA-04: Scalability:** Horizontal scaling for processing workers, auto-scaling based on queue depth

**QA-05: Usability:** < 30 minutes training required for basic operation

### 5.4 Business Rules

**BR-01:** Egyptian Code Service Factor: Motors < 40 kW: 25%; 40–100 kW: 20%; > 100 kW: 15%

**BR-02:** Revision Control: RFQs must include source document revision references (e.g., "Based on Rev C")

**BR-03:** Approval Authority: RFQs above a defined value threshold require Senior Engineer sign-off

---

## 6. DATA REQUIREMENTS

### 6.1 Logical Data Model

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Project   │◄─────►│   Document  │◄─────►│  Extraction │
│             │  1:M  │             │  1:1  │    Job      │
└──────┬──────┘       └─────────────┘       └──────┬──────┘
       │                                           │
       │ 1:M                                       │ 1:M
       ▼                                           ▼
┌─────────────┐       ┌─────────────┐      ┌─────────────┐
│  Equipment  │◄─────►│Specification│      │    RFQ      │
│   Master    │  1:M  │   Value     │      │  Package    │
└─────────────┘       └─────────────┘      └─────────────┘
```

### 6.2 Data Dictionary

**Table: projects**

| Field        | Type         | Description         | Constraints                         |
| :----------- | :----------- | :------------------ | :---------------------------------- |
| project_id   | UUID         | Primary key         | PK, auto-generated                  |
| project_code | VARCHAR(50)  | Internal code       | Unique, indexed                     |
| project_name | VARCHAR(255) | Descriptive name    | Not null                            |
| client_id    | UUID         | FK to clients       | Indexed                             |
| region       | ENUM         | Geographic region   | ME, Africa, EU                      |
| status       | ENUM         | Workflow status     | Draft, Active, Completed, Archived  |
| created_at   | TIMESTAMP    | Creation time       | Auto-set                            |
| updated_at   | TIMESTAMP    | Last modification   | Auto-update                         |

**Table: equipment_master**

| Field             | Type         | Description           | Constraints                           |
| :---------------- | :----------- | :-------------------- | :------------------------------------ |
| equipment_id      | UUID         | Primary key           | PK                                    |
| project_id        | UUID         | FK to project         | Indexed, cascade delete               |
| tag_number        | VARCHAR(20)  | Equipment tag         | Not null, format: [A-Z]{1,2}-\d{2,4} |
| category          | ENUM         | Equipment type        | pump, blower, valve, tank, etc.       |
| description       | TEXT         | Narrative description |                                       |
| specifications    | JSONB        | Flexible spec storage | GIN indexed                           |
| confidence_score  | DECIMAL(3,2) | 0.00–1.00             |                                       |
| validation_status | ENUM         | Review state          | pending, approved, corrected          |
| extracted_at      | TIMESTAMP    | Extraction time       |                                       |
| reviewed_by       | UUID         | FK to users           | Nullable                              |
| reviewed_at       | TIMESTAMP    | Review completion     | Nullable                              |

**Table: rfq_packages**

| Field           | Type         | Description        | Constraints               |
| :-------------- | :----------- | :----------------- | :------------------------ |
| rfq_id          | UUID         | Primary key        | PK                        |
| project_id      | UUID         | FK to project      | Indexed                   |
| package_name    | VARCHAR(100) | Descriptive name   | Not null                  |
| equipment_ids   | UUID[]       | Equipment array    | Foreign key array         |
| generated_files | JSONB        | File metadata      |                           |
| status          | ENUM         | Package state      | draft, approved, sent     |
| approved_by     | UUID         | FK to users        | Nullable                  |
| approved_at     | TIMESTAMP    | Approval time      | Nullable                  |

### 6.3 Data Retention

**Active Projects:** Full data retention for project duration + 7 years

**Completed Projects:** Archive to cold storage after 2 years, retain metadata for 10 years

**Audit Logs:** Immutable retention for 10 years

---

## 7. FUTURE PHASES

### 7.1 Phase 2 — Compliance Matrix Generation

#### 7.1.1 Overview

After an RFQ is issued and vendor offers are received, the next step is evaluating those offers against the technical requirements specified in the RFQ. This is currently a manual process performed by the technical engineer. Phase 2 will automate this through an AI-generated Compliance Matrix.

#### 7.1.2 Concept

The Compliance Matrix is a structured comparison document that evaluates each vendor's offer item by item against the issued RFQ. Each line item is assigned a score and a remark explaining its compliance status. The output consolidates all vendor offers into a single Excel document, providing management-level insights for decision-making.

**Typical flow:**

1. Engineer uploads the issued RFQ and all received vendor offers
2. System parses each offer and maps line items to the corresponding RFQ fields
3. System generates a scored compliance table per vendor, then a consolidated multi-vendor comparison sheet
4. Engineer reviews and validates the matrix
5. Final document is exported for management review and decision-making

#### 7.1.3 Scope of Phase 2 Features

**CM-01:** System shall accept uploaded vendor offer documents (PDF, DOCX, XLSX) alongside the original issued RFQ

**CM-02:** System shall extract and map vendor-provided values to corresponding RFQ fields

**CM-03:** System shall score each line item against the RFQ requirement:

- **Compliant:** Vendor value meets or exceeds the RFQ requirement
- **Deviation:** Vendor value differs within an acceptable tolerance
- **Non-Compliant:** Vendor value does not meet the RFQ requirement
- **Not Provided:** Vendor did not address this item

**CM-04:** System shall generate per-vendor compliance summary with an overall compliance score

**CM-05:** System shall generate a consolidated multi-vendor comparison sheet suitable for management review

**CM-06:** System shall allow the engineer to add remarks, override scores, and annotate individual items

**CM-07:** System shall export the Compliance Matrix as Excel (.xlsx) and PDF

#### 7.1.4 Dependencies

Phase 2 depends on the completion and stability of Phase 1, specifically:

- The structured RFQ data model (so the system knows what was required)
- The document ingestion and extraction pipeline (reused for parsing vendor offers)
- The review workbench UI (extended for compliance review)

---

## 8. APPENDICES

### Appendix A: Glossary

| Term       | Definition                                                     |
| :--------- | :------------------------------------------------------------- |
| **Blower** | Mechanical device for moving air/gas in aeration systems       |
| **DOL**    | Direct On Line motor starting method                           |
| **FAT**    | Factory Acceptance Testing                                     |
| **IE3**    | International Efficiency class 3 (premium efficiency motor)    |
| **MLLM**   | Multimodal Large Language Model (processes text + images)      |
| **NDT**    | Non-Destructive Testing                                        |
| **NPSH**   | Net Positive Suction Head (pump cavitation prevention)         |
| **PT100**  | Platinum resistance thermometer (temperature sensor)           |
| **PTC**    | Positive Temperature Coefficient thermistor (motor protection) |
| **RAS**    | Return Activated Sludge (wastewater treatment process)         |
| **SBU**    | Strategic Business Unit                                        |
| **SS316L** | Stainless Steel grade 316 Low carbon                           |
| **TEFC**   | Totally Enclosed Fan Cooled motor                              |
| **VFD**    | Variable Frequency Drive                                       |

### Appendix B: Open Issues

| ID    | Description                                              | Impact | Target       |
| :---- | :------------------------------------------------------- | :----- | :----------- |
| OI-01 | DWG file parsing for native CAD extraction               | Medium | Phase 1 v1.1 |
| OI-02 | Arabic text RTL support in generated PDFs                | Low    | Phase 1 v1.1 |
| OI-03 | Mobile offline review mode                               | Medium | Phase 2      |
| OI-04 | AI-powered vendor quote comparison (Compliance Matrix)   | High   | Phase 2      |

### Appendix C: Document Change History

| Version | Date       | Author        | Changes                                                                                                                                     |
| :------ | :--------- | :------------ | :------------------------------------------------------------------------------------------------------------------------------------------ |
| 1.0     | 2026-02-15 | Initial Draft | Baseline requirements                                                                                                                       |
| 2.0     | 2026-02-18 | Revised       | Added real-world data structures from RFQ Templates analysis, clarified Claude Opus 4.6 integration, expanded validation matrix             |
| 3.0     | 2026-04-15 | Revised       | Removed SAP ERP and vendor portal integrations; simplified to single RFQ template type; added Compliance Matrix as Phase 2 future scope     |

---

**END OF DOCUMENT**
