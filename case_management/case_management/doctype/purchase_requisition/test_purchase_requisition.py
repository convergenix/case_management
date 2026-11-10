# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestPurchaseRequisition(FrappeTestCase):
	def _make_employee(self, label):
		return frappe.get_doc({
			"doctype": "Employee", "employee_name": label, "status": "Active",
		}).insert(ignore_mandatory=True)

	def _make_matter(self, label):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

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
		company = frappe.db.get_value("Company", {}, "name")

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": frappe.utils.nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee, "company": company,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter

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

	def test_supplied_fetch_field_values_are_overridden_by_the_real_source(self):
		requester = self._make_employee("PR Override Requester")
		approver = self._make_employee("PR Override Approver")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)

		real_company = frappe.db.get_value("Company", {}, "name")
		requester.company = real_company
		requester.save(ignore_permissions=True)

		matter = self._make_matter("PR Override")

		pr = frappe.get_doc({
			"doctype": "Purchase Requisition",
			"employee": requester.name,
			"approver": approver.name,
			"matter": matter.name,
			"company": "Bogus Company That Should Not Stick",
			"client": "Bogus Client That Should Not Stick",
			"items": [{"item_description": "Pens", "qty": 1, "estimated_rate": 10}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Purchase Requisition", pr.name, force=True)

		self.assertEqual(pr.company, real_company)
		self.assertEqual(pr.client, matter.client)

	def _make_requisition(self, requester, approver, status="Pending"):
		pr = frappe.get_doc({
			"doctype": "Purchase Requisition",
			"employee": requester, "approver": approver,
			"items": [{"item_description": "Office chair", "qty": 1, "estimated_rate": 150}],
		}).insert()

		def _cleanup():
			# Several of these tests submit the requisition; delete_doc refuses
			# a submitted record regardless of force=True, so drop docstatus
			# back to Draft directly before deleting.
			frappe.db.set_value("Purchase Requisition", pr.name, "docstatus", 0)
			frappe.delete_doc("Purchase Requisition", pr.name, force=True)

		self.addCleanup(_cleanup)
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

		# A bystander with neither the named-approver identity nor a privileged
		# role: Administrator (the default test session) holds System Manager
		# via frappe.get_roles' "Administrator gets every role" special case,
		# so it would silently pass the gate this block means to test.
		outsider_user = frappe.new_doc("User")
		outsider_user.email = "pr-state-outsider-3@example.com"
		outsider_user.first_name = "PR State Outsider 3"
		outsider_user.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", outsider_user.name, force=True)

		pr.reload()
		pr.approval_status = "Approved"
		frappe.set_user(outsider_user.name)
		try:
			with self.assertRaises(frappe.ValidationError):
				pr.save()
		finally:
			frappe.set_user("Administrator")

		pr.reload()
		pr.approval_status = "Approved"
		frappe.set_user(approver_user.name)
		try:
			pr.save()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(pr.approval_status, "Approved")

	def test_requester_cannot_approve_own_requisition_without_privileged_role(self):
		requester = self._make_employee("PR State Requester 4")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)

		# Same reasoning as above: this must run as a genuinely non-privileged
		# user, since Administrator (the default test session) always holds
		# System Manager and would bypass the independence check. The acting
		# user is bound to the requester Employee so this test isolates the
		# independence check from the separate requester-identity check.
		outsider_user = frappe.new_doc("User")
		outsider_user.email = "pr-state-outsider-4@example.com"
		outsider_user.first_name = "PR State Outsider 4"
		outsider_user.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", outsider_user.name, force=True)
		frappe.db.set_value("Employee", requester.name, "user_id", outsider_user.name)

		frappe.set_user(outsider_user.name)
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_requisition(requester.name, requester.name)
		finally:
			frappe.set_user("Administrator")

	def test_non_privileged_user_cannot_name_a_different_employee_as_requester(self):
		requester = self._make_employee("PR Identity Requester 7")
		approver = self._make_employee("PR Identity Approver 7")
		self.addCleanup(frappe.delete_doc, "Employee", requester.name, force=True)
		self.addCleanup(frappe.delete_doc, "Employee", approver.name, force=True)

		# requester.user_id is left unset, so the acting user below is nobody's
		# named Employee -- creating a requisition "as" requester must fail.
		outsider_user = frappe.new_doc("User")
		outsider_user.email = "pr-identity-outsider-7@example.com"
		outsider_user.first_name = "PR Identity Outsider 7"
		outsider_user.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", outsider_user.name, force=True)

		frappe.set_user(outsider_user.name)
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_requisition(requester.name, approver.name)
		finally:
			frappe.set_user("Administrator")

	def _make_user(self, label):
		user = frappe.new_doc("User")
		user.email = f"{frappe.scrub(label).replace('_', '-')}@example.com"
		user.first_name = label
		user.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", user.name, force=True)
		return user.name

	def _make_rehired_employee_pair(self, label):
		user = self._make_user(f"{label} User")
		former = frappe.get_doc({
			"doctype": "Employee", "first_name": f"{label} Former", "status": "Left",
			"relieving_date": frappe.utils.nowdate(), "user_id": user, "create_user_permission": 0,
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Employee", former.name, force=True)
		current = frappe.get_doc({
			"doctype": "Employee", "first_name": f"{label} Current", "status": "Active",
			"user_id": user, "create_user_permission": 0,
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Employee", current.name, force=True)
		return user, current, former

	def test_requester_cannot_name_their_own_aliased_employee_record_as_approver(self):
		user, current, former = self._make_rehired_employee_pair("PR Alias Requester 1")

		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_requisition(current.name, former.name)
		finally:
			frappe.set_user("Administrator")

	def test_requester_cannot_approve_own_requisition_through_an_aliased_approver_record(self):
		user, current, former = self._make_rehired_employee_pair("PR Alias Requester 2")
		pr = self._make_requisition(current.name, former.name)
		pr.submit()

		pr.reload()
		pr.approval_status = "Approved"
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.ValidationError):
				pr.save()
		finally:
			frappe.set_user("Administrator")

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

		# The failed save() above already advanced the in-memory modified
		# timestamp before the gate rejected it; reload to get a fresh
		# baseline before retrying, or the retry trips a spurious
		# TimestampMismatchError instead of actually saving.
		pr.reload()
		pr.approval_status = "Rejected"
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
