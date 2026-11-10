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
