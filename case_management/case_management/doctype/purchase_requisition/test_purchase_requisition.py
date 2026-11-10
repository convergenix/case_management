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
