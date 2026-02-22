# SOFTWARE REQUIREMENTS SPECIFICATION

## RFQ Automation System for VA Tech Wabag

### Water & Wastewater Treatment Plant Engineering

**Document Version:** 2.0
**Date:** February 2026
**Prepared for:** Momen Yasser by mohamed Sallam
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
7. Appendices

---

## 1. INTRODUCTION

### 1.1 Purpose

This SRS document defines the complete requirements for the RFQ Automation System designed for VA Tech Wabag's water and wastewater treatment plant engineering division. The system automates the transformation of multi-source engineering documents into structured Request for Quotation (RFQ) packages using multimodal Large Language Models (LLMs).

### 1.2 Document Conventions

Table

Copy

| Term      | Definition                                                        |
| :-------- | :---------------------------------------------------------------- |
| **RFQ**   | Request for Quotation - formal document requesting vendor pricing |
| **P&ID**  | Piping and Instrumentation Diagram                                |
| **BOQ**   | Bill of Quantities                                                |
| **EPC**   | Engineering, Procurement, Construction                            |
| **RAS**   | Return Activated Sludge                                           |
| **TC-CS** | Technical Clearance - Coarse Screens                              |
| **MLLM**  | Multimodal Large Language Model                                   |
| **HITL**  | Human-in-the-Loop                                                 |

### 1.3 Intended Audience

- Software Architects and Developers
- VA Tech Wabag Engineering Managers
- Project Managers and Procurement Teams
- Quality Assurance and Compliance Officers

### 1.4 Project Scope

**In Scope:**

- Automated extraction from 6 document types (01-06 series)
- Generation of 3 RFQ template types (RAS Pump, TC-CS, Variance Analysis)
- Human review workflow with confidence-based routing
- Integration with Wabag ERP (SAP) and vendor portals

**Out of Scope:**

- Tender/bidding phase (pre-award)
- Vendor selection algorithms
- Post-PO manufacturing tracking
- Real-time collaboration features (Phase 3)

### 1.5 References

1. IEEE Std 830-1998 - IEEE Recommended Practice for Software Requirements Specifications
2. ISO/IEC/IEEE 29148:2018 - Systems and software engineering - Life cycle processes - Requirements engineering
3. VA Tech Wabag Internal Document Standards (Project Execution Process Flow v2.1)
4. Real-world document analysis: RFQ Templates.xlsx (03_RFQ_Templates.xlsx)

---

## 2. OVERALL DESCRIPTION

### 2.1 Product Perspective

The RFQ Automation System is a new standalone web application that integrates with existing Wabag systems (SAP ERP, Document Management, SSO). It operates in the post-tender phase of EPC projects, bridging the gap between engineering design completion and procurement initiation.

**System Context Diagram:**

plain

Copy

```plain
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SYSTEMS                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Client  │  │  SAP ERP │  │  Vendor  │  │  Azure   │        │
│  │  Docs    │  │  System  │  │  Portals │  │   AD     │        │
│  │ (PDF)    │  │          │  │          │  │  (SSO)   │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │             │             │               │
│       │             │             │             │               │
│       ▼             ▼             ▼             ▼               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              RFQ AUTOMATION SYSTEM                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │   │
│  │  │ Document │  │   AI     │  │  Review  │  │  Output  │  │   │
│  │  │ Ingestion│  │Extraction│  │ Workbench│  │ Generator│  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ▲                                     │
│                           │                                     │
│                    ┌──────┴──────┐                              │
│                    │   Wabag     │                              │
│                    │  Engineers  │                              │
│                    │  (Users)    │                              │
│                    └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Product Functions

**Major Functions:**

1. **F-01: Multi-Document Ingestion** - Accept batch uploads of 6 document types
2. **F-02: Intelligent Document Classification** - Auto-detect document type and revision
3. **F-03: Cross-Document Extraction** - Extract equipment data with source tracking
4. **F-04: Validation & Verification** - Multi-layer validation with discrepancy detection
5. **F-05: Human Review Workflow** - Confidence-based routing with side-by-side editing
6. **F-06: RFQ Generation** - Template population with client-specific formatting
7. **F-07: Variance Analysis** - Compare proposal vs. detailed engineering stages
8. **F-08: System Integration** - Export to SAP and vendor portals

### 2.3 User Classes and Characteristics

Table

Copy

| User Class                      | Role                                          | Technical Skill      | Usage Frequency | Key Needs                                      |
| :------------------------------ | :-------------------------------------------- | :------------------- | :-------------- | :--------------------------------------------- |
| **UC-01: Project Engineer**     | Creates RFQs, reviews extractions             | High (domain expert) | Daily           | Accuracy, speed, source traceability           |
| **UC-02: Senior Engineer**      | Approves complex RFQs, resolves discrepancies | Very High            | Weekly          | Oversight, exception handling, compliance      |
| **UC-03: Project Manager**      | Monitors progress, manages timelines          | Medium               | Weekly          | Dashboards, status tracking, resource planning |
| **UC-04: Procurement Officer**  | Receives RFQs, distributes to vendors         | Medium               | Daily           | Format compliance, completeness checks         |
| **UC-05: System Administrator** | Manages templates, users, audit logs          | High                 | Monthly         | Governance, security, performance              |

### 2.4 Operating Environment

**Server Environment:**

- Cloud: AWS/Azure/GCP or On-premise Kubernetes
- OS: Linux (Ubuntu 22.04 LTS)
- Container Orchestration: Kubernetes 1.28+
- Database: PostgreSQL 16, Neo4j 5, Redis 7

**Client Environment:**

- Modern web browsers (Chrome 120+, Firefox 121+, Edge 120+)
- Minimum resolution: 1920x1080 (optimized for dual-monitor setups)
- PDF viewer integration for source document display

### 2.5 Design and Implementation Constraints

**C-01: Data Residency:** Middle East projects require data storage within regional boundaries (UAE, Saudi Arabia)

**C-02: LLM Provider:** Primary: Claude Opus 4.6 (1M token context). Fallback: Kimi 2.5 (2M token context) for cost optimization

**C-03: Integration:** Must support SAP RFC connections and legacy vendor email-based RFQ distribution

**C-04: Compliance:** All actions must generate immutable audit logs per ISO 9001:2015 requirements

**C-05: Accessibility:** System must function with intermittent connectivity (offline review mode)

---

## 3. SYSTEM FEATURES & REQUIREMENTS

### 3.1 Feature: Multi-Document Ingestion (F-01)

#### 3.1.1 Description

Enable batch upload of all project source documents with automatic format detection and validation.

#### 3.1.2 Functional Requirements

**F-01-01:** System shall accept simultaneous upload of up to 20 files (total size ≤ 500MB)

**F-01-02:** System shall support formats: PDF, DOCX, XLSX, XLS, DWG (with converter), PNG, JPG

**F-01-03:** System shall auto-classify documents using filename patterns and content analysis:

- Pattern matching: `01_*` → Employer Technical Specifications
- Pattern matching: `02_*` → Process Engineering Profile
- Pattern matching: `03_*` → Process Simulation Reports OR RFQ Templates (disambiguate by content)
- Pattern matching: `04_*` → Hydraulic Calculation Profile
- Pattern matching: `06_*` → Equipment List

**F-01-04:** System shall detect document revision from headers/footers (Rev A, Rev B, Rev C, Rev 1, Rev 2)

**F-01-05:** System shall validate file integrity (checksum) and reject corrupted files with specific error messages

**F-01-06:** System shall extract metadata: page count, author, creation date, last modified date

#### 3.1.3 Use Case: Upload Project Documents

**Primary Actor:** Project Engineer (UC-01)

**Preconditions:** User authenticated, project created in system

**Main Flow:**

1. Engineer navigates to project workspace
2. Clicks "Upload Documents" button
3. System displays dropzone with document type indicators
4. Engineer drags 6 files (01-06 series) into dropzone
5. System validates files and displays classification preview
6. Engineer confirms or corrects document type assignments
7. System initiates processing pipeline
8. Engineer receives notification when extraction complete

**Alternative Flows:**

- 5a. File corrupted: System highlights specific file, requests re-upload
- 5b. Revision conflict detected: System warns "Rev C detected but project has Rev B - continue?"
- 6a. Engineer reassigns document type: System reprocesses classification

---

### 3.2 Feature: Intelligent Document Classification (F-02)

#### 3.2.1 Description

Automatically identify document structure, extract layout elements, and prepare for MLLM processing.

#### 3.2.2 Functional Requirements

**F-02-01:** System shall detect document structure:

- Text-based PDF: Extract native text with bounding boxes
- Scanned/image PDF: Apply OCR (PaddleOCR for multi-language support)
- DOCX: Extract structured XML with heading hierarchy
- XLSX/XLS: Identify sheet types (data vs. charts vs. calculations)

**F-02-02:** System shall identify and extract tables with preservation of merged cells and formulas

**F-02-03:** System shall detect P&ID diagrams using computer vision (symbol detection for pumps, valves, tanks)

**F-02-04:** System shall identify equipment tags using regex patterns: `[A-Z]{1,2}-\d{2,4}[A-Z]?` (e.g., P-101, TK-201, B-100A)

**F-02-05:** System shall create document map: index of all pages with content type classification

**F-02-06:** System shall handle Arabic and Chinese text in vendor documentation

---

### 3.3 Feature: Cross-Document Extraction (F-03)

#### 3.3.1 Description

Extract equipment specifications across all source documents with cross-referencing and conflict detection.

#### 3.3.2 Functional Requirements

**F-03-01:** System shall extract equipment master data including:

- Tag number (primary identifier)
- Equipment category (pump, blower, valve, tank, instrument, screen, conveyor)
- Description (narrative)
- Process parameters (capacity, head, temperature, pressure)
- Material specifications (impeller, casing, shaft, seal)
- Performance data (efficiency, power, speed)
- Testing requirements (FAT, NDT, certifications)
- Scope of supply (what vendor provides)

**F-03-02:** System shall perform cross-document validation per Reference Matrix:

Table

Copy

| RFQ Field             | Primary Source           | Secondary Source             | Validation Rule               |
| :-------------------- | :----------------------- | :--------------------------- | :---------------------------- |
| Capacity (m³/hr)      | 04_Hydraulic_Calculation | 03_Process_Simulation        | Values must be within ±10%    |
| Differential Head (m) | 04_Hydraulic_Calculation | 02_Process_Engineering       | Values must be within ±5%     |
| Material Grade        | 01_Employer_Specs        | Wabag Material Master        | Must exist in approved list   |
| Motor Power (kW)      | 04_Hydraulic_Calculation | Egyptian Code service factor | Must apply 25%/20%/15% factor |
| Quantity              | 06_Equipment_List        | P&ID tag count               | Must match                    |
| Testing Requirements  | 01_Employer_Specs        | Client-specific standards    | Must include mandatory tests  |

**F-03-03:** System shall detect and flag discrepancies between sources with severity levels:

- **Critical:** Values differ by >20% (blocks RFQ generation)
- **Warning:** Values differ by 10-20% (requires engineer review)
- **Info:** Values differ by <10% (auto-resolve using primary source)

**F-03-04:** System shall resolve "same as" references (e.g., "P-102 same as P-101") by copying validated specifications

**F-03-05:** System shall extract and normalize units (convert m³/hr to L/s if needed, standardize on metric)

**F-03-06:** System shall identify client-specific requirements from 01_Employer_Specs and apply to all relevant equipment

#### 3.3.3 Real-World Data Structure Analysis

Based on analysis of 03_RFQ_Templates.xlsx, the system must handle:

**RAS Pump Datasheet Structure:**

plain

Copy

```plain
Section: Header
├── Project (text)
├── Location (text)
├── Client (text)
├── Consultant (text)
├── WABAG Doc. No. (text)
└── Client Doc. No. (text)

Section: Process Data
├── Fluid Handled (text)
├── Quantity (integer, Nos.)
├── Capacity (numeric, m³/hr)
├── Ambient Temperature (numeric, °C)
├── Solid Handling Size (numeric, mm)
├── Suction Pressure (numeric, bar)
├── Differential Head (numeric, mwc)
├── Head Range (min/max, mwc)
└── Service Duty (text)

Section: Performance Data
├── Type (text)
├── Impeller Type (text)
├── Design Standard (text: ISO 9906, API 610, etc.)
├── Full Load Speed (integer, rpm)
├── No. of Stages (integer)
├── Pump Efficiency (numeric, %)
├── Power Required at Duty Point (numeric, kW)
└── Shut-Off Head (numeric, m)

Section: Material of Construction
├── Impeller (material code)
├── Casing (material code)
├── Shaft (material code)
├── Type of Seal (text)
├── Fasteners (material code)
├── Foundation Bolts (material code)
├── Bearing (text)
├── Guide Rail (material code)
└── Lifting Chain (material code)

Section: Drive Motor
├── Type (text)
├── Rating (numeric, kW)
├── Speed (integer, rpm)
├── Starting Method (text: DOL, Star-Delta, VFD)
├── Motor Efficiency Class (text: IE2, IE3, IE4)
├── Power Supply (text: V/Ph/Hz, e.g., "400/3/50")
├── Ingress Protection (text: IP55, IP65)
├── Insulation (text: Class F, Class H)
├── Mounting/Frame Size (text)
├── Moisture and Thermal Sensors (boolean)
├── Thermal Protection 3*PTC (boolean)
├── Thermal Protection for Bearing PT100 (boolean)
├── Vibration Sensor (boolean)
├── Cooling Method (text)
└── Submerged gearboxes moisture sensor (boolean)

Section: Vendor Scope (checklist)
├── Pump (boolean)
├── Motor (boolean)
├── Cables 20m (boolean)
├── Guide Rails (boolean)
├── Pedestal Coupling (boolean)
├── Guide Bar and Bracket (boolean)
├── Lifting Chain with Shackles (boolean)
└── Spare Parts (array of strings)
```

**TC-CS (Technical Clearance - Screens/Screw Conveyor) Structure:**

plain

Copy

```plain
├── SBU (text)
├── Project Name (text)
├── Client (text)
├── Consultant (text)
├── Project No (text)
├── Location (text)
├── Discipline (text)
├── Clearance Date (date)
├── MR No/Rev. No (text)
├── MR Date (date)
├── Project Manager (text)
├── Product Description (text)
├── Specifications & Datasheets (array)
├── Approved Vendors (array)
├── Received Offers (array of {vendor_name, offer_reference})
├── Enclosures (array)
└── Comments/Remarks (text) with signature blocks
```

**Variance Analysis Structure:**

plain

Copy

```plain
├── Project (text)
├── Project No (text)
├── Equipment (text)
├── Comparison Table:
│   ├── S.No (integer)
│   ├── Equipment Details:
│   │   ├── Name (text)
│   │   └── Tag No (text)
│   ├── Proposal Stage:
│   │   ├── Qty (Nos.) (integer)
│   │   └── Specification (text)
│   └── Detailed Engineering:
│       ├── Qty (Nos.) (integer)
│       └── Specification (text)
└── Remarks (text)
```

---

### 3.4 Feature: Validation & Verification (F-04)

#### 3.4.1 Description

Multi-layer validation system ensuring extracted data meets engineering standards and business rules.

#### 3.4.2 Functional Requirements

**F-04-01:** System shall perform Schema Validation (L1):

- All required fields present per equipment category
- Data types correct (numeric fields contain numbers)
- Enumerated values valid (category must be in approved list)

**F-04-02:** System shall perform Cross-Reference Validation (L2):

- Query Knowledge Graph for equipment relationships
- Verify P&ID tags exist in Equipment List
- Check hydraulic calculations reference valid equipment tags

**F-04-03:** System shall perform Material Master Validation (L3):

- Query Wabag Material Master database
- Validate material codes (SS316L, SS304, Duplex 2205, etc.)
- Suggest alternatives if material unavailable

**F-04-04:** System shall perform Standards Validation (L4):

- Verify ISO, ASTM, API, DIN standard numbers are current
- Flag deprecated standards (e.g., old ISO 9906 versions)
- Suggest current equivalent standards

**F-04-05:** System shall perform Engineering Logic Validation (L5):

- NPSH_available > NPSH_required + 0.5m safety margin
- Pump efficiency within 40-85% range (flag if outside)
- Motor power matches calculated hydraulic power + service factor
- Temperature ratings exceed maximum process temperature

**F-04-06:** System shall perform Historical Validation (L6):

- Compare against similar past projects
- Flag if specification deviates >30% from historical norms
- Suggest "typical" values from past successful RFQs

**F-04-07:** System shall calculate composite Confidence Score (0.0-1.0) based on:

- LLM token probabilities (30%)
- Schema compliance (25%)
- Cross-reference consistency (25%)
- Historical similarity (20%)

---

### 3.5 Feature: Human Review Workflow (F-05)

#### 3.5.1 Description

Intelligent routing of extractions to engineers based on confidence scores, with specialized UI for validation and correction.

#### 3.5.2 Functional Requirements

**F-05-01:** System shall route extractions based on Confidence Score:

- **Auto-Approve:** Confidence ≥ 0.95 AND no critical fields → Direct to RFQ generation
- **Quick Review:** 0.85 ≤ Confidence < 0.95 OR contains critical field → Standard review queue
- **Detailed Review:** Confidence < 0.85 OR discrepancies detected → Expert review queue

**F-05-02:** System shall provide Review Workbench UI with:

- Three-panel layout: Source Documents | Extracted Data | RFQ Preview
- Synchronized scrolling between source and extraction
- Color-coded confidence indicators (green ≥0.95, yellow 0.85-0.95, red <0.85)

**F-05-03:** System shall support inline editing:

- Click any field to edit
- Auto-save drafts
- Track all changes with timestamp and user
- Show "original | modified" diff view

**F-05-04:** System shall provide source linking:

- Click "View Source" on any field → jump to exact page/location in PDF
- Highlight relevant text in source document
- Support multiple sources (show all locations where value appears)

**F-05-05:** System shall support discrepancy resolution:

- Side-by-side comparison of conflicting sources
- Engineer selects which source to trust
- Option to "escalate to client" for clarification
- Resolution logged for future reference

**F-05-06:** System shall support batch operations:

- Multi-select equipment items
- Apply correction to all selected (e.g., change material grade for all pumps)
- Bulk approve after spot-checking samples

**F-05-07:** System shall support comment threads:

- @mention colleagues
- Attach files (photos, sketches, client emails)
- Mark as resolved/unresolved
- Email notifications for mentions

**F-05-08:** System shall track review metrics:

- Time spent reviewing per equipment item
- Correction rate by field type
- Reviewer accuracy (corrections that were later reversed)

---

### 3.6 Feature: RFQ Generation (F-06)

#### 3.6.1 Description

Populate client-specific templates with extracted and validated equipment data.

#### 3.6.2 Functional Requirements

**F-06-01:** System shall support template types:

- **RAS Pump Datasheet** (mechanical equipment)
- **TC-CS Technical Clearance** (screens, conveyors)
- **Variance Analysis** (proposal vs. detailed engineering comparison)
- **Generic Equipment Datasheet** (customizable)

**F-06-02:** System shall auto-select template based on:

- Equipment category (pump → RAS Pump template)
- Client (ADNOC, MWSS, etc. have specific formats)
- Region (Middle East, India, Africa have different standard clauses)

**F-06-03:** System shall populate templates with:

- Header information from project metadata
- Process data from extraction
- Performance data with unit conversions as needed
- Material specifications with full descriptions (not just codes)
- Motor data with Egyptian Code service factors applied
- Vendor scope checklists pre-populated based on Wabag standards

**F-06-04:** System shall preserve Excel features:

- Formulas (e.g., auto-calculate efficiency from power/flow/head)
- Conditional formatting (flag values outside norms)
- Data validation dropdowns (e.g., material selection lists)
- Protected cells (prevent editing of calculated fields)

**F-06-05:** System shall generate output formats:

- Excel (.xlsx) - primary editable format
- PDF - for client/vendor distribution
- JSON - for system integration
- XML - for SAP ERP import

**F-06-06:** System shall support package grouping:

- Auto-group equipment by category (all pumps → Package A)
- Allow manual reassignment
- Generate cover sheet with package summary
- Create vendor distribution lists per package

---

### 3.7 Feature: Variance Analysis (F-07)

#### 3.7.1 Description

Compare equipment specifications between proposal stage and detailed engineering stage, highlighting changes for client approval.

#### 3.7.2 Functional Requirements

**F-07-01:** System shall import proposal stage data (from legacy systems or uploaded files)

**F-07-02:** System shall compare proposal vs. detailed engineering:

- Quantity changes (e.g., 2 pumps → 3 pumps)
- Specification changes (e.g., SS304 → SS316L)
- Performance changes (e.g., 45 m³/hr → 50 m³/hr)

**F-07-03:** System shall classify variances:

- **Client-driven:** Change requested by client (billable variation)
- **Design evolution:** Technical optimization (internal cost)
- **Error correction:** Mistake in proposal (internal cost)
- **Regulatory:** New code requirement (negotiate with client)

**F-07-04:** System shall generate Variance Analysis report:

- Side-by-side comparison table
- Financial impact estimate (if cost data available)
- Approval signature blocks
- Supporting documentation references

---

### 3.8 Feature: System Integration (F-08)

#### 3.8.1 Description

Export RFQ data to external systems and distribute to vendors.

#### 3.8.2 Functional Requirements

**F-08-01:** System shall integrate with SAP ERP:

- Create RFQ headers in SAP MM module
- Upload item details and specifications
- Attach generated documents
- Update status when vendor quotes received

**F-08-02:** System shall support vendor portal integration:

- API upload to approved vendor platforms
- Email distribution with formatted PDF attachments
- Tracking of delivery and open rates

**F-08-03:** System shall integrate with Document Management System:

- Store generated RFQs in project folder
- Maintain revision history
- Link to source documents for audit trail

**F-08-04:** System shall provide SSO integration:

- Azure AD authentication
- Role-based access control (RBAC)
- Project-based permissions (engineer sees only assigned projects)

---

## 4. EXTERNAL INTERFACE REQUIREMENTS

### 4.1 User Interfaces

**UI-01: Project Dashboard**

- List view with filters (client, status, date range)
- Kanban board view (uploading → processing → reviewing → completed)
- Quick stats: projects this month, pending reviews, accuracy trend

**UI-02: Upload Wizard**

- Drag-and-drop with visual feedback
- Document type icons and descriptions
- Progress bars for upload and processing
- Error display with retry options

**UI-03: Review Workbench**

- Three-panel responsive layout (collapsible panels)
- PDF viewer with annotation tools
- Spreadsheet-like data editor
- Real-time collaboration indicators

**UI-04: Admin Dashboard**

- User management
- Template editor (WYSIWYG Excel template builder)
- System health monitoring
- Cost tracking (LLM usage, storage)

### 4.2 Hardware Interfaces

Not applicable - web-based system.

### 4.3 Software Interfaces

| Interface           | Protocol   | Data Format | Purpose                            |
| :------------------ | :--------- | :---------- | :--------------------------------- |
| Claude Opus 4.6 API | HTTPS/REST | JSON        | Primary extraction engine          |
| Kimi 2.5 API        | HTTPS/REST | JSON        | Fallback/cost-optimized extraction |
| SAP ERP             | RFC/OData  | IDoc/JSON   | Procurement integration            |
| Azure AD            | SAML 2.0   | XML         | SSO authentication                 |
| Email Gateway       | SMTP/IMAP  | MIME        | Vendor distribution                |
| Document Management | REST API   | JSON/Binary | File storage                       |

### 4.4 Communications Interfaces

- WebSocket for real-time updates (processing progress, notifications)
- Server-Sent Events (SSE) for long-running extraction jobs
- Email notifications for task assignments and completions

---

## 5. NON-FUNCTIONAL REQUIREMENTS

### 5.1 Performance Requirements

**PR-01:** Upload to extraction completion: < 10 minutes for 200-page document set

**PR-02:** Review workbench load time: < 2 seconds for 100 equipment items

**PR-03:** RFQ generation time: < 30 seconds per package

**PR-04:** Concurrent users: Support 50+ engineers, 10+ projects simultaneously

**PR-05:** API response time: < 500ms for 95% of requests

### 5.2 Safety Requirements

Not applicable - non-safety-critical business system.

### 5.3 Security Requirements

**SR-01:** Data encryption at rest: AES-256

**SR-02:** Data encryption in transit: TLS 1.3

**SR-03:** Authentication: Multi-factor authentication for admin roles

**SR-04:** Authorization: Project-based access control (engineer sees only assigned projects)

**SR-05:** Audit logging: Immutable logs of all data access and modifications

**SR-06:** Data residency: Configurable storage region per project (Middle East, India, EU)

### 5.4 Software Quality Attributes

**QA-01: Availability:** 99.5% uptime (scheduled maintenance windows excluded)

**QA-02: Maintainability:** Modular architecture, comprehensive API documentation

**QA-03: Portability:** Docker containerization, Kubernetes orchestration

**QA-04: Scalability:** Horizontal scaling for processing workers, auto-scaling based on queue depth

**QA-05: Usability:** < 30 minutes training required for basic operation

### 5.5 Business Rules

**BR-01:** Egyptian Code Service Factor: Motors < 40kW: 25%; 40-100kW: 20%; > 100kW: 15%

**BR-02:** Material Approval: All materials must exist in Wabag Material Master v2024.1 or later

**BR-03:** Standard Currency: All costs in project currency (EGP, USD, EUR) with conversion timestamp

**BR-04:** Revision Control: RFQs must include document revision numbers (e.g., "Based on Rev C")

**BR-05:** Approval Authority: RFQs > $500K value require Senior Engineer sign-off

---

## 6. DATA REQUIREMENTS

### 6.1 Logical Data Model

**Entity Relationship Diagram (Conceptual):**

plain

Copy

```plain
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Project   │◄─────►│   Document  │◄─────►│   Extraction│
│             │  1:M  │             │  1:1   │   Job       │
└──────┬──────┘       └─────────────┘       └──────┬──────┘
       │                                            │
       │ 1:M                                        │ 1:M
       ▼                                            ▼
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  Equipment  │◄─────►│Specification│       │   RFQ       │
│   Master    │  1:M  │   Value     │       │  Package    │
└──────┬──────┘       └─────────────┘       └──────┬──────┘
       │                                            │
       │ M:N                                        │ 1:M
       ▼                                            ▼
┌─────────────┐                            ┌─────────────┐
│   Material  │                            │   Vendor    │
│   Grade     │                            │             │
└─────────────┘                            └─────────────┘
```

### 6.2 Data Dictionary

**Table: projects**

Table

Copy

| Field        | Type         | Description         | Constraints                        |
| :----------- | :----------- | :------------------ | :--------------------------------- |
| project_id   | UUID         | Primary key         | PK, auto-generated                 |
| project_code | VARCHAR(50)  | Wabag internal code | Unique, indexed                    |
| project_name | VARCHAR(255) | Descriptive name    | Not null                           |
| client_id    | UUID         | FK to clients       | Indexed                            |
| region       | ENUM         | Geographic region   | ME, India, Africa, EU              |
| status       | ENUM         | Workflow status     | Draft, Active, Completed, Archived |
| created_at   | TIMESTAMP    | Creation time       | Auto-set                           |
| updated_at   | TIMESTAMP    | Last modification   | Auto-update                        |

**Table: equipment_master**

Table

Copy

| Field             | Type         | Description           | Constraints                          |
| :---------------- | :----------- | :-------------------- | :----------------------------------- |
| equipment_id      | UUID         | Primary key           | PK                                   |
| project_id        | UUID         | FK to project         | Indexed, cascade delete              |
| tag_number        | VARCHAR(20)  | Equipment tag         | Not null, format: [A-Z]{1,2}-\d{2,4} |
| category          | ENUM         | Equipment type        | pump, blower, valve, tank, etc.      |
| description       | TEXT         | Narrative description |                                      |
| specifications    | JSONB        | Flexible spec storage | GIN indexed                          |
| confidence_score  | DECIMAL(3,2) | 0.00-1.00             |                                      |
| validation_status | ENUM         | Review state          | pending, approved, corrected         |
| extracted_at      | TIMESTAMP    | Extraction time       |                                      |
| reviewed_by       | UUID         | FK to users           | Nullable                             |
| reviewed_at       | TIMESTAMP    | Review completion     | Nullable                             |

**Table: rfq_packages**

Table

Copy

| Field           | Type         | Description        | Constraints                        |
| :-------------- | :----------- | :----------------- | :--------------------------------- |
| rfq_id          | UUID         | Primary key        | PK                                 |
| project_id      | UUID         | FK to project      | Indexed                            |
| package_name    | VARCHAR(100) | Descriptive name   | Not null                           |
| template_type   | ENUM         | RFQ format         | RAS_PUMP, TC_CS, VARIANCE, GENERIC |
| equipment_ids   | UUID[]       | Array of equipment | Foreign key array                  |
| generated_files | JSONB        | File metadata      |                                    |
| status          | ENUM         | Package state      | draft, approved, sent              |
| approved_by     | UUID         | FK to users        | Nullable                           |
| approved_at     | TIMESTAMP    | Approval time      | Nullable                           |

### 6.3 Data Retention

**Active Projects:** Full data retention for project duration + 7 years (statute of limitations)

**Completed Projects:** Archive to cold storage after 2 years, retain metadata for 10 years

**Audit Logs:** Immutable retention for 10 years

**LLM Training Data:** Anonymized corrections retained indefinitely for model improvement

---

## 7. APPENDICES

### Appendix A: Analysis of Real-World Documents

**Source:** 03_RFQ_Templates.xlsx (analyzed February 2026)

**Key Findings:**

1. **Template Complexity:** RAS Pump template has 63 rows across 12 columns, spanning 8 major sections (Process Data, Performance Data, Material, Motor, etc.)
2. **Data Relationships:** Equipment specifications cross-reference multiple documents:
   - Capacity appears in Hydraulic Calcs (primary), Process Simulation (validation), Equipment List (quantity)
   - Material specifications in Employer Specs (requirements) vs. RFQ (vendor proposal)

3. **Conditional Logic:** Motor selection depends on calculated power + service factor (Egyptian Code)
   - Formula: `Motor_kW = Hydraulic_Power_kW × (1 + Service_Factor_Percent)`
   - Where Service_Factor_Percent = 0.25 if <40kW, 0.20 if 40-100kW, 0.15 if >100kW

4. **Vendor Scope Variability:** Checklist items vary by project (some include cables, some don't)
5. **Revision Tracking:** Documents show evolution from "Proposal Stage" to "Detailed Engineering" with variance tracking

### Appendix B: Glossary

Table

Copy

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
| **RAG**    | Retrieval-Augmented Generation (LLM technique)                 |
| **SBU**    | Strategic Business Unit                                        |
| **SS316L** | Stainless Steel grade 316 Low carbon                           |
| **TEFC**   | Totally Enclosed Fan Cooled motor                              |
| **VFD**    | Variable Frequency Drive                                       |

### Appendix C: Open Issues

Table

Copy

| ID    | Description                                       | Impact | Resolution Target |
| :---- | :------------------------------------------------ | :----- | :---------------- |
| OI-01 | DWG file parsing for native CAD extraction        | Medium | Phase 2           |
| OI-02 | Arabic text RTL support in generated PDFs         | Low    | Phase 2           |
| OI-03 | Integration with legacy Wabag ERP (non-SAP sites) | High   | Phase 3           |
| OI-04 | Mobile offline review mode                        | Medium | Phase 3           |
| OI-05 | AI-powered vendor quote comparison                | Low    | Future release    |

### Appendix D: Document Change History

Table

Copy

| Version | Date       | Author        | Changes                                                                                                                              |
| :------ | :--------- | :------------ | :----------------------------------------------------------------------------------------------------------------------------------- |
| 1.0     | 2026-02-15 | Initial Draft | Baseline requirements                                                                                                                |
| 2.0     | 2026-02-18 | Revised       | Added real-world data structures from RFQ Templates.xlsx analysis, clarified Claude Opus 4.6 integration, expanded validation matrix |

---

**END OF DOCUMENT**
