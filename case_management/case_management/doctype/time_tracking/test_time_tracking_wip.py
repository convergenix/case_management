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
