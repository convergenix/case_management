# LawERP R0 Foundation — M2 (Verified Obligations & Deadline Recovery) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `case_management` a verified-deadline record (`Legal Obligation`) independent of any calendar event, with a durable, outage-recoverable reminder/escalation pipeline (`Obligation Reminder`), on top of the M1 foundation (`Matter`, `Intake`, `Conflict Review`, `Legal Party`) already merged on this branch.

**Architecture:** Two new doctypes. `Legal Obligation` is the authoritative deadline record with its own state machine (`Proposed → Verified → Active → Completed/Superseded/Cancelled`) and reschedule tracking (old date + reason preserved, never silently overwritten). `Obligation Reminder` is a standalone doctype (not a child table — the scheduler needs to query across all obligations for due reminders, which a child table makes awkward) with its own lifecycle (`Queued → Delivered → Acknowledged → Completed`), auto-generated when an obligation goes Active and auto-invalidated/regenerated when the obligation is rescheduled. A scheduled job processes due reminders; a heartbeat-based health check detects scheduler outages and reprocesses backlog without duplicating already-delivered reminders.

**Tech Stack:** Frappe v15.99.0 (same bench as M1), `FrappeTestCase`, Frappe's `scheduler_events` hook for cron-style jobs.

**Spec:** `docs/superpowers/specs/2026-10-19-lawerp-r0-foundation-design.md` (M2 section)

## Global Constraints

- All new doctypes live in the existing `Case Management` module, directory `case_management/case_management/doctype/<name>/` — same convention as M1, no new module.
- Current Frappe-15 DocType JSON schema (`actions`, `field_order`, `links`, `naming_rule`, `states`, `row_format`, `sort_field`, `sort_order` — see `time_tracking.json` as the reference). Child tables (none in this plan) would use `"istable": 1` and `"permissions": []`.
- Tests use `FrappeTestCase` against the real bench DB on site `home.com`. No mocks, no raw SQL inserts — build fixtures via `frappe.get_doc({...}).insert()`. Assert on returned document values / DB state.
- **Do not run `bench --site home.com migrate`** — this site has pre-existing, unrelated broken Custom Fields that make a full migrate fail (see M1's plan/ledger for the full story — already cleaned up once, but `migrate`'s broader validation pass is still not safe to rely on here). Sync each new/changed doctype individually: `bench --site home.com --force reload-doc case_management doctype <docname>` (`--site`/`--force` come before the subcommand).
- Always pass `--skip-test-records` to `bench run-tests` — Frappe's dependency-record walker reaches unrelated broken fixtures elsewhere in this bench otherwise. No test in this plan relies on Frappe's auto-generated test records.
- `Matter`'s own pre-existing permission model (discovered during M1): role `Lawyer Manager` has `if_owner: 1` on Matter (can only read Matters it personally owns); role `Partners` has unrestricted read but is marked `disabled` in this bench's Role data, and Frappe's `User.validate()` silently strips disabled roles from any user on every save — so `Partners` cannot be assigned to a test user at all. If any test in this plan needs a non-privileged user to read a `Matter` it doesn't own, do NOT repeat M1's early mistakes: either make that user own the record, or avoid needing baseline Matter visibility for the scenario under test. This plan's own doctypes (`Legal Obligation`, `Obligation Reminder`) get fresh permission rows — grant `All` role read/write for M2 (ethical-wall-style restriction on obligations is out of scope for this milestone; `Matter`'s own `is_restricted` flag already gates the parent Matter).
- Work directly in `/home/okeke/clients/graceco/frappe-bench/apps/case_management`, already on branch `lawerp/r0-foundation`. No worktree — this app is editable-installed via a hardcoded absolute path to this directory.

---

### Task 1: `Legal Obligation` doctype (core fields, state machine, reschedule tracking)

**Files:**
- Create: `case_management/case_management/doctype/legal_obligation/__init__.py`
- Create: `case_management/case_management/doctype/legal_obligation/legal_obligation.json`
- Create: `case_management/case_management/doctype/legal_obligation/legal_obligation.py`
- Test: `case_management/case_management/doctype/legal_obligation/test_legal_obligation.py`

**Interfaces:**
- Consumes: `Matter` (Task 4 of M1, already merged) via Link field, no new coupling.
- Produces: `Legal Obligation.status` (Select: `Proposed`/`Verified`/`Active`/`Completed`/`Superseded`/`Cancelled`), `Legal Obligation.due_date` (Date), `Legal Obligation.previous_due_date` (Date, set only when a Verified/Active obligation's `due_date` changes) — Task 2's auto-reminder-generation hook and Task 3's reschedule-invalidation hook both key off these three fields by name.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestLegalObligation(FrappeTestCase):
	def _make_matter_and_obligation(self, due_date=None, **overrides):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Obligation Test Customer",
			"customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "Obligation Test Client",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Advisory",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Obligation Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Obligation Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"open_date": nowdate(),
			"practice_area": practice_area.name,
			"transaction": "Obligation Test Transaction",
			"responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		fields = {
			"doctype": "Legal Obligation",
			"matter": matter.name,
			"obligation_type": "Filing Deadline",
			"due_date": due_date or add_days(nowdate(), 14),
			"responsible_user": "Administrator",
		}
		fields.update(overrides)
		obligation = frappe.get_doc(fields).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)
		return obligation

	def test_new_obligation_defaults_to_proposed(self):
		obligation = self._make_matter_and_obligation()
		self.assertEqual(obligation.status, "Proposed")

	def test_critical_obligation_requires_verifier_before_verified(self):
		obligation = self._make_matter_and_obligation(is_critical=1)
		obligation.status = "Verified"
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

	def test_rescheduling_active_obligation_requires_reason_and_preserves_old_date(self):
		obligation = self._make_matter_and_obligation(is_critical=0)
		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()

		old_due_date = obligation.due_date
		obligation.due_date = add_days(old_due_date, 7)
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

		obligation.reload()
		obligation.due_date = add_days(old_due_date, 7)
		obligation.reschedule_reason = "Court granted an extension"
		obligation.save()
		self.assertEqual(str(obligation.previous_due_date), str(old_due_date))

	def test_completing_requires_evidence(self):
		obligation = self._make_matter_and_obligation()
		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		obligation.status = "Completed"
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

		obligation.reload()
		obligation.status = "Completed"
		obligation.completion_evidence = "Filed stamped copy attached"
		obligation.save()
		self.assertEqual(obligation.status, "Completed")
		self.assertEqual(obligation.completed_by, "Administrator")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.legal_obligation.test_legal_obligation`
Expected: FAIL — `ModuleNotFoundError` / `DoesNotExistError: DocType Legal Obligation not found` (doctype doesn't exist yet).

- [ ] **Step 3: Create `__init__.py`**

```python
```

(empty file, matches convention of every other doctype folder in this app)

- [ ] **Step 4: Create `legal_obligation.json`**

```json
{
 "actions": [],
 "autoname": "OBL-.#####",
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "matter",
  "obligation_type",
  "jurisdiction",
  "column_break_1",
  "due_date",
  "date_only",
  "due_time",
  "timezone",
  "sb_source",
  "source_reference",
  "sb_team",
  "responsible_user",
  "deputy",
  "column_break_2",
  "is_critical",
  "verifier",
  "sb_status",
  "status",
  "verified_by",
  "verified_on",
  "sb_reschedule",
  "previous_due_date",
  "reschedule_reason",
  "sb_completion",
  "completion_evidence",
  "completed_by",
  "completed_on"
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
   "fieldname": "obligation_type",
   "fieldtype": "Select",
   "label": "Obligation Type",
   "options": "Court Hearing\nFiling Deadline\nLimitation Date\nRegulatory Submission\nClient Deadline\nOther",
   "reqd": 1
  },
  {
   "fieldname": "jurisdiction",
   "fieldtype": "Data",
   "label": "Jurisdiction"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "due_date",
   "fieldtype": "Date",
   "in_list_view": 1,
   "label": "Due Date",
   "reqd": 1
  },
  {
   "default": "1",
   "fieldname": "date_only",
   "fieldtype": "Check",
   "label": "Date-Only (No Specific Time)"
  },
  {
   "depends_on": "eval:!doc.date_only",
   "fieldname": "due_time",
   "fieldtype": "Time",
   "label": "Due Time"
  },
  {
   "default": "Africa/Lagos",
   "fieldname": "timezone",
   "fieldtype": "Data",
   "label": "Timezone"
  },
  {
   "fieldname": "sb_source",
   "fieldtype": "Section Break",
   "label": "Source"
  },
  {
   "fieldname": "source_reference",
   "fieldtype": "Small Text",
   "label": "Source Document / Instruction"
  },
  {
   "fieldname": "sb_team",
   "fieldtype": "Section Break",
   "label": "Ownership"
  },
  {
   "fieldname": "responsible_user",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Owner",
   "options": "User",
   "reqd": 1
  },
  {
   "fieldname": "deputy",
   "fieldtype": "Link",
   "label": "Deputy",
   "options": "User"
  },
  {
   "fieldname": "column_break_2",
   "fieldtype": "Column Break"
  },
  {
   "default": "0",
   "fieldname": "is_critical",
   "fieldtype": "Check",
   "label": "Critical Date (Requires Independent Verification)"
  },
  {
   "description": "Required reviewer for critical dates before status can reach Verified.",
   "fieldname": "verifier",
   "fieldtype": "Link",
   "label": "Verifier",
   "options": "User"
  },
  {
   "fieldname": "sb_status",
   "fieldtype": "Section Break",
   "label": "Status"
  },
  {
   "default": "Proposed",
   "fieldname": "status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Status",
   "options": "Proposed\nVerified\nActive\nCompleted\nSuperseded\nCancelled"
  },
  {
   "fieldname": "verified_by",
   "fieldtype": "Link",
   "label": "Verified By",
   "no_copy": 1,
   "options": "User",
   "read_only": 1
  },
  {
   "fieldname": "verified_on",
   "fieldtype": "Datetime",
   "label": "Verified On",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "sb_reschedule",
   "fieldtype": "Section Break",
   "label": "Reschedule History"
  },
  {
   "fieldname": "previous_due_date",
   "fieldtype": "Date",
   "label": "Previous Due Date",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "description": "Required when changing Due Date after the obligation has been Verified or Active.",
   "fieldname": "reschedule_reason",
   "fieldtype": "Small Text",
   "label": "Reschedule Reason",
   "no_copy": 1
  },
  {
   "fieldname": "sb_completion",
   "fieldtype": "Section Break",
   "label": "Completion"
  },
  {
   "description": "Required when marking Completed.",
   "fieldname": "completion_evidence",
   "fieldtype": "Small Text",
   "label": "Completion Evidence",
   "no_copy": 1
  },
  {
   "fieldname": "completed_by",
   "fieldtype": "Link",
   "label": "Completed By",
   "no_copy": 1,
   "options": "User",
   "read_only": 1
  },
  {
   "fieldname": "completed_on",
   "fieldtype": "Datetime",
   "label": "Completed On",
   "no_copy": 1,
   "read_only": 1
  }
 ],
 "is_submittable": 0,
 "links": [],
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Legal Obligation",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
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

- [ ] **Step 5: Create `legal_obligation.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


TRANSITIONS = {
	"Proposed": {"Verified", "Cancelled"},
	"Verified": {"Active", "Superseded", "Cancelled"},
	"Active": {"Completed", "Superseded", "Cancelled"},
	"Completed": set(),
	"Superseded": set(),
	"Cancelled": set(),
}


class LegalObligation(Document):
	def validate(self):
		if self.is_new():
			self.status = self.status or "Proposed"
			return

		previous = frappe.db.get_value(
			"Legal Obligation", self.name, ["status", "due_date"], as_dict=True
		)

		if previous.status != self.status:
			if self.status not in TRANSITIONS.get(previous.status, set()):
				frappe.throw(
					f"Cannot move Legal Obligation from {previous.status} to {self.status}."
				)
			if self.status == "Verified":
				if self.is_critical and not self.verifier:
					frappe.throw(
						"Critical obligations require a Verifier before they can be Verified."
					)
				self.verified_by = frappe.session.user
				self.verified_on = now_datetime()
			if self.status == "Completed":
				if not self.completion_evidence:
					frappe.throw(
						"Completing an obligation requires completion evidence."
					)
				self.completed_by = frappe.session.user
				self.completed_on = now_datetime()

		if previous.due_date and self.due_date and str(previous.due_date) != str(self.due_date):
			if previous.status in ("Verified", "Active"):
				if not self.reschedule_reason:
					frappe.throw(
						"Rescheduling a Verified/Active obligation requires a reason "
						"in 'Reschedule Reason'."
					)
				self.previous_due_date = previous.due_date
```

- [ ] **Step 6: Sync the new DocType into the site**

Run: `bench --site home.com --force reload-doc case_management doctype legal_obligation`
Expected: Completes with no output/error; creates the `tabLegal Obligation` table and `DocType` record.

- [ ] **Step 7: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.legal_obligation.test_legal_obligation`
Expected: PASS (4/4)

- [ ] **Step 8: Commit**

```bash
git add case_management/case_management/doctype/legal_obligation/
git commit -m "feat: add Legal Obligation doctype with state machine and reschedule tracking"
```

---

### Task 2: `Obligation Reminder` doctype and auto-generation on activation

**Files:**
- Create: `case_management/case_management/doctype/obligation_reminder/__init__.py`
- Create: `case_management/case_management/doctype/obligation_reminder/obligation_reminder.json`
- Create: `case_management/case_management/doctype/obligation_reminder/obligation_reminder.py`
- Modify: `case_management/hooks.py` (add a `doc_events` entry for `Legal Obligation`)
- Test: `case_management/case_management/doctype/obligation_reminder/test_obligation_reminder.py`

**Interfaces:**
- Consumes: `Legal Obligation.status`, `Legal Obligation.due_date`, `Legal Obligation.responsible_user`, `Legal Obligation.deputy` (Task 1).
- Produces: `generate_default_reminders(obligation_name)` module function in `obligation_reminder.py` — called from the `doc_events` hook when a `Legal Obligation` transitions into `Active` for the first time (idempotent: does nothing if reminders already exist for that obligation). `Obligation Reminder.status` (Select: `Queued`/`Delivered`/`Acknowledged`/`Completed`/`Superseded`), `Obligation Reminder.scheduled_for` (Datetime), `Obligation Reminder.obligation` (Link) — Task 3's reschedule-invalidation and Task 4's scheduler-processing both key off these by name. `acknowledge(reminder)` whitelisted function.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate, now_datetime


class TestObligationReminder(FrappeTestCase):
	def _make_active_obligation(self, due_date=None):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Reminder Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Reminder Test Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Reminder Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Reminder Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Reminder Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Filing Deadline",
			"due_date": due_date or add_days(nowdate(), 14), "responsible_user": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		return obligation

	def test_activating_obligation_generates_default_reminders(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, fields=["name", "status", "recipient"]
		)
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r.name, force=True)
		self.assertEqual(len(reminders), 2)
		self.assertTrue(all(r.status == "Queued" for r in reminders))
		self.assertTrue(all(r.recipient == "Administrator" for r in reminders))

	def test_activation_is_idempotent_no_duplicate_reminders(self):
		obligation = self._make_active_obligation()
		reminders_first = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name})
		for r in reminders_first:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r.name, force=True)

		obligation.source_reference = "Updated via an unrelated field edit"
		obligation.save()

		reminders_second = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name})
		self.assertEqual(len(reminders_first), len(reminders_second))

	def test_acknowledge_requires_delivered_status(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import acknowledge
		with self.assertRaises(frappe.ValidationError):
			acknowledge(reminders[0])

		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")
		result = acknowledge(reminders[0])
		self.assertEqual(result, reminders[0])
		self.assertEqual(frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Acknowledged")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_obligation_reminder`
Expected: FAIL — `DoesNotExistError: DocType Obligation Reminder not found`

- [ ] **Step 3: Create `__init__.py`**

```python
```

- [ ] **Step 4: Create `obligation_reminder.json`**

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "obligation",
  "scheduled_for",
  "recipient",
  "escalation_level",
  "column_break_1",
  "status",
  "is_overdue",
  "sb_lifecycle",
  "queued_at",
  "delivered_at",
  "column_break_2",
  "acknowledged_at",
  "acknowledged_by"
 ],
 "fields": [
  {
   "fieldname": "obligation",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Obligation",
   "options": "Legal Obligation",
   "reqd": 1
  },
  {
   "fieldname": "scheduled_for",
   "fieldtype": "Datetime",
   "in_list_view": 1,
   "label": "Scheduled For",
   "reqd": 1
  },
  {
   "fieldname": "recipient",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Recipient",
   "options": "User",
   "reqd": 1
  },
  {
   "default": "Owner",
   "fieldname": "escalation_level",
   "fieldtype": "Select",
   "label": "Escalation Level",
   "options": "Owner\nDeputy\nPartner"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "default": "Queued",
   "fieldname": "status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Status",
   "options": "Queued\nDelivered\nAcknowledged\nCompleted\nSuperseded"
  },
  {
   "default": "0",
   "description": "Set when this reminder is processed later than scheduled, e.g. after scheduler recovery.",
   "fieldname": "is_overdue",
   "fieldtype": "Check",
   "label": "Overdue"
  },
  {
   "fieldname": "sb_lifecycle",
   "fieldtype": "Section Break",
   "label": "Lifecycle"
  },
  {
   "fieldname": "queued_at",
   "fieldtype": "Datetime",
   "label": "Queued At",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "delivered_at",
   "fieldtype": "Datetime",
   "label": "Delivered At",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "column_break_2",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "acknowledged_at",
   "fieldtype": "Datetime",
   "label": "Acknowledged At",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "acknowledged_by",
   "fieldtype": "Link",
   "label": "Acknowledged By",
   "no_copy": 1,
   "options": "User",
   "read_only": 1
  }
 ],
 "is_submittable": 0,
 "links": [],
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Obligation Reminder",
 "naming_rule": "Random",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "All",
   "share": 1,
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "scheduled_for",
 "sort_order": "ASC",
 "states": []
}
```

- [ ] **Step 5: Create `obligation_reminder.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime, get_datetime


TRANSITIONS = {
	"Queued": {"Delivered", "Superseded"},
	"Delivered": {"Acknowledged", "Superseded"},
	"Acknowledged": {"Completed"},
	"Completed": set(),
	"Superseded": set(),
}

DEFAULT_ADVANCE_DAYS = [7, 1]


class ObligationReminder(Document):
	def validate(self):
		if self.is_new():
			self.status = self.status or "Queued"
			self.queued_at = self.queued_at or now_datetime()
			return

		previous_status = frappe.db.get_value("Obligation Reminder", self.name, "status")
		if previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(
					f"Cannot move Obligation Reminder from {previous_status} to {self.status}."
				)


def generate_default_reminders(obligation_name, method=None):
	if frappe.db.exists("Obligation Reminder", {"obligation": obligation_name}):
		return

	obligation = frappe.get_doc("Legal Obligation", obligation_name)
	if obligation.status != "Active":
		return

	due = get_datetime(obligation.due_date)
	for days_before in DEFAULT_ADVANCE_DAYS:
		scheduled_for = add_days(due, -days_before)
		frappe.get_doc({
			"doctype": "Obligation Reminder",
			"obligation": obligation.name,
			"scheduled_for": scheduled_for,
			"recipient": obligation.responsible_user,
			"escalation_level": "Owner",
		}).insert(ignore_permissions=True)


@frappe.whitelist()
def acknowledge(reminder):
	doc = frappe.get_doc("Obligation Reminder", reminder)
	if doc.status != "Delivered":
		frappe.throw("Only a Delivered reminder can be acknowledged.")
	doc.status = "Acknowledged"
	doc.acknowledged_at = now_datetime()
	doc.acknowledged_by = frappe.session.user
	doc.save(ignore_permissions=True)
	return doc.name
```

- [ ] **Step 6: Wire the `on_update` hook**

In `case_management/hooks.py`, find the existing `doc_events` dict (it already has entries for `Sales Invoice`, `Expense Claim`, `Payment Entry`, `Timesheet`, `Company`, `Customer`, `Matter`, `File`). Add a new entry for `Legal Obligation`:

```python
    "Legal Obligation": {
        "on_update": "case_management.case_management.doctype.obligation_reminder.obligation_reminder.generate_default_reminders"
    },
```

Place it as a new top-level key inside the `doc_events = { ... }` dict, alongside the existing entries (order doesn't matter, but keep it readable — e.g. add it right after the `"Matter": {...}` entry and before `"File": {...}`).

- [ ] **Step 7: Sync the new DocType into the site**

Run: `bench --site home.com --force reload-doc case_management doctype obligation_reminder`
Expected: Completes with no output/error; creates the `tabObligation Reminder` table and `DocType` record.

- [ ] **Step 8: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_obligation_reminder`
Expected: PASS (3/3)

- [ ] **Step 9: Commit**

```bash
git add case_management/case_management/doctype/obligation_reminder/ case_management/hooks.py
git commit -m "feat: add Obligation Reminder doctype with auto-generation on obligation activation"
```

---

### Task 3: Reschedule invalidates obsolete reminders and regenerates fresh ones

**Files:**
- Modify: `case_management/case_management/doctype/obligation_reminder/obligation_reminder.py:generate_default_reminders` (extend, don't replace)
- Test: `case_management/case_management/doctype/obligation_reminder/test_obligation_reminder_reschedule.py`

**Interfaces:**
- Consumes: `Legal Obligation.previous_due_date` (Task 1 — set only when a Verified/Active obligation's `due_date` actually changes), `Obligation Reminder.status`/`obligation` (Task 2).
- Produces: nothing new consumed by later tasks — this closes the reschedule-invalidation loop entirely within `generate_default_reminders`.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestObligationReminderReschedule(FrappeTestCase):
	def _make_active_obligation(self, due_date=None):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Reschedule Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Reschedule Test Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Reschedule Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Reschedule Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Reschedule Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Filing Deadline",
			"due_date": due_date or add_days(nowdate(), 14), "responsible_user": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		return obligation

	def test_rescheduling_supersedes_old_reminders_and_creates_new_ones(self):
		obligation = self._make_active_obligation()
		original_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, pluck="name"
		)
		for r in original_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(original_reminders), 2)

		old_due_date = obligation.due_date
		obligation.due_date = add_days(old_due_date, 10)
		obligation.reschedule_reason = "Hearing adjourned"
		obligation.save()

		for r in original_reminders:
			self.assertEqual(
				frappe.db.get_value("Obligation Reminder", r, "status"), "Superseded"
			)

		new_reminders = frappe.get_all(
			"Obligation Reminder",
			filters={"obligation": obligation.name, "status": "Queued"},
			pluck="name",
		)
		for r in new_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(new_reminders), 2)

	def test_rescheduling_does_not_supersede_already_delivered_reminders(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")

		obligation.due_date = add_days(obligation.due_date, 5)
		obligation.reschedule_reason = "Minor date shift"
		obligation.save()

		self.assertEqual(
			frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Delivered"
		)

		new_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name, "status": "Queued"}, pluck="name"
		)
		for r in new_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(new_reminders), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_obligation_reminder_reschedule`
Expected: FAIL — both tests fail; after reschedule, the original 2 reminders are still `Queued` (not `Superseded`), and no new reminders are created, because `generate_default_reminders` currently returns early (it only runs when no reminders exist at all for that obligation).

- [ ] **Step 3: Extend `generate_default_reminders` in `obligation_reminder.py`**

Replace the existing `generate_default_reminders` function body with:

```python
def generate_default_reminders(obligation_name, method=None):
	obligation = frappe.get_doc("Legal Obligation", obligation_name)
	if obligation.status != "Active":
		return

	existing_queued = frappe.get_all(
		"Obligation Reminder",
		filters={"obligation": obligation_name, "status": ["in", ["Queued"]]},
		pluck="name",
	)

	if obligation.previous_due_date and str(obligation.previous_due_date) != str(obligation.due_date):
		for reminder_name in existing_queued:
			frappe.db.set_value("Obligation Reminder", reminder_name, "status", "Superseded")
	elif frappe.db.exists("Obligation Reminder", {"obligation": obligation_name}):
		return

	due = get_datetime(obligation.due_date)
	for days_before in DEFAULT_ADVANCE_DAYS:
		scheduled_for = add_days(due, -days_before)
		frappe.get_doc({
			"doctype": "Obligation Reminder",
			"obligation": obligation.name,
			"scheduled_for": scheduled_for,
			"recipient": obligation.responsible_user,
			"escalation_level": "Owner",
		}).insert(ignore_permissions=True)
```

This keeps the Task 2 idempotency behavior (no duplicate reminders on an unrelated field edit — the `elif ... exists(...): return` branch) while adding the reschedule path: when `previous_due_date` is set and differs from the current `due_date` (meaning `Legal Obligation.validate()` just recorded a genuine reschedule), supersede only the still-`Queued` reminders (never touch `Delivered`/`Acknowledged`/`Completed` ones — those reflect real, already-happened events) and generate a fresh pair for the new date.

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_obligation_reminder_reschedule`
Expected: PASS (2/2)

- [ ] **Step 5: Run Task 2's test module too, to confirm the extension didn't break idempotency**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_obligation_reminder`
Expected: PASS (3/3, unchanged)

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/doctype/obligation_reminder/obligation_reminder.py case_management/case_management/doctype/obligation_reminder/test_obligation_reminder_reschedule.py
git commit -m "feat: supersede and regenerate reminders when an obligation is rescheduled"
```

---

### Task 4: Scheduled delivery of due reminders

**Files:**
- Modify: `case_management/case_management/doctype/obligation_reminder/obligation_reminder.py` (add `process_due_reminders`)
- Modify: `case_management/hooks.py` (add `scheduler_events`)
- Test: `case_management/case_management/doctype/obligation_reminder/test_scheduler_processing.py`

**Interfaces:**
- Consumes: `Obligation Reminder.status`/`scheduled_for` (Task 2).
- Produces: `process_due_reminders()` module function — Task 5's recovery logic calls this same function after detecting an outage, so it must be idempotent (never double-delivers a reminder already marked `Delivered`).

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime, nowdate


class TestSchedulerProcessing(FrappeTestCase):
	def _make_matter(self):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Scheduler Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Scheduler Test Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Scheduler Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Scheduler Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Scheduler Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter

	def _make_obligation_stub(self):
		matter = self._make_matter()
		obligation = frappe.get_doc({
			"doctype": "Legal Obligation",
			"matter": matter.name,
			"obligation_type": "Other",
			"due_date": nowdate(),
			"responsible_user": "Administrator",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)
		return obligation

	def _make_reminder(self, obligation_name, scheduled_for, status="Queued"):
		reminder = frappe.get_doc({
			"doctype": "Obligation Reminder",
			"obligation": obligation_name,
			"scheduled_for": scheduled_for,
			"recipient": "Administrator",
			"status": status,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Obligation Reminder", reminder.name, force=True)
		return reminder

	def test_process_due_reminders_delivers_only_due_queued_reminders(self):
		obligation = self._make_obligation_stub()
		due_reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), minutes=-10))
		future_reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), hours=2))

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
		process_due_reminders()

		self.assertEqual(frappe.db.get_value("Obligation Reminder", due_reminder.name, "status"), "Delivered")
		self.assertEqual(frappe.db.get_value("Obligation Reminder", future_reminder.name, "status"), "Queued")

	def test_process_due_reminders_does_not_redeliver_already_delivered(self):
		obligation = self._make_obligation_stub()
		reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), minutes=-10))
		frappe.db.set_value("Obligation Reminder", reminder.name, "status", "Delivered")
		frappe.db.set_value("Obligation Reminder", reminder.name, "delivered_at", add_to_date(now_datetime(), minutes=-5))
		original_delivered_at = frappe.db.get_value("Obligation Reminder", reminder.name, "delivered_at")

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
		process_due_reminders()

		self.assertEqual(
			str(frappe.db.get_value("Obligation Reminder", reminder.name, "delivered_at")),
			str(original_delivered_at),
		)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_scheduler_processing`
Expected: FAIL — `ImportError: cannot import name 'process_due_reminders'`

- [ ] **Step 3: Add `process_due_reminders` to `obligation_reminder.py`**

Add this function (alongside `generate_default_reminders` and `acknowledge`):

```python
@frappe.whitelist()
def process_due_reminders(mark_overdue_after_minutes=60):
	now = now_datetime()
	due = frappe.get_all(
		"Obligation Reminder",
		filters={"status": "Queued", "scheduled_for": ["<=", now]},
		fields=["name", "scheduled_for"],
	)
	for row in due:
		minutes_late = (now - get_datetime(row.scheduled_for)).total_seconds() / 60
		doc = frappe.get_doc("Obligation Reminder", row.name)
		doc.status = "Delivered"
		doc.delivered_at = now
		if minutes_late > mark_overdue_after_minutes:
			doc.is_overdue = 1
		doc.save(ignore_permissions=True)
	return len(due)
```

- [ ] **Step 4: Register the scheduled job in `hooks.py`**

Find the commented-out `scheduler_events` block in `hooks.py` (currently looks like:
```python
# scheduler_events = {
# 	"all": [
# 		"case_management.tasks.all"
# 	],
...
# }
```
). Replace the entire commented block with:

```python
scheduler_events = {
	"cron": {
		"*/10 * * * *": [
			"case_management.case_management.doctype.obligation_reminder.obligation_reminder.process_due_reminders"
		]
	}
}
```

(Runs every 10 minutes. This is the production-schedule registration — Task 5's outage-recovery logic calls `process_due_reminders` directly too, independent of this cron entry, so a missed cron tick still gets caught up.)

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.obligation_reminder.test_scheduler_processing`
Expected: PASS (2/2)

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/doctype/obligation_reminder/obligation_reminder.py case_management/hooks.py case_management/case_management/doctype/obligation_reminder/test_scheduler_processing.py
git commit -m "feat: process due reminders via a scheduled job, idempotent against redelivery"
```

---

### Task 5: Scheduler heartbeat and outage recovery

**Files:**
- Create: `case_management/case_management/doctype/scheduler_heartbeat/__init__.py`
- Create: `case_management/case_management/doctype/scheduler_heartbeat/scheduler_heartbeat.json`
- Create: `case_management/case_management/doctype/scheduler_heartbeat/scheduler_heartbeat.py`
- Modify: `case_management/hooks.py` (add a heartbeat-recording cron entry alongside `process_due_reminders`)
- Test: `case_management/case_management/doctype/scheduler_heartbeat/test_scheduler_heartbeat.py`

**Interfaces:**
- Consumes: `process_due_reminders` (Task 4) — called from the recovery path.
- Produces: `record_heartbeat()`, `check_for_outage(expected_interval_minutes=10, grace_minutes=20)` module functions in `scheduler_heartbeat.py`. Task 6's acceptance test calls `check_for_outage` directly to verify outage detection and recovery end to end.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime


class TestSchedulerHeartbeat(FrappeTestCase):
	def tearDown(self):
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat", None)
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_outage_detected", None)
		frappe.db.commit()

	def test_record_heartbeat_sets_timestamp(self):
		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import record_heartbeat
		record_heartbeat()
		stored = frappe.db.get_single_value("Scheduler Heartbeat", "last_heartbeat")
		self.assertIsNotNone(stored)

	def test_check_for_outage_detects_stale_heartbeat(self):
		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-45),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		outage_detected = check_for_outage(expected_interval_minutes=10, grace_minutes=20)
		self.assertTrue(outage_detected)
		self.assertIsNotNone(frappe.db.get_single_value("Scheduler Heartbeat", "last_outage_detected"))

	def test_check_for_outage_false_when_heartbeat_recent(self):
		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-5),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		outage_detected = check_for_outage(expected_interval_minutes=10, grace_minutes=20)
		self.assertFalse(outage_detected)

	def test_check_for_outage_processes_backlog_on_recovery(self):
		matter = frappe.db.get_value("Matter", {}, "name")
		if not matter:
			self.skipTest("No Matter fixture available")
		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter, "obligation_type": "Other",
			"due_date": frappe.utils.nowdate(), "responsible_user": "Administrator",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		overdue_reminder = frappe.get_doc({
			"doctype": "Obligation Reminder", "obligation": obligation.name,
			"scheduled_for": add_to_date(now_datetime(), hours=-2),
			"recipient": "Administrator",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Obligation Reminder", overdue_reminder.name, force=True)

		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-45),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		check_for_outage(expected_interval_minutes=10, grace_minutes=20)

		self.assertEqual(
			frappe.db.get_value("Obligation Reminder", overdue_reminder.name, "status"), "Delivered"
		)
		self.assertEqual(
			frappe.db.get_value("Obligation Reminder", overdue_reminder.name, "is_overdue"), 1
		)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.scheduler_heartbeat.test_scheduler_heartbeat`
Expected: FAIL — `DoesNotExistError: DocType Scheduler Heartbeat not found`

- [ ] **Step 3: Create `__init__.py`**

```python
```

- [ ] **Step 4: Create `scheduler_heartbeat.json`**

A Single doctype (one record total, Frappe's standard pattern for a settings/status singleton — see `issingle: 1`):

```json
{
 "actions": [],
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "last_heartbeat",
  "last_outage_detected"
 ],
 "fields": [
  {
   "fieldname": "last_heartbeat",
   "fieldtype": "Datetime",
   "label": "Last Heartbeat",
   "read_only": 1
  },
  {
   "fieldname": "last_outage_detected",
   "fieldtype": "Datetime",
   "label": "Last Outage Detected",
   "read_only": 1
  }
 ],
 "issingle": 1,
 "links": [],
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Scheduler Heartbeat",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "email": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 5: Create `scheduler_heartbeat.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, time_diff_in_seconds


class SchedulerHeartbeat(Document):
	pass


def record_heartbeat():
	frappe.db.set_single_value("Scheduler Heartbeat", "last_heartbeat", now_datetime())


def check_for_outage(expected_interval_minutes=10, grace_minutes=20):
	last_heartbeat = frappe.db.get_single_value("Scheduler Heartbeat", "last_heartbeat")
	if not last_heartbeat:
		return False

	allowed_gap_seconds = (expected_interval_minutes + grace_minutes) * 60
	gap_seconds = time_diff_in_seconds(now_datetime(), get_datetime(last_heartbeat))

	if gap_seconds <= allowed_gap_seconds:
		return False

	frappe.db.set_single_value("Scheduler Heartbeat", "last_outage_detected", now_datetime())

	from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
	process_due_reminders(mark_overdue_after_minutes=expected_interval_minutes)

	return True
```

- [ ] **Step 6: Wire both heartbeat-recording and outage-checking into `hooks.py`**

Extend the `scheduler_events` block added in Task 4 to also run the heartbeat and the outage check:

```python
scheduler_events = {
	"cron": {
		"*/10 * * * *": [
			"case_management.case_management.doctype.obligation_reminder.obligation_reminder.process_due_reminders",
			"case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat.record_heartbeat"
		],
		"*/30 * * * *": [
			"case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat.check_for_outage"
		]
	}
}
```

(The heartbeat is recorded on the same 10-minute cadence as reminder processing — if that cron stops firing, the heartbeat stops updating too, which is exactly the failure this is meant to catch. The outage check runs independently every 30 minutes so it keeps running even if the 10-minute job itself is the thing that died.)

- [ ] **Step 7: Sync the new DocType into the site**

Run: `bench --site home.com --force reload-doc case_management doctype scheduler_heartbeat`
Expected: Completes with no output/error; creates the `tabScheduler Heartbeat` table (a single row) and `DocType` record.

- [ ] **Step 8: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.scheduler_heartbeat.test_scheduler_heartbeat`
Expected: PASS (4/4)

- [ ] **Step 9: Commit**

```bash
git add case_management/case_management/doctype/scheduler_heartbeat/ case_management/hooks.py
git commit -m "feat: add scheduler heartbeat and outage recovery, catching up missed reminder processing"
```

---

### Task 6: M2 acceptance suite (spec scenario matrix, end to end)

**Files:**
- Create: `case_management/case_management/doctype/legal_obligation/test_m2_acceptance.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5.

This task has no "implementation" step — it only adds tests that exercise the full M2 acceptance list from the spec, using the real APIs built in Tasks 1-5 together.

- [ ] **Step 1: Write the acceptance tests**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, nowdate, now_datetime


class TestM2Acceptance(FrappeTestCase):
	def _make_active_obligation(self, due_date=None):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "M2 Acceptance Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "M2 Acceptance Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "M2 Acceptance Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "M2 Acceptance Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "M2 Acceptance Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Court Hearing",
			"due_date": due_date or add_days(nowdate(), 14), "responsible_user": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		return obligation

	def test_amended_date_preserves_old_date_and_supersedes_obsolete_reminders(self):
		obligation = self._make_active_obligation()
		original_due_date = obligation.due_date
		original_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, pluck="name"
		)
		for r in original_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		obligation.due_date = add_days(original_due_date, 21)
		obligation.reschedule_reason = "Court rescheduled the hearing"
		obligation.save()

		self.assertEqual(str(obligation.previous_due_date), str(original_due_date))
		for r in original_reminders:
			self.assertEqual(frappe.db.get_value("Obligation Reminder", r, "status"), "Superseded")

		new_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name, "status": "Queued"}, pluck="name"
		)
		for r in new_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(new_reminders), 2)

	def test_stopped_scheduler_is_detected_and_recovered_without_duplicating_delivered(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		overdue_reminder = reminders[0]
		frappe.db.set_value("Obligation Reminder", overdue_reminder, "scheduled_for", add_to_date(now_datetime(), hours=-3))

		already_delivered = reminders[1]
		frappe.db.set_value("Obligation Reminder", already_delivered, "status", "Delivered")
		frappe.db.set_value("Obligation Reminder", already_delivered, "delivered_at", add_to_date(now_datetime(), hours=-1))
		delivered_at_before_recovery = frappe.db.get_value("Obligation Reminder", already_delivered, "delivered_at")

		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-50),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		outage_detected = check_for_outage(expected_interval_minutes=10, grace_minutes=20)
		self.assertTrue(outage_detected)

		self.assertEqual(frappe.db.get_value("Obligation Reminder", overdue_reminder, "status"), "Delivered")
		self.assertEqual(frappe.db.get_value("Obligation Reminder", overdue_reminder, "is_overdue"), 1)

		self.assertEqual(
			str(frappe.db.get_value("Obligation Reminder", already_delivered, "delivered_at")),
			str(delivered_at_before_recovery),
		)

		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat", None)
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_outage_detected", None)
		frappe.db.commit()

	def test_completing_a_reminder_does_not_complete_the_obligation(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import acknowledge
		acknowledge(reminders[0])

		reminder_doc = frappe.get_doc("Obligation Reminder", reminders[0])
		reminder_doc.status = "Completed"
		reminder_doc.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Completed")
		self.assertEqual(frappe.db.get_value("Legal Obligation", obligation.name, "status"), "Active")
```

- [ ] **Step 2: Run the full M2 suite**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.legal_obligation.test_m2_acceptance`
Expected: PASS — if any of these fail, the gap is in Tasks 1-5, not in this test file; go back and fix the relevant task before continuing.

- [ ] **Step 3: Run every test file added across M1 and M2 together, to catch cross-plan interference**

Run: `bench --site home.com run-tests --skip-test-records --app case_management`
Expected: PASS (M1's 21 tests plus M2's new tests, all passing, no regressions)

- [ ] **Step 4: Commit**

```bash
git add case_management/case_management/doctype/legal_obligation/test_m2_acceptance.py
git commit -m "test: add M2 end-to-end acceptance suite (reschedule, scheduler outage recovery, reminder/obligation independence)"
```

---

## Known M2 Simplifications (intentional, not oversights)

- **Default reminder offsets are fixed (7 days, 1 day before due date), not firm-configurable.** The spec says "Create configurable advance reminders" — a firm-level configuration doctype for this is deferred; M2 ships one sensible default pair to prove the mechanism end to end.
- **No deputy/partner escalation on non-acknowledgement.** The spec calls for escalating to a deputy or partner if a reminder isn't acknowledged in time. `Obligation Reminder.escalation_level` exists as a field, but nothing yet automatically creates a follow-up reminder at the Deputy/Partner level when the Owner-level one goes unacknowledged — that's the natural next increment on top of this foundation, not included here.
- **Delivery is in-app state only, no actual notification channel wired.** `process_due_reminders` marks a reminder `Delivered` in the database; it does not send an email, push notification, or calendar sync. The spec's "queued, provider accepted, delivered where confirmed" language anticipates a real external provider — this plan proves the state machine and durability guarantees (no duplicate delivery, outage detection/recovery) without yet integrating one.
- **No external calendar sync.** The spec notes "An external calendar is a synchronized view; deleting its event cannot silently delete the legal obligation" — there's no calendar integration at all yet in M2, so this constraint is trivially satisfied (nothing to desync from) rather than actively enforced.
- **`Obligation Reminder` has no matter-level ethical-wall access control.** Unlike `Matter`, nothing here restricts who can read/acknowledge a reminder beyond the fixture's blanket `All`-role grant. If the parent `Matter` is `is_restricted`, its obligations/reminders are not currently covered by the same restriction — worth closing in a later pass, flagged here rather than silently assumed.
