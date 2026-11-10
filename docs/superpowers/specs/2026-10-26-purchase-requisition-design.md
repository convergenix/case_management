# Purchase Requisition — Design

## Intent

The LawERP home page's "Purchase Requisition" tile currently links to ERPNext's `Expense Claim` as a stand-in — a deliberate placeholder put there when the tile was first built, with no real doctype behind it. This replaces that stand-in with a real `Purchase Requisition` doctype: a request to buy something, routed for approval *before* any money is spent — distinct from `Expense Claim`, which reimburses money already spent.

## Why now

The firm wants staff to be able to request purchases — both firm overhead (supplies, software, equipment) and client-matter costs they'll later bill back to the client (expert witnesses, filing fees, process servers) — through the same LawERP home page the rest of their work lives on, instead of a tile that silently opens the wrong form.

## Goals

- A requester can submit a purchase request naming what's needed, an estimated cost, and the matter it's chargeable to (when it's a client cost rather than firm overhead).
- A named approver reviews and approves or rejects it. Approval is the end state — nothing downstream (no Purchase Order, no payment) happens automatically.
- The approver can't approve their own requisition unless they hold the **Managing Partner** or **System Manager** role.
- Matter-linked requisitions are covered by the same ethical wall as every other matter-linked doctype in this app.

## Non-goals

- No vendor/supplier selection — who to actually buy from is decided outside the system, after approval.
- No conversion to a native ERPNext Purchase Order, Purchase Invoice, or any GL/accounting entry. Approval alone covers it.
- No multi-stage review (no Partner Review → Finance Review chain like Fee Note). One named approver, full stop.
- Not a rebuild of Expense Claim's actual payment/reimbursement machinery (`is_paid`, `mode_of_payment`, `payable_account`, `clearance_date`) — none of that applies here, since no money moves through this doctype.

## Anti-goals

Nothing here should let a requisition be approved without a named, accountable approver, or let the independence check be silently bypassed by a role other than the two explicitly named (Managing Partner, System Manager).

## Constraints

- Follows this app's established Frappe-15/16-compatible DocType JSON schema and the project's standing testing rule: `FrappeTestCase` against the real bench DB, no mocks, fixtures built via `.insert()`.
- Avoid `naming_series`-based autoname. This app's `fixtures = [...]` list includes `"Naming Series"`, and syncing that fixture is already broken on the Frappe v16 test bench (`Module import failed for Naming Series`) — a simple counter autoname (matching `Fee Note`'s `"FN-.#####"` pattern) sidesteps a known-broken sync path entirely rather than depending on it.
- Reuses `matter.py`'s `get_matter_access_condition`/`has_permission` helpers for the ethical wall, wired in from the same task that creates the doctype — not deferred, per the standing lesson from M1/M2's retrofits and M3's Global Constraint.
- Known bug class this app has hit repeatedly and must not reintroduce: a `validate()` that lets a document be created directly into a privileged status by returning early for `is_new()` before its transition/role gates run. `is_new()` must be treated as an implicit transition from the doctype's initial state.

## The how, as decided

**Doctypes:**
- `Purchase Requisition` (parent, submittable) + `Purchase Requisition Item` (child table).

**Parent fields:**
- `employee` (Link → Employee, reqd) — the requester.
- `employee_name`, `department`, `company` — fetched from `employee` (mirrors Expense Claim's own fetch pattern).
- `matter` (Link → Matter) — optional; set only when the cost is chargeable to a client matter rather than firm overhead.
- `client` — fetched from `matter.client` when `matter` is set (mirrors the existing `Expense Claim.client_name` custom field already shipped in this app).
- `approver` (Link → Employee, reqd) — the named approver.
- `approval_status` (Select: `Pending` / `Approved` / `Rejected`, default `Pending`).
- `rejection_reason` (Small Text) — required when `approval_status` is set to `Rejected`. Matches this app's established house style of requiring a reason wherever something is declined or returned (`Fee Note.decision_reason`, `Legal Obligation.reschedule_reason`).
- `items` (Table → Purchase Requisition Item).
- `total_estimated_amount` (Currency, read-only) — sum of the child table's line amounts, computed in `validate()` (same pattern as `Fee Note.total_amount`).
- `amended_from` (Link → Purchase Requisition) — standard field for a submittable doctype.

**Child table (`Purchase Requisition Item`) fields:**
- `item_description` (Data, reqd) — plain text, not a Link to the `Item` doctype. A purchase requisition can name something that was never catalogued as a stock/service Item (a software renewal, a one-off office purchase), so forcing a catalogue match would be too restrictive for a thin request form.
- `qty` (Float, reqd).
- `estimated_rate` (Currency, reqd) — estimated cost per unit.
- `estimated_amount` (Currency, read-only) — `qty * estimated_rate`, computed the same way `Fee Note Line.amount` is validated against its source.

**State model:**
- `is_submittable: 1`. The requester submits their own requisition (`docstatus` 0 → 1) the same way an employee submits their own Expense Claim — this locks the record and the line items.
- `approval_status` can only move away from `Pending` once `docstatus == 1` (the requisition must be submitted before it can be approved or rejected) — enforced in `validate()`, not left to UI convention.
- Only the named `approver` can move `approval_status` to `Approved` or `Rejected` — mirrors `Legal Obligation`'s "only the named verifier can move it" check, with the same two-role bypass (**Managing Partner**, **System Manager**) already used for comparable self-certification guards elsewhere in this app.
- The `employee` (requester) cannot also be the `approver` on the same requisition, unless the acting user holds **Managing Partner** or **System Manager** — checked unconditionally, the same way `Legal Obligation` checks verifier/owner independence for critical obligations.
- `is_new()` is treated as an implicit transition from `Pending` — a direct creation with `approval_status` already set to `Approved`/`Rejected` must fail the same gates a later transition would.

**Access control:**
- `permission_query_conditions` / `has_permission` registered in `hooks.py` in the same task that creates the doctype, delegating to `matter.py`'s existing helpers — but only enforced when `matter` is actually set. A pure-overhead requisition with no matter has no ethical-wall restriction to apply; visibility for those falls back to ordinary role-based DocPerm.

**Navigation:**
- The LawERP home page's "Purchase Requisition" tile is repointed from `/app/expense-claim` to the new doctype's list route, and its "Coming soon"-adjacent framing (it was already live, just wrong) is unaffected — no change needed there beyond the href.

## What's left to the builder

- Exact `permission_query_conditions` SQL fragment wording for the matter-optional case (the pattern exists in `matter.py` and every other matter-linked doctype in this app already shows how to call it; applying the same shape here when `matter` is set, and skipping it cleanly when it isn't, is mechanical).
- Exact field layout (section breaks, column breaks) — functionally inert, builder's choice, follow this app's existing doctype JSON conventions.
- Test fixture construction detail — follow this app's established fixture-builder pattern already used across M1–M3's test files (Customer → Legal Party → Intake → Conflict Review → Matter → Employee, etc.).
