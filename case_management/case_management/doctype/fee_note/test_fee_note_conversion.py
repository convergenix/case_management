# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


def _cancel_and_delete_invoice(invoice_name):
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.docstatus == 1:
		invoice.cancel()
	frappe.delete_doc("Sales Invoice", invoice_name, force=True)


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
		self.addCleanup(_cancel_and_delete_invoice, invoice_name)

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
		self.addCleanup(_cancel_and_delete_invoice, first_invoice)

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
