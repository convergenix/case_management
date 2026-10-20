# LawERP R0 Foundation — M3 (Thin Billing Slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the WIP→Fee-Note→Invoice financial-conservation invariants end to end — no double-billing, no double-posting on retry, no unapproved invoice — on top of the M1/M2 foundation already merged to `master`.

**Architecture:** Extend the existing `Time Tracking` doctype (not a parallel entity) with a WIP-approval lifecycle: `Draft → Approved → Reserved → Billed`/`Written Off`, with a rate/currency/amount snapshot taken at approval time so a later rate change can't rewrite approved history. A new `Fee Note` doctype is the pre-bill/approval record (`Draft → Partner Review → Finance Review → Approved → Converted`/`Returned`/`Superseded`), with an approval-time content hash that invalidates on any post-approval edit. Converting an Approved Fee Note atomically reserves its Time Tracking lines (conditional `UPDATE ... WHERE wip_status='Approved'`, the same atomic-claim pattern already proven correct in M2's `process_due_reminders`) and creates exactly one native ERPNext Sales Invoice, idempotent on retry.

**Tech Stack:** Frappe v15.99.0, ERPNext (native `Sales Invoice`), `FrappeTestCase`.

**Spec:** `docs/superpowers/specs/2026-10-19-lawerp-r0-foundation-design.md` (M3 section — "M3 — Thin Billing Slice")

## Global Constraints

- All new doctypes live in the existing `Case Management` module, `case_management/case_management/doctype/<name>/` — same convention as M1/M2.
- Current Frappe-15 DocType JSON schema (`actions`, `field_order`, `links`, `naming_rule`, `states`, `row_format`, `sort_field`, `sort_order`).
- Tests use `FrappeTestCase` against the real bench DB on site `home.com`. No mocks, no raw SQL inserts for fixtures — build via `frappe.get_doc({...}).insert()`. Raw SQL is permitted ONLY for the atomic-claim pattern in Task 3/4 (same justified exception already established in M2), never for ordinary fixture creation.
- **Do not run `bench --site home.com migrate`** — this site has pre-existing, unrelated broken Custom Fields. Sync any new/changed doctype with `bench --site home.com --force reload-doc case_management doctype <docname>` (`--site`/`--force` before the subcommand).
- Always pass `--skip-test-records` to `bench run-tests`.
- **Known bug class to avoid from the start** (found and fixed twice already in M1/M2): a `validate()` that does `if self.is_new(): ...; return` before running its transition-gate logic lets a document be CREATED directly into a privileged status, bypassing every gate meant to guard that status. Every new state machine in this plan must treat `is_new()` as an implicit transition FROM the initial state, exactly like `legal_obligation.py`'s final (fixed) `validate()` — never an early return that skips the gates.
- **Known bug class to avoid**: a self-referential `frappe.db.set_value()` call from inside a document's own save-triggered logic must pass `update_modified=False`, or it silently desyncs the in-memory object from the DB on the next save (found and fixed in M2 Task 3). This plan's reservation/claim logic uses raw SQL specifically to sidestep this class of problem entirely — stick to the given patterns, don't improvise a `.save()`-based alternative for the atomic-claim steps.
- **Ethical wall, built in from the start this time** (M2 had to retrofit this after its final review — don't repeat that): `Fee Note` must get `permission_query_conditions`/`has_permission` reusing `matter.py`'s `get_matter_access_condition`/`has_permission` helpers, registered in `hooks.py`, in the SAME task that creates the doctype — not deferred to a later pass.
- Matter already has `company` (Link → Company) and `client` (Link → Customer) fields — use `matter.company`/`matter.client` directly for Sales Invoice creation; don't rely on a global default company.
- `Billing Details` (existing doctype) has fields `customer` (Link → Customer), `billing_rate` (Currency), `billing_currency` (Link → Currency) — the existing `time_tracking.py` already looks these up via `frappe.db.get_value("Billing Details", {"customer": customer}, [...])`; reuse that same lookup pattern for the approval-time snapshot in Task 1.

---

### Task 1: Time Tracking WIP approval lifecycle

**Files:**
- Modify: `case_management/case_management/doctype/time_tracking/time_tracking.json`
- Modify: `case_management/case_management/doctype/time_tracking/time_tracking.py`
- Test: `case_management/case_management/doctype/time_tracking/test_time_tracking_wip.py` (new file — don't touch the existing `test_time_tracking.py`, which stays as the empty stub it already is)

**Interfaces:**
- Consumes: existing `Time Tracking` fields `matter`, `matter_name` (fetched client), `time` (hours), `billing` (Billable/Non-Billable), `employee`.
- Produces: `Time Tracking.wip_status` (Select: `Draft`/`Approved`/`Reserved`/`Billed`/`Written Off`), `approved_rate`/`approved_currency`/`approved_amount` (snapshot fields), `approve_time_entry(time_tracking)` whitelisted function — Task 2/3's Fee Note logic reads `wip_status`/`approved_amount` and writes `wip_status`/`fee_note` by name.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestTimeTrackingWip(FrappeTestCase):
	def _make_matter(self, label="WIP Test"):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		billing = frappe.get_doc({
			"doctype": "Billing Details", "customer": customer.name,
			"billing_rate": 80000, "billing_currency": "NGN",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Billing Details", billing.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter, employee

	def _make_time_entry(self, matter, employee, hours=3.5, billing="Billable"):
		entry = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": hours, "billing": billing, "notes": "Drafting", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry.name, force=True)
		return entry

	def test_new_time_entry_defaults_to_draft_wip_status(self):
		matter, employee = self._make_matter()
		entry = self._make_time_entry(matter, employee)
		self.assertEqual(entry.wip_status, "Draft")

	def test_approving_a_billable_entry_snapshots_rate_and_amount(self):
		matter, employee = self._make_matter()
		entry = self._make_time_entry(matter, employee, hours=3.5)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry.name)

		entry.reload()
		self.assertEqual(entry.wip_status, "Approved")
		self.assertEqual(float(entry.approved_rate), 80000.0)
		self.assertEqual(entry.approved_currency, "NGN")
		self.assertEqual(float(entry.approved_amount), 280000.0)
		self.assertEqual(entry.approved_by, "Administrator")

	def test_approving_a_non_billable_entry_is_rejected(self):
		matter, employee = self._make_matter()
		entry = self._make_time_entry(matter, employee, billing="Non-Billable")

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		with self.assertRaises(frappe.ValidationError):
			approve_time_entry(entry.name)

	def test_direct_creation_with_approved_wip_status_is_rejected(self):
		matter, employee = self._make_matter()
		entry = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": 1, "billing": "Billable", "notes": "x", "employee": employee,
			"wip_status": "Billed",
		})
		with self.assertRaises(frappe.ValidationError):
			entry.insert()

	def test_rate_change_after_approval_does_not_rewrite_approved_amount(self):
		matter, employee = self._make_matter()
		entry = self._make_time_entry(matter, employee, hours=2)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry.name)
		entry.reload()
		original_amount = float(entry.approved_amount)

		frappe.db.set_value("Billing Details", {"customer": frappe.db.get_value("Matter", matter.name, "client")}, "billing_rate", 999999)

		entry.reload()
		self.assertEqual(float(entry.approved_amount), original_amount)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.time_tracking.test_time_tracking_wip`
Expected: FAIL — `wip_status` field doesn't exist yet / `ImportError: cannot import name 'approve_time_entry'`.

- [ ] **Step 3: Add the WIP fields to `time_tracking.json`**

Read the current file first — `time_tracking.json`'s `field_order` currently ends `..., "revenue_in_naira", "amended_from"`. Insert a new section just before `amended_from`. Add these fieldnames to `field_order` in this position (after `revenue_in_naira`, before `amended_from`):

```
"sb_wip",
"wip_status",
"approved_rate",
"approved_currency",
"column_break_wip",
"approved_amount",
"approved_by",
"approved_on",
"fee_note"
```

Add the matching field objects to the `fields` array (insert anywhere — Frappe doesn't require `fields` array order to match `field_order`, but keep them together for readability):

```json
{
 "fieldname": "sb_wip",
 "fieldtype": "Section Break",
 "label": "WIP Approval"
},
{
 "default": "Draft",
 "fieldname": "wip_status",
 "fieldtype": "Select",
 "in_list_view": 1,
 "label": "WIP Status",
 "options": "Draft\nApproved\nReserved\nBilled\nWritten Off",
 "read_only": 1
},
{
 "fieldname": "approved_rate",
 "fieldtype": "Currency",
 "label": "Approved Rate",
 "no_copy": 1,
 "read_only": 1
},
{
 "fieldname": "approved_currency",
 "fieldtype": "Data",
 "label": "Approved Currency",
 "no_copy": 1,
 "read_only": 1
},
{
 "fieldname": "column_break_wip",
 "fieldtype": "Column Break"
},
{
 "fieldname": "approved_amount",
 "fieldtype": "Currency",
 "label": "Approved Amount",
 "no_copy": 1,
 "read_only": 1
},
{
 "fieldname": "approved_by",
 "fieldtype": "Link",
 "label": "Approved By",
 "no_copy": 1,
 "options": "User",
 "read_only": 1
},
{
 "fieldname": "approved_on",
 "fieldtype": "Datetime",
 "label": "Approved On",
 "no_copy": 1,
 "read_only": 1
},
{
 "fieldname": "fee_note",
 "fieldtype": "Link",
 "label": "Fee Note",
 "no_copy": 1,
 "options": "Fee Note",
 "read_only": 1
}
```

Note: `wip_status` is `read_only: 1` at the form level (mirrors the pattern already used for `status` in this same file) — it's only ever changed through `approve_time_entry` and the Fee Note reservation/conversion logic in later tasks, never hand-edited. `fee_note` field references a doctype that doesn't exist until Task 2 — that's fine, Frappe doesn't validate Link target existence at JSON-parse time, only when the field is actually used; just make sure Task 2 lands before you try to populate this field in Task 3.

- [ ] **Step 4: Add the approval logic to `time_tracking.py`**

The existing file has a `TimeTracking(Document)` class with `on_submit`/`before_save` methods and several `@frappe.whitelist()` functions below it (`finalize_time_tracking`, `stop_time_tracking_now`, etc. — leave every one of these completely unchanged). Add a `validate()` method to the class (it doesn't have one currently) and a new whitelisted function. Read the current file first to see exactly where the class body and the `# ─── Whitelisted API methods` section begin, then add:

In the `TimeTracking` class, add:

```python
	def validate(self):
		if self.is_new():
			previous_wip_status = "Draft"
			self.wip_status = self.wip_status or "Draft"
		else:
			previous_wip_status = frappe.db.get_value("Time Tracking", self.name, "wip_status")

		wip_transitions = {
			"Draft": {"Approved"},
			"Approved": {"Reserved", "Written Off"},
			"Reserved": {"Approved", "Billed"},
			"Billed": set(),
			"Written Off": set(),
		}
		if previous_wip_status != self.wip_status:
			if self.wip_status not in wip_transitions.get(previous_wip_status, set()):
				frappe.throw(
					f"Cannot move Time Tracking WIP status from {previous_wip_status} to {self.wip_status}."
				)
```

Add a new whitelisted function in the `# ─── Whitelisted API methods` section (alongside the existing ones):

```python
@frappe.whitelist()
def approve_time_entry(time_tracking):
	doc = frappe.get_doc("Time Tracking", time_tracking)
	if doc.billing != "Billable":
		frappe.throw("Only Billable time entries can be approved for WIP.")
	if doc.wip_status != "Draft":
		frappe.throw(f"Only a Draft entry can be approved (current WIP status: {doc.wip_status}).")

	customer = doc.matter_name
	rate_info = frappe.db.get_value(
		"Billing Details", {"customer": customer}, ["billing_rate", "billing_currency"], as_dict=True
	)
	if not rate_info or not rate_info.billing_rate:
		frappe.throw(f"No Billing Details rate configured for {customer}.")

	doc.wip_status = "Approved"
	doc.approved_rate = rate_info.billing_rate
	doc.approved_currency = rate_info.billing_currency
	doc.approved_amount = flt(doc.time) * flt(rate_info.billing_rate)
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save(ignore_permissions=True)
	return doc.name
```

(`flt` and `now_datetime` are already imported at the top of this file — confirm, don't re-import if already present.)

- [ ] **Step 5: Sync the DocType**

Run: `bench --site home.com --force reload-doc case_management doctype time_tracking`
Expected: Completes with no output/error; adds the new columns to the existing `tabTime Tracking` table.

- [ ] **Step 6: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.time_tracking.test_time_tracking_wip`
Expected: PASS (5/5)

- [ ] **Step 7: Run the pre-existing Time Tracking test file to confirm nothing broke**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.time_tracking.test_time_tracking`
Expected: PASS (0 tests — it's an empty stub, same as before this task).

- [ ] **Step 8: Commit**

```bash
git add case_management/case_management/doctype/time_tracking/
git commit -m "feat: add WIP approval lifecycle to Time Tracking with rate snapshot"
```

---

### Task 2: `Fee Note` doctype (pre-bill/approval record, ethical wall built in)

**Files:**
- Create: `case_management/case_management/doctype/fee_note/__init__.py`
- Create: `case_management/case_management/doctype/fee_note/fee_note.json`
- Create: `case_management/case_management/doctype/fee_note/fee_note.py`
- Create: `case_management/case_management/doctype/fee_note_line/__init__.py`
- Create: `case_management/case_management/doctype/fee_note_line/fee_note_line.json`
- Create: `case_management/case_management/doctype/fee_note_line/fee_note_line.py`
- Modify: `case_management/hooks.py` (add `permission_query_conditions`/`has_permission` entries — alongside the existing `Matter`/`Conflict Review`/`Legal Obligation`/`Obligation Reminder` entries, don't replace them)
- Test: `case_management/case_management/doctype/fee_note/test_fee_note.py`

**Interfaces:**
- Consumes: `Matter.company`/`Matter.client` (existing), `Time Tracking.wip_status`/`approved_amount`/`approved_rate`/`approved_currency` (Task 1).
- Produces: `Fee Note.status` (Select: `Draft`/`Partner Review`/`Finance Review`/`Approved`/`Converted`/`Returned`/`Superseded`), `Fee Note.approved_hash` (Data), `Fee Note.native_invoice` (Link → Sales Invoice). `compute_content_hash(self)` instance method on `FeeNote` — Task 3/4 call this to detect post-approval edits.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestFeeNote(FrappeTestCase):
	def _make_matter_with_approved_time(self, label="Fee Note Test", hours=3.5, rate=80000):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		billing = frappe.get_doc({
			"doctype": "Billing Details", "customer": customer.name,
			"billing_rate": rate, "billing_currency": "NGN",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Billing Details", billing.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		company = frappe.db.get_value("Company", {}, "name")

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee, "company": company,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		entry = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": hours, "billing": "Billable", "notes": "Drafting", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry.name, force=True)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry.name)
		entry.reload()
		return matter, entry

	def _make_fee_note(self, matter, entry):
		fee_note = frappe.get_doc({
			"doctype": "Fee Note",
			"matter": matter.name,
			"cutoff_date": nowdate(),
			"lines": [{
				"time_entry": entry.name,
				"hours": entry.time,
				"rate": entry.approved_rate,
				"amount": entry.approved_amount,
			}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		return fee_note

	def test_new_fee_note_defaults_to_draft(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		self.assertEqual(fee_note.status, "Draft")
		self.assertEqual(float(fee_note.total_amount), float(entry.approved_amount))

	def test_direct_creation_with_approved_status_is_rejected(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(), "status": "Approved",
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		})
		with self.assertRaises(frappe.ValidationError):
			fee_note.insert()

	def test_approving_computes_and_stores_a_content_hash(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)

		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()

		self.assertTrue(fee_note.approved_hash)
		self.assertEqual(fee_note.approved_hash, fee_note.compute_content_hash())

	def test_editing_an_approved_fee_note_invalidates_its_approval(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()
		approved_hash = fee_note.approved_hash

		fee_note.lines[0].hours = 10
		fee_note.lines[0].amount = 10 * float(entry.approved_rate)
		fee_note.save()

		self.assertNotEqual(fee_note.status, "Approved")
		self.assertEqual(fee_note.status, "Finance Review")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note`
Expected: FAIL — `DoesNotExistError: DocType Fee Note not found`

- [ ] **Step 3: Create `fee_note_line/__init__.py`**

```python
```

- [ ] **Step 4: Create `fee_note_line.json`**

```json
{
 "actions": [],
 "creation": "2026-10-20 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "time_entry",
  "hours",
  "rate",
  "amount"
 ],
 "fields": [
  {
   "fieldname": "time_entry",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Time Entry",
   "options": "Time Tracking",
   "reqd": 1
  },
  {
   "fieldname": "hours",
   "fieldtype": "Float",
   "in_list_view": 1,
   "label": "Hours",
   "reqd": 1
  },
  {
   "fieldname": "rate",
   "fieldtype": "Currency",
   "in_list_view": 1,
   "label": "Rate",
   "reqd": 1
  },
  {
   "fieldname": "amount",
   "fieldtype": "Currency",
   "in_list_view": 1,
   "label": "Amount",
   "reqd": 1
  }
 ],
 "istable": 1,
 "links": [],
 "modified": "2026-10-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Fee Note Line",
 "owner": "Administrator",
 "permissions": [],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 5: Create `fee_note_line.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class FeeNoteLine(Document):
	pass
```

- [ ] **Step 6: Create `fee_note/__init__.py`**

```python
```

- [ ] **Step 7: Create `fee_note.json`**

```json
{
 "actions": [],
 "autoname": "FN-.#####",
 "creation": "2026-10-20 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "matter",
  "cutoff_date",
  "column_break_1",
  "status",
  "sb_lines",
  "lines",
  "sb_totals",
  "total_amount",
  "column_break_2",
  "approved_hash",
  "approved_by",
  "approved_on",
  "sb_disposition",
  "decision_reason",
  "native_invoice",
  "conversion_idempotency_key"
 ],
 "fields": [
  {
   "fieldname": "matter",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Matter",
   "options": "Matter",
   "reqd": 1
  },
  {
   "fieldname": "cutoff_date",
   "fieldtype": "Date",
   "in_list_view": 1,
   "label": "Cutoff Date",
   "reqd": 1
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "default": "Draft",
   "fieldname": "status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Status",
   "options": "Draft\nPartner Review\nFinance Review\nApproved\nConverted\nReturned\nSuperseded"
  },
  {
   "fieldname": "sb_lines",
   "fieldtype": "Section Break",
   "label": "Lines"
  },
  {
   "fieldname": "lines",
   "fieldtype": "Table",
   "label": "Lines",
   "options": "Fee Note Line",
   "reqd": 1
  },
  {
   "fieldname": "sb_totals",
   "fieldtype": "Section Break",
   "label": "Approval"
  },
  {
   "fieldname": "total_amount",
   "fieldtype": "Currency",
   "label": "Total Amount",
   "read_only": 1
  },
  {
   "fieldname": "column_break_2",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "approved_hash",
   "fieldtype": "Data",
   "label": "Approved Hash",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "approved_by",
   "fieldtype": "Link",
   "label": "Approved By",
   "no_copy": 1,
   "options": "User",
   "read_only": 1
  },
  {
   "fieldname": "approved_on",
   "fieldtype": "Datetime",
   "label": "Approved On",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "sb_disposition",
   "fieldtype": "Section Break",
   "label": "Disposition"
  },
  {
   "fieldname": "decision_reason",
   "fieldtype": "Small Text",
   "label": "Decision Reason",
   "no_copy": 1
  },
  {
   "fieldname": "native_invoice",
   "fieldtype": "Link",
   "label": "Native Invoice",
   "no_copy": 1,
   "options": "Sales Invoice",
   "read_only": 1
  },
  {
   "fieldname": "conversion_idempotency_key",
   "fieldtype": "Data",
   "label": "Conversion Idempotency Key",
   "no_copy": 1,
   "read_only": 1
  }
 ],
 "is_submittable": 0,
 "links": [],
 "modified": "2026-10-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Fee Note",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "email": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "All",
   "share": 1,
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

Note: role `All` does NOT get `delete`/`export` here — learned from the M2 final review finding, applied from the start this time.

- [ ] **Step 8: Create `fee_note.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


TRANSITIONS = {
	"Draft": {"Partner Review", "Returned"},
	"Partner Review": {"Finance Review", "Returned"},
	"Finance Review": {"Approved", "Returned"},
	"Approved": {"Converted", "Superseded"},
	"Converted": set(),
	"Returned": {"Draft"},
	"Superseded": set(),
}


class FeeNote(Document):
	def validate(self):
		if self.is_new():
			previous_status = "Draft"
			self.status = self.status or "Draft"
		else:
			previous = frappe.db.get_value("Fee Note", self.name, ["status", "approved_hash"], as_dict=True)
			previous_status = previous.status

		self.total_amount = sum(flt(row.amount) for row in self.lines)

		if previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(f"Cannot move Fee Note from {previous_status} to {self.status}.")
			if self.status == "Approved":
				self.approved_by = frappe.session.user
				self.approved_on = now_datetime()
				self.approved_hash = self.compute_content_hash()
		elif previous_status == "Approved" and not self.is_new():
			# A material edit to an already-Approved note (content changed
			# without an explicit status transition) invalidates the
			# approval -- drop back to Finance Review rather than silently
			# keeping a stale hash.
			if self.compute_content_hash() != previous.approved_hash:
				self.status = "Finance Review"
				self.approved_hash = None
				self.approved_by = None
				self.approved_on = None

	def compute_content_hash(self):
		parts = sorted(
			f"{row.time_entry}:{row.hours}:{row.rate}:{row.amount}" for row in self.lines
		)
		raw = "|".join(parts) + f"|{self.matter}|total:{self.total_amount}"
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_permission_query_conditions(user=None):
	from case_management.case_management.doctype.matter.matter import get_matter_access_condition
	return get_matter_access_condition("`tabFee Note`.matter", user)


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	from case_management.case_management.doctype.matter.matter import has_permission as matter_has_permission
	matter_doc = frappe.get_cached_doc("Matter", doc.matter)
	return matter_has_permission(matter_doc, user=user, permission_type=permission_type)
```

- [ ] **Step 9: Register the permission hooks**

In `case_management/hooks.py`, find the existing `permission_query_conditions` and `has_permission` dicts (they already have entries for `Matter`, `Conflict Review`, `Legal Obligation`, `Obligation Reminder`) and add one more key to each, alongside the existing ones:

```python
    "Fee Note": "case_management.case_management.doctype.fee_note.fee_note.get_permission_query_conditions",
```
and
```python
    "Fee Note": "case_management.case_management.doctype.fee_note.fee_note.has_permission",
```

- [ ] **Step 10: Sync the new DocTypes**

Run:
```bash
bench --site home.com --force reload-doc case_management doctype fee_note_line
bench --site home.com --force reload-doc case_management doctype fee_note
```

- [ ] **Step 11: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note`
Expected: PASS (4/4)

- [ ] **Step 12: Commit**

```bash
git add case_management/case_management/doctype/fee_note/ case_management/case_management/doctype/fee_note_line/ case_management/hooks.py
git commit -m "feat: add Fee Note pre-bill/approval record with content-hash invalidation"
```

---

### Task 3: Atomic reservation of Time Tracking lines on Fee Note approval

**Files:**
- Modify: `case_management/case_management/doctype/fee_note/fee_note.py`
- Test: `case_management/case_management/doctype/fee_note/test_fee_note_reservation.py`

**Interfaces:**
- Consumes: `Time Tracking.wip_status`/`fee_note` (Task 1), `Fee Note.status`/`lines` (Task 2).
- Produces: nothing new consumed by later tasks beyond the already-defined `Fee Note.status == "Approved"` meaning "lines are now Reserved" — Task 4's conversion logic relies on lines already being `Reserved` by the time it runs.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestFeeNoteReservation(FrappeTestCase):
	def _make_matter_with_approved_time(self, label="Reservation Test", hours=3.5, rate=80000):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		billing = frappe.get_doc({
			"doctype": "Billing Details", "customer": customer.name,
			"billing_rate": rate, "billing_currency": "NGN",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Billing Details", billing.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		company = frappe.db.get_value("Company", {}, "name")

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee, "company": company,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		entry = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": hours, "billing": "Billable", "notes": "Drafting", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry.name, force=True)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry.name)
		entry.reload()
		return matter, entry

	def _make_fee_note(self, matter, entry):
		fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		return fee_note

	def _approve(self, fee_note):
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()
		fee_note.reload()
		return fee_note

	def test_approving_reserves_the_line_time_entries(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		self._approve(fee_note)

		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "wip_status"), "Reserved")
		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "fee_note"), fee_note.name)

	def test_two_fee_notes_cannot_both_reserve_the_same_time_entry(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note_a = self._make_fee_note(matter, entry)
		fee_note_b = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note_b.name, force=True)

		self._approve(fee_note_a)

		fee_note_b.status = "Partner Review"
		fee_note_b.save()
		fee_note_b.status = "Finance Review"
		fee_note_b.save()
		fee_note_b.status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			fee_note_b.save()

	def test_returning_an_approved_fee_note_releases_the_reservation(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		self._approve(fee_note)

		fee_note.status = "Superseded"
		fee_note.save()

		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "wip_status"), "Approved")
		self.assertFalse(frappe.db.get_value("Time Tracking", entry.name, "fee_note"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note_reservation`
Expected: FAIL — reservation never happens, `wip_status` stays `Approved` after Fee Note approval; the double-reservation test fails because nothing rejects it.

- [ ] **Step 3: Add reservation/release logic to `fee_note.py`**

Modify the `validate()` method's `if self.status == "Approved":` branch (inside the `if previous_status != self.status:` block) to call a new reservation step AFTER the hash is computed, and add release logic for the `Superseded`/`Returned`-from-`Approved` paths. Replace the whole `validate()` method with:

```python
	def validate(self):
		if self.is_new():
			previous_status = "Draft"
			self.status = self.status or "Draft"
		else:
			previous = frappe.db.get_value("Fee Note", self.name, ["status", "approved_hash"], as_dict=True)
			previous_status = previous.status

		self.total_amount = sum(flt(row.amount) for row in self.lines)

		if previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(f"Cannot move Fee Note from {previous_status} to {self.status}.")
			if self.status == "Approved":
				self.approved_by = frappe.session.user
				self.approved_on = now_datetime()
				self.approved_hash = self.compute_content_hash()
				self._reserve_lines()
			if previous_status == "Approved" and self.status in ("Superseded",):
				self._release_lines()
		elif previous_status == "Approved" and not self.is_new():
			if self.compute_content_hash() != previous.approved_hash:
				self.status = "Finance Review"
				self.approved_hash = None
				self.approved_by = None
				self.approved_on = None
				self._release_lines()

	def _reserve_lines(self):
		for row in self.lines:
			frappe.db.sql(
				"""update `tabTime Tracking` set wip_status='Reserved', fee_note=%(fee_note)s
				   where name=%(name)s and wip_status='Approved'""",
				{"fee_note": self.name, "name": row.time_entry},
			)
			claimed = frappe.db.sql("select ROW_COUNT()")[0][0]
			if not claimed:
				frappe.throw(
					f"Time entry {row.time_entry} is no longer available for billing "
					f"(already reserved, billed, or written off elsewhere)."
				)

	def _release_lines(self):
		for row in self.lines:
			frappe.db.sql(
				"""update `tabTime Tracking` set wip_status='Approved', fee_note=NULL
				   where name=%(name)s and wip_status='Reserved' and fee_note=%(fee_note)s""",
				{"name": row.time_entry, "fee_note": self.name},
			)
```

Note on the double-reservation test's "cannot both reserve" scenario: if `fee_note_a`'s approval already reserved the shared entry, `fee_note_b`'s approval attempt will fail the `ROW_COUNT()` check for that same entry (its `wip_status` is no longer `'Approved'` by the time `fee_note_b` tries), correctly throwing before `fee_note_b.status` is ever persisted as `"Approved"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note_reservation`
Expected: PASS (3/3)

- [ ] **Step 5: Run Task 2's test module too, to confirm the extension didn't break approval/hash behavior**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note`
Expected: PASS (4/4, unchanged)

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/doctype/fee_note/fee_note.py case_management/case_management/doctype/fee_note/test_fee_note_reservation.py
git commit -m "feat: atomically reserve Time Tracking lines when a Fee Note is approved"
```

---

### Task 4: Convert an Approved Fee Note into a native Sales Invoice

**Files:**
- Modify: `case_management/case_management/doctype/fee_note/fee_note.py`
- Test: `case_management/case_management/doctype/fee_note/test_fee_note_conversion.py`

**Interfaces:**
- Consumes: `Fee Note.status`/`approved_hash`/`native_invoice`/`total_amount`/`matter` (Task 2/3), `Time Tracking.wip_status` (Task 1).
- Produces: `convert_fee_note(fee_note, idempotency_key=None)` whitelisted function, returning the Sales Invoice name — this is the thin slice's main acceptance-tested entry point, consumed directly by Task 5's acceptance suite.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestFeeNoteConversion(FrappeTestCase):
	def _make_matter_with_approved_fee_note(self, label="Conversion Test", hours=3.5, rate=80000):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		billing = frappe.get_doc({
			"doctype": "Billing Details", "customer": customer.name,
			"billing_rate": rate, "billing_currency": "NGN",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Billing Details", billing.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		company = frappe.db.get_value("Company", {}, "name")

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee, "company": company,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		entry = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": hours, "billing": "Billable", "notes": "Drafting", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry.name, force=True)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry.name)
		entry.reload()

		fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()
		fee_note.reload()
		return fee_note, entry

	def test_converting_an_approved_fee_note_creates_one_submitted_invoice(self):
		fee_note, entry = self._make_matter_with_approved_fee_note()

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		invoice_name = convert_fee_note(fee_note.name, idempotency_key="test-key-1")
		self.addCleanup(frappe.delete_doc, "Sales Invoice", invoice_name, force=True)

		fee_note.reload()
		self.assertEqual(fee_note.status, "Converted")
		self.assertEqual(fee_note.native_invoice, invoice_name)

		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(float(invoice.grand_total), float(fee_note.total_amount))

		entry.reload()
		self.assertEqual(entry.wip_status, "Billed")

	def test_retrying_conversion_after_crash_returns_the_same_invoice_not_a_new_one(self):
		fee_note, entry = self._make_matter_with_approved_fee_note()

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		first_invoice = convert_fee_note(fee_note.name, idempotency_key="retry-key")
		self.addCleanup(frappe.delete_doc, "Sales Invoice", first_invoice, force=True)

		second_invoice = convert_fee_note(fee_note.name, idempotency_key="retry-key")
		self.assertEqual(first_invoice, second_invoice)

		all_invoices = frappe.get_all(
			"Sales Invoice", filters={"name": ["in", [first_invoice, second_invoice]]}
		)
		self.assertEqual(len(frappe.get_all("Sales Invoice", filters={"customer": frappe.db.get_value("Matter", fee_note.matter, "client")})), 1)

	def test_a_draft_fee_note_cannot_be_converted(self):
		matter, entry = None, None
		fee_note, entry = self._make_matter_with_approved_fee_note()
		fee_note.reload()
		frappe.db.set_value("Fee Note", fee_note.name, "status", "Draft")

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		with self.assertRaises(frappe.ValidationError):
			convert_fee_note(fee_note.name, idempotency_key="bad-attempt")

	def test_editing_lines_after_approval_via_direct_db_write_is_caught_at_conversion(self):
		fee_note, entry = self._make_matter_with_approved_fee_note()

		frappe.db.set_value("Fee Note Line", fee_note.lines[0].name, "amount", 999999999)

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		with self.assertRaises(frappe.ValidationError):
			convert_fee_note(fee_note.name, idempotency_key="tampered")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note_conversion`
Expected: FAIL — `ImportError: cannot import name 'convert_fee_note'`

- [ ] **Step 3: Add `convert_fee_note` to `fee_note.py`**

Add this function at the end of the file (after the `has_permission` function):

```python
def _get_or_create_legal_fees_item():
	if not frappe.db.exists("Item", "Legal Fees"):
		frappe.get_doc({
			"doctype": "Item",
			"item_code": "Legal Fees",
			"item_name": "Legal Fees",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
		}).insert(ignore_permissions=True)
	return "Legal Fees"


@frappe.whitelist()
def convert_fee_note(fee_note, idempotency_key=None):
	doc = frappe.get_doc("Fee Note", fee_note)

	if doc.native_invoice:
		return doc.native_invoice

	if doc.status != "Approved":
		frappe.throw(f"Only an Approved Fee Note can be converted (current status: {doc.status}).")

	if doc.compute_content_hash() != doc.approved_hash:
		frappe.throw(
			"This Fee Note has changed since it was approved. "
			"Re-approve before converting."
		)

	matter = frappe.get_doc("Matter", doc.matter)
	item_code = _get_or_create_legal_fees_item()

	invoice = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": matter.client,
		"company": matter.company,
		"matter_id": matter.name,
		"items": [{
			"item_code": item_code,
			"description": f"Legal fees — {matter.name} ({doc.name})",
			"qty": 1,
			"rate": doc.total_amount,
		}],
	})
	invoice.insert(ignore_permissions=True)
	invoice.submit()

	doc.db_set("native_invoice", invoice.name, update_modified=False)
	doc.db_set("status", "Converted", update_modified=False)
	if idempotency_key:
		doc.db_set("conversion_idempotency_key", idempotency_key, update_modified=False)

	for row in doc.lines:
		frappe.db.set_value("Time Tracking", row.time_entry, "wip_status", "Billed", update_modified=False)

	return invoice.name
```

Note on `doc.db_set(...)`: this is Frappe's standard helper for updating a single field on an already-loaded document without re-running `validate()` — appropriate here since we've already done our own explicit checks above and don't want `Fee Note.validate()`'s transition table to reject `Approved → Converted` being set this way (it's already a valid transition per `TRANSITIONS`, but going through `.save()` here would re-run the hash/reservation logic unnecessarily). This mirrors the same pattern this codebase already uses for post-insert state stamps (see `Matter.after_insert` in M1).

Note on idempotency: `if doc.native_invoice: return doc.native_invoice` at the very top handles the retry-after-crash case — once the first call successfully reaches `doc.db_set("native_invoice", ...)`, any later call (same or different idempotency key) returns the existing invoice rather than creating a second one. This is a stronger guarantee than key-matching alone would give (a Fee Note can only ever produce one invoice, period, regardless of what key is passed) and is simpler to reason about.

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note_conversion`
Expected: PASS (4/4)

- [ ] **Step 5: Run Tasks 2 and 3's test modules too, to confirm nothing broke**

Run:
```bash
bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note
bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_fee_note_reservation
```
Expected: PASS (4/4), PASS (3/3), unchanged.

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/doctype/fee_note/fee_note.py case_management/case_management/doctype/fee_note/test_fee_note_conversion.py
git commit -m "feat: convert an Approved Fee Note into a native, idempotent Sales Invoice"
```

---

### Task 5: M3 acceptance suite (spec scenario matrix, end to end)

**Files:**
- Create: `case_management/case_management/doctype/fee_note/test_m3_acceptance.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.

This task has no "implementation" step — it only adds tests that exercise the full M3 acceptance list from the spec, using the real APIs built in Tasks 1-4 together. All of these should already pass given the work in Tasks 1-4; this task proves the pieces compose correctly as whole journeys, including the one scenario no single task's tests fully covers: two *simultaneous* billing runs racing for the same WIP.

- [ ] **Step 1: Write the acceptance tests**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestM3Acceptance(FrappeTestCase):
	def _make_matter_with_two_approved_entries(self, label="M3 Acceptance", hours=3.5, rate=80000):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		billing = frappe.get_doc({
			"doctype": "Billing Details", "customer": customer.name,
			"billing_rate": rate, "billing_currency": "NGN",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Billing Details", billing.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		company = frappe.db.get_value("Company", {}, "name")

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee, "company": company,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry

		entry_a = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": hours, "billing": "Billable", "notes": "Drafting", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry_a.name, force=True)
		approve_time_entry(entry_a.name)
		entry_a.reload()

		entry_b = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": 1.0, "billing": "Billable", "notes": "Review", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry_b.name, force=True)
		approve_time_entry(entry_b.name)
		entry_b.reload()

		return matter, entry_a, entry_b

	def test_two_simultaneous_billing_runs_cannot_together_allocate_more_than_approved_source(self):
		matter, entry_a, entry_b = self._make_matter_with_two_approved_entries()

		fee_note_a = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [
				{"time_entry": entry_a.name, "hours": entry_a.time, "rate": entry_a.approved_rate, "amount": entry_a.approved_amount},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note_a.name, force=True)

		fee_note_b = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [
				{"time_entry": entry_a.name, "hours": entry_a.time, "rate": entry_a.approved_rate, "amount": entry_a.approved_amount},
				{"time_entry": entry_b.name, "hours": entry_b.time, "rate": entry_b.approved_rate, "amount": entry_b.approved_amount},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note_b.name, force=True)

		def _approve(fee_note):
			fee_note.status = "Partner Review"
			fee_note.save()
			fee_note.status = "Finance Review"
			fee_note.save()
			fee_note.status = "Approved"
			fee_note.save()
			return fee_note

		_approve(fee_note_a)

		with self.assertRaises(frappe.ValidationError):
			_approve(fee_note_b)

		fee_note_b.reload()
		self.assertNotEqual(fee_note_b.status, "Approved")

		entry_a.reload()
		self.assertEqual(entry_a.wip_status, "Reserved")
		self.assertEqual(entry_a.fee_note, fee_note_a.name)

	def test_crash_and_retry_on_conversion_cannot_double_post(self):
		matter, entry_a, entry_b = self._make_matter_with_two_approved_entries()

		fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry_a.name, "hours": entry_a.time, "rate": entry_a.approved_rate, "amount": entry_a.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note

		first_attempt = convert_fee_note(fee_note.name, idempotency_key="crash-retry-key")
		self.addCleanup(frappe.delete_doc, "Sales Invoice", first_attempt, force=True)

		retried_attempt = convert_fee_note(fee_note.name, idempotency_key="crash-retry-key")
		self.assertEqual(first_attempt, retried_attempt)

		invoices_for_this_customer = frappe.get_all(
			"Sales Invoice",
			filters={"customer": frappe.db.get_value("Matter", matter.name, "client")},
		)
		self.assertEqual(len(invoices_for_this_customer), 1)

	def test_unapproved_or_edited_fee_note_cannot_reach_a_native_invoice(self):
		matter, entry_a, entry_b = self._make_matter_with_two_approved_entries()
		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note

		draft_fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry_a.name, "hours": entry_a.time, "rate": entry_a.approved_rate, "amount": entry_a.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", draft_fee_note.name, force=True)

		with self.assertRaises(frappe.ValidationError):
			convert_fee_note(draft_fee_note.name, idempotency_key="bypass-attempt-1")

		draft_fee_note.status = "Partner Review"
		draft_fee_note.save()
		draft_fee_note.status = "Finance Review"
		draft_fee_note.save()
		draft_fee_note.status = "Approved"
		draft_fee_note.save()
		draft_fee_note.reload()

		frappe.db.set_value("Fee Note Line", draft_fee_note.lines[0].name, "amount", 1)

		with self.assertRaises(frappe.ValidationError):
			convert_fee_note(draft_fee_note.name, idempotency_key="bypass-attempt-2")

		self.assertFalse(frappe.db.get_value("Fee Note", draft_fee_note.name, "native_invoice"))
```

- [ ] **Step 2: Run the full M3 suite**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.fee_note.test_m3_acceptance`
Expected: PASS — if any of these fail, the gap is in Tasks 1-4, not in this test file; go back and fix the relevant task before continuing.

- [ ] **Step 3: Run every test file added across M1, M2, and M3 together, to catch cross-plan interference**

Run: `bench --site home.com run-tests --skip-test-records --app case_management`
Expected: PASS (M1's 37 + M2's 36 tests plus M3's new tests, all passing, no regressions)

- [ ] **Step 4: Commit**

```bash
git add case_management/case_management/doctype/fee_note/test_m3_acceptance.py
git commit -m "test: add M3 end-to-end acceptance suite (concurrent billing, crash-retry, approval bypass)"
```

---

## Known M3 Simplifications (intentional, not oversights)

- **One matter per Fee Note, no multi-matter consolidation.** The spec explicitly scopes this for the first financial release ("Use one matter per legal invoice... A client statement may consolidate multiple invoices" is a separately scoped extension).
- **Single-currency only.** A Fee Note's lines must all share the Matter's one Billing Details currency; no FX conversion, no multi-currency aggregation.
- **No tax/discount handling.** The native Sales Invoice is created with a single flat-amount line item; VAT/WHT configuration is explicitly out of scope per the spec ("Effective tax and withholding treatment require finance-approved configuration").
- **No disbursements.** This slice covers time/WIP only, not recoverable costs — the spec's disbursement-recovery invariants are a separate future piece of the R2 workstream.
- **No partial-allocation across multiple Fee Notes for one time entry.** A Time Tracking line is reserved in full by whichever Fee Note claims it first; splitting one entry's hours across two invoices is not supported in this thin slice.
- **No credit/rebilling flow.** `Converted` is terminal; cancelling or crediting the native Sales Invoice (and what that means for the underlying Time Tracking entries' `Billed` status) is explicitly deferred, matching the spec's "credit does not automatically make all original time available again" note as a later design.
- **Reviewer role gating not yet added.** `Fee Note`'s `Partner Review`/`Finance Review` transitions are not yet gated behind specific roles the way M1 gated `Conflict Review.decision` behind `Conflicts Reviewer` — any user with write access can move a Fee Note through every status. This mirrors a gap M1 and M2 both initially shipped with and then had to close in their final reviews; flagging it here explicitly so it's a known, deliberate scope boundary for this first pass rather than a silent omission.
