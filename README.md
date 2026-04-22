# RFQ Automation System — Software Requirements Specification

## 1. Purpose

An AI-enhanced system that transforms multi-source engineering documents into structured Request for Quotation (RFQ) packages for VA Tech Wabag's water and wastewater treatment plant projects. A senior engineer currently takes 2–3 days to prepare a single RFQ; this system reduces that to hours.

The system draws from real-world project packages (e.g., Old-Kohafa WWTP, Fayoum) containing tender documents, employer specifications, hydraulic profiles, equipment lists, and reference RFQ templates across 20+ equipment categories.

---

## 2. Core Flow

```
Upload → Classify → Extract → Generate
```

1. **Upload** — Engineer uploads project documents (PDF, DOCX, XLSX, XLS)
2. **Classify** — System auto-detects document type by filename pattern
3. **Extract** — LLM extracts equipment specifications with cross-document validation
4. **Generate** — System populates the appropriate RFQ Excel template (fixed templates) and produces a single Excel file for download

No human-in-the-loop review step. The LLM operates autonomously under the AI Operating Rules (§F-04); every populated field carries confidence and source-reference metadata so the output is fully auditable after the fact.

---

## 3. MVP Features

### F-01: Document Upload

- Accept up to 20 files per batch (max 500MB total)
- Supported formats: PDF, DOCX, XLSX, XLS
- Extract metadata: page count, file size, MIME type
- Validate file integrity, reject corrupted files
- Support multi-sheet Excel workbooks (a single `.xls`/`.xlsx` may contain 6+ equipment datasheets)

### F-02: Document Classification

Auto-classify by filename prefix pattern:

| Pattern                           | Document Type                                  |
| --------------------------------- | ---------------------------------------------- |
| `01_*`                            | Employer Technical Specifications              |
| `02_*`                            | Process Engineering Profile                    |
| `03_*` (specs)                    | Process Simulation Reports                     |
| `03_RFQ*`                         | RFQ Template                                   |
| `04_*`                            | Hydraulic Calculation Profile                  |
| `05_*`                            | Hydraulic Profile (DWG/CAD)                    |
| `06_*`                            | Equipment List                                 |
| `SectionII_*`                     | Tender DataSheet                               |
| `SectionIII_*`                    | Tender Evaluation Method                       |
| `SectionIV_*`                     | Eligibility & Qualification Criteria           |
| `SectionV_*`                      | Tender Forms                                   |
| `SectionVI_*`                     | Employer's Requirements                        |
| `SectionVII_*`                    | Contract Conditions & Forms                    |
| `*Specs*.pdf`                     | Equipment Specification Document               |
| `General Motors Specs*`           | General Motor Specifications                   |
| `GENERAL MECHANICAL WORKS*`       | General Mechanical Works Specs                 |
| `*DataSheet*.pdf`                 | Equipment DataSheet                            |
| `Local control panels DataSheet*` | Local Control Panel DataSheet                  |
| `Authorization letter*`           | RFQ Authorization Letter                       |
| `*Rev##*`                         | Revision-tracked document (extract rev number) |

Engineer can override classification if incorrect.

**Revision Detection:** The system shall parse revision indicators from filenames (`Rev00`, `Rev01`, `rev.01`, `Rev00a`, etc.) and use the latest revision as the active document.

### F-03: Cross-Document Extraction

Extract equipment master data from all uploaded documents:

- **Tag number** (e.g., P-101, TK-201, B-100A)
- **Category** — one of the expanded equipment categories (see §3.1)
- **Sub-type** — equipment-specific sub-classification (see §3.2)
- **Process area** — which plant section the equipment belongs to (see §3.3)
- **Process parameters** (capacity, head, temperature, pressure, flow rate)
- **Performance data** (efficiency, power, speed, noise level)
- **Material specifications** (impeller, casing, shaft, seal, fasteners, gears, belts)
- **Drive motor data** (type, rating, speed, power supply, IP rating, insulation, efficiency class, starting method, thermal protection, cooling method)
- **Scope of supply checklist** (per equipment category)
- **Vendor deliverables** (data sheets, curves, GA drawings, certificates)
- **Spare parts requirements** (duration, percentage)

Cross-document validation (Reference Matrix):

| Field                     | Primary Source         | Secondary Source      | Rule                 |
| ------------------------- | ---------------------- | --------------------- | -------------------- |
| Capacity (m³/hr)          | 04_Hydraulic           | 03_Process            | Within ±10%          |
| Differential Head (m)     | 04_Hydraulic           | 02_Process            | Within ±5%           |
| Material Grade            | 01_Employer_Specs      | Wabag Material Master | Must exist in list   |
| Motor Power (kW)          | 04_Hydraulic           | Egyptian Code factor  | Apply service factor |
| Quantity                  | 06_Equipment_List      | P&ID tag count        | Must match           |
| Discharge Pressure (mbar) | Blower spec sheet      | Process design        | Within ±10%          |
| DN / PN (valves)          | Valve List             | Piping P&ID           | Must match           |
| Belt Width (m)            | Belt Press datasheet   | Process design        | Must match           |
| Dosing Rate (mg/l)        | Chlorination datasheet | Process requirements  | Must match           |

#### 3.1 Equipment Categories

The system shall support the following equipment categories:

| #   | Category                         | Template Type                 | Example Equipment                                                           |
| --- | -------------------------------- | ----------------------------- | --------------------------------------------------------------------------- |
| 1   | **Submersible Pump**             | RAS Pump Datasheet            | RAS pump, excess pump, primary sludge pump, supernatant pump, drainage pump |
| 2   | **Vortex Pump**                  | RAS Pump Datasheet            | Scum/grit/oil & grease pump                                                 |
| 3   | **Progressive Cavity Pump**      | Thickened Sludge Datasheet    | Thickened sludge pump                                                       |
| 4   | **Blower**                       | Blower Datasheet              | Aeration blower, grit blower, re-aeration blower                            |
| 5   | **Screen**                       | TC-CS / Steel Works Datasheet | Mechanical fine screen, coarse screen, manual screen                        |
| 6   | **Conveyor**                     | TC-CS / Steel Works Datasheet | Screenings conveyor, belt press conveyor, screw conveyor                    |
| 7   | **Mixer**                        | Mixer Datasheet               | Submersible mixer (aeration, anoxic)                                        |
| 8   | **Diffuser**                     | Diffuser Datasheet            | Fine bubble disc diffuser                                                   |
| 9   | **Belt Press**                   | Belt Press Datasheet          | Mechanical dewatering belt press                                            |
| 10  | **Chlorination System**          | Chlorination Datasheet        | Gas chlorinators, fume treatment                                            |
| 11  | **Crane**                        | Crane Datasheet               | Overhead crane, gantry crane, jib crane                                     |
| 12  | **Valve**                        | Valve List (BOQ)              | Gate, check, butterfly, ball, quick valve                                   |
| 13  | **Penstock**                     | Penstock List (BOQ)           | Sluice gates, penstocks                                                     |
| 14  | **Dismantling Joint**            | List (BOQ)                    | Expansion/dismantling joints                                                |
| 15  | **Grit & Grease Removal**        | Steel Works Datasheet         | Grit removal bridge, grease removal system                                  |
| 16  | **Sand Classifier**              | Steel Works Datasheet         | Sand classifier, grit washer                                                |
| 17  | **Sludge Thickener**             | Steel Works Datasheet         | Gravity sludge thickener bridge                                             |
| 18  | **Screenings Compactor**         | Steel Works Datasheet         | Screenings washer/compactor                                                 |
| 19  | **Polymer Dosing System**        | Dosing System Datasheet       | Polymer preparation & dosing unit                                           |
| 20  | **Container**                    | Container Datasheet           | Screening container, sludge cake container                                  |
| 21  | **Sedimentation Tank Equipment** | Steel Works Datasheet         | Scraper bridges, scum skimmers                                              |
| 22  | **Piping (Internal)**            | Piping BOQ                    | Internal plant piping                                                       |
| 23  | **Stainless Steel Items**        | SS BOQ                        | Miscellaneous stainless steel items                                         |
| 24  | **Instrument**                   | Instrument DataSheet          | Level, flow, pressure transmitters                                          |

#### 3.2 Equipment Sub-Types

Within each category, equipment has sub-types that map to a fixed sheet within the relevant datasheet template. Pump sub-types observed in Old-Kohafa:

| Pump Sub-Type          | Fluid Handled            | Typical Capacity | Impeller Type      |
| ---------------------- | ------------------------ | ---------------- | ------------------ |
| RAS Pump               | Concentrated sludge      | 860 m³/hr        | VTF                |
| Excess Sludge Pump     | Concentrated sludge      | 45 m³/hr         | VTF                |
| Primary Sludge Pump    | Concentrated sludge      | 50 m³/hr         | VTF                |
| Supernatant Pump       | Supernatant water        | 150 m³/hr        | VTF                |
| Vortex Pump            | Scum, grit, oil & grease | 18 m³/hr         | Vortex             |
| Portable Drainage Pump | Raw sewage water         | 50 m³/hr         | VTF                |
| Thickened Sludge Pump  | Thickened sludge         | Per design       | Progressive cavity |

Blower sub-types: Aeration blower, Grit air blower, Re-aeration blower.

#### 3.3 Process Areas

Equipment is organized by plant process area:

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
| 9   | Primary Scum Pump Station        |
| 10  | Final Scum Pump Station          |
| 11  | Supernatant Pump Station         |
| 12  | Aeration Air Blower Room         |
| 13  | Re-Aeration Blower               |
| 14  | Grit Air Blower                  |
| 15  | Belt Press / Dewatering Building |
| 16  | Chlorination Building            |
| 17  | Administration / Utilities       |

### F-04: AI Operating Rules

These rules govern how the extraction engine and LLM layer process data. Each extracted field carries a `confidence` score (0.0–1.0) and a `source_ref` linking back to the originating document, page, and cell/section. The rules are the sole safeguard on output quality — there is no human review step — so they are enforced strictly.

#### Rule 1 – Source of Truth

Only use uploaded documents and explicit user instructions. Never invent, guess, or assume values. If a value is not found in any source document → set the field to `null` with a `status` of `"TBD"` and `confidence: 0.0`.

#### Rule 2 – Precedence Hierarchy

When the same field appears in multiple documents, resolve using this priority order:

1. Employer's Requirements / Project Specifications (`01_*`, `SectionVI_*`)
2. Process Engineering (`02_*`)
3. Hydraulic Profile (`04_*`)
4. Equipment List (`06_*`)
5. Industry Standards (DIN, IEC, EN)

If conflict remains after applying precedence, store both values in a `conflicts[]` array on the field, set `confidence: 0.0`, and mark `status: "conflict"`. Never auto-resolve conflicts — emit the conflict as output metadata.

#### Rule 3 – Cell Authorization & Output Metadata

Only populate fields that are mapped as `editable: true` in the template schema. Templates are fixed and immutable — the LLM only writes values into predefined editable cells. It must never alter template structure, headers, formulas, merged-cell layout, or conditional formatting.

Each AI-populated field must carry:

- `confidence` (float 0.0–1.0)
- `source_ref` (document name, page/sheet, cell/section)
- `status`: one of `"extracted"`, `"conflict"`, `"tbd"`

Use the template's unit column to validate data types and unit consistency. Apply the VTF Rule: vendor-related fields default to `"VTF (Vendor to Furnish)"` unless specs explicitly provide a value.

#### Rule 4 – Confidence-Based Field Population

Each extracted field is assigned a confidence score that determines its status:

| Case  | Condition                                     | Confidence | Status                                                 |
| ----- | --------------------------------------------- | ---------- | ------------------------------------------------------ |
| **A** | Explicit value, single source, no conflict    | 0.85–1.0   | `"extracted"`                                          |
| **B** | Two conflicting values from different sources | 0.0        | `"conflict"` — store both values in `conflicts[]`      |
| **C** | Partial match or inferred from context        | 0.4–0.84   | `"extracted"` (low-confidence flag in output metadata) |
| **D** | No data found in any source                   | 0.0        | `"tbd"` — value is `null`                              |

#### Rule 5 – Calculations

Only calculate if the formula is explicitly stated in documents AND all inputs are available with `confidence >= 0.85`. Never derive formulas or assume constants. Calculated values inherit the lowest confidence of their inputs.

#### Rule 6 – RFQ Limitations

The system may transfer, copy, and match values between documents. The system may NOT:

- Size equipment or select motor power
- Define flow rates or pressure requirements
- Decide duty/standby philosophy or equipment configuration
- Override any engineer-specified value
- Modify the template layout, structure, or formulas

#### Rule 7 – Safety & Integrity

Accuracy over completeness. Leaving a field as `"tbd"` is correct behavior. Speculative output is unacceptable. Every populated field must have a traceable `source_ref`.

#### Rule 8 – Hard Stop Conditions

The extraction pipeline must halt and emit the partial output with explicit error flags when:

- Column-to-field mapping is ambiguous (`confidence < 0.4`)
- Sources conflict without clear precedence resolution
- Unit mismatch is detected between source and template
- User intent cannot be safely inferred from available data

These conditions are recorded in the audit trail (§F-09) and surfaced as cell-level annotations in the generated Excel file.

#### Rule 9 – Employer's Requirements Golden Rule

Employer's Requirements / Project Specifications always prevail over all other documents in any conflict. No averaging, interpolation, or interpretation. Values from `01_*` or `SectionVI_*` documents override all others with no exception.

#### Rule 11 – Final Guiding Rule

Every extracted value must be auditable: traceable to a source, assigned a confidence score, and defensible under review. The system's job is not to look complete — it is to be correct and transparent.

### F-06: RFQ Generation

Templates are **fixed and immutable per equipment type** — the engineering team authors one canonical template per equipment category (e.g. one blower template, one RAS pump template, one mixer template). These templates live **outside** this system; the engineer uploads the appropriate template(s) in the same batch as the source documents (§F-01), classified via the `03_RFQ*` filename pattern (§F-02). See §F-11 for template handling. The LLM populates the predefined editable cells only — it does not create, modify, or restructure templates under any circumstances. Template structure, headers, formulas, and conditional formatting are preserved byte-for-byte in the output.

> The eight template structures below are **illustrative examples** derived from past Wabag projects (see Appendix A). They document what the engineer-authored canonical templates typically look like for common equipment types; the system does not bundle these templates — they arrive with the engineer's upload batch.

Six primary template types:

#### Template 1: RAS Pump / Mechanical Datasheet

**Used for:** All submersible pumps, excess pumps, primary sludge pumps, supernatant pumps, vortex pumps, drainage pumps

**Structure:**

- **Header:** Project name, location, client, consultant, WABAG doc no., rev. no., date
- **Process Data:** Fluid handled, quantity (duty + standby), capacity (m³/hr), ambient temperature (°C), solid handling size (mm), suction pressure (bar), differential head (mwc), head range, service duty
- **Performance / Mechanical Data:** Type, impeller type, design standard (DIN 19569), full load speed (rpm), no. of stages, pump efficiency (%), power at duty point (kW), shut-off head (m), working range rule (80–110% of duty point)
- **Material of Construction:** Impeller, casing, shaft, type of seal, fasteners, foundation bolts, bearing, guide rail, lifting chain
- **Drive Motor:** Type, rating (kW), speed (rpm), starting method (VFD/star-delta), motor efficiency class (IE3), power supply (V/Ph/Hz), ingress protection (IP68), insulation class, mounting/frame size, moisture & thermal sensors, thermal protection (PTC, PT100), vibration sensor, cooling method
- **Vendor Scope:** Pump, motor, cables (20m), guide rails, pedestal coupling, guide bar & bracket, lifting chain with shackles, spare parts (3 years)
- **Notes:** VTF legend, vendor requirements (data sheets, performance curves, GA drawings, guarantee tables — filled/signed/stamped, general catalogue)

#### Template 2: Blower Datasheet

**Used for:** Aeration blowers, grit blowers, re-aeration blowers

**Structure:**

- **Header:** Project, location, client, consultant, doc numbers
- **Process Data:** Fluid (Air), quantity, capacity (Nm³/hr), suction/discharge pressure (mbar), suction/discharge temperature (°C), relative humidity (%), location (indoor/outdoor), service duty
- **Mechanical Data:** Design standard (DIN 1945), type (positive displacement rotary lobe / Roots type), direction of rotation, blower speed (rpm), shaft power (kW), drive type (belt & pulley), volumetric efficiency (%), noise level (dB(A)), safety valve type, lubrication, inlet filter, suction & discharge silencer, sound enclosure, unloading device, expansion bellow, anti-vibration pads, acoustic hood
- **Material of Construction:** Casing (GG20), shaft (C45N carbon steel), gears (16 Mn Cr5E), shaft seal, sleeve, base frame, pulleys, V-belt, V-belt guard, suction filter/silencer, discharge silencer
- **Drive Motor:** Type (IEC Standard), rating (kW), max speed (rpm), nominal current (Amp), power supply (V/Ph/Hz), motor frame (TEFC), cooling, protection degree (IP54), insulation (Class B), mounting/frame size, starting method (VFD), service factor, thermal protection (klaxon switches)
- **Scope of Supply:** Blower, base frame, motor slide rail, motor, pulleys, V-belt/guard, expansion bellows, suction filter, silencers, anti-vibration pads, safety valve, check/unloading valve, foundation bolts, acoustic hood, spare parts (3 years)
- **Notes:** VTF legend, vendor deliverables including valid C14 certificate

#### Template 3: TC-CS (Technical Clearance — Steel Works)

**Used for:** Screens (mechanical fine, coarse, manual), conveyors (screenings, belt press), grit & grease removal, sedimentation tank equipment, sludge thickener bridges, screenings compactors, containers

**Structure:**

- **Header Block:** SBU, project name, client, consultant, project no., location, discipline, clearance date, MR no./rev. no., MR date, project manager
- **Product Description** (equipment-specific datasheet embedded)
- **Specifications & Datasheets** (references)
- **Approved Vendors** (list)
- **Received Offers** (vendor name, offer reference)
- **Enclosures**
- **Comments / Remarks**
- **Signature Block:** Date, Prepared By, Checked By, Approved By

#### Template 4: Belt Press Datasheet

**Used for:** Mechanical dewatering belt press, polymer dosing systems

**Structure:**

- **Header:** Project, location, client, consultant, doc numbers
- **Process Data:** Equipment name, quantity, flow per unit (m³/h), specific density (kg/m³), belt width (m), working time (h/d), thickened sludge feeding pump head (m), DS concentration in/out (%)
- **Mechanical Data (sub-equipment):** Wash pumps (flow, head, type), air compressor (capacity, head), sludge conveyor (capacity, length), sludge cake container (capacity, quantity)
- **Drive Unit Details:** Motor type (electric/hydraulic), variable speed control, drive rating (kW), ambient temperature, insulation class (F/B), ingress protection (IP55), voltage/frequency, duty class (S1), motor efficiency class (IE3), thermal/overload protection, gear type & service factor
- **Material of Construction:** Main structural frame (1.4401 SS), conditioning tank/mixing paddle/shaft, rollers, washing nozzles & header, roller shaft (chromium alloy), belt material (monofilament polyester), scrapper blade (polypropylene), drainage pans (SS 304), fasteners (A4), control panel (SS)
- **Scope of Supply:** Complete belt press assembly, wash pumps, air compressor, sludge cake conveyors (horizontal + inclined), fasteners & anchor bolts, polymer dosing system, sludge cake container, commissioning spares, control panel (IP65), spare parts (3 years)

#### Template 5: Diffuser Datasheet

**Used for:** Fine bubble disc diffuser systems, aeration systems

**Structure (Sections A–I):**

- **A — General Information:** Plant location, project status, application
- **B — Plant Data:** Plant flow rate (m³/d), average/peak flow rate (m³/h), ambient temperature, water temperature range
- **C — Aeration Tank Dimension:** Tank material, number of tanks, length/width/depth (m), unit/total volume (m³)
- **D — Aeration System:** Diffuser type, total quantity, AOTR (kg O₂/hr), SOTR (kg O₂/hr), water depth, max air demand, blower specs (total air flow, quantity duty+standby, pressure difference)
- **E — Material of Construction:** Diffusers, drop legs (SS 1.4307), manifold/header pipes (UPVC), distribution grids (UPVC), supports (SS 1.4307)
- **F — Accessories:** All required supports, fixtures, etc.
- **G — Spare Parts:** Supply 5% air diffusers
- **H — Scope of Supply:** Diffusers, distribution pipes (drop legs, headers, grids), clamps, supports
- **I — High Important Requirements:** GA drawings, process air verification, air calculation summary, heat loss calculations (air temp ≤ 45°C at grids)

#### Template 6: Chlorination Datasheet

**Used for:** Gas chlorination systems, dosing stations

**Structure:**

- **Header:** Project, location, client, consultant, doc numbers
- **Process Data:** Plant capacity (m³/day), dosing rate (mg/l)
- **Chlorinator Specs:** Capacity (kg/hr), number of units (duty + standby + future), type (vacuum operated), location (indoor), instruments, mounting (wall-mounted), control (automatic + manual), chlorine gas cylinders/tonner count (duty + standby + storage), injector water requirements (capacity, pressure)
- **Scope of Supply:** Chlorinators, chlorine solution injector & diffuser, booster pumps, sample pump, automatic changeover device, residual chlorine measuring cell, gas pressure reducing valve, chlorine fume detector, gas cylinders/tonner, cylinders supporting trunnions, cylinder handling equipment, weighing balance, safety equipment, chlorine fume treatment system (tower media, caustic soda mixer, recirculating pumps, duct, exhaust fan/blower), control system (local panel IP54), pipes & electrical connections, commissioning spares, recommended spares (3 years)
- **Notes:** Concrete neutralization tower by Wabag (not vendor)

#### Template 7: Valve / Penstock / Dismantling Joint List (BOQ Format)

**Used for:** Valves, penstocks, dismantling joints, piping BOQs

**Structure:**

- **Header:** Project name, date
- **Columns:** Item #, Description, DN (mm), PN (bar), Connection type, Operation (Manual/Electrical), Material specification, Quantity, Stem type, Fluid handled, Remarks
- **Grouped by Process Area** (Headworks, PST, Aeration Tank, FST, etc.)
- **Valve Types:** Gate valve, check valve, butterfly valve, ball valve, quick valve
- **Material Details:** Body (Ductile Iron DIN 1563 GGG-50), trim (Dezincification Resistant Brass BS 2874 CZ132), stem (Stainless Steel DIN X 20 Cr 13 / EN 1.4021), seals (EPDM or NBR rubber)

#### Template 8: Mixer Datasheet

**Used for:** Submersible mixers (aeration zone, anoxic zone)

**Structure:**

- **Header:** Project, location, client, doc numbers
- **Design Data:** Biological treatment type, fluid handled, no. of tanks, no. of mixers per tank, total mixers, tank dimensions (L × W × D), tank shape, ambient/fluid temperature, application, location (submerged), service duty
- **Mechanical Data:** Tank material, manufacturer, model, mixer type (submerged rotating propeller), mixer power (kW), propeller speed (rpm), direction of rotation, propeller diameter (m), no. of blades, bearing life time (100,000 hr), max torque (N-m), type of seal (mechanical), mixing flow (m³/s), service factor of gear, weight of mixer/total assembly (kg)
- **Drive Motor:** Type (submerged), make, rating (kW), speed (rpm), power supply (V/Ph/Hz), no. of poles, cooling, IP rating (IP68), leak detector (IP69), insulation/temp rise (class H), efficiency (min 80%), mounting/frame size, duty class (S1), coupling, thermal sensors (bimetal/klixon or PT100), starting method (star-delta), motor cable, service factor, excess power required (0.25), no. of starts/hr (≥15)
- **Material of Construction:** Propeller (SS or glass fibre polyurethane), shaft (SS 1.4021), jet ring, bolts & nuts (A4), guide bar (SS 1.4307), wire rope (SS 1.4307), lifting chain (SS 1.4307), bracket, motor casing (GG25)
- **Scope of Supply:** Mixer with motor, mixer monitoring unit, cable length (15m), lifting mechanism, wire rope, commissioning spares, spare parts (3 years)

**Auto-selection logic:**

| Equipment Category                                                 | Template                   |
| ------------------------------------------------------------------ | -------------------------- |
| Submersible pump, vortex pump                                      | RAS Pump Datasheet         |
| Progressive cavity pump                                            | Thickened Sludge Datasheet |
| Blower                                                             | Blower Datasheet           |
| Screen, conveyor, grit/grease removal, thickener bridge, compactor | TC-CS                      |
| Belt press, polymer dosing                                         | Belt Press Datasheet       |
| Diffuser                                                           | Diffuser Datasheet         |
| Chlorination system                                                | Chlorination Datasheet     |
| Valve, penstock, dismantling joint, piping                         | BOQ List                   |
| Mixer                                                              | Mixer Datasheet            |

Unit conversions applied where needed (m³/hr ↔ L/s, bar ↔ psi, °C ↔ °F, mbar ↔ mwc, Nm³/hr ↔ m³/hr).

### F-08: RFQ Output

The system produces a **single Excel file (`.xlsx`)** as the RFQ deliverable. The file preserves the fixed template structure exactly — formulas, conditional formatting, merged cells, and styling are carried through untouched. Only the editable cells defined in the template schema are populated. The engineer downloads this single file; no additional package, zip, or supplementary assembly is produced.

### F-09: Audit Trail & Change Log

All extraction and generation actions are recorded:

- Timestamp, user ID, action type
- Field-level values written to the template
- Source document reference (page, cell, section) for every populated field
- Confidence score at time of extraction
- Conflict records (both values, precedence applied)
- Hard-stop conditions triggered (§F-04 Rule 8)

The audit trail is the definitive record of how each cell in the output Excel was produced. It is queryable per-project and per-field.

### F-11: Template Handling

The system does **not** maintain a server-side template library. Templates are authored and versioned by the engineering team externally, and uploaded with each project batch (classified via the `03_RFQ*` filename pattern, §F-02).

- Engineers upload one canonical fixed template per equipment type in the batch (e.g. blower datasheet, RAS pump datasheet, mixer datasheet — see §F-06 for illustrative structures)
- Uploaded templates are treated as immutable inputs: the system only populates predefined editable cells; it never alters structure, headers, formulas, merged cells, or conditional formatting (F-04.R6)
- The system consumes a per-template-type editable-cell map (maintained as application configuration, keyed by equipment category) to know which cells are writable
- Standard specification PDFs referenced by a template are uploaded alongside it as regular source documents
- No admin publish workflow, no server-side template versioning — revisions are tracked on the uploaded template filename (§5.6 / §F-02 `*Rev##*` pattern)

### F-12: Reporting Dashboard

Project-level reporting:

- RFQ preparation progress (equipment extracted / total)
- Discrepancy summary (conflict / TBD / low-confidence counts)
- Generation status per equipment category
- Audit trail browser (by project, equipment, field)

---

## 4. Data Model

```
Project 1:M Document         (uploaded source files)
Project 1:M ProcessArea      (plant process areas)
Project 1:M Equipment        (extracted equipment specs)
Project 1:M RFQPackage       (generated RFQ outputs)

ProcessArea 1:M Equipment        (equipment belongs to a process area)
Equipment   M:1 EquipmentCategory (pump, blower, valve, etc.)
Equipment   M:1 EquipmentSubType  (RAS pump, vortex pump, etc.)

RFQPackage M:M Equipment     (an RFQ may cover multiple equipment items)
RFQPackage M:M Document      (attached specification PDFs)
```

**Entity Details:**

- **Project** — name, location, client, consultant, project number, capacity (m³/d)
- **Document** — file metadata, classification, revision, parsed content
- **Equipment** — category, sub-type, process area, extracted specs (JSONB), field-level confidence & source_ref
- **RFQPackage** — template type + version, generated file path, revision, generated timestamp, status (draft/final), source equipment references
- **AuditEntry** — action type (extract/generate), timestamp, actor, field-level before/after, source_ref, confidence

Equipment stores specifications as JSONB for flexible per-category schema.
RFQPackage stores generated file metadata and links to source equipment.

---

## 5. Engineering Reference (Informational Only)

> **Scope note.** The standards and defaults in §5.1–§5.8 are **engineering reference material** drawn from past Wabag projects (e.g. Old-Kohafa WWTP, see Appendix A). They describe how engineers typically size motors, pick materials, apply service factors, and stamp revisions when **authoring the canonical templates** external to this system. They are **not** runtime guardrails this system enforces. The only runtime invariants are the AI Operating Rules in §F-04, which explicitly forbid the system from sizing equipment, selecting motors, or setting flows (F-04.R6). These rules are retained in the SRS as shared vocabulary for engineers and prompt authors — not as system behavior.

### 5.1 Egyptian Code Service Factor

Motor sizing based on Egyptian electrical code:

| Motor Rating | Service Factor |
| ------------ | -------------- |
| < 40 kW      | +25%           |
| 40–100 kW    | +20%           |
| > 100 kW     | +15%           |

Motor power is selected based on:

- Max power on curve (considering 80–110% head range only)
- Then applying the Egyptian Code service factor above

### 5.2 Equipment Working Range

- **Pumps:** 80% below the duty point head and 110% above the duty point head is the minimum accepted working range
- **Blower speed:** Not to exceed 1,500 rpm (standard), 2,900 rpm max for vortex pumps

### 5.3 Material Codes

Standard material codes (expandable):

| Code        | Material                             | Common Application                              |
| ----------- | ------------------------------------ | ----------------------------------------------- |
| GG20        | Grey Cast Iron Grade 20              | Blower casings                                  |
| GG25        | Grey Cast Iron Grade 25              | Pump impellers, casings, motor casings          |
| SS 1.4301   | Stainless Steel (AISI 304)           | Shafts, guide rails, lifting chains             |
| SS 1.4307   | Stainless Steel (AISI 304L)          | Guide bars, wire ropes, supports                |
| SS 1.4401   | Stainless Steel (AISI 316)           | Belt press structural frame, conditioning tanks |
| SS 1.4021   | Stainless Steel (AISI 420)           | Mixer shafts, valve stems                       |
| Duplex 2205 | Duplex Stainless Steel               | High-corrosion environments                     |
| C45N        | Carbon Steel                         | Blower shafts (drop-forged)                     |
| 16 Mn Cr5E  | Case-hardening Steel                 | Blower gears                                    |
| A4          | Stainless Steel Fasteners (AISI 316) | Bolts, nuts (submersible equipment)             |
| GGG-50      | Ductile Iron (DIN 1563)              | Valve bodies                                    |
| EPDM / NBR  | Rubber                               | Seals and O-rings                               |
| UPVC        | Unplasticized PVC                    | Diffuser headers, distribution grids            |

### 5.4 Motor Specifications (Standard Defaults)

| Parameter          | Submersible Equipment        | Indoor Equipment (Blower) | Belt Press        |
| ------------------ | ---------------------------- | ------------------------- | ----------------- |
| IP Rating          | IP68                         | IP54                      | IP55              |
| Insulation Class   | F (rise limited to B)        | Class B                   | F/B               |
| Efficiency Class   | IE3                          | —                         | IE3               |
| Power Supply       | 380(±10%)V / 3Ph / 50(±2%)Hz | 380V / 3Ph / 50Hz         | 400V / 50Hz / 3Ph |
| Motor Frame        | —                            | TEFC                      | —                 |
| Thermal Protection | 3×PTC + PT100 (mandatory)    | Klaxon switches           | On windings       |

### 5.5 Spare Parts

- Standard requirement: "Sufficient for 3 years operation"
- Diffuser systems: Supply 5% air diffusers as spares
- Commissioning spares: Always included in scope

### 5.6 Revision Control

- All RFQs reference source document revision numbers
- Latest revision is auto-detected from filename patterns
- Previous revisions retained for comparison
- Revision naming convention: `Rev00`, `Rev01`, `Rev02`, etc.

### 5.7 Approval Authority

- Senior Engineer sign-off on the generated Excel file is required before it is released externally (handled outside the system)
- Signature blocks in the template: Prepared By → Checked By → Approved By

### 5.8 Design Standards (Generation Guidelines)

| Standard              | Application                    |
| --------------------- | ------------------------------ |
| DIN 19569             | Submersible pump design        |
| DIN 1945              | Blower design                  |
| IEC                   | Blower motor standard          |
| DIN 2576 B / DIN 2632 | Flange standards (ball valves) |
| EN 1563               | Cast iron grades               |
| BS 2874 / EN 12167    | Brass specifications           |
| BS 970 / EN 10083     | Stainless steel valve trim     |

---

## 6. System Architecture

### 6.1 Five-Layer Architecture

```
┌──────────────────────────────────────────┐
│ L1 — Presentation Layer (UI)             │
│ Engineer dashboard, RFQ download         │
├──────────────────────────────────────────┤
│ L2 — API Layer (FastAPI)                 │
│ REST endpoints, auth, file upload        │
├──────────────────────────────────────────┤
│ L3 — Business Logic Layer                │
│ Classification, extraction, validation,  │
│ template generation                      │
├──────────────────────────────────────────┤
│ L4 — AI/LLM Layer                        │
│ Structured extraction, cross-validation, │
│ prompt management, confidence scoring    │
├──────────────────────────────────────────┤
│ L5 — Data Layer                          │
│ PostgreSQL (Supabase), uploaded-file     │
│ storage, audit trail                     │
└──────────────────────────────────────────┘
```

### 6.2 Procedural Workflow

```
Engineer Upload
      │
      ▼
┌──────────┐     ┌──────────────┐
│ Classify │────▶│ Auto-detect  │
│ Documents│     │ type + rev   │
└──────────┘     └──────────────┘
      │
      ▼
┌─────────────────┐
│ Extract         │
│ Equipment Specs │◀── LLM structured output
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Cross-Document  │
│ Validation      │──── Discrepancy metadata
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Template Match  │──── Category → Fixed template
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Populate Fixed  │
│ Excel Template  │──── Editable cells only
└─────────────────┘
      │
      ▼
Single Excel file download
```

### 6.3 Access Control Levels

| Role       | Permissions                                              |
| ---------- | -------------------------------------------------------- |
| **Viewer** | View projects, download the generated Excel file         |
| **Admin**  | All permissions + manage templates, users, system config |

---

## 8. LLM Configuration

- Primary model: opus (via OpenRouter, `moonshotai/kimi-k2`)
- Fallback model: sonnet (via OpenRouter, `minimax/minimax-01`)
- Router tries primary, falls back on failure/timeout
- Extraction uses structured JSON output mode
- Equipment-specific extraction prompts per category (pump prompt differs from blower prompt differs from valve prompt)
- Context window must accommodate multi-page spec PDFs alongside datasheet templates

---

## 9. Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), Pydantic
- **Database:** PostgreSQL 16, Supabase
- **LLM:** OpenRouter (opus / sonnet)
- **Document Processing:** pypdf, python-docx, openpyxl, xlrd (for legacy .xls), Pillow
- **Excel Generation:** openpyxl (with formula and conditional formatting preservation)
- **Migrations:** Alembic
- **Package Manager:** uv
- **Code Quality:** ruff, mypy (strict), pytest (80% coverage floor)
- **Containerization:** Docker, docker-compose

---

## Appendix A: Real-World Reference — Old-Kohafa WWTP

> **Reference only.** The equipment catalog and file names below are drawn from one real tender package. They informed the SRS design and illustrate what an engineer typically uploads, but the runtime system does not assume these specific categories, counts, or filenames — real batches may differ project-to-project.

The following data was extracted from the actual Old-Kohafa WWTP (Fayoum Governorate) tender package to inform this SRS:

- **Project:** Kohafa WWTP — (20,000 – 80,000) m³/d
- **Client:** Holding Company for Water and Wastewater (HCWW)
- **Consultant:** Stantec in consortium with Suez, EGEC and ERCC
- **Location:** Fayoum Governorate, Egypt

### Equipment discovered in the project

| Equipment             | File                                       | Sheets/Items                                                       |
| --------------------- | ------------------------------------------ | ------------------------------------------------------------------ |
| Submersible Pumps     | Submersible Pump RFQ rev02.xls             | 6 pump types (RAS, Excess, Primary, Supernatant, Vortex, Drainage) |
| Thickened Sludge Pump | Thickened Sludge Pump RFQ.xls              | Progressive cavity type                                            |
| Blowers               | Blowers RFQ.xlsx                           | 3 types (Aeration, Grit, Re-aeration)                              |
| Submersible Mixers    | Submersible Mixer RFQ.xlsx                 | Aeration zone mixer                                                |
| Diffusers             | Diffusers RFQ.xlsx                         | Fine bubble disc diffuser                                          |
| Belt Press            | Dewatering Belt Press Datasheet.xlsx       | 1 unit                                                             |
| Polymer Dosing        | Polymer Dosing system data sheet.xlsx      | Dosing system                                                      |
| Chlorination          | Chlorination Equipment RFQ.xlsx            | Extension + existing WWTP                                          |
| Screens               | Mechanical Fine/Coarse Screen Rev000.xlsx  | Fine and coarse screens                                            |
| Conveyors             | Screenings/Belt Press Conveyor Rev000.xlsx | 2 conveyor types                                                   |
| Grit & Grease Removal | GRIT & GREASE Removal system Rev00.xlsx    | Removal system                                                     |
| Sand Classifier       | Sand Classifier Rev00.xlsx                 | 1 unit                                                             |
| Sludge Thickener      | Sludge Thickener Bridge Rev000.xlsx        | Bridge type                                                        |
| Screenings Compactor  | Screenings Compactor Rev00.xlsx            | 1 unit                                                             |
| Cranes                | Cranes old kohafa.xlsx                     | Multiple locations                                                 |
| Valves                | Valve List rev.01.xlsx                     | ~60+ valves across all process areas                               |
| Penstocks             | Penstockes List.xlsx                       | Multiple locations                                                 |
| Dismantling Joints    | Dismantling Joints List.xlsx               | Multiple items                                                     |
| Containers            | Screening/Belt Press Container.xlsx        | 2 types                                                            |
| Internal Piping       | pipes inside.xlsx                          | Full plant piping                                                  |
| SS Items              | ST.ST List.xlsx                            | Stainless steel items list                                         |
| Equipment List        | kohafa WWTP\_ Equipment List_Rev02.xlsx    | Master equipment list                                              |
