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


class TestM3Acceptance(FrappeTestCase):
	def setUp(self):
		# convert_fee_note bills in the client's own Billing Details currency (NGN in
		# these fixtures), which may differ from the company's base currency. ERPNext
		# requires either a currency-matching receivable account or this setting to post
		# a foreign-currency invoice against the company's single base-currency Debtors
		# account; restore the original value so this test module doesn't leak a global
		# Accounts Settings change into other test modules.
		settings = frappe.get_single("Accounts Settings")
		original = settings.allow_multi_currency_invoices_against_single_party_account
		if not original:
			frappe.db.set_single_value(
				"Accounts Settings", "allow_multi_currency_invoices_against_single_party_account", 1
			)
			self.addCleanup(
				frappe.db.set_single_value,
				"Accounts Settings",
				"allow_multi_currency_invoices_against_single_party_account",
				original,
			)
		self._ensure_currency_exchange(
			"NGN", frappe.db.get_value("Company", frappe.db.get_value("Company", {}, "name"), "default_currency"), 0.0048
		)

	def _ensure_currency_exchange(self, from_currency, to_currency, rate):
		"""Seed a deterministic Currency Exchange record so get_exchange_rate()
		resolves from the DB instead of falling through to a live API call
		(which has no network access in this test environment and would
		otherwise silently return 0.0)."""
		if from_currency == to_currency:
			return
		existing = frappe.db.exists(
			"Currency Exchange",
			{"from_currency": from_currency, "to_currency": to_currency, "date": nowdate()},
		)
		if existing:
			return
		doc = frappe.get_doc({
			"doctype": "Currency Exchange",
			"date": nowdate(),
			"from_currency": from_currency,
			"to_currency": to_currency,
			"exchange_rate": rate,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Currency Exchange", doc.name, force=True)

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
		self.addCleanup(_cancel_and_delete_invoice, first_attempt)

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
