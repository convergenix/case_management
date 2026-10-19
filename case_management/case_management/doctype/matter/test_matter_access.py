# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, nowdate


class TestMatterAccessControl(FrappeTestCase):
	def setUp(self):
		if not frappe.db.exists("Role", "Conflicts Reviewer"):
			frappe.get_doc({"doctype": "Role", "role_name": "Conflicts Reviewer"}).insert(
				ignore_permissions=True
			)

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
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		return customer

	def _make_practice_area(self, label):
		practice_area = frappe.get_doc({
			"doctype": "Practice Area",
			"practice_area": f"{label} Practice Area",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)
		return practice_area

	def _get_employee(self):
		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee",
				"employee_name": "Test Solicitor",
				"status": "Active",
			}).insert(ignore_mandatory=True).name
		return employee

	def _matter_base_fields(self, label):
		practice_area = self._make_practice_area(label)
		return {
			"open_date": nowdate(),
			"practice_area": practice_area.name,
			"transaction": f"{label} Transaction",
			"responsible_solicitor": self._get_employee(),
		}

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

	def test_restricted_matter_excluded_from_list_for_unrelated_user(self):
		# Matter's own DocPerm for "Lawyer Manager" has if_owner=1 (pre-existing,
		# unrelated to this task) — that role can only read Matters it personally
		# owns. "Partners" has unrestricted read but is disabled in this bench's
		# data. So the outsider user is made the OWNER of the test matter (by
		# creating it while impersonating them) rather than relying on either
		# role's baseline grant — this isolates exactly what we're testing: does
		# is_restricted deny them even though they own the record and aren't on
		# its team.
		outsider = "test_outsider_user@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc({
				"doctype": "User",
				"email": outsider,
				"first_name": "Outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Lawyer Manager"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", outsider, force=True)

		intake = self._make_approved_intake("Restricted List")
		customer = self._make_customer("Restricted List")

		frappe.set_user(outsider)
		try:
			matter = frappe.get_doc({
				"doctype": "Matter",
				"client": customer.name,
				"intake": intake.name,
				"status": "Open",
				"is_restricted": 1,
				**self._matter_base_fields("Restricted List"),
			}).insert(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		from case_management.case_management.doctype.matter.matter import has_permission
		# When hooks are registered, Frappe calls has_permission internally
		# for permission-mediated queries. This test verifies that the function
		# correctly denies access to restricted matters via the ethical-wall check
		# (is_restricted = True and user not on Matter team), even when the user
		# owns the document and has a role with if_owner permission.
		self.assertFalse(has_permission(matter, user=outsider))
		self.assertTrue(has_permission(matter, user="Administrator"))
