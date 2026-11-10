# Purchase Requisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the LawERP home page's Expense-Claim stand-in with a real `Purchase Requisition` doctype — a pre-spend purchase request, submitted by a requester and approved or rejected by one named approver, optionally tied to a Matter under the same ethical wall as every other matter-linked doctype in this app.

**Architecture:** Two new doctypes (`Purchase Requisition`, submittable parent; `Purchase Requisition Item`, child table) following this app's established Fee Note/Legal Obligation shape: a plain `validate()` state machine (no Workflow doctype), `get_permission_query_conditions`/`has_permission` delegating to `matter.py`'s existing ethical-wall helpers, registered in `hooks.py` in the same task that creates the doctype. The home page's "Purchase Requisition" tile href is repointed from `/app/expense-claim` to `/app/purchase-requisition`.

**Tech Stack:** Frappe v15/v16, `FrappeTestCase`.

**Spec:** `docs/superpowers/specs/2026-10-26-purchase-requisition-design.md`

## Global Constraints

- `FrappeTestCase` against the real bench DB, no mocks, fixtures built via `.insert()` — this app's standing house rule.
- `autoname: "PR-.#####"` / `naming_rule: "Expression"` — mirrors `Fee Note`'s `"FN-.#####"` pattern. Do not use a `Naming Series` field; syncing that fixture is already broken on the v16 test bench.
- Known bug class this app has hit repeatedly: a `validate()` that lets a document reach a privileged state by returning early for `is_new()` before its gates run. `is_new()` is treated as an implicit transition from `Pending`, not a bypass.
- The self-certification bypass role pair is **exactly** `{"Managing Partner", "System Manager"}` — the same pair `legal_obligation.py` already uses (confirmed verbatim in that file), not the `"Directors"` role named in an earlier draft of the spec (no such role has any precedent in this codebase; the spec was corrected to `Managing Partner` before this plan was written).
- `approval_status` and `rejection_reason` must both be `allow_on_submit: 1` in the DocType JSON — `is_submittable: 1` locks every other field edit once `docstatus` reaches 1, but the approver's whole job (setting `approval_status`/`rejection_reason`) happens *after* the requester has already submitted. Missing this flag on either field silently blocks the approver from ever acting.
- Reuse, don't reinvent: `matter.py`'s `get_matter_access_condition(matter_column, user=None)` already treats a blank/null matter column as visible to everyone (confirmed in its own docstring and implementation) — the matter-optional case needs no special-casing in `get_permission_query_conditions`, just the same one-line delegation `fee_note.py`/`legal_obligation.py` already use.

## Review Focus

- A `Purchase Requisition` created directly with `approval_status` already `"Approved"`/`"Rejected"` (bypassing `is_new()`) must fail the same gates a normal transition would — the named bug class above, applied to this doctype's own gate.
- An approver trying to move `approval_status` away from `"Pending"` while `docstatus` is still `0` (the requisition was never submitted) must be blocked — "submit first, then approve" is a stated requirement, not a UI convention.
- Someone who is neither the named `approver` nor holding `Managing Partner`/`System Manager` attempting to move `approval_status` must be blocked, even if they otherwise have write access to the document.
- Setting `approval_status` to `"Rejected"` with no `rejection_reason` must be blocked, matching this app's established "a reason is required wherever something is declined" house style.
- A pure firm-overhead requisition (`matter` left blank) must remain visible under ordinary role-based `DocPerm` — the ethical wall must never accidentally hide a non-matter requisition from its own requester/approver, and a matter-linked restricted requisition must still be hidden from someone outside that matter's team.

---

### Task 1: `Purchase Requisition` / `Purchase Requisition Item` doctypes — schema and computed amounts

**Files:**
- Create: `case_management/case_management/doctype/purchase_requisition/purchase_requisition.json`
- Create: `case_management/case_management/doctype/purchase_requisition/purchase_requisition.py`
- Create: `case_management/case_management/doctype/purchase_requisition_item/purchase_requisition_item.json`
- Create: `case_management/case_management/doctype/purchase_requisition_item/purchase_requisition_item.py`
- Test: `case_management/case_management/doctype/purchase_requisition/test_purchase_requisition.py`

**Interfaces:**
- Produces: `Purchase Requisition` fields `employee`, `employee_name`, `department`, `company`, `matter`, `client`, `approver`, `approval_status` (`Pending`/`Approved`/`Rejected`, default `Pending`), `rejection_reason`, `items` (Table → `Purchase Requisition Item`), `total_estimated_amount`, `amended_from`. `Purchase Requisition Item` fields `item_description`, `qty`, `estimated_rate`, `estimated_amount`. Task 2 extends `PurchaseRequisition.validate()`; Task 3 adds module-level `get_permission_query_conditions`/`has_permission` to the same `purchase_requisition.py` file.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestPurchaseRequisition(FrappeTestCase):
	def _make_employee(self, label):
		return frappe.get_doc({
			"doctype": "Employee", "employee_name": label, "status": "Active",
		}).insert(ignore_mandatory=True)

	def test_total_estimated_amount_sums_item_lines(self):
		requester = self._make_employee("PR Test Requester")
		approver = self._make_employee("PR Test Approver")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)

		pr = frappe.get_doc({
			"doctype": "Purchase Requisition",
			"employee": requester.name,
			"approver": approver.name,
			"items": [
				{"item_description": "Laptop stand", "qty": 2, "estimated_rate": 50},
				{"item_description": "Monitor", "qty": 1, "estimated_rate": 300},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Purchase Requisition", pr.name, force=True)

		self.assertEqual(pr.items[0].estimated_amount, 100)
		self.assertEqual(pr.items[1].estimated_amount, 300)
		self.assertEqual(pr.total_estimated_amount, 400)

	def test_employee_and_matter_fetch_fields_populate(self):
		requester = self._make_employee("PR Fetch Requester")
		approver = self._make_employee("PR Fetch Approver")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)

		pr = frappe.get_doc({
			"doctype": "Purchase Requisition",
			"employee": requester.name,
			"approver": approver.name,
			"items": [{"item_description": "Filing fee", "qty": 1, "estimated_rate": 75}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Purchase Requisition", pr.name, force=True)

		self.assertEqual(pr.employee_name, requester.employee_name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.purchase_requisition.test_purchase_requisition`
Expected: FAIL — `Purchase Requisition` doctype does not exist yet.

- [ ] **Step 3: Create `purchase_requisition_item.json`**

A plain child table (`istable: 1`), module `Case Management`, fields:

```json
[
 {"fieldname": "item_description", "fieldtype": "Data", "label": "Item Description", "reqd": 1, "in_list_view": 1},
 {"fieldname": "qty", "fieldtype": "Float", "label": "Qty", "reqd": 1, "in_list_view": 1},
 {"fieldname": "estimated_rate", "fieldtype": "Currency", "label": "Estimated Rate", "reqd": 1, "in_list_view": 1},
 {"fieldname": "estimated_amount", "fieldtype": "Currency", "label": "Estimated Amount", "read_only": 1, "in_list_view": 1}
]
```

Follow this app's existing child-table JSON conventions (compare `fee_note_line.json`) for the surrounding boilerplate (`doctype`, `engine`, `istable`, `module`, `name`, `owner`, etc.) — don't guess the Frappe-version-specific boilerplate keys, copy them from `fee_note_line.json` and adjust.

- [ ] **Step 4: Create `purchase_requisition_item.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe.model.document import Document


class PurchaseRequisitionItem(Document):
	pass
```

- [ ] **Step 5: Create `purchase_requisition.json`**

`autoname: "PR-.#####"`, `naming_rule: "Expression"`, `is_submittable: 1`, module `Case Management`. Fields (section/column breaks are the builder's own choice — functionally inert):

```json
[
 {"fieldname": "employee", "fieldtype": "Link", "options": "Employee", "label": "Employee", "reqd": 1},
 {"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name", "read_only": 1, "fetch_from": "employee.employee_name", "fetch_if_empty": 1},
 {"fieldname": "department", "fieldtype": "Link", "options": "Department", "label": "Department", "read_only": 1, "fetch_from": "employee.department", "fetch_if_empty": 1},
 {"fieldname": "company", "fieldtype": "Link", "options": "Company", "label": "Company", "read_only": 1, "fetch_from": "employee.company", "fetch_if_empty": 1},
 {"fieldname": "matter", "fieldtype": "Link", "options": "Matter", "label": "Matter"},
 {"fieldname": "client", "fieldtype": "Link", "options": "Customer", "label": "Client", "read_only": 1, "fetch_from": "matter.client", "fetch_if_empty": 1, "depends_on": "matter"},
 {"fieldname": "approver", "fieldtype": "Link", "options": "Employee", "label": "Approver", "reqd": 1},
 {"fieldname": "approval_status", "fieldtype": "Select", "options": "Pending\nApproved\nRejected", "default": "Pending", "label": "Approval Status", "allow_on_submit": 1, "in_list_view": 1},
 {"fieldname": "rejection_reason", "fieldtype": "Small Text", "label": "Rejection Reason", "allow_on_submit": 1},
 {"fieldname": "items", "fieldtype": "Table", "options": "Purchase Requisition Item", "label": "Items", "reqd": 1},
 {"fieldname": "total_estimated_amount", "fieldtype": "Currency", "label": "Total Estimated Amount", "read_only": 1},
 {"fieldname": "amended_from", "fieldtype": "Link", "options": "Purchase Requisition", "label": "Amended From", "read_only": 1, "no_copy": 1, "print_hide": 1}
]
```

Copy most boilerplate (`engine`, `module`, field-object shape, etc.) from `fee_note.json`, but `fee_note.json` isn't itself submittable — for `is_submittable: 1`'s own companion keys (`autoname` alongside submittability, the standard submit/cancel permission columns, etc.), cross-check against `case_management/case_management/doctype/time_tracking/time_tracking.json`, the one existing submittable custom doctype already in this app.

- [ ] **Step 6: Implement `purchase_requisition.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PurchaseRequisition(Document):
	def validate(self):
		self._compute_amounts()

	def _compute_amounts(self):
		for row in self.items:
			row.estimated_amount = flt(row.qty) * flt(row.estimated_rate)
		self.total_estimated_amount = sum(flt(row.estimated_amount) for row in self.items)
```

(Task 2 extends this same `validate()` with the approval state machine; this task only wires the amount computation.)

- [ ] **Step 7: Sync and run the tests**

Run:
```bash
bench --site home.com --force reload-doc case_management doctype purchase_requisition_item
bench --site home.com --force reload-doc case_management doctype purchase_requisition
bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.purchase_requisition.test_purchase_requisition
```
Expected: PASS (2/2)

- [ ] **Step 8: Commit**

```bash
git add case_management/case_management/doctype/purchase_requisition_item/ case_management/case_management/doctype/purchase_requisition/
git commit -m "feat: add Purchase Requisition and Purchase Requisition Item doctypes"
```

---

### Task 2: Approval state machine — submit gate, named-approver gate, independence bypass, rejection reason

**Files:**
- Modify: `case_management/case_management/doctype/purchase_requisition/purchase_requisition.py`
- Test: `case_management/case_management/doctype/purchase_requisition/test_purchase_requisition.py` (same file as Task 1, new test methods)

**Interfaces:**
- Consumes: nothing new from elsewhere in the codebase — this task's logic is self-contained within `PurchaseRequisition.validate()`.
- Produces: the state machine itself. Task 3 does not depend on anything this task adds.

- [ ] **Step 1: Write the failing tests**

Append to `test_purchase_requisition.py`:

```python
	def _make_requisition(self, requester, approver, status="Pending"):
		pr = frappe.get_doc({
			"doctype": "Purchase Requisition",
			"employee": requester, "approver": approver,
			"items": [{"item_description": "Office chair", "qty": 1, "estimated_rate": 150}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Purchase Requisition", pr.name, force=True)
		return pr

	def test_cannot_create_directly_into_approved_status(self):
		requester = self._make_employee("PR State Requester 1")
		approver = self._make_employee("PR State Approver 1")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Purchase Requisition",
				"employee": requester.name, "approver": approver.name,
				"approval_status": "Approved",
				"items": [{"item_description": "Office chair", "qty": 1, "estimated_rate": 150}],
			}).insert()

	def test_cannot_approve_before_submit(self):
		requester = self._make_employee("PR State Requester 2")
		approver = self._make_employee("PR State Approver 2")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)
		pr = self._make_requisition(requester.name, approver.name)

		pr.approval_status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			pr.save()

	def test_only_named_approver_or_privileged_role_can_approve(self):
		requester = self._make_employee("PR State Requester 3")
		approver = self._make_employee("PR State Approver 3")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)
		pr = self._make_requisition(requester.name, approver.name)
		pr.submit()

		approver_user = frappe.new_doc("User")
		approver_user.email = "pr-state-approver-3@example.com"
		approver_user.first_name = "PR State Approver 3"
		approver_user.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", approver_user.name, force=True)
		frappe.db.set_value("Employee", approver.name, "user_id", approver_user.name)

		pr.reload()
		pr.approval_status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			pr.save()

		frappe.set_user(approver_user.name)
		try:
			pr.save()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(pr.approval_status, "Approved")

	def test_requester_cannot_approve_own_requisition_without_privileged_role(self):
		requester = self._make_employee("PR State Requester 4")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		with self.assertRaises(frappe.ValidationError):
			self._make_requisition(requester.name, requester.name)

	def test_rejecting_without_a_reason_is_blocked(self):
		requester = self._make_employee("PR State Requester 5")
		approver = self._make_employee("PR State Approver 5")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)
		pr = self._make_requisition(requester.name, approver.name)
		pr.submit()

		pr.approval_status = "Rejected"
		with self.assertRaises(frappe.ValidationError):
			pr.save()

		pr.rejection_reason = "Budget exceeded for this quarter."
		pr.save()
		self.assertEqual(pr.approval_status, "Rejected")

	def test_approval_status_cannot_change_once_decided(self):
		requester = self._make_employee("PR State Requester 6")
		approver = self._make_employee("PR State Approver 6")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)
		pr = self._make_requisition(requester.name, approver.name)
		pr.submit()
		pr.approval_status = "Approved"
		pr.save()

		pr.approval_status = "Rejected"
		pr.rejection_reason = "Changed my mind."
		with self.assertRaises(frappe.ValidationError):
			pr.save()
```

Note: `test_only_named_approver_or_privileged_role_can_approve` and the `insert()` calls in `_make_requisition` run as `Administrator`, who holds `System Manager` — confirm during implementation whether this already satisfies the privileged-bypass path for every test that *doesn't* specifically mean to test the named-approver-only path (most of these tests approve/reject as Administrator deliberately, relying on the `System Manager` bypass; only `test_only_named_approver_or_privileged_role_can_approve` exercises the non-privileged path explicitly, by creating a real non-privileged `User` and switching to it with `frappe.set_user`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.purchase_requisition.test_purchase_requisition`
Expected: FAIL — no state-machine gates exist yet.

- [ ] **Step 3: Extend `PurchaseRequisition.validate()`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt

PRIVILEGED_ROLES = {"Managing Partner", "System Manager"}


class PurchaseRequisition(Document):
	def validate(self):
		self._compute_amounts()
		self._validate_independence()
		self._validate_approval_transition()

	def _compute_amounts(self):
		for row in self.items:
			row.estimated_amount = flt(row.qty) * flt(row.estimated_rate)
		self.total_estimated_amount = sum(flt(row.estimated_amount) for row in self.items)

	def _validate_independence(self):
		if self.employee and self.approver and self.employee == self.approver:
			if not (PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user))):
				frappe.throw(
					"The requester cannot also be the approver on the same requisition, "
					"unless you hold the Managing Partner or System Manager role."
				)

	def _validate_approval_transition(self):
		previous_approval_status = "Pending" if self.is_new() else frappe.db.get_value(
			"Purchase Requisition", self.name, "approval_status"
		)

		if previous_approval_status == self.approval_status:
			return

		if previous_approval_status in ("Approved", "Rejected"):
			frappe.throw(
				f"Purchase Requisition is already {previous_approval_status} and cannot be changed."
			)

		if self.docstatus != 1:
			frappe.throw(
				"A Purchase Requisition must be submitted before it can be approved or rejected."
			)

		if self.approval_status not in ("Approved", "Rejected"):
			frappe.throw(
				f"Cannot move Purchase Requisition from {previous_approval_status} to {self.approval_status}."
			)

		approver_user = frappe.db.get_value("Employee", self.approver, "user_id")
		if frappe.session.user != approver_user:
			if not (PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user))):
				frappe.throw(
					"Only the named Approver (or a Managing Partner/System Manager) "
					"can approve or reject this requisition."
				)

		if self.approval_status == "Rejected" and not self.rejection_reason:
			frappe.throw(
				"Rejecting a Purchase Requisition requires a reason in 'Rejection Reason'."
			)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.purchase_requisition.test_purchase_requisition`
Expected: PASS (8/8, all tests across Task 1 and Task 2)

- [ ] **Step 5: Commit**

```bash
git add case_management/case_management/doctype/purchase_requisition/
git commit -m "feat: add Purchase Requisition approval state machine"
```

---

### Task 3: Ethical wall — `permission_query_conditions` / `has_permission`

**Files:**
- Modify: `case_management/case_management/doctype/purchase_requisition/purchase_requisition.py`
- Modify: `case_management/hooks.py`
- Test: `case_management/case_management/doctype/purchase_requisition/test_purchase_requisition.py` (same file, new test methods)

**Interfaces:**
- Consumes: `matter.py`'s `get_matter_access_condition(matter_column, user=None)` and `has_permission(doc, user=None, permission_type=None)` (both already exist, confirmed in `matter.py`).

- [ ] **Step 1: Write the failing tests**

Append to `test_purchase_requisition.py`:

```python
	def test_non_matter_requisition_has_no_ethical_wall_restriction(self):
		requester = self._make_employee("PR Wall Requester 1")
		approver = self._make_employee("PR Wall Approver 1")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)
		pr = self._make_requisition(requester.name, approver.name)

		self.assertTrue(frappe.has_permission("Purchase Requisition", doc=pr, ptype="read"))

	def test_restricted_matter_requisition_is_hidden_from_an_outsider(self):
		# Matter requires a real, Approved Intake (confirmed in test_matter_access.py's
		# own _make_approved_intake) -- a bare Matter.insert() with no intake fails.
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "PR Wall Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)
		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "General advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		review = frappe.get_doc({
			"doctype": "Conflict Review", "intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": frappe.utils.now_datetime(), "searched_by": "Administrator",
			"decision": "Clear",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "PR Wall Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		requester = self._make_employee("PR Wall Requester 2")
		approver = self._make_employee("PR Wall Approver 2")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "PR Wall Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)
		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": frappe.utils.nowdate(), "practice_area": practice_area.name,
			"transaction": "PR Wall Transaction", "responsible_solicitor": requester.name,
			"is_restricted": 1,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		pr = frappe.get_doc({
			"doctype": "Purchase Requisition",
			"employee": requester.name, "approver": approver.name, "matter": matter.name,
			"items": [{"item_description": "Expert witness fee", "qty": 1, "estimated_rate": 500}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Purchase Requisition", pr.name, force=True)

		outsider = frappe.new_doc("User")
		outsider.email = "pr-wall-outsider@example.com"
		outsider.first_name = "PR Wall Outsider"
		outsider.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", outsider.name, force=True)

		self.assertFalse(frappe.has_permission("Purchase Requisition", doc=pr, ptype="read", user=outsider.name))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.purchase_requisition.test_purchase_requisition`
Expected: FAIL — no permission hooks registered yet, so both tests see default (unrestricted) DocPerm behavior.

- [ ] **Step 3: Add the permission functions to `purchase_requisition.py`**

```python
def get_permission_query_conditions(user=None):
	from case_management.case_management.doctype.matter.matter import get_matter_access_condition
	return get_matter_access_condition("`tabPurchase Requisition`.matter", user)


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	if not doc.matter:
		return True
	from case_management.case_management.doctype.matter.matter import has_permission as matter_has_permission
	matter_doc = frappe.get_cached_doc("Matter", doc.matter)
	return matter_has_permission(matter_doc, user=user, permission_type=permission_type)
```

- [ ] **Step 4: Register both hooks in `hooks.py`**

Add one entry to each of the existing top-level `permission_query_conditions` and `has_permission` dicts (both already exist in `hooks.py`, alongside `Fee Note`'s and `Legal Obligation`'s own entries — add to those dicts, don't create new ones):

```python
"Purchase Requisition": "case_management.case_management.doctype.purchase_requisition.purchase_requisition.get_permission_query_conditions",
```
and
```python
"Purchase Requisition": "case_management.case_management.doctype.purchase_requisition.purchase_requisition.has_permission",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.purchase_requisition.test_purchase_requisition`
Expected: PASS (10/10, all tests across Tasks 1-3)

- [ ] **Step 6: Run the existing Matter/Fee Note/Legal Obligation test suites to confirm no regression**

Run: `bench --site home.com run-tests --app case_management --module case_management.case_management.doctype.matter.test_matter_access` (and any other existing ethical-wall test files already in this app)
Expected: PASS, unchanged

- [ ] **Step 7: Commit**

```bash
git add case_management/case_management/doctype/purchase_requisition/ case_management/hooks.py
git commit -m "feat: wire Purchase Requisition into the ethical wall"
```

---

### Task 4: Point the home page tile at the new doctype

**Files:**
- Modify: `case_management/fixtures/custom_html_block.json`

**Interfaces:**
- Consumes: nothing — this is a one-line href change inside the single HTML Block fixture's inline markup. No test needed; the change is a static asset edit, not executable logic.

- [ ] **Step 1: Repoint the href**

Find the single `<a class="lawerp-tile" href="/app/expense-claim">...<span class="lawerp-label">Purchase Requisition</span></a>` anchor inside `custom_html_block.json`'s inline `html` string, and change `href="/app/expense-claim"` to `href="/app/purchase-requisition"` on that one anchor only — every other tile's href (`/app/fee-note`, `/app/time-tracking`, etc.) stays untouched. Leave the SVG icon and label exactly as they are.

- [ ] **Step 2: Sync the fixture**

Run: `bench --site home.com --force reload-doc case_management custom_html_block LawERP-Home-Tiles` (confirm the exact fixture doc name from the file itself — it's the `"name"` key at the top level of `custom_html_block.json` — before running this; it may not literally be `LawERP-Home-Tiles`).

- [ ] **Step 3: Manually verify in the browser**

Load the LawERP home page, confirm the "Purchase Requisition" tile now opens `/app/purchase-requisition` (the new doctype's list view) instead of the Expense Claim list.

- [ ] **Step 4: Commit**

```bash
git add case_management/fixtures/custom_html_block.json
git commit -m "fix: point the Purchase Requisition tile at the real doctype"
```
