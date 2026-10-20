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
	def setUp(self):
		# convert_fee_note bills in the client's own Billing Details currency, which
		# may differ from the company's base currency (this bench: NGN vs INR). ERPNext
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

	def _make_outsider(self, email):
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User", "email": email, "first_name": "Outsider",
				"send_welcome_email": 0, "roles": [{"role": "Lawyer Manager"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", email, force=True)
		return email

	def _make_matter_with_approved_fee_note(self, label="Conversion Test", hours=3.5, rate=80000, billing_currency="NGN", is_restricted=0):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		billing = frappe.get_doc({
			"doctype": "Billing Details", "customer": customer.name,
			"billing_rate": rate, "billing_currency": billing_currency,
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
			"is_restricted": is_restricted,
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

	def test_conversion_fails_its_claim_if_fee_note_was_already_claimed_elsewhere(self):
		# FrappeTestCase can't truly exercise two concurrent convert_fee_note calls, but
		# we can simulate the window a second caller would land in: another process's
		# claim already won (status flipped to Converted) before the invoice/native_invoice
		# bookkeeping finished. This attempt must fail cleanly and never create an invoice.
		fee_note, entry = self._make_matter_with_approved_fee_note()
		frappe.db.set_value("Fee Note", fee_note.name, "status", "Converted")

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		with self.assertRaises(frappe.ValidationError):
			convert_fee_note(fee_note.name, idempotency_key="lost-the-race")

		self.assertFalse(frappe.db.get_value("Fee Note", fee_note.name, "native_invoice"))
		self.assertEqual(
			len(frappe.get_all(
				"Sales Invoice", filters={"customer": frappe.db.get_value("Matter", fee_note.matter, "client")}
			)),
			0,
		)

	def test_converted_invoice_is_denominated_in_the_clients_billing_currency(self):
		company_currency = frappe.db.get_value("Company", frappe.db.get_value("Company", {}, "name"), "default_currency")
		self.assertNotEqual(
			company_currency, "NGN",
			"this test needs a company whose base currency differs from the billing currency "
			"under test; adjust the billing_currency below if this bench's default company is NGN",
		)
		self._ensure_currency_exchange("NGN", company_currency, 0.0048)

		fee_note, entry = self._make_matter_with_approved_fee_note(
			label="Multi Currency", billing_currency="NGN"
		)

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		invoice_name = convert_fee_note(fee_note.name, idempotency_key="currency-key")
		self.addCleanup(_cancel_and_delete_invoice, invoice_name)

		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.currency, "NGN")
		self.assertNotEqual(invoice.currency, company_currency)
		self.assertEqual(float(invoice.grand_total), float(fee_note.total_amount))

	def test_a_user_without_matter_access_cannot_convert_its_fee_note(self):
		outsider = self._make_outsider("test_fee_note_conversion_outsider@example.com")
		self.assertIsNone(frappe.db.get_value("Employee", {"user_id": outsider}, "name"))

		fee_note, entry = self._make_matter_with_approved_fee_note(
			label="Restricted Conversion", is_restricted=1
		)

		from case_management.case_management.doctype.fee_note.fee_note import convert_fee_note
		frappe.set_user(outsider)
		try:
			with self.assertRaises(frappe.PermissionError):
				convert_fee_note(fee_note.name, idempotency_key="outsider-attempt")
		finally:
			frappe.set_user("Administrator")

		fee_note.reload()
		self.assertFalse(fee_note.native_invoice)
		self.assertEqual(fee_note.status, "Approved")
