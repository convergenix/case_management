# LawERP R0 Foundation — M1 (Canonical Parties, Intake Gate, Matter State Machine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `case_management` a real intake/conflict gate and an enforced Matter state machine with ethical-wall access control, so a Matter can no longer be opened informally and its lifecycle is auditable.

**Architecture:** Three new parent doctypes (`Legal Party`, `Intake`, `Conflict Review`) plus their child tables, wired together by a stable party-set hash that detects staleness. `Matter` is reworked to require an Approved, non-stale Intake before it can be created, to enforce a fixed set of status transitions (with a reason+role gate for reopening), and to log every transition. Matter-level confidentiality is enforced via Frappe's `permission_query_conditions` + `has_permission` hooks rather than new infrastructure.

**Tech Stack:** Frappe v15 (`frappe.model.document.Document`, standard DocType JSON), MariaDB/InnoDB, Python 3, `FrappeTestCase` for tests.

**Spec:** `docs/superpowers/specs/2026-10-19-lawerp-r0-foundation-design.md` (M1 section) — this plan implements that spec's M1 data model, state machine, and access-control sections. Executors should read the spec's M1 section alongside this plan.

## Global Constraints

- All new doctypes live in the existing `Case Management` module, directory `case_management/case_management/doctype/<name>/`, matching the current app's layout (no new module).
- Frappe version in this bench is 15.99.0 — use the current (not legacy) DocType JSON schema: include `actions`, `field_order`, `links`, `naming_rule`, `states`, `row_format`, `sort_field`, `sort_order` keys as seen in `time_tracking.json`. Child tables use `"istable": 1` and an empty `"permissions": []` (they inherit the parent's permissions), matching `matter_team_item.json`.
- Tests use `FrappeTestCase` (`from frappe.tests.utils import FrappeTestCase`) against the real bench DB on site `home.com`. No mocks, no raw SQL inserts in tests — build fixtures through `frappe.get_doc({...}).insert()`. Assert on returned document values / DB state, never on which internal method fired.
- Run tests with: `bench --site home.com run-tests --module case_management.case_management.doctype.<doctype_folder>.test_<doctype_file>`
- After creating or modifying any DocType JSON file, the site's schema must be synced with `bench --site home.com migrate` before a test that uses that DocType will pass — the JSON file alone does not create the DB table or `tabDocType` row. Each task below has an explicit migrate step at the point it's needed; don't skip it even if a step looks redundant.
- No new Python dependencies — everything here uses the standard library (`hashlib`) and `frappe`/`frappe.utils` already in use elsewhere in this app.
- Money/financial-conservation work (Fee Note, billing) is explicitly out of scope for M1 — that's M3, a separate future plan.

---

### Task 1: Legal Party (canonical parties) and Legal Party Relation

**Files:**
- Create: `case_management/case_management/doctype/legal_party/__init__.py`
- Create: `case_management/case_management/doctype/legal_party/legal_party.json`
- Create: `case_management/case_management/doctype/legal_party/legal_party.py`
- Create: `case_management/case_management/doctype/legal_party/test_legal_party.py`
- Create: `case_management/case_management/doctype/legal_party_relation/__init__.py`
- Create: `case_management/case_management/doctype/legal_party_relation/legal_party_relation.json`
- Create: `case_management/case_management/doctype/legal_party_relation/legal_party_relation.py`

**Interfaces:**
- Produces: `case_management.case_management.doctype.legal_party.legal_party.normalize_name(value: str) -> str`, used internally by `Legal Party.before_save` to populate the `normalized_name` field.
- Produces: `Legal Party` doctype with fields `party_name`, `party_type`, `normalized_name`, `identifier`, `linked_contact`, `linked_customer`, `aliases`, `related_parties` (child table), `effective_from`, `effective_to`. Tasks 2 and 3 consume the stored `normalized_name`/`identifier` field values, not the `normalize_name()` function directly.

- [ ] **Step 1: Create the doctype directory and `__init__.py` files**

```bash
mkdir -p case_management/case_management/doctype/legal_party
mkdir -p case_management/case_management/doctype/legal_party_relation
touch case_management/case_management/doctype/legal_party/__init__.py
touch case_management/case_management/doctype/legal_party_relation/__init__.py
```

- [ ] **Step 2: Write `legal_party_relation.json` (child table)**

```json
{
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "related_party",
  "relationship_type"
 ],
 "fields": [
  {
   "fieldname": "related_party",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Related Party",
   "options": "Legal Party",
   "reqd": 1
  },
  {
   "fieldname": "relationship_type",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Relationship Type",
   "options": "Affiliate\nParent Company\nSubsidiary\nAssociated Company\nOther",
   "reqd": 1
  }
 ],
 "istable": 1,
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Legal Party Relation",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

- [ ] **Step 3: Write `legal_party_relation.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class LegalPartyRelation(Document):
	pass
```

- [ ] **Step 4: Write `legal_party.json` (parent doctype)**

```json
{
 "actions": [],
 "autoname": "LP-.#####",
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "party_name",
  "party_type",
  "identifier",
  "column_break_identity",
  "normalized_name",
  "linked_contact",
  "linked_customer",
  "section_break_aliases",
  "aliases",
  "section_break_related",
  "related_parties",
  "section_break_effective",
  "effective_from",
  "effective_to"
 ],
 "fields": [
  {
   "fieldname": "party_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Party Name",
   "reqd": 1
  },
  {
   "default": "Organization",
   "fieldname": "party_type",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Party Type",
   "options": "Person\nOrganization",
   "reqd": 1
  },
  {
   "fieldname": "identifier",
   "fieldtype": "Data",
   "label": "Identifier (Reg. No. / BVN / Other Stable ID)"
  },
  {
   "fieldname": "column_break_identity",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "normalized_name",
   "fieldtype": "Data",
   "label": "Normalized Name",
   "read_only": 1
  },
  {
   "fieldname": "linked_contact",
   "fieldtype": "Link",
   "label": "Linked Contact",
   "options": "Contact"
  },
  {
   "description": "Set only when this party becomes a billing client. A prospect or adverse party must not be linked here automatically.",
   "fieldname": "linked_customer",
   "fieldtype": "Link",
   "label": "Linked Customer",
   "options": "Customer"
  },
  {
   "fieldname": "section_break_aliases",
   "fieldtype": "Section Break",
   "label": "Aliases"
  },
  {
   "description": "One alias per line. Used for exact/normalized-name conflict matching.",
   "fieldname": "aliases",
   "fieldtype": "Small Text",
   "label": "Known Aliases"
  },
  {
   "fieldname": "section_break_related",
   "fieldtype": "Section Break",
   "label": "Related Parties"
  },
  {
   "fieldname": "related_parties",
   "fieldtype": "Table",
   "label": "Related Parties",
   "options": "Legal Party Relation"
  },
  {
   "fieldname": "section_break_effective",
   "fieldtype": "Section Break",
   "label": "Effective Dates"
  },
  {
   "fieldname": "effective_from",
   "fieldtype": "Date",
   "label": "Effective From"
  },
  {
   "fieldname": "effective_to",
   "fieldtype": "Date",
   "label": "Effective To"
  }
 ],
 "is_submittable": 0,
 "links": [],
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Legal Party",
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

- [ ] **Step 5: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestLegalParty(FrappeTestCase):
	def test_normalized_name_is_computed_on_save(self):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "  Acme   Holdings, LLC ",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)

		self.assertEqual(party.normalized_name, "acme holdings llc")

	def test_linked_customer_is_not_auto_populated(self):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "Jane Doe",
			"party_type": "Person",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)

		self.assertFalse(party.linked_customer)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.legal_party.test_legal_party`
Expected: FAIL — DocType "Legal Party" not found (JSON not yet picked up) or `normalized_name` not computed (empty string vs expected value).

- [ ] **Step 7: Write `legal_party.py` (minimal implementation)**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re
import frappe
from frappe.model.document import Document


def normalize_name(value):
	"""Lowercase, strip, collapse whitespace, drop punctuation — used for
	exact/normalized-name conflict matching in Intake and Conflict Review."""
	if not value:
		return ""
	value = value.lower()
	value = re.sub(r"[^\w\s]", "", value)
	value = re.sub(r"\s+", " ", value).strip()
	return value


class LegalParty(Document):
	def before_save(self):
		self.normalized_name = normalize_name(self.party_name)
```

- [ ] **Step 8: Sync the new DocTypes into the site**

Run: `bench --site home.com migrate`
Expected: Completes without error; creates the `tabLegal Party` and `tabLegal Party Relation` tables and `DocType` records.

- [ ] **Step 9: Run test to verify it passes**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.legal_party.test_legal_party`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add case_management/case_management/doctype/legal_party case_management/case_management/doctype/legal_party_relation
git commit -m "feat: add Legal Party canonical identity doctype"
```

---

### Task 2: Intake (staged pre-matter form with party set and conflict gate)

**Files:**
- Create: `case_management/case_management/doctype/intake_party/__init__.py`
- Create: `case_management/case_management/doctype/intake_party/intake_party.json`
- Create: `case_management/case_management/doctype/intake_party/intake_party.py`
- Create: `case_management/case_management/doctype/intake_evidence/__init__.py`
- Create: `case_management/case_management/doctype/intake_evidence/intake_evidence.json`
- Create: `case_management/case_management/doctype/intake_evidence/intake_evidence.py`
- Create: `case_management/case_management/doctype/intake/__init__.py`
- Create: `case_management/case_management/doctype/intake/intake.json`
- Create: `case_management/case_management/doctype/intake/intake.py`
- Create: `case_management/case_management/doctype/intake/test_intake.py`

**Interfaces:**
- Consumes: `Legal Party` doctype (Task 1).
- Produces: `Intake` doctype with fields `proposed_client`, `practice_area`, `scope`, `status`, `requested_by`, `requested_on`, `parties` (child), `evidence` (child), `decision_reason`, `converted_matter`.
- Produces: `Intake.get_party_set_hash() -> str` (instance method) — used by `Conflict Review` (Task 3) and `Matter` (Task 4) to detect a stale clearance.

- [ ] **Step 1: Create directories**

```bash
mkdir -p case_management/case_management/doctype/intake_party
mkdir -p case_management/case_management/doctype/intake_evidence
mkdir -p case_management/case_management/doctype/intake
touch case_management/case_management/doctype/intake_party/__init__.py
touch case_management/case_management/doctype/intake_evidence/__init__.py
touch case_management/case_management/doctype/intake/__init__.py
```

- [ ] **Step 2: Write `intake_party.json`**

```json
{
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "legal_party",
  "role"
 ],
 "fields": [
  {
   "fieldname": "legal_party",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Legal Party",
   "options": "Legal Party",
   "reqd": 1
  },
  {
   "fieldname": "role",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Role",
   "options": "Proposed Client\nAdverse Party\nAffiliate\nOther",
   "reqd": 1
  }
 ],
 "istable": 1,
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Intake Party",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

- [ ] **Step 3: Write `intake_party.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class IntakeParty(Document):
	pass
```

- [ ] **Step 4: Write `intake_evidence.json`**

```json
{
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "description",
  "attachment"
 ],
 "fields": [
  {
   "fieldname": "description",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Description"
  },
  {
   "fieldname": "attachment",
   "fieldtype": "Attach",
   "in_list_view": 1,
   "label": "Attachment",
   "reqd": 1
  }
 ],
 "istable": 1,
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Intake Evidence",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

- [ ] **Step 5: Write `intake_evidence.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class IntakeEvidence(Document):
	pass
```

- [ ] **Step 6: Write `intake.json`**

```json
{
 "actions": [],
 "autoname": "INTK-.#####",
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "proposed_client",
  "practice_area",
  "status",
  "column_break_header",
  "requested_by",
  "requested_on",
  "converted_matter",
  "section_break_scope",
  "scope",
  "section_break_parties",
  "parties",
  "section_break_evidence",
  "evidence",
  "section_break_decision",
  "decision_reason"
 ],
 "fields": [
  {
   "fieldname": "proposed_client",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Proposed Client",
   "options": "Legal Party",
   "reqd": 1
  },
  {
   "fieldname": "practice_area",
   "fieldtype": "Link",
   "label": "Practice Area",
   "options": "Practice Area"
  },
  {
   "default": "Draft",
   "fieldname": "status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Status",
   "options": "Draft\nUnder Review\nApproved\nDeclined\nWithdrawn\nConverted",
   "read_only": 1
  },
  {
   "fieldname": "column_break_header",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "requested_by",
   "fieldtype": "Link",
   "label": "Requested By",
   "options": "User",
   "read_only": 1
  },
  {
   "fieldname": "requested_on",
   "fieldtype": "Datetime",
   "label": "Requested On",
   "read_only": 1
  },
  {
   "fieldname": "converted_matter",
   "fieldtype": "Link",
   "label": "Converted Matter",
   "no_copy": 1,
   "options": "Matter",
   "read_only": 1
  },
  {
   "fieldname": "section_break_scope",
   "fieldtype": "Section Break",
   "label": "Scope"
  },
  {
   "fieldname": "scope",
   "fieldtype": "Small Text",
   "label": "Scope of Engagement",
   "reqd": 1
  },
  {
   "fieldname": "section_break_parties",
   "fieldtype": "Section Break",
   "label": "Party Set"
  },
  {
   "fieldname": "parties",
   "fieldtype": "Table",
   "label": "Parties",
   "options": "Intake Party",
   "reqd": 1
  },
  {
   "fieldname": "section_break_evidence",
   "fieldtype": "Section Break",
   "label": "Evidence"
  },
  {
   "fieldname": "evidence",
   "fieldtype": "Table",
   "label": "Evidence",
   "options": "Intake Evidence"
  },
  {
   "fieldname": "section_break_decision",
   "fieldtype": "Section Break",
   "label": "Decision"
  },
  {
   "fieldname": "decision_reason",
   "fieldtype": "Small Text",
   "label": "Decision Reason"
  }
 ],
 "is_submittable": 0,
 "links": [],
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Intake",
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

- [ ] **Step 7: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestIntake(FrappeTestCase):
	def _make_party(self, name):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def test_requires_a_proposed_client_party_row(self):
		client = self._make_party("Test Client Co")

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [
				{"legal_party": client.name, "role": "Affiliate"},
			],
		})
		with self.assertRaises(frappe.ValidationError):
			intake.insert()

	def test_party_set_hash_is_stable_for_same_parties(self):
		client = self._make_party("Hash Test Client")
		adverse = self._make_party("Hash Test Adversary")

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Litigation",
			"parties": [
				{"legal_party": client.name, "role": "Proposed Client"},
				{"legal_party": adverse.name, "role": "Adverse Party"},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		first_hash = intake.get_party_set_hash()
		reloaded = frappe.get_doc("Intake", intake.name)
		self.assertEqual(first_hash, reloaded.get_party_set_hash())

	def test_cannot_approve_without_clear_conflict_review(self):
		client = self._make_party("Gate Test Client")

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [
				{"legal_party": client.name, "role": "Proposed Client"},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			intake.save()
```

- [ ] **Step 8: Run test to verify it fails**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.intake.test_intake`
Expected: FAIL — DocType "Intake" not found, or `AttributeError: get_party_set_hash`.

- [ ] **Step 9: Write `intake.py` (implementation)**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

TRANSITIONS = {
	"Draft": {"Under Review", "Withdrawn"},
	"Under Review": {"Approved", "Declined", "Withdrawn"},
	"Approved": {"Converted", "Under Review"},
	"Declined": set(),
	"Withdrawn": set(),
	"Converted": set(),
}


class Intake(Document):
	def validate(self):
		previous_status = None
		if not self.is_new():
			previous_status = frappe.db.get_value("Intake", self.name, "status")

		if not self.requested_by:
			self.requested_by = frappe.session.user
		if not self.requested_on:
			self.requested_on = now_datetime()

		if not any(row.role == "Proposed Client" for row in self.parties):
			frappe.throw("Intake must include exactly one party with role 'Proposed Client'.")

		if previous_status and previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(f"Cannot move Intake from {previous_status} to {self.status}.")

		if previous_status == "Approved" and self.status == "Approved" and self.has_value_changed("parties"):
			self.status = "Under Review"
			frappe.msgprint(
				"Party set changed after approval — Intake reverted to Under Review for re-review."
			)

		if self.status == "Approved":
			self._validate_conflict_clearance()

	def get_party_set_hash(self):
		pairs = sorted((row.legal_party, row.role) for row in self.parties)
		raw = "|".join(f"{party}:{role}" for party, role in pairs)
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()

	def _validate_conflict_clearance(self):
		reviews = frappe.get_all(
			"Conflict Review",
			filters={"intake": self.name, "decision": ["in", ["Clear", "Waiver Granted"]]},
			fields=["name", "party_set_hash"],
			order_by="search_timestamp desc",
			limit=1,
		)
		if not reviews:
			frappe.throw(
				"Intake cannot be Approved without a Conflict Review decided Clear or Waiver Granted."
			)
		if reviews[0].party_set_hash != self.get_party_set_hash():
			frappe.throw(
				"The Conflict Review on file is stale — the party set has changed since it ran. "
				"Run a new conflict search before approving."
			)
```

- [ ] **Step 10: Sync the new DocTypes into the site**

Run: `bench --site home.com migrate`
Expected: Completes without error; creates the `tabIntake`, `tabIntake Party`, and `tabIntake Evidence` tables and `DocType` records.

- [ ] **Step 11: Run test to verify it passes**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.intake.test_intake`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add case_management/case_management/doctype/intake_party case_management/case_management/doctype/intake_evidence case_management/case_management/doctype/intake
git commit -m "feat: add Intake doctype with party-set hash and conflict-clearance gate"
```

---

### Task 3: Conflict Review (search record, decision, restricted-match visibility)

**Files:**
- Create: `case_management/case_management/doctype/conflict_match/__init__.py`
- Create: `case_management/case_management/doctype/conflict_match/conflict_match.json`
- Create: `case_management/case_management/doctype/conflict_match/conflict_match.py`
- Create: `case_management/case_management/doctype/conflict_review/__init__.py`
- Create: `case_management/case_management/doctype/conflict_review/conflict_review.json`
- Create: `case_management/case_management/doctype/conflict_review/conflict_review.py`
- Create: `case_management/case_management/doctype/conflict_review/test_conflict_review.py`

**Interfaces:**
- Consumes: `Intake.get_party_set_hash()` (Task 2); `Legal Party.normalized_name`/`identifier` stored field values (Task 1, populated by `normalize_name()` — not called directly here).
- Produces: `case_management.case_management.doctype.conflict_review.conflict_review.run_conflict_search(intake: str) -> str` (whitelisted, returns new Conflict Review name).
- Produces: `case_management.case_management.doctype.conflict_review.conflict_review.has_permission(doc, user=None, permission_type=None) -> bool` — registered in `hooks.py` by Task 5.

- [ ] **Step 1: Create directories**

```bash
mkdir -p case_management/case_management/doctype/conflict_match
mkdir -p case_management/case_management/doctype/conflict_review
touch case_management/case_management/doctype/conflict_match/__init__.py
touch case_management/case_management/doctype/conflict_review/__init__.py
```

- [ ] **Step 2: Write `conflict_match.json`**

```json
{
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "legal_party",
  "match_type",
  "notes"
 ],
 "fields": [
  {
   "fieldname": "legal_party",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Legal Party",
   "options": "Legal Party",
   "reqd": 1
  },
  {
   "fieldname": "match_type",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Match Type",
   "options": "Exact Identifier\nNormalized Name",
   "reqd": 1
  },
  {
   "fieldname": "notes",
   "fieldtype": "Data",
   "label": "Notes"
  }
 ],
 "istable": 1,
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Conflict Match",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

- [ ] **Step 3: Write `conflict_match.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class ConflictMatch(Document):
	pass
```

- [ ] **Step 4: Write `conflict_review.json`**

```json
{
 "actions": [],
 "autoname": "CR-.#####",
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "document_type": "Document",
 "engine": "InnoDB",
 "field_order": [
  "intake",
  "party_set_hash",
  "column_break_header",
  "search_timestamp",
  "searched_by",
  "total_records_searched",
  "section_break_matches",
  "matches",
  "section_break_decision",
  "decision",
  "decision_reason",
  "waiver_evidence",
  "column_break_decision",
  "reviewed_by",
  "reviewed_on"
 ],
 "fields": [
  {
   "fieldname": "intake",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Intake",
   "options": "Intake",
   "reqd": 1
  },
  {
   "fieldname": "party_set_hash",
   "fieldtype": "Data",
   "label": "Party Set Hash (at time of search)",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "column_break_header",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "search_timestamp",
   "fieldtype": "Datetime",
   "label": "Search Timestamp",
   "read_only": 1,
   "reqd": 1
  },
  {
   "fieldname": "searched_by",
   "fieldtype": "Link",
   "label": "Searched By",
   "options": "User",
   "read_only": 1,
   "reqd": 1
  },
  {
   "description": "Count of Legal Party records included in this search — stands in for a corpus/index version until a dedicated search index exists.",
   "fieldname": "total_records_searched",
   "fieldtype": "Int",
   "label": "Total Records Searched",
   "read_only": 1
  },
  {
   "fieldname": "section_break_matches",
   "fieldtype": "Section Break",
   "label": "Candidate Matches"
  },
  {
   "fieldname": "matches",
   "fieldtype": "Table",
   "label": "Matches",
   "options": "Conflict Match"
  },
  {
   "fieldname": "section_break_decision",
   "fieldtype": "Section Break",
   "label": "Decision"
  },
  {
   "fieldname": "decision",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Decision",
   "options": "\nClear\nRestricted Match - Escalated\nWaiver Granted\nDeclined"
  },
  {
   "fieldname": "decision_reason",
   "fieldtype": "Small Text",
   "label": "Decision Reason"
  },
  {
   "fieldname": "waiver_evidence",
   "fieldtype": "Attach",
   "label": "Waiver Evidence"
  },
  {
   "fieldname": "column_break_decision",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "reviewed_by",
   "fieldtype": "Link",
   "label": "Reviewed By",
   "options": "User",
   "read_only": 1
  },
  {
   "fieldname": "reviewed_on",
   "fieldtype": "Datetime",
   "label": "Reviewed On",
   "read_only": 1
  }
 ],
 "is_submittable": 0,
 "links": [],
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Conflict Review",
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

- [ ] **Step 5: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from case_management.case_management.doctype.conflict_review.conflict_review import (
	run_conflict_search,
	has_permission,
)


class TestConflictReview(FrappeTestCase):
	def _make_party(self, name, identifier=None):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
			"identifier": identifier,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def _make_intake(self, client, adverse):
		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Litigation",
			"parties": [
				{"legal_party": client.name, "role": "Proposed Client"},
				{"legal_party": adverse.name, "role": "Adverse Party"},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		return intake

	def test_run_conflict_search_finds_exact_identifier_match(self):
		existing = self._make_party("Already Known Co", identifier="RC-1001")
		client = self._make_party("New Client Co")
		adverse_duplicate = self._make_party("Totally Different Name", identifier="RC-1001")
		intake = self._make_intake(client, adverse_duplicate)

		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)

		review = frappe.get_doc("Conflict Review", review_name)
		self.assertEqual(review.intake, intake.name)
		self.assertEqual(review.party_set_hash, intake.get_party_set_hash())
		matched_names = [row.legal_party for row in review.matches]
		self.assertIn(existing.name, matched_names)

	def test_restricted_match_hidden_from_ordinary_requester(self):
		client = self._make_party("Restricted Test Client")
		adverse = self._make_party("Restricted Test Adversary")
		intake = self._make_intake(client, adverse)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": frappe.utils.now_datetime(),
			"searched_by": "Administrator",
			"decision": "Restricted Match - Escalated",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		self.assertFalse(has_permission(review, user="test_ordinary_requester@example.com"))
		self.assertTrue(has_permission(review, user="Administrator"))
```

- [ ] **Step 6: Run test to verify it fails**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.conflict_review.test_conflict_review`
Expected: FAIL — `ImportError: cannot import name 'run_conflict_search'`.

- [ ] **Step 7: Write `conflict_review.py` (implementation)**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

PRIVILEGED_ROLES = {"System Manager", "Managing Partner", "Conflicts Reviewer"}


class ConflictReview(Document):
	def validate(self):
		if self.decision and not self.reviewed_by:
			self.reviewed_by = frappe.session.user
			self.reviewed_on = now_datetime()


@frappe.whitelist()
def run_conflict_search(intake):
	intake_doc = frappe.get_doc("Intake", intake)

	review = frappe.new_doc("Conflict Review")
	review.intake = intake_doc.name
	review.party_set_hash = intake_doc.get_party_set_hash()
	review.search_timestamp = now_datetime()
	review.searched_by = frappe.session.user
	review.total_records_searched = frappe.db.count("Legal Party")

	all_parties = frappe.get_all(
		"Legal Party",
		fields=["name", "identifier", "normalized_name"],
	)
	already_matched = set()
	for intake_party in intake_doc.parties:
		this_party = frappe.get_doc("Legal Party", intake_party.legal_party)
		for other in all_parties:
			if other.name == this_party.name or other.name in already_matched:
				continue
			match_type = None
			if this_party.identifier and other.identifier and this_party.identifier == other.identifier:
				match_type = "Exact Identifier"
			elif this_party.normalized_name and other.normalized_name == this_party.normalized_name:
				match_type = "Normalized Name"
			if match_type:
				review.append("matches", {
					"legal_party": other.name,
					"match_type": match_type,
				})
				already_matched.add(other.name)

	review.insert()
	return review.name


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	if PRIVILEGED_ROLES & set(frappe.get_roles(user)):
		return True
	if doc.decision == "Restricted Match - Escalated" and doc.searched_by != user:
		return False
	return True
```

- [ ] **Step 8: Sync the new DocTypes into the site**

Run: `bench --site home.com migrate`
Expected: Completes without error; creates the `tabConflict Review` and `tabConflict Match` tables and `DocType` records.

- [ ] **Step 9: Run test to verify it passes**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.conflict_review.test_conflict_review`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add case_management/case_management/doctype/conflict_match case_management/case_management/doctype/conflict_review
git commit -m "feat: add Conflict Review doctype with search and restricted-match visibility"
```

---

### Task 4: Matter rework — state machine, intake gate, state log

**Files:**
- Create: `case_management/case_management/doctype/matter_state_log/__init__.py`
- Create: `case_management/case_management/doctype/matter_state_log/matter_state_log.json`
- Create: `case_management/case_management/doctype/matter_state_log/matter_state_log.py`
- Modify: `case_management/case_management/doctype/matter/matter.json`
- Modify: `case_management/case_management/doctype/matter/matter.py`
- Create: `case_management/case_management/doctype/matter/test_matter_lifecycle.py` (new file — the existing `test_matter.py` stays untouched, see Step 9)

**Interfaces:**
- Consumes: `Intake` (Task 2), `Conflict Review` (Task 3).
- Produces: `case_management.case_management.doctype.matter.matter.get_permission_query_conditions(user=None) -> str` and `has_permission(doc, user=None, permission_type=None) -> bool` — registered in `hooks.py` by Task 5.

- [ ] **Step 1: Create `Matter State Log` child doctype directory**

```bash
mkdir -p case_management/case_management/doctype/matter_state_log
touch case_management/case_management/doctype/matter_state_log/__init__.py
```

- [ ] **Step 2: Write `matter_state_log.json`**

```json
{
 "creation": "2026-10-19 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "previous_state",
  "new_state",
  "changed_by",
  "changed_at",
  "reason"
 ],
 "fields": [
  {
   "fieldname": "previous_state",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Previous State",
   "read_only": 1
  },
  {
   "fieldname": "new_state",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "New State",
   "read_only": 1
  },
  {
   "fieldname": "changed_by",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Changed By",
   "options": "User",
   "read_only": 1
  },
  {
   "fieldname": "changed_at",
   "fieldtype": "Datetime",
   "in_list_view": 1,
   "label": "Changed At",
   "read_only": 1
  },
  {
   "fieldname": "reason",
   "fieldtype": "Data",
   "label": "Reason",
   "read_only": 1
  }
 ],
 "istable": 1,
 "modified": "2026-10-19 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Case Management",
 "name": "Matter State Log",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

- [ ] **Step 3: Write `matter_state_log.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class MatterStateLog(Document):
	pass
```

- [ ] **Step 4: Modify `matter.json`** — replace the `status` field's `options`, and add the new lifecycle fields. In the `fields` array, replace the existing `status` field object:

```json
  {
   "default": "Open",
   "fieldname": "status",
   "fieldtype": "Select",
   "label": "Status",
   "options": "Open\nActive\nOn Hold\nClosing\nClosed\nArchived"
  },
```

Then add these field objects to the `fields` array (placed anywhere in the array — ordering is controlled by `field_order` below):

```json
  {
   "fieldname": "sb_lifecycle",
   "fieldtype": "Section Break",
   "label": "Lifecycle"
  },
  {
   "description": "The approved Intake this Matter was opened from. Required for new matters; cannot be changed after opening.",
   "fieldname": "intake",
   "fieldtype": "Link",
   "label": "Intake",
   "options": "Intake",
   "read_only_depends_on": "eval:!doc.__islocal",
   "reqd": 1
  },
  {
   "default": "None",
   "fieldname": "waiting_on",
   "fieldtype": "Select",
   "label": "Waiting On",
   "options": "None\nClient\nCourt\nCounterparty"
  },
  {
   "fieldname": "column_break_lifecycle",
   "fieldtype": "Column Break"
  },
  {
   "description": "Required only when moving a Closed/Archived matter back to Open/Active.",
   "fieldname": "reopen_reason",
   "fieldtype": "Small Text",
   "label": "Reopen Reason",
   "no_copy": 1
  },
  {
   "default": "0",
   "fieldname": "is_restricted",
   "fieldtype": "Check",
   "label": "Restricted (Ethical Wall)"
  },
  {
   "fieldname": "sb_state_log",
   "fieldtype": "Section Break",
   "label": "State History"
  },
  {
   "fieldname": "state_log",
   "fieldtype": "Table",
   "label": "State History",
   "options": "Matter State Log",
   "read_only": 1
  },
```

Update `field_order` to the following (inserts the lifecycle section after `transaction` and the state-log section after `invoice`):

```json
 "field_order": [
  "sb1",
  "original_matter_id",
  "status",
  "naming_series",
  "client",
  "ref_no",
  "column_break_5",
  "open_date",
  "close_date",
  "practice_area",
  "transaction",
  "sb_lifecycle",
  "intake",
  "waiting_on",
  "is_restricted",
  "column_break_lifecycle",
  "reopen_reason",
  "responsible_solicitor",
  "solicitor_name",
  "team",
  "legal_team",
  "matter_information",
  "sb2",
  "custom_field",
  "get_custom_field",
  "check_list",
  "sb4",
  "activities",
  "expense_section",
  "expense",
  "sb5",
  "invoice",
  "sb_state_log",
  "state_log",
  "section_break_26",
  "amended_from",
  "cost_center",
  "company"
 ],
```

- [ ] **Step 5: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime


class TestMatterLifecycle(FrappeTestCase):
	def _make_party(self, name):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def _make_customer(self, label):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": f"{label} Customer",
			"customer_type": "Company",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		return customer

	def _make_approved_intake(self, label):
		client = self._make_party(f"{label} Client")
		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": now_datetime(),
			"searched_by": "Administrator",
			"decision": "Clear",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		return intake

	def test_matter_cannot_be_opened_without_intake(self):
		customer = self._make_customer("No Intake")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"status": "Open",
		})
		with self.assertRaises(frappe.ValidationError):
			matter.insert()

	def test_matter_opens_from_approved_intake_and_marks_it_converted(self):
		intake = self._make_approved_intake("Open Flow")
		customer = self._make_customer("Open Flow")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		reloaded_intake = frappe.get_doc("Intake", intake.name)
		self.assertEqual(reloaded_intake.status, "Converted")
		self.assertEqual(reloaded_intake.converted_matter, matter.name)
		self.assertEqual(len(matter.state_log), 1)
		self.assertEqual(matter.state_log[0].new_state, "Open")

	def test_same_intake_cannot_open_a_second_matter(self):
		intake = self._make_approved_intake("Double Conversion")
		customer = self._make_customer("Double Conversion")
		first = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", first.name, force=True)

		second = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		})
		with self.assertRaises(frappe.ValidationError):
			second.insert()

	def test_invalid_status_transition_is_rejected(self):
		intake = self._make_approved_intake("Bad Transition")
		customer = self._make_customer("Bad Transition")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		matter.status = "Closed"
		with self.assertRaises(frappe.ValidationError):
			matter.save()

	def test_reopen_requires_reason(self):
		intake = self._make_approved_intake("Reopen Flow")
		customer = self._make_customer("Reopen Flow")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		matter.status = "Active"
		matter.save()
		matter.status = "Closing"
		matter.save()
		matter.status = "Closed"
		matter.save()

		matter.status = "Active"
		with self.assertRaises(frappe.ValidationError):
			matter.save()

		matter.reload()
		matter.status = "Active"
		matter.reopen_reason = "Client reinstated the engagement."
		matter.save()
		self.assertEqual(matter.status, "Active")
```

- [ ] **Step 6: Run test to verify it fails**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.matter.test_matter_lifecycle`
Expected: FAIL — Matter can currently be inserted without an `intake` value (no gate yet), and `state_log`/`intake`/`reopen_reason` fields don't exist yet.

- [ ] **Step 7: Modify `matter.py`** — add the gate, transition enforcement, and permission functions. Insert the following near the top of the file (after the existing imports) and replace/extend the `Matter` class as shown; leave all the existing module-level functions (`create_new_folder`, `get_events`, `get_lawyer`, `make_invoice`, etc.) exactly as they are, below this block:

```python
TRANSITIONS = {
    "Open": {"Active", "On Hold", "Closing"},
    "Active": {"On Hold", "Closing"},
    "On Hold": {"Active", "Closing"},
    "Closing": {"Closed", "Active"},
    "Closed": set(),
    "Archived": set(),
}

REOPEN_ROLES = {"Partner", "Managing Partner", "System Manager"}


class Matter(Document):
    def validate(self):
        if self.is_new():
            self._validate_intake_gate()
        else:
            self._enforce_state_transition()

    def _validate_intake_gate(self):
        if not self.intake:
            frappe.throw("A Matter cannot be opened without an approved Intake.")
        intake = frappe.get_doc("Intake", self.intake)
        if intake.status != "Approved":
            frappe.throw(f"Intake {intake.name} is not Approved (current status: {intake.status}).")
        if intake.converted_matter:
            frappe.throw(f"Intake {intake.name} has already been converted to Matter {intake.converted_matter}.")
        reviews = frappe.get_all(
            "Conflict Review",
            filters={"intake": intake.name, "decision": ["in", ["Clear", "Waiver Granted"]]},
            fields=["party_set_hash"],
            order_by="search_timestamp desc",
            limit=1,
        )
        if not reviews or reviews[0].party_set_hash != intake.get_party_set_hash():
            frappe.throw(
                "Conflict clearance for this Intake is missing or stale. "
                "Re-run the conflict search before opening the matter."
            )

    def _enforce_state_transition(self):
        previous_status = frappe.db.get_value("Matter", self.name, "status")
        if previous_status == self.status:
            return

        allowed = TRANSITIONS.get(previous_status, set())
        reopening = previous_status in ("Closed", "Archived") and self.status in ("Open", "Active")

        if self.status not in allowed and not reopening:
            frappe.throw(f"Invalid Matter status transition: {previous_status} -> {self.status}.")

        if reopening:
            if not self.reopen_reason:
                frappe.throw("Reopening a Closed/Archived matter requires a reason in 'Reopen Reason'.")
            if not REOPEN_ROLES & set(frappe.get_roles(frappe.session.user)):
                frappe.throw("You are not authorized to reopen this matter.")

        self.append("state_log", {
            "previous_state": previous_status,
            "new_state": self.status,
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": self.reopen_reason if reopening else "",
        })

        if reopening:
            self.reopen_reason = None

    def after_insert(self):
        frappe.get_doc({
            "doctype": "Matter State Log",
            "parent": self.name,
            "parenttype": "Matter",
            "parentfield": "state_log",
            "previous_state": "",
            "new_state": self.status,
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": "Matter opened",
        }).insert(ignore_permissions=True)

        frappe.db.set_value("Intake", self.intake, {
            "status": "Converted",
            "converted_matter": self.name,
        })

    def before_submit(self):
        previous_status = frappe.db.get_value("Matter", self.name, "status")
        self.status = "Closed"
        self.close_date = frappe.utils.nowdate()
        self.append("state_log", {
            "previous_state": previous_status,
            "new_state": "Closed",
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": "Matter closed via submit",
        })

    def on_trash(self):
        file = frappe.db.sql("select name from `tabFile` where file_name = \"Home/Clients/{0}\"".format(self.name))
        if len(file) > 0:
            frappe.throw("Sorry, Matter cannot be deleted. Case files exist for matter.")

    def autoname(self):
        if self.original_matter_id is not None:
            self.name = str(self.original_matter_id).replace('"', '')
        self.name = self.name

    def get_custom_field(self):
        if self.custom_field:
            data = frappe.db.sql(
                """select title from `tabMatter Custom Check List Item` where parent="{}" """
                    .format(self.custom_field), as_list=1)
            self.check_list = []
            for row in data:
                dt = self.append('check_list', {})
                dt.title = row[0]
        else:
            frappe.throw("""Please select a Custom Field Preset. """)


def get_permission_query_conditions(user=None):
    if not user:
        user = frappe.session.user
    if {"System Manager", "Managing Partner"} & set(frappe.get_roles(user)):
        return ""
    return """(`tabMatter`.is_restricted = 0 or `tabMatter`.name in (
        select mti.parent from `tabMatter Team Item` mti
        inner join `tabEmployee` emp on emp.name = mti.employee
        where emp.user_id = {user}
    ))""".format(user=frappe.db.escape(user))


def has_permission(doc, user=None, permission_type=None):
    if not user:
        user = frappe.session.user
    if not doc.is_restricted:
        return True
    if {"System Manager", "Managing Partner"} & set(frappe.get_roles(user)):
        return True
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return False
    return bool(frappe.db.exists("Matter Team Item", {"parent": doc.name, "employee": employee}))
```

Note: this replaces the original `class Matter(Document): def before_submit(self): ...` block (the original had `before_submit`, `on_trash`, `autoname`, `get_custom_field` only) with the expanded version above, which keeps all four original methods and adds `validate`, `_validate_intake_gate`, `_enforce_state_transition`, `after_insert`, plus the two module-level permission functions. The original `before_submit` set `self.status = "Close"` (not a valid value in either the old or new options list) — the replacement uses `"Closed"`, consistent with the new state machine.

- [ ] **Step 8: Sync the new/changed DocTypes into the site**

Run: `bench --site home.com migrate`
Expected: Completes without error; creates the `tabMatter State Log` table and `DocType` record, and applies the new/changed columns (`intake`, `waiting_on`, `is_restricted`, `reopen_reason`, `status` options) to the existing `tabMatter` table.

- [ ] **Step 9: Run test to verify it passes**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.matter.test_matter_lifecycle`
Expected: PASS

- [ ] **Step 10: Confirm the pre-existing `test_matter.py` still passes (it's an empty `pass`-only test, included for completeness, not modified by this plan)**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.matter.test_matter`
Expected: PASS (no-op test, unaffected)

- [ ] **Step 11: Commit**

```bash
git add case_management/case_management/doctype/matter_state_log case_management/case_management/doctype/matter/matter.json case_management/case_management/doctype/matter/matter.py case_management/case_management/doctype/matter/test_matter_lifecycle.py
git commit -m "feat: enforce Matter state machine, intake gate, and ethical-wall access control"
```

---

### Task 5: Wire access-control hooks and Conflicts Reviewer role

**Files:**
- Modify: `case_management/case_management/hooks.py`
- Modify: `case_management/fixtures/role.json`
- Create: `case_management/case_management/doctype/matter/test_matter_access.py`

**Interfaces:**
- Consumes: `get_permission_query_conditions`/`has_permission` from `matter.py` (Task 4), `has_permission` from `conflict_review.py` (Task 3).

- [ ] **Step 1: Add the `Conflicts Reviewer` role to the fixture**

Open `case_management/fixtures/role.json` and append this object to the JSON array (match the existing entries' shape, e.g. the `"Managing Partner"` entry):

```json
 {
  "desk_access": 1,
  "disabled": 0,
  "docstatus": 0,
  "doctype": "Role",
  "home_page": null,
  "is_custom": 0,
  "modified": "2026-10-19 00:00:00.000000",
  "name": "Conflicts Reviewer",
  "restrict_to_domain": null,
  "role_name": "Conflicts Reviewer",
  "two_factor_auth": 0
 }
```

- [ ] **Step 2: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime


class TestMatterAccessControl(FrappeTestCase):
	def setUp(self):
		if not frappe.db.exists("Role", "Conflicts Reviewer"):
			frappe.get_doc({"doctype": "Role", "role_name": "Conflicts Reviewer"}).insert(
				ignore_permissions=True
			)

	def _make_approved_intake(self, label):
		client = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": f"{label} Client",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": now_datetime(),
			"searched_by": "Administrator",
			"decision": "Clear",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		return intake

	def _make_customer(self, label):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": f"{label} Customer",
			"customer_type": "Company",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		return customer

	def test_restricted_matter_excluded_from_list_for_unrelated_user(self):
		# Matter's base role permissions only grant read to "Lawyer Manager" and
		# "Partners" (no "All"), so this user is given the "Partners" role —
		# otherwise they'd have zero baseline access to any Matter and the test
		# would pass for the wrong reason (no role permission at all, rather than
		# the is_restricted ethical-wall check this test is meant to isolate).
		outsider = "test_outsider_user@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc({
				"doctype": "User",
				"email": outsider,
				"first_name": "Outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Partners"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", outsider, force=True)

		intake = self._make_approved_intake("Restricted List")
		customer = self._make_customer("Restricted List")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"is_restricted": 1,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		names = frappe.get_list("Matter", filters={"name": matter.name}, user=outsider, pluck="name")
		self.assertNotIn(matter.name, names)

		from case_management.case_management.doctype.matter.matter import has_permission
		self.assertFalse(has_permission(matter, user=outsider))
		self.assertTrue(has_permission(matter, user="Administrator"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.matter.test_matter_access`
Expected: FAIL — the restricted matter is still visible to `outsider` because the hooks aren't registered yet (Frappe only calls `permission_query_conditions`/`has_permission` for a doctype if it's wired in `hooks.py`).

- [ ] **Step 4: Register the hooks in `hooks.py`**

Find the commented-out example block:

```python
# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }
```

Replace it with:

```python
permission_query_conditions = {
	"Matter": "case_management.case_management.doctype.matter.matter.get_permission_query_conditions",
}

has_permission = {
	"Matter": "case_management.case_management.doctype.matter.matter.has_permission",
	"Conflict Review": "case_management.case_management.doctype.conflict_review.conflict_review.has_permission",
}
```

Also add `"Role"` is already in the `fixtures` list (`fixtures = ["Custom Field", "Role", "Translation", "Folder", "Folder Structure", "Naming Series"]`) — no change needed there, the new `Conflicts Reviewer` role will export via the existing fixture on next `bench export-fixtures`.

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.matter.test_matter_access`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add case_management/fixtures/role.json case_management/case_management/hooks.py case_management/case_management/doctype/matter/test_matter_access.py
git commit -m "feat: wire Matter/Conflict Review permission hooks and add Conflicts Reviewer role"
```

---

### Task 6: M1 acceptance suite (spec scenario matrix, end to end)

**Files:**
- Create: `case_management/case_management/doctype/matter/test_m1_acceptance.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5.

This task has no "implementation" step — it only adds tests that exercise the full M1 acceptance list from the spec, using the real APIs built in Tasks 1-5 together. All of these should already pass given the work in Tasks 1-5; this task proves the pieces compose correctly as whole journeys, not just in isolation.

- [ ] **Step 1: Write the acceptance tests**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime
from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search


class TestM1Acceptance(FrappeTestCase):
	def _make_party(self, name, identifier=None):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
			"identifier": identifier,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def _make_customer(self, label):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": f"{label} Customer",
			"customer_type": "Company",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		return customer

	def test_stale_clearance_blocks_matter_opening_after_party_set_change(self):
		client = self._make_party("Stale Flow Client")
		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		self.assertEqual(intake.status, "Approved")

		new_adverse = self._make_party("Newly Added Adversary")
		intake.append("parties", {"legal_party": new_adverse.name, "role": "Adverse Party"})
		intake.save()
		self.assertEqual(intake.status, "Under Review")

		customer = self._make_customer("Stale Flow")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		})
		with self.assertRaises(frappe.ValidationError):
			matter.insert()

	def test_direct_insert_cannot_bypass_intake_gate(self):
		customer = self._make_customer("Bypass Attempt")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"status": "Open",
		})
		with self.assertRaises(frappe.ValidationError):
			matter.insert(ignore_permissions=True)

	def test_restricted_conflict_match_does_not_leak_to_requester(self):
		existing = self._make_party("Confidential Existing Party", identifier="RC-9999")
		client = self._make_party("Discloser Client")
		adverse = self._make_party("Disclosure Test Adversary", identifier="RC-9999")

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Litigation",
			"parties": [
				{"legal_party": client.name, "role": "Proposed Client"},
				{"legal_party": adverse.name, "role": "Adverse Party"},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		self.assertTrue(any(row.legal_party == existing.name for row in review.matches))

		review.decision = "Restricted Match - Escalated"
		review.save()

		from case_management.case_management.doctype.conflict_review.conflict_review import has_permission
		self.assertFalse(has_permission(review, user="test_requester_no_access@example.com"))
```

- [ ] **Step 2: Run the full M1 suite**

Run: `bench --site home.com run-tests --module case_management.case_management.doctype.matter.test_m1_acceptance`
Expected: PASS — if any of these fail, the gap is in Tasks 1-5, not in this test file; go back and fix the relevant task before continuing.

- [ ] **Step 3: Run every test file added in this plan together, to catch cross-task interference**

Run: `bench --site home.com run-tests --app case_management`
Expected: PASS (existing tests unaffected; all new M1 tests pass)

- [ ] **Step 4: Commit**

```bash
git add case_management/case_management/doctype/matter/test_m1_acceptance.py
git commit -m "test: add M1 end-to-end acceptance suite (stale clearance, bypass attempts, restricted disclosure)"
```

---

## Known M1 Simplifications (intentional, not oversights)

- **No fuzzy/explainable name matching.** `run_conflict_search` only matches on exact identifier or exact normalized name. The spec allows this for M1 ("Fuzzy matches are review candidates, never automatic clearance") — fuzzy matching is deferred to a later spec.
- **No emergency/bypass intake route.** The spec allows firms to configure one; M1 has none — every Matter requires an Approved, non-stale Intake with no exceptions. Safer default for a first build.
- **Existing `Matter.status` values are not migrated.** Any pre-existing Matter records with old status strings (`"Pending Document"`, `"Filed"`, etc.) will not match the new 6-value enum. This bench's dev site (`home.com`) has no production matter data, so no migration patch is included here — write one before this branch is proposed for a site with real data.
- **`is_restricted` is a manual flag, not automatic.** Nothing currently sets it based on matter sensitivity; a partner/admin must check it. Automatic classification is out of scope for M1.
- **Reminder/obligation work (M2) and billing (M3) are untouched** — this plan covers M1 only, per the spec's sequencing.
