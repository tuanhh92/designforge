<!-- Exported from the live PRD: https://claude.ai/artifact/PEdpP2AJZP9ExWaynorr8z (rev 23, 2026-10-24). The live document is the source of truth; re-export after edits. -->

# DesignForge — Product Requirements Document

Oct 24, 2026 · @Tuan Hoang

DesignForge turns a furniture reference photo into a manufacturable design — SketchUp model, production drawings, cut list, BOM and CNC files — in under 10 minutes, with a human approving every dimension before anything is cut.

**Launch market: Vietnam.** The product ships in Vietnamese first, prices in VND, takes local payments, and starts with workshops and designers in Hanoi and Ho Chi Minh City.

## Vision and problem

**Vision.** Every custom furniture workshop can go from "my client sent me this picture" to "the CNC is cutting it" in one sitting. DesignForge becomes the design-to-manufacture layer between the people who imagine furniture and the machines that make it.

**One-line pitch.** Upload a furniture photo, confirm the sizes, download a production package your workshop can build from.

### The problem

Custom panel furniture (wardrobes, kitchens, cabinets, bookcases, sideboards) is sold from pictures and built from drawings. The step in between is manual, slow and error-prone:

- **Clients and designers bring images, not specifications.** A Pinterest photo has no dimensions, materials, construction or hardware.
- **Workshops redraw everything by hand.** A skilled person rebuilds the piece in SketchUp, AutoCAD or a cabinet program, then derives the cut list, edge banding, hardware and drilling. A typical wardrobe takes several hours of drafting before a quote can be given.
- **Quoting is slow, so deals are lost.** The client waits days for a price; many quotes never convert, so the drafting time is unpaid.
- **Errors are expensive.** One wrong dimension or a mirrored part wastes a full sheet, edge banding and machine time, and can delay installation.
- **Existing software assumes you already have a design.** Cabinet CAD/CAM suites are powerful but expensive and slow to learn; general 3D tools produce pretty models with no manufacturing data; AI image tools produce pictures, not parts.

### Why now

- Multimodal models can now reliably read furniture category, layout, counts and materials from photos, and return strict structured output.
- MCP gives a standard way to drive design tools such as SketchUp from software.
- Small workshops are buying CNC routers and need digital part data they cannot produce themselves.

### Our approach in one sentence

AI proposes a short, editable furniture specification; the user confirms it; deterministic code expands it into every part, and every output — SketchUp model, drawings, cut list, BOM, CNC — is generated from that single parts model.

## User personas

The paying buyer at launch is the workshop owner; designers are the main source of new designs and the growth channel.

| Persona | Who they are | Job to be done | Top pains today | What success looks like |
| --- | --- | --- | --- | --- |
| **Minh — Workshop owner** (primary buyer) | Runs a 5–30 person custom furniture shop with a panel saw or CNC router | Quote fast, win the job, build it right the first time | Hours of drafting per quote; drafting is unpaid when quotes are lost; errors waste sheets | Photo to quote and cut list in under 10 minutes; fewer wasted sheets |
| **Lan — Production lead / CNC operator** | Turns drawings into machine programs, labels and cutting plans | Get correct, complete part data in the format the machine accepts | Re-entering parts by hand; drilling errors; mirrored parts | DXF/CNC files and labels that load without rework |
| **Thu — Interior designer** (primary user) | Designs rooms for residential and hospitality clients | Turn a mood-board image into something a workshop can price and build | Workshops ask for drawings she cannot produce; slow back-and-forth | A model and drawings to send the workshop the same day |
| **Khánh — Architect** (secondary) | Specifies built-in joinery in projects | Fitted furniture that fits the plan and can be tendered | Joinery drawings are low priority and done late | Fitted units with correct scribes and a tender-ready drawing set |
| **Phong — Furniture freelancer** (secondary) | Independent maker or designer-maker | Look professional with no drafting staff | Cannot afford cabinet CAD/CAM suites | Professional drawings and a cut list at a freelancer price |

## User stories

Stories are grouped by epic; P0 = MVP, P1 = V1, P2 = V2. Acceptance criteria are the testable part.

| ID | Epic | As a… | I want to… | So that… | Acceptance criteria | Pri |
| --- | --- | --- | --- | --- | --- | --- |
| US-01 | Capture | Designer | upload 1–6 photos of one furniture piece | the system sees it from several angles | JPG/PNG/WEBP/HEIC up to 20 MB each; duplicates detected; irrelevant images rejected with a reason | P0 |
| US-02 | Capture | Designer | tap the piece I mean when a photo shows several | the AI analyses the right object | Tap point stored and used as a focus hint | P0 |
| US-03 | Capture | Workshop owner | enter one measured dimension | the sizes are accurate | Anchor field for width, height, depth or section width; solver honours it exactly | P0 |
| US-04 | Spec | Designer | see the AI's specification with a confidence level on each value | I know what to check | Every dimension shows a high, medium or low badge and its source | P0 |
| US-05 | Spec | Designer | edit sizes, sections, doors, drawers, materials and hardware in a form | the design matches the client's room | Edits re-validate within 1 s; the 3D preview updates | P0 |
| US-06 | Spec | Workshop owner | see rule violations with one-click fixes | nothing unbuildable reaches production | Errors block approval; each fix shows what it changes | P0 |
| US-07 | Spec | Designer | start from a blank form instead of a photo | I can use the product without an image | Manual mode produces the same outputs | P0 |
| US-08 | Spec | Designer | edit the design by chat ("make it 200 mm wider, add a drawer") | changes are faster | Chat produces a reviewable change, never a silent edit | P1 |
| US-09 | Model | Designer | download a SketchUp model with named components and scenes | I can present and adjust it | .skp opens in SketchUp 2023+; parts are named components on tags | P0 |
| US-10 | Drawings | Workshop owner | get a production drawing set | my team can build from it | Elevations, sections, part drawings, hardware schedule, title block, PDF + DXF | P0 |
| US-11 | Manufacturing | Production lead | get a cut list with edge banding and grain | I can cut on the saw | Cut sizes account for edge band thickness; identical parts grouped | P0 |
| US-12 | Manufacturing | Workshop owner | get a BOM with costs | I can quote | Sheets, edge band, hardware, consumables and labour with my prices | P0 |
| US-13 | Manufacturing | Production lead | get nesting layouts | I use fewer sheets | Yield shown per sheet; grain respected | P0 |
| US-14 | CNC | Production lead | export DXF per part with my layer names | my CAM imports it unchanged | Layer mapping configurable per organisation | P0 (generic) / P1 (mapping) |
| US-15 | CNC | Production lead | export native Homag or Biesse programs | no CAM step is needed | Validated on a partner machine before release | P1 |
| US-16 | Shop | Workshop owner | release a version to the shop | everyone builds the same thing | Released versions are frozen and audited | P0 |
| US-17 | Shop | Production lead | scan part labels to track progress | I know what is cut, banded, drilled, assembled | QR label per part; status board | P1 |
| US-18 | Commercial | Designer | send a branded quote PDF to my client | I can sell faster | Quote from BOM with margin and branding | P1 |
| US-19 | Admin | Workshop owner | import my materials, hardware and prices | outputs match my stock | CSV import; catalog used as the only allowed choices for the AI | P0 |
| US-20 | Admin | Workshop owner | set my construction rules | designs follow how my shop builds | Rule pack: thicknesses, back style, connectors, hinge brand, clearances | P0 |
| US-21 | Admin | Owner | invite my team with roles | the right people can approve and release | Owner, admin, designer, shop, viewer roles | P0 |
| US-22 | Network | Designer | send an approved design to partner workshops for quotes | I find a maker quickly | Marketplace with quote requests | P2 |

## Functional requirements

Every requirement has an ID that engineering tickets and tests reference. Phase: MVP, V1 or V2.

| ID | Area | Requirement | Phase |
| --- | --- | --- | --- |
| FR-01 | Accounts | Sign-up and sign-in with email, Google and Microsoft; organisations with invitations | MVP |
| FR-02 | Accounts | Roles: owner, admin, designer, shop, viewer, enforced on every API call | MVP |
| FR-03 | Projects | Projects contain designs; designs contain immutable versions | MVP |
| FR-04 | Ingest | Upload 1–6 images per design directly to storage; dedupe; relevance check with a stated reason on rejection | MVP |
| FR-05 | Ingest | Optional measured anchor dimensions and free-text notes per design | MVP |
| FR-06 | AI | Detect category, layout (sections, doors, drawers, shelves), materials, handle and base type, style, printed dimensions | MVP |
| FR-07 | AI | Estimate absolute dimensions with a confidence and source per value | MVP |
| FR-08 | AI | Produce a valid FurnitureSpec that uses only the organisation's catalog items | MVP |
| FR-09 | AI | Dual-model "accurate" mode with disagreement flags | V1 |
| FR-10 | AI | Chat-to-edit that proposes a reviewable change to the specification | V1 |
| FR-11 | Spec Review | Form editor with live validation and a live 3D preview | MVP |
| FR-12 | Spec Review | Rule violations with severity and one-click fixes; errors block approval | MVP |
| FR-13 | Spec Review | Manual mode: create a design with no images | MVP |
| FR-14 | Parametric | Deterministic generation of all parts, machining, hardware and joints from an approved spec | MVP |
| FR-15 | Geometry | SketchUp model with named components, materials, tags and four standard scenes | MVP |
| FR-16 | Geometry | glTF web preview; STL and OBJ exports | MVP |
| FR-17 | Drawings | Production drawing set as PDF, DXF and SVG | MVP |
| FR-18 | Manufacturing | Cut list (CSV, XLSX) with cut sizes, edge banding, grain and grouping | MVP |
| FR-19 | Manufacturing | BOM with quantities and costs from the organisation's price list | MVP |
| FR-20 | Manufacturing | Rectangular nesting with grain, kerf and trim | MVP |
| FR-21 | CNC | Generic layered DXF per part | MVP |
| FR-22 | CNC | Per-organisation layer mapping; native Homag MPR and Biesse BPP | V1 |
| FR-23 | Delivery | Production package zip with manifest and checksums | MVP |
| FR-24 | Delivery | Part labels with QR codes (PDF) | MVP |
| FR-25 | Shop | Release to shop freezes a version and records who released it | MVP |
| FR-26 | Shop | Part status tracking by QR scan | V1 |
| FR-27 | Catalog | Materials, sheet stock, edge band, hardware and price import by CSV | MVP |
| FR-28 | Catalog | Rule pack editor, versioned | V1 |
| FR-29 | Commercial | Quote PDF with margin and branding | V1 |
| FR-30 | Billing | Plans, credits, local payment checkout (VietQR, VNPay, MoMo), e-invoices, usage history | MVP |
| FR-31 | Integrations | Outbound webhooks and API keys | V1 |
| FR-32 | Network | Designer-to-workshop quote marketplace | V2 |
| FR-33 | Context | Room-aware fitted furniture from site photos and floor plans | V2 |
| FR-34 | Notifications | Email and in-app notice when a package is ready or a run fails | MVP |

## Non-functional requirements

The hardest requirement is correctness: a production package must never contain a software-caused wrong part.

| ID | Category | Requirement | Target |
| --- | --- | --- | --- |
| NFR-01 | Correctness | Parts generated from the same approved spec and rule pack are identical on every run | 100%, enforced by hash tests |
| NFR-02 | Correctness | Automated verification gates pass before any package is released (dimensions add up, holes inside parts, every part in the cut list) | 100% of packages |
| NFR-03 | Correctness | Software-caused wrong parts reported by customers | 0 per quarter |
| NFR-04 | AI accuracy | Category correct on the evaluation set | ≥ 95% |
| NFR-05 | AI accuracy | Door, drawer and section counts exactly right | ≥ 85% |
| NFR-06 | AI accuracy | Overall dimension error with one user anchor (median) | ≤ 5% |
| NFR-07 | AI accuracy | Edits needed between AI draft and approval (median) | < 10 |
| NFR-08 | Performance | Upload to Spec Review ready (p50 / p95) | 60 s / 120 s |
| NFR-09 | Performance | Spec edit to validated result and preview | < 1 s |
| NFR-10 | Performance | Approval to full production package (p50) | < 5 min |
| NFR-11 | Availability | Web app and API | 99.5% MVP, 99.9% V1 |
| NFR-12 | Degradation | Drawings, cut list, BOM and 3D preview keep working when SketchUp is unavailable | Always |
| NFR-13 | Security | Tenant isolation by database row-level security plus server-side scoping | Zero cross-tenant reads in tests |
| NFR-14 | Security | Encryption in transit (TLS 1.2+) and at rest; signed download URLs that expire in 5 minutes | Always |
| NFR-15 | Security | No public network endpoint on geometry machines; no remote code tools in production | Always |
| NFR-16 | Privacy | Customer images are not used to train third-party models; raw AI responses kept 30 days unless the organisation opts in | Always |
| NFR-17 | Compliance | Vietnam Law on Personal Data Protection: consent, data-subject requests, transfer impact assessment for processing in Singapore; data processing agreement available | MVP |
| NFR-18 | Compliance | SOC 2 Type I, then Type II | V1, V2 |
| NFR-19 | Auditability | Every version records spec, rule pack, generator and bridge versions and who approved and released it | Always |
| NFR-20 | Scalability | Workers scale horizontally; geometry nodes scale by queue depth | 1,000 designs per day in V1 |
| NFR-21 | Cost | AI and geometry cost per design | < 13% of revenue per design (about 2.000 ₫ at Workshop tier) |
| NFR-22 | Usability | First package for a new user without help | < 20 min from sign-up |
| NFR-23 | Accessibility | Web app | WCAG 2.1 AA |
| NFR-24 | Localisation | Vietnamese by default with an English toggle; workshop vocabulary (hông, nóc, đợt, cánh, len chân); units mm; VND prices | MVP: vi + en, mm |
| NFR-25 | Observability | Errors, traces and AI calls logged with cost and latency; alert on failed packages | MVP |
| NFR-26 | Recovery | Database point-in-time recovery | RPO 5 min, RTO 4 h |

## AI workflows

AI is used only to understand images and propose a specification; a person approves it, and deterministic code produces everything that gets manufactured.

_Diagram: DesignForge pipeline · 6 stages, 1 human approval — see the live document._

The dashed top zone can be wrong and is checked by a person; the bottom zone is tested code that gives the same parts for the same approved spec.

**Stage by stage**

1. **Ingest.** Normalise images, remove duplicates, reject images with no clear furniture subject, and let the user tap the piece they mean.
2. **Perception.** A vision model (GPT-5 or Claude) returns a strict, structured observation: category, sections, doors, drawers, shelves, handle and base type, materials, style, printed dimensions, scale cues, each with a confidence and the evidence for it. It returns proportions, not millimetres.
3. **Knowledge engine.** A solver combines the user's measured size, dimensions printed in the image, proportions, scale cues and standard sizes for the category into millimetres with a confidence each. A second model call maps the observation to sections, compartments, doors and hardware, choosing only from the organisation's catalog. A rule engine checks buildability and proposes fixes.
4. **Spec Review.** The user sees each value with its confidence, edits in a form with a live 3D preview, applies fixes, and approves.
5. **Parametric generator.** Code turns the approved spec into every part, hole, groove, hinge and joint.
6. **Outputs.** SketchUp model, drawings, cut list, BOM and CNC files are produced from those parts and packaged.

**Guardrails**

- The AI can never invent a material or hinge the workshop does not stock: catalog codes are the only allowed values in its output schema.
- Numbers come from the solver, not free text from the model.
- Rule errors block approval; no geometry or manufacturing output is produced before approval.
- Two-model "accurate" mode (V1) flags any value the models disagree on for review.

**Quality measurement**

| Metric | MVP target |
| --- | --- |
| Category accuracy | ≥ 95% |
| Door, drawer, section counts exactly right | ≥ 85% |
| Dimension error with one measured size (median) | ≤ 5% |
| Edits from AI draft to approval (median) | < 10 |
| Upload to Spec Review (p50) | ≤ 60 s |

Metrics are tracked on a growing evaluation set of real furniture with known dimensions (retailer products and partner workshops' past jobs). Any prompt or model change that makes a headline metric worse by more than 2% is blocked.

## SketchUp MCP integration

SketchUp is the design engine users see and trust, so every approved design ships as a native .skp model built through SketchUp MCP. It is never the source of manufacturing data: drawings, cut list, BOM and CNC come from the parts model, so they cannot drift from what SketchUp shows.

**How it works**

1. After approval, the parts model is queued as a geometry job.
2. A DesignForge agent on a Windows geometry machine claims the job over HTTPS.
3. The agent starts the DesignForge SketchUp MCP server locally and calls its tools.
4. A DesignForge extension inside SketchUp builds the whole model in one undoable operation.
5. The agent checks the model's size and part count against the parts model, exports the files and uploads them.

**Capabilities**

| Capability | What the user gets | Phase |
| --- | --- | --- |
| Connect | Health checks and version handshake with each SketchUp machine | MVP |
| Components | Each part is a named component; identical parts share one definition | MVP |
| Panels, carcasses, cabinets | Panels built from the parts model; carcasses and cabinets assembled as nested groups | MVP |
| Materials | Organisation materials with colour, texture and grain direction | MVP |
| Tags | Carcass, fronts, back and hardware on separate tags | MVP |
| Scenes | Iso, front, interior (fronts hidden), exploded | MVP |
| Export SKP | Native model, SketchUp 2023+ | MVP |
| Export OBJ, STL | 3D interchange and printing | MVP |
| Export DXF (3D) | 3D interchange for CAD users | V1 |
| Scene images | PNG renders for quotes and presentations | MVP |
| Real hardware models | Manufacturer hinge, slide and handle components | V1 |
| SketchUp plugin | Designers push a SketchUp model into DesignForge for production data | V2 |

**Requirements**

- Geometry machines hold no database credentials and expose no public network port.
- Arbitrary code tools (such as eval\_ruby) are disabled in production.
- A failed SketchUp build never blocks drawings, cut list, BOM or the web 3D preview.
- Identical parts models reuse an earlier SketchUp build at no cost.
- Each build records the SketchUp and extension versions that produced it.

**Licensing dependency.** Running SketchUp unattended for a SaaS needs written confirmation from Trimble before launch. The fallback is the SketchUp C SDK, which writes .skp files without the desktop app; the product is designed so either engine can be used.

## Production drawing system

Drawings are generated automatically from the parts model in seconds, to a standard a CNC operator or bench joiner can build from without asking questions.

**Drawing set (MVP)**

| Sheet | Contents |
| --- | --- |
| General arrangement | Iso render, overall dimensions, material and finish schedule |
| Elevations | Front with doors on; front interior with doors off; dimension chains for sections and compartments |
| Sections | Side section through each section showing shelves, drawers, back and plinth |
| Plan | Top view with depth and overhangs |
| Part drawings | One per unique part: size, edge banding marks, grain arrow, every hole and groove with a hole table |
| Hardware schedule | Hinges, slides, connectors, handles with positions and quantities |
| Cut list and BOM | Tables matching the separate files |
| Nesting | One page per sheet with part labels (optional) |

**Requirements**

- Outputs: combined PDF, single-sheet PDFs, DXF with layers per element type, SVG.
- Paper A3 by default (A4, A2, Letter, Tabloid selectable); scale chosen automatically (1:10, 1:20, 1:25).
- Title block with organisation logo, client, project, design, version, date, scale, sheet n of N, approved by and released by.
- First-angle or third-angle projection set per organisation; dimensions in mm or inches.
- Every part carries a label code that matches the cut list, labels and CNC file names.
- Revision table: a new version shows what changed since the last released version (V1).
- Custom title block and sheet templates per organisation (V1); SketchUp LayOut presentation sets (V2).

**Verification before release.** Section widths and divider thicknesses must add up to the inner width; every part must appear once in the cut list and drawings; every hole must sit inside its part and respect minimum edge distances. A failed check blocks the package and alerts the team.

## BOM, cut list and CNC export

All three are computed from the same parts model, so a quantity in the BOM, a line in the cut list and a CNC file always describe the same part.

### Cut list generation

- One line per group of identical parts: same material, thickness, cut size, grain, edge banding and machining. Left and right parts with mirrored drilling stay separate lines.
- **Cut size** = finished size minus edge band thickness (and pre-mill allowance, if the shop's edgebander pre-mills) on each banded edge.
- Columns: label code, part name, material, thickness, cut length, cut width, quantity, grain, edge banding per edge (L1, L2, W1, W2), machining yes/no.
- Totals: parts, area per material, edge band metres per type.
- Formats: on-screen table, CSV, XLSX; column presets compatible with common cutting optimisers (OpenCutList, CutList Optimizer).
- Nesting: rectangular layouts per material respecting grain, saw kerf and sheet trim; guillotine-only mode for panel saws; yield per sheet. Offcut reuse in V1.

### BOM generation

| Category | Quantity comes from | Unit |
| --- | --- | --- |
| Sheet material | Sheets used by nesting (or area × waste factor) | sheet |
| Edge banding | Banded edge lengths plus a per-edge allowance, rounded to roll | m |
| Hardware | Hinges by door height, slides by drawer, handles, legs, rails, shelf pins | pcs, rounded to pack size |
| Connectors | Minifix, dowels, confirmat screws from the joints | pcs |
| Consumables | Glue, screws, back-panel fixings by rule | estimate |
| Labour | Minutes per part, per edge, per drilling and per assembly, from the rule pack | h |

Prices come from the organisation's price list; the BOM shows unit price, line total and grand total with currency. A quote PDF with margin and client branding is built on top of the BOM in V1.

### CNC export system

| Output | Description | Phase |
| --- | --- | --- |
| Generic DXF per part | Outline and machining on named layers (for example DRILL\_V\_D35\_Z13 for a 35 mm, 13 mm deep hinge cup); face B in a separate file; units mm | MVP |
| Nesting DXF per sheet | Parts placed on the sheet with label codes, for routers | MVP |
| Operation simulation PDF | Every operation per face for the operator to check before cutting | MVP |
| Layer mapping | Each organisation maps our layers to its CAM's naming | V1 |
| Homag / Weeke (MPR) | Native program, no CAM step | V1 |
| Biesse (BPP), SCM (XXL) | Native programs | V2 |

A native machine format ships only after a test cut on a partner's machine. Export is possible only from a released version, and every file name carries the label code and version.

## Pricing model

Seat-based subscription plus included design credits, priced in VND for Vietnamese workshops and designers and paid through local payment methods. Prices below are a launch proposal excluding VAT, to be tested with design partners in Hanoi and Ho Chi Minh City.

| Plan | Price / month (paid yearly) | For | Included | Key limits and features |
| --- | --- | --- | --- | --- |
| Free | 0 ₫ | Trying it out | 3 designs / month | Spec Review, 3D preview, watermarked PDF drawings; no SKP, cut list or CNC |
| Studio | 390.000 ₫ (312.000 ₫) | Designers, freelancers | 1 seat, 30 designs | SKP, drawings, scene renders, quote PDF (V1); cut list read-only |
| Workshop | 1.490.000 ₫ (1.190.000 ₫) | Small workshops | 3 seats, 100 designs | Everything in Studio + cut list, BOM with costing, nesting, generic DXF, labels, own catalog and rule pack |
| Production | 3.990.000 ₫ (3.190.000 ₫) | CNC shops | 10 seats, 400 designs | Workshop + native CNC formats, layer mapping, shop tracking, API and webhooks, priority geometry queue |
| Enterprise | From 15.000.000 ₫ | Manufacturers, chains | Custom | SSO, Vietnam-hosted option, dedicated geometry capacity, SLA, custom rule packs and integrations |

**Add-ons.** Extra seats (150.000 ₫ Studio, 250.000 ₫ Workshop and above); design credit packs (25.000 ₫ to 50.000 ₫ per design, cheaper in volume); "accurate" dual-model mode at 2 credits per design; native CNC dialect set-up and test-cut service as a one-off fee.

**Payments and invoices.** Stripe does not onboard merchants registered in Vietnam, so billing goes through a local payment gateway: bank transfer with VietQR, VNPay and MoMo, with card payments through the gateway. Every payment issues an electronic invoice (hóa đơn điện tử), which Vietnamese business customers need for their accounts. Yearly plans are the default offer because many workshops prefer one bank transfer a year to a stored card. Confirm VAT treatment of the subscription with an accountant before launch.

**What counts as a design.** One image-to-spec run plus all regenerations of that design within 30 days. Manual-mode designs cost no AI credit, only geometry.

**Unit economics targets (assumptions to validate)**

- At Workshop tier a design brings about 15.000 ₫ of revenue (1.490.000 ₫ ÷ 100 designs), so AI plus geometry cost must stay under about 2.000 ₫ (≈ 13%) per design. This needs the cheaper vision model by default, the dual-model mode only as a paid add-on, and cached perception so regenerations cost almost nothing.
- Gross margin above 70% at Workshop tier.
- Payback under 6 months through a self-serve funnel, Zalo and Facebook groups of furniture makers, and partner workshops referring their designers.

**Expansion revenue.** Seats as workshops add designers; Production tier when a shop buys a CNC; marketplace take rate (V2) on designer-to-workshop jobs.

## SaaS multi-tenant architecture

DesignForge uses a shared database and shared services with strict per-organisation isolation; enterprise customers can get dedicated geometry capacity and regional data residency.

**Tenancy model**

- Tenant = organisation (a workshop, a design studio, a manufacturer). Users can belong to several organisations and switch between them.
- Every row of customer data carries the organisation ID. Isolation is enforced twice: database row-level security for any direct client access, and organisation scoping in every server-side query, because background workers bypass row-level security.
- Files are stored under an organisation-specific path and served only through signed URLs that expire in 5 minutes.
- Catalogs are layered: a global DesignForge catalog (materials, hardware, standard rule packs) with per-organisation overrides and additions.

**Roles and permissions**

| Role | Can |
| --- | --- |
| Owner | Everything, including billing and deleting the organisation |
| Admin | Manage members, catalog, rule packs, integrations; release to shop |
| Designer | Create and edit designs, approve specifications, download models and drawings |
| Shop | View production data, release to shop, export CNC, update part status |
| Viewer | Read-only access to designs and drawings |

**Platform**

| Layer | Choice |
| --- | --- |
| Web app | Next.js, TypeScript, Tailwind, shadcn/ui |
| API | FastAPI (Python) |
| Background work | Celery workers on Redis, separate queues for AI and manufacturing work |
| Data and files | Supabase Postgres with row-level security, Supabase Storage, Realtime for progress |
| Identity | Clerk organisations; Supabase accepts Clerk tokens |
| AI | GPT-5 vision and Claude vision through a provider-neutral interface |
| 3D | SketchUp via MCP on isolated Windows geometry machines; web glTF engine on Linux |
| Billing | Local payment gateway (VietQR bank transfer, VNPay, MoMo), credits and e-invoices |

**Fair use and noisy neighbours.** Per-organisation rate limits and credit quotas; geometry jobs queued fairly across organisations, with a priority lane for Production and Enterprise plans.

**Data region (MVP).** All data and files are hosted in Singapore (the Singapore regions of Supabase and the cloud provider), the closest major cloud region to Vietnam. Processing data collected in Vietnam on servers abroad is a cross-border transfer under Vietnam's Law on Personal Data Protection, in force since 1 January 2026 ([source](https://vn.rajahtannasia.com/?p=63356)). DesignForge therefore:

- prepares a cross-border transfer impact assessment and submits it to the data protection authority within 60 days of the first transfer, and updates it when the processing changes;
- keeps personal data to the minimum: account names, emails and phone numbers, client names on projects; photos are re-encoded on upload, which strips location metadata;
- records consent at sign-up and handles access, correction and deletion requests from the account settings.

**Vietnam-hosted option (V1).** For manufacturers and chains that require data to stay in Vietnam, a deployment on a Vietnamese cloud provider is offered at Enterprise tier. Have a Vietnamese data-protection lawyer review the transfer impact assessment and the implementing decree before launch.

**Enterprise (V2).** SSO (SAML), SCIM provisioning, audit log export, dedicated geometry machines, custom data retention.

## MVP scope and future scope

The MVP is a paid beta in about 16 weeks: carcass furniture only, done end to end, for 3–5 design-partner workshops.

_Diagram: DesignForge roadmap · 3 phases, 2 gates — see the live document._

Phases are unlocked by their gates, not by the calendar; a gate that is not met extends the phase.

### MVP: in and out

| Area | In the MVP | Not in the MVP |
| --- | --- | --- |
| Furniture | Wardrobes, base, wall and tall cabinets, bookcases, sideboards | Kitchens as runs, desks, beds, chairs, sofas, curved or solid-wood joinery |
| Construction | Sides-over-top carcass, minifix and dowel, grooved back, plinth or legs, overlay doors, one drawer slide family, hanging rail, adjustable shelves | Inset fronts, sliding and lift-up doors, mitred joints |
| AI | One vision model, size solver with a measured anchor, layout mapper, rule checks and fixes | Two-model mode, chat editing, photo rectification |
| 3D | SketchUp .skp with scenes via MCP on one geometry machine; web 3D preview; STL, OBJ | 3D DXF from SketchUp, real hardware models |
| Production | Drawing set, cut list, BOM with costs, nesting, generic DXF, labels, package zip | Native machine formats, offcut reuse, quote PDF |
| Platform | Organisations and roles, catalog import, credits and local payments with e-invoices | SSO, API keys, webhooks, data residency |

### Success metrics

| Metric | MVP target |
| --- | --- |
| Workshops using DesignForge on real paid jobs | ≥ 3 |
| Median edits from AI draft to approval | < 10 |
| Software-caused wrong parts | 0 |
| Approval to production package (p50) | < 5 min |
| Designs per active organisation per month | ≥ 15 |

### Launch plan

1. Before building: interview 10 workshops and designers, collect 50 past jobs (photos plus final drawings) as the evaluation set, sign 3–5 design partners.
2. Weeks 1–4: manual spec mode with drawings, cut list and BOM, so partners get value before the AI is ready.
3. Weeks 5–9: AI pipeline and SketchUp MCP integration.
4. Weeks 10–16: drawings, nesting, billing, hardening; paid beta launch.

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A photo cannot fix absolute size | Wrong-size designs | Ask for one measured size; show confidence; mandatory review |
| SketchUp licence may not allow unattended SaaS use | Loss of the .skp output path | Written confirmation from Trimble before launch; SketchUp C SDK fallback |
| A wrong part gets cut | Waste, liability, lost trust | Verification gates, release step, operation preview, test cuts for machine formats |
| Every shop builds differently | Outputs do not match the shop | Per-organisation rule packs and layer mapping from day one |
| AI model changes or price rises | Accuracy or margin drop | Two providers behind one interface, evaluation gate, caching |
| Solo-founder bandwidth | Slow delivery | Narrow scope, managed services, design partners as testers |

### Open questions

- Does Trimble permit SketchUp to run unattended as a SaaS back end, and on what licence?
- Which CNC format do the first design partners need most: Homag MPR or Biesse BPP?
- Decided: the launch market is Vietnam. This sets VND pricing with local payments and e-invoices, a Vietnamese-first product, and Singapore hosting covered by a transfer impact assessment.
- Should the free tier include SketchUp downloads to drive designer adoption, at higher geometry cost?
