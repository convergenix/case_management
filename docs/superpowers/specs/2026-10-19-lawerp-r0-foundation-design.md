# LawERP R0 Foundation — Design

**Date:** 2026-10-19
**Status:** Approved for implementation
**Branch:** `lawerp/r0-foundation` (does not touch `master` — current clients stay on today's behavior until this is reviewed and merged deliberately)
**Scope:** First buildable slice of the LawERP refinement effort described in the supplied roadmap (`world_class_lawerp_product_roadmap.pdf`) and the Convergenix "LawERP Product and Developer Implementation Plan" (v1.0, 12 Oct 2026). Covers that plan's R0 (foundation) release plus a solo-paced resequencing of its "first three end-to-end journeys." Everything from R1 onward in the source plan (financial controls, client funds, document governance, client portal, AI) is out of scope here and stays tracked as backlog.

## Motivation

The source plan was written for a 4-engineer + QA team delivering 105 work packages over 40 weeks. The actual team on this branch is one developer working with Claude Code, so the plan's sprint cadence and package granularity don't transfer directly — the *architecture and acceptance criteria* do, but the *sequencing* has to be re-scoped for solo pace.

The current `case_management` app is much earlier-stage than either source document assumes: `Matter` is a single flat doctype with a free-text `status` Select, a client link, a legal team table, and child tables for checklist/activities/expenses/invoices. There is no intake/conflict gate, no enforced state machine, no deadline/obligation record, and no matter-level access control. Most of the plan's domain model is new build on top of a thin skeleton, not a refactor.

This spec covers only the foundation: canonical legal parties, an enforced intake/conflict gate before a matter can open, a real Matter state machine, matter-level access control (ethical walls), and verified deadlines/obligations. Billing, client funds, documents, AI, and dashboards are explicitly deferred to later specs that will build on this foundation.

## Non-Goals (deferred to later specs)

- Time/WIP capture, fee notes, native invoice conversion, AR, collections (plan's R2) — beyond the thin M3 slice described below.
- Client funds / safeguarded money / trust accounting (plan's R2, gated separately regardless of price tier).
- Disbursement and staff-advance recovery (plan's R2).
- Document register, immutable versions, malware quarantine, legal hold, retention (plan's R1 "document governance" workstream — not R0).
- Client portal, workspace connectors (Microsoft 365/Google), WhatsApp/Telegram (plan's R3).
- Partner dashboard, deterministic exception engine, metric dictionary (plan's R1→R2 "profitability and dashboard" workstream).
- AI jobs of any kind (plan's R4) — out until the deterministic foundation below exists and is trustworthy.
- Migration tooling, onboarding wizard, commercial packaging/tiers (plan's R0-onward "onboarding" and R3 "commercialization" workstreams, beyond the R0 inventory step captured here).
- Renaming/restructuring `case_management` into a new `lawerp` app — evolving in place for now; that's a separate decision if it comes up later.

## R0 Inventory (completed as part of this spec, not a separate step)

Per the source plan's "Days one to two" deliverable (inventory, baseline manifest, existing-component map):

- App: `case_management`, installed in this bench alongside `erpnext`, `hrms`, `frappe`; upstream remote is `convergenix/case_management.git`; this branch is based on `master` at commit `911c566`.
- Existing doctypes relevant to this spec: `Matter`, `Matter Team Item`, `Matter Custom Check List` (+ item), `Matter Check List Item`, `Practice Area`, `Supervisor`, `Time Tracking`, `Matter Activity` (+ item), `Matter Expense`, `Matter Invoice`, `Matter Notes`, `Matter Task`, `Matter File Item`, `Billing Details`, `Transaction(s)`.
- No existing `Legal Party`, `Intake`, `Conflict Review`, `Legal Obligation`, or matter-level access-control configuration.
- `Matter.status` is a plain Select with no transition enforcement and no audit trail of state changes.
- Fixtures already exported: `Custom Field`, `Role`, `Translation`, `Folder`, `Folder Structure`, `Naming Series` (see `hooks.py`).

## Sequencing

Three independently reviewable sub-milestones on this one branch:

1. **M1 — Canonical parties, intake gate, matter state machine.** The architectural spine. Nothing in M2/M3 is meaningful without this.
2. **M2 — Verified obligations & deadline recovery.** Mostly additive; lower risk than M1 or M3.
3. **M3 — Thin WIP→Fee-Note→Invoice slice.** Touches money; comes last and gets the most scrutiny, per the source plan's warning that financial controls are easy to fake in a demo and hard to retrofit.

Each sub-milestone gets its own PR/review checkpoint before the next starts.

## M1 — Data Model

| Doctype | Purpose | Key fields / invariants |
|---|---|---|
| `Legal Party` | Canonical party record wrapping Contact/Customer. | Stable ID, person-or-organization, aliases, normalized name, related-party links, effective dates. A prospect or adverse party is **not** automatically an accounting Customer. |
| `Intake` | Staged pre-matter form. | Proposed client, complete party set (client + adverse + affiliates), scope, evidence attachments. States: `Draft → Under Review → Approved / Declined / Withdrawn → Converted`. |
| `Conflict Review` | Record of a conflict search and decision. | Party-set version/hash, corpus/index version searched, search timestamp, query parameters, reviewer, decision, reason, waiver evidence if any. |
| `Matter` (reworked) | Replace free-text `status` with an enforced state machine. | States: `Open → Active → On Hold → Closing → Closed → Archived`, plus a separate `waiting_on` field (client/court/counterparty/none) so a matter can be `Active` and `Waiting on Court` simultaneously. Normal opening requires an `Approved` Intake + Conflict Review; direct API/import creation goes through the same `validate` gate. |
| `Matter State Log` | Append-only transition history. | Previous state, new state, changed by, changed at, reason. Written automatically on every transition — never hand-edited. |

Reuse per the source plan's reuse table: `Company`, `Customer`, `Contact`, `Address`, `Currency` stay as-is; `Legal Party` sits alongside them rather than replacing them.

## M1 — State Machine Mechanism

Two options considered:

- **Frappe Workflow doctype** (declarative state + transition rules, native UI buttons). Rejected as the sole mechanism — workflow permissions aren't fine-grained enough for "block opening until conflict clearance is current," and that logic needs a server-side hook regardless.
- **Plain Select field + enforced transitions in `Matter.validate()` / `before_save`** (chosen). Full control over the conflict-gate and re-review triggers (stale clearance, material party/scope change invalidates prior approval). Testable as pure Python against a real DB. The `Matter State Log` child table carries the audit trail that a Workflow's native history would otherwise provide.

## M1 — Access Control (Ethical Walls)

Reuse Frappe's existing permission layers rather than building parallel infrastructure:

- Role-level permissions for the baseline (Associate, Partner, Finance, Conflicts Reviewer, etc.).
- `User Permission` records scoped to restricted Matters for narrower grants.
- A `permission_query_conditions` hook on `Matter` (and later on child/related doctypes) so list views, reports, search, and any `get_all`/`get_list` call honor the same restriction — the source plan explicitly flags privileged query APIs as the common bypass route around UI-only permission checks.

Acceptance for M1 includes: an unauthorized user sees neither content nor confidential titles; a restricted-match conflict search reaches the designated reviewer without disclosing matter details to the requester; a direct API or import cannot bypass the intake-approval gate.

### Known limitation: the ALLOW side of the wall is unreachable on this bench

`Matter`'s pre-existing base `DocPerm` rows make the ethical wall's *allow* branch structurally unreachable, and M1 does not change them. `Lawyer Manager` has `if_owner: 1`, so that role can only read Matters the user personally created; `Partners` has unrestricted read but is `disabled` in this bench's `Role` data, and `User.validate()` silently strips disabled roles from any user it is assigned to. Frappe **ANDs** role-level DocPerm conditions with `permission_query_conditions`, so a non-owning `Lawyer Manager` who sits on a matter's `Matter Team Item` team is excluded by the base role permission before `is_restricted` or team membership is ever consulted.

The consequence is asymmetric: the DENY side works correctly — a restricted matter is hidden from users who should not see it, through list views, the calendar, Script Reports and document reads alike — but the team-membership and responsible-solicitor allowances M1 builds can never actually grant access to a Matter a user did not create. Closing this requires either removing `if_owner` from `Lawyer Manager`'s DocPerm or enabling the `Partners` role (and deciding who holds it). Both are product/security decisions about base permission configuration with blast radius across the whole app, so they are deliberately left for a human to make rather than being folded into an implementation or fix wave. `test_known_limitation_team_member_without_ownership_cannot_see_matter` in `test_matter_access.py` pins the current behavior so the gap stays visible and is not mistaken for a regression.

## M2 — Data Model

| Doctype | Purpose | Key fields / invariants |
|---|---|---|
| `Legal Obligation` | Deadline/obligation record, independent of any calendar event. | Matter, obligation type, jurisdiction, source document/instruction, due date, date-only vs. time-specific semantics, timezone, owner, deputy, verifier, supporting evidence. Completion is independent of reminder delivery or acknowledgement. |
| `Obligation Reminder` (or reminder fields on `Legal Obligation`) | Scheduled reminder/escalation state. | Queued → provider-accepted → delivered (where confirmed) → acknowledged → completed. Deputy and partner escalation on non-acknowledgement. |

Run reminders through Frappe's scheduler with an outbox-style durability check: detect scheduler failure independently, and on recovery, process due reminders without duplicating already-delivered ones and raise an overdue exception for anything now late.

Acceptance for M2 mirrors the source plan's scenario matrix: a rescheduled date preserves the old date and reason and invalidates obsolete reminders; a stopped scheduler and its recovery are both detected; completing a reminder does not complete the underlying filing.

### Known M2 limitations surfaced by final review

Two gaps were identified in the final whole-branch review of M2. Neither is a defect against the M2 table above, and neither is fixed in the branch — both are decisions for a human to make before production use, recorded here so they stay visible rather than being mistaken for finished work.

- **`Legal Obligation` has no append-only transition history.** M1 introduced `Matter State Log` precisely because an unauditable status field was flagged as a defect in the original R0 inventory, but the M2 table does not require an equivalent for obligations, so none was built. The state machine as implemented permits cancelling a critical court deadline with no evidence and no durable record of who cancelled it or why — only the current `status` and the `verified_by`/`completed_by` stamps survive. Whether that is acceptable, or whether obligations need the same append-only log M1 established, should be decided deliberately.
- **`due_time`, `date_only` and `timezone` are collected but never consumed.** `generate_default_reminders` computes reminder times from `due_date` alone and always schedules at midnight local, regardless of these three fields. The M2 table lists "date-only vs. time-specific semantics, timezone" among the key invariants, so the fields exist and are editable, but they are currently decorative: a 9:00 AM hearing in another timezone produces exactly the same reminder schedule as an all-day filing deadline. This needs either real implementation or an explicit decision to defer, on the same footing as the other documented M2 simplifications.

## M3 — Thin Billing Slice

Scope is deliberately narrow — just enough to validate the plan's financial-conservation invariants end to end, not the full billing module (that's a separate future spec covering the rest of the plan's R2 workstream):

- One authoritative time/WIP source per matter (extend existing `Time Tracking` rather than introducing a parallel entity, pending a short spike to confirm it can carry rate snapshot + approval + partial-allocation behavior).
- A `Fee Note` as the pre-bill/approval record (not an extra ledger) — partner review, finance review, immutable approved-version hash.
- Conversion to a native ERPNext Sales Invoice only from an approved, hash-matched Fee Note, with reservation of source allocations so the same WIP can't be billed twice and a retried conversion returns the existing invoice rather than double-posting.

Acceptance for M3: two simultaneous billing runs against the same WIP cannot together allocate more than the approved source value; a crash-and-retry on conversion cannot double-post; an unapproved or edited fee note cannot reach a native invoice through UI, API, or import.

## Testing Approach

Per house rules: `FrappeTestCase` against a real bench DB. Fixtures built through actual doctype creation (no mocks, no raw SQL inserts). Assertions on DB state and returned document values — never on which internal method fired or how many queries ran. The source plan's own acceptance scenarios (stale clearance blocks reopening, restricted matter invisible to unauthorized users, simultaneous conflicting intakes can't both activate, duplicate billing runs can't over-allocate) become the literal test cases for each sub-milestone.

## Source References

- `world_class_lawerp_product_roadmap.pdf` — original roadmap, sections 1-11 and the four-phase practical roadmap (cited in the implementation plan as S0).
- "LawERP Product and Developer Implementation Plan," v1.0, 12 Oct 2026 — sections 3-6 (release scope, architecture, data model) and section 18 (acceptance/release gates) are the primary basis for this spec.
