# RFQ Automation System — MVP Specification

## 1. Purpose

An AI-enhanced system that transforms multi-source engineering documents into structured Request for Quotation (RFQ) packages for VA Tech Wabag's water and wastewater treatment plant projects. A senior engineer currently takes 2–3 days to prepare a single RFQ; this system reduces that to hours.

---

## 2. Core Flow

```
Upload → Classify → Extract → Review → Generate
```

1. **Upload** — Engineer uploads project documents (PDF, DOCX, XLSX, XLS)
2. **Classify** — System auto-detects document type by filename pattern
3. **Extract** — LLM extracts equipment specifications with cross-document validation
4. **Review** — Engineer reviews extracted data, approves or corrects
5. **Generate** — System populates the correct RFQ Excel template and downloads it

---

## 3. MVP Features

### F-01: Document Upload

- Accept up to 20 files per batch (max 500MB total)
- Supported formats: PDF, DOCX, XLSX, XLS
- Extract metadata: page count, file size, MIME type
- Validate file integrity, reject corrupted files
- Support multi-sheet Excel workbooks (a single file may contain multiple equipment datasheets)

### F-02: Document Classification

Auto-classify by filename prefix pattern:

| Pattern       | Document Type                                  |
| ------------- | ---------------------------------------------- |
| `01_*`        | Employer Technical Specifications              |
| `02_*`        | Process Engineering Profile                    |
| `03_RFQ*`     | RFQ Template                                   |
| `04_*`        | Hydraulic Calculation Profile                  |
| `06_*`        | Equipment List                                 |
| `*Specs*.pdf` | Equipment Specification Document               |
| `*Rev##*`     | Revision-tracked document (extract rev number) |

Engineer can override classification if incorrect.

### F-03: Cross-Document Extraction

Extract equipment master data from all uploaded documents:

- **Tag number** (e.g., P-101, TK-201, B-100A)
- **Category** — equipment type (see §3.1)
- **Sub-type** — equipment-specific sub-classification (see §3.2)
- **Process area** — plant section (see §3.3)
- **Process parameters** (capacity, head/pressure, temperature, flow rate)
- **Performance data** (efficiency, power, speed, noise level)
- **Material specifications** (impeller, casing, shaft, seal, fasteners, gears, belts)
- **Drive motor data** (type, rating, speed, power supply, IP rating, insulation, efficiency class, starting method, thermal protection)
- **Scope of supply checklist**

Cross-document validation (Reference Matrix):

| Field                 | Primary Source    | Secondary Source      | Rule                 |
| --------------------- | ----------------- | --------------------- | -------------------- |
| Capacity (m³/hr)      | 04_Hydraulic      | 03_Process            | Within ±10%          |
| Differential Head (m) | 04_Hydraulic      | 02_Process            | Within ±5%           |
| Material Grade        | 01_Employer_Specs | Wabag Material Master | Must exist in list   |
| Motor Power (kW)      | 04_Hydraulic      | Egyptian Code factor  | Apply service factor |
| Quantity              | 06_Equipment_List | P&ID tag count        | Must match           |

#### 3.1 Equipment Categories

| #   | Category                    | Template Type          |
| --- | --------------------------- | ---------------------- |
| 1   | **Submersible Pump**        | RAS Pump Datasheet     |
| 2   | **Vortex Pump**             | RAS Pump Datasheet     |
| 3   | **Progressive Cavity Pump** | RAS Pump Datasheet     |
| 4   | **Blower**                  | Blower Datasheet       |
| 5   | **Screen**                  | TC-CS                  |
| 6   | **Conveyor**                | TC-CS                  |
| 7   | **Mixer**                   | Mixer Datasheet        |
| 8   | **Diffuser**                | Diffuser Datasheet     |
| 9   | **Belt Press**              | Belt Press Datasheet   |
| 10  | **Chlorination System**     | Chlorination Datasheet |
| 11  | **Valve**                   | BOQ List               |
| 12  | **Penstock**                | BOQ List               |
| 13  | **Dismantling Joint**       | BOQ List               |
| 14  | **Grit & Grease Removal**   | TC-CS                  |
| 15  | **Sludge Thickener**        | TC-CS                  |
| 16  | **Sand Classifier**         | TC-CS                  |
| 17  | **Screenings Compactor**    | TC-CS                  |
| 18  | **Container**               | TC-CS                  |
| 19  | **Crane**                   | BOQ List               |
| 20  | **Polymer Dosing System**   | Belt Press Datasheet   |

#### 3.2 Equipment Sub-Types

**Pump sub-types** (each gets its own sheet in a single workbook):

| Sub-Type               | Fluid Handled            | Impeller Type      |
| ---------------------- | ------------------------ | ------------------ |
| RAS Pump               | Concentrated sludge      | VTF                |
| Excess Sludge Pump     | Concentrated sludge      | VTF                |
| Primary Sludge Pump    | Concentrated sludge      | VTF                |
| Supernatant Pump       | Supernatant water        | VTF                |
| Vortex Pump            | Scum, grit, oil & grease | Vortex             |
| Portable Drainage Pump | Raw sewage water         | VTF                |
| Thickened Sludge Pump  | Thickened sludge         | Progressive cavity |

**Blower sub-types:** Aeration blower, Grit air blower, Re-aeration blower.

#### 3.3 Process Areas

| #   | Process Area                     |
| --- | -------------------------------- |
| 1   | Headworks / Inlet Works          |
| 2   | Primary Sedimentation (PST)      |
| 3   | Primary Sludge Pump Station      |
| 4   | Aeration Tank                    |
| 5   | Final Sedimentation (FST)        |
| 6   | RAS & WAS Pump Station           |
| 7   | Sludge Gravity Thickener         |
| 8   | Thickened Sludge Pump Station    |
| 9   | Scum Pump Station                |
| 10  | Supernatant Pump Station         |
| 11  | Blower Room                      |
| 12  | Belt Press / Dewatering Building |
| 13  | Chlorination Building            |

### F-04: AI Operating Rules

These rules govern how the extraction engine and LLM layer process data. Each extracted field carries a `confidence` score (0.0–1.0) and a `source_ref` linking back to the originating document, page, and cell/section.

#### Rule 1 – Source of Truth

Only use uploaded documents and explicit user instructions. Never invent, guess, or assume values. If a value is not found in any source document → set the field to `null` with a `status` of `"TBD"` and `confidence: 0.0`.

#### Rule 2 – Precedence Hierarchy

When the same field appears in multiple documents, resolve using this priority order:

1. Employer's Requirements / Project Specifications (`01_*`, `SectionVI_*`)
2. Process Engineering (`02_*`)
3. Hydraulic Profile (`04_*`)
4. Equipment List (`06_*`)
5. Industry Standards (DIN, IEC, EN)

If conflict remains after applying precedence, store both values in a `conflicts[]` array on the field, set `confidence: 0.0`, and flag `requires_review: true`. Never auto-resolve conflicts.

#### Rule 3 – Cell Authorization & Output Metadata

Only populate fields that are mapped as `editable: true` in the template schema. Each AI-populated field must carry:

- `confidence` (float 0.0–1.0)
- `source_ref` (document name, page/sheet, cell/section)
- `status`: one of `"extracted"`, `"conflict"`, `"tbd"`

Use the template's unit column to validate data types and unit consistency. Apply the VTF Rule: vendor-related fields default to `"VTF (Vendor to Furnish)"` unless specs explicitly provide a value.

#### Rule 4 – Confidence-Based Field Population

Each extracted field is assigned a confidence score that determines its status:

| Case  | Condition                                     | Confidence | Status                                                                         |
| ----- | --------------------------------------------- | ---------- | ------------------------------------------------------------------------------ |
| **A** | Explicit value, single source, no conflict    | 0.85–1.0   | `"extracted"`                                                                  |
| **B** | Two conflicting values from different sources | 0.0        | `"conflict"` — store both values in `conflicts[]`, set `requires_review: true` |
| **C** | Partial match or inferred from context        | 0.4–0.84   | `"extracted"` — set `requires_review: true`                                    |
| **D** | No data found in any source                   | 0.0        | `"tbd"` — value is `null`                                                      |

#### Rule 5 – Calculations

Only calculate if the formula is explicitly stated in documents AND all inputs are available with `confidence >= 0.85`. Never derive formulas or assume constants. Calculated values inherit the lowest confidence of their inputs.

#### Rule 6 – RFQ Limitations

The system may transfer, copy, and match values between documents. The system may NOT:

- Size equipment or select motor power
- Define flow rates or pressure requirements
- Decide duty/standby philosophy or equipment configuration
- Override any engineer-specified value

#### Rule 7 – Safety & Integrity

Accuracy over completeness. Leaving a field as `"tbd"` is correct behavior. Speculative output is unacceptable. Every populated field must have a traceable `source_ref`.

#### Rule 8 – Stop Conditions

The extraction pipeline must halt and flag for human review when:

- Column-to-field mapping is ambiguous (`confidence < 0.4`)
- Sources conflict without clear precedence resolution
- Unit mismatch is detected between source and template
- User intent cannot be safely inferred from available data

#### Rule 9 – Employer's Requirements Golden Rule

Employer's Requirements / Project Specifications always prevail over all other documents in any conflict. No averaging, interpolation, or interpretation. Values from `01_*` or `SectionVI_*` documents override all others with no exception.

#### Rule 11 – Final Guiding Rule

Every extracted value must be auditable: traceable to a source, assigned a confidence score, and defensible under review. The system's job is not to look complete — it is to be correct and transparent.

### F-06: RFQ Generation

Seven template types. All datasheets use a **dual-column layout** (WABAG specification + VENDOR response).

#### Template 1: RAS Pump / Mechanical Datasheet

**Used for:** All pump types (submersible, vortex, progressive cavity)

- **Header:** Project name, location, client, consultant, WABAG doc no., rev. no., date
- **Process Data:** Fluid handled, quantity (duty + standby), capacity (m³/hr), ambient temperature (°C), solid handling size (mm), differential head (mwc), head range, service duty
- **Mechanical Data:** Type, impeller type, design standard (DIN 19569), speed (rpm), stages, efficiency (%), power at duty point (kW), shut-off head (m)
- **Material of Construction:** Impeller, casing, shaft, seal, fasteners, foundation bolts, bearing, guide rail, lifting chain
- **Drive Motor:** Type, rating (kW), speed (rpm), starting method (VFD/star-delta), efficiency class (IE3), power supply (V/Ph/Hz), IP68, insulation class, thermal protection (3×PTC + PT100), vibration sensor, cooling method
- **Vendor Scope:** Pump, motor, cables (20m), guide rails, coupling, lifting chain, spare parts (3 years)
- **Notes:** VTF legend, vendor deliverables (data sheets, performance curves, GA drawings, guarantee tables)

**Output:** Multi-sheet Excel — one sheet per pump sub-type.

#### Template 2: Blower Datasheet

**Used for:** Aeration, grit, re-aeration blowers

- **Header:** Project, location, client, consultant, doc numbers
- **Process Data:** Fluid (Air), quantity, capacity (Nm³/hr), suction/discharge pressure (mbar), suction/discharge temperature (°C), relative humidity (%)
- **Mechanical Data:** Design standard (DIN 1945), type (rotary lobe / Roots), blower speed (rpm), shaft power (kW), drive type (belt & pulley), volumetric efficiency (%), noise level (dB(A)), safety valve, inlet filter, silencers, acoustic hood
- **Material of Construction:** Casing (GG20), shaft (C45N), gears (16 Mn Cr5E), shaft seal, base frame, pulleys, V-belt
- **Drive Motor:** Type (IEC), rating (kW), power supply (V/Ph/Hz), motor frame (TEFC), IP54, insulation (Class B), starting method (VFD), thermal protection (klaxon switches)
- **Scope of Supply:** Blower, base frame, motor, pulleys, V-belt, expansion bellows, filters, silencers, acoustic hood, spare parts (3 years)
- **Notes:** VTF legend, valid C14 certificate required

#### Template 3: TC-CS (Technical Clearance — Steel Works)

**Used for:** Screens, conveyors, grit & grease removal, sludge thickener, sand classifier, screenings compactor, containers

- **Header Block:** SBU, project name, client, consultant, project no., location, MR no./rev.
- **Product Description** (equipment-specific datasheet)
- **Approved Vendors** list
- **Received Offers** tracking
- **Signature Block:** Prepared By → Checked By → Approved By

#### Template 4: Belt Press Datasheet

**Used for:** Belt press, polymer dosing systems

- **Process Data:** Equipment name, quantity, flow per unit (m³/h), belt width (m), DS concentration in/out (%)
- **Mechanical Data:** Wash pumps, air compressor, sludge conveyor, sludge cake container
- **Drive Unit:** Motor type, variable speed control, drive rating (kW), insulation (F/B), IP55, duty class (S1), efficiency (IE3)
- **Material of Construction:** Frame (SS 1.4401), rollers, belt (monofilament polyester), scrapper (polypropylene), drainage pans (SS 304), fasteners (A4)
- **Scope:** Complete assembly, wash pumps, compressor, conveyors, polymer dosing system, control panel (IP65), spare parts (3 years)

#### Template 5: Diffuser Datasheet

**Used for:** Fine bubble disc diffuser systems

- **Plant Data:** Flow rate (m³/d), ambient/water temperature
- **Tank Dimension:** Number of tanks, L × W × D, volume
- **Aeration System:** Diffuser type, total quantity, AOTR/SOTR (kg O₂/hr), water depth, max air demand
- **Material:** Diffusers, drop legs (SS 1.4307), headers (UPVC), supports (SS 1.4307)
- **Scope:** Diffusers, distribution pipes, clamps, supports, 5% spare diffusers

#### Template 6: Chlorination Datasheet

**Used for:** Gas chlorination systems

- **Process Data:** Plant capacity (m³/day), dosing rate (mg/l)
- **Chlorinator Specs:** Capacity (kg/hr), units (duty + standby + future), type (vacuum operated), cylinders/tonner count
- **Scope:** Chlorinators, injector, booster pumps, changeover device, fume detector, fume treatment system, safety equipment, control panel (IP54), spare parts (3 years)

#### Template 7: BOQ List (Valves / Penstocks / Dismantling Joints / Cranes)

**Used for:** Valves, penstocks, dismantling joints, cranes

- **Columns:** Item #, Description, DN (mm), PN (bar), Connection type, Operation (Manual/Electrical), Material, Quantity, Fluid handled
- **Grouped by Process Area**
- **Valve Materials:** Body (GGG-50), trim (CZ132 brass), stem (SS 1.4021), seals (EPDM/NBR)

#### Template 8: Mixer Datasheet

**Used for:** Submersible mixers (aeration, anoxic zones)

- **Design Data:** Biological treatment type, no. of tanks, mixers per tank, tank dimensions, fluid temperature
- **Mechanical Data:** Mixer type (submerged propeller), power (kW), propeller speed/diameter/blades, bearing lifetime (100,000 hr), max torque, mixing flow (m³/s), service factor
- **Drive Motor:** Type (submerged), IP68, leak detector (IP69), insulation (Class H), efficiency (min 80%), thermal sensors, starting method (star-delta), excess power (0.25), starts/hr (≥15)
- **Material:** Propeller (SS/glass fibre polyurethane), shaft (SS 1.4021), guide bar/wire rope/lifting chain (SS 1.4307), motor casing (GG25)
- **Scope:** Mixer with motor, monitoring unit, cable (15m), lifting mechanism, spare parts (3 years)

#### Auto-Selection Logic

| Equipment Category                                                         | Template               |
| -------------------------------------------------------------------------- | ---------------------- |
| All pump types                                                             | RAS Pump Datasheet     |
| Blower                                                                     | Blower Datasheet       |
| Screen, conveyor, grit/grease, thickener, classifier, compactor, container | TC-CS                  |
| Belt press, polymer dosing                                                 | Belt Press Datasheet   |
| Diffuser                                                                   | Diffuser Datasheet     |
| Chlorination system                                                        | Chlorination Datasheet |
| Valve, penstock, dismantling joint, crane                                  | BOQ List               |
| Mixer                                                                      | Mixer Datasheet        |

Output: Excel (.xlsx) with formulas and conditional formatting preserved.

---

## 4. Data Model

```
Project 1:M Document        (uploaded source files)
Project 1:M Equipment       (extracted equipment specs)
Project 1:M RFQPackage      (generated RFQ outputs)

Equipment 1:M Review        (human review records)
Equipment M:1 EquipmentCategory
```

- **Project** — name, location, client, consultant, project number, capacity (m³/d)
- **RFQPackage** — template type, generated file path, revision, status (draft/final)
- **Review** — equipment ref, reviewer, action (approve/reject/edit), corrections (JSONB), notes, timestamp

Equipment stores specifications as JSONB for flexible per-category schema.

---

## 5. Business Rules

### 5.1 Egyptian Code Service Factor

| Motor Rating | Service Factor |
| ------------ | -------------- |
| < 40 kW      | +25%           |
| 40–100 kW    | +20%           |
| > 100 kW     | +15%           |

Motor power = max power on curve (80–110% head range) × service factor.

### 5.2 Equipment Working Range

- **Pumps:** 80–110% of duty point head is the minimum accepted working range
- **Blower speed:** Max 1,500 rpm

### 5.3 Material Codes

| Code       | Material                | Application                 |
| ---------- | ----------------------- | --------------------------- |
| GG20       | Grey Cast Iron Grade 20 | Blower casings              |
| GG25       | Grey Cast Iron Grade 25 | Pump impellers, casings     |
| SS 1.4301  | Stainless Steel 304     | Shafts, guide rails         |
| SS 1.4307  | Stainless Steel 304L    | Guide bars, supports        |
| SS 1.4401  | Stainless Steel 316     | Belt press frame            |
| SS 1.4021  | Stainless Steel 420     | Mixer shafts, valve stems   |
| C45N       | Carbon Steel            | Blower shafts               |
| 16 Mn Cr5E | Case-hardening Steel    | Blower gears                |
| A4         | SS Fasteners (316)      | Submersible equipment bolts |
| GGG-50     | Ductile Iron            | Valve bodies                |
| EPDM / NBR | Rubber                  | Seals and O-rings           |
| UPVC       | Unplasticized PVC       | Diffuser headers            |

### 5.4 Motor Specifications (Defaults)

| Parameter          | Submersible   | Indoor (Blower) | Belt Press    |
| ------------------ | ------------- | --------------- | ------------- |
| IP Rating          | IP68          | IP54            | IP55          |
| Insulation         | F (rise to B) | Class B         | F/B           |
| Efficiency         | IE3           | —               | IE3           |
| Power Supply       | 380V/3Ph/50Hz | 380V/3Ph/50Hz   | 400V/3Ph/50Hz |
| Thermal Protection | 3×PTC + PT100 | Klaxon switches | On windings   |

### 5.5 Design Standards

| Standard              | Application             |
| --------------------- | ----------------------- |
| DIN 19569             | Submersible pump design |
| DIN 1945              | Blower design           |
| IEC                   | Motor standard          |
| DIN 2576 B / DIN 2632 | Valve flange standards  |
| EN 1563               | Cast iron grades        |

### 5.6 Universal Constraints

- Spare parts: Sufficient for 3 years operation (all equipment)
- Ambient temperature: Max 45°C
- All stainless steel: pickled and passivated in acid bath
- Revision convention: `Rev00`, `Rev01`, `Rev02`

---

## 6. LLM Configuration

- Primary model: opus (via OpenRouter, `moonshotai/kimi-k2`)
- Fallback model: sonnet (via OpenRouter, `minimax/minimax-01`)
- Router tries primary, falls back on failure/timeout
- Extraction uses structured JSON output mode
- Equipment-specific prompts per category

---

## 8. Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), Pydantic
- **Database:** PostgreSQL 16, Supabase
- **LLM:** OpenRouter (opus / sonnet)
- **Document Processing:** pypdf, python-docx, openpyxl, xlrd (legacy .xls), Pillow
- **Excel Generation:** openpyxl (formula + conditional formatting preserved)
- **Migrations:** Alembic
- **Package Manager:** uv
- **Code Quality:** ruff, mypy (strict), pytest (80% coverage)
- **Containerization:** Docker, docker-compose
