# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestFeeNote(FrappeTestCase):
	def _make_matter_with_approved_time(self, label="Fee Note Test", hours=3.5, rate=80000):
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
		return matter, entry

	def _make_fee_note(self, matter, entry):
		fee_note = frappe.get_doc({
			"doctype": "Fee Note",
			"matter": matter.name,
			"cutoff_date": nowdate(),
			"lines": [{
				"time_entry": entry.name,
				"hours": entry.time,
				"rate": entry.approved_rate,
				"amount": entry.approved_amount,
			}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		return fee_note

	def test_new_fee_note_defaults_to_draft(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		self.assertEqual(fee_note.status, "Draft")
		self.assertEqual(float(fee_note.total_amount), float(entry.approved_amount))

	def test_direct_creation_with_approved_status_is_rejected(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(), "status": "Approved",
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		})
		with self.assertRaises(frappe.ValidationError):
			fee_note.insert()

	def test_approving_computes_and_stores_a_content_hash(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)

		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()

		self.assertTrue(fee_note.approved_hash)
		self.assertEqual(fee_note.approved_hash, fee_note.compute_content_hash())

	def test_editing_an_approved_fee_note_invalidates_its_approval(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()
		approved_hash = fee_note.approved_hash

		# Adding a second, independently-approved line is a material edit that changes
		# the hash without claiming more than either line's own approved snapshot.
		second_entry = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": 1, "billing": "Billable", "notes": "Extra work",
			"employee": frappe.db.get_value("Matter", matter.name, "responsible_solicitor"),
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", second_entry.name, force=True)
		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(second_entry.name)
		second_entry.reload()

		fee_note.append("lines", {
			"time_entry": second_entry.name,
			"hours": second_entry.time,
			"rate": second_entry.approved_rate,
			"amount": second_entry.approved_amount,
		})
		fee_note.save()

		self.assertNotEqual(fee_note.status, "Approved")
		self.assertEqual(fee_note.status, "Finance Review")
		self.assertNotEqual(fee_note.approved_hash, approved_hash)

	def test_line_claiming_more_than_approved_snapshot_is_rejected(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = frappe.get_doc({
			"doctype": "Fee Note",
			"matter": matter.name,
			"cutoff_date": nowdate(),
			"lines": [{
				"time_entry": entry.name,
				"hours": entry.time,
				"rate": entry.approved_rate,
				"amount": float(entry.approved_amount) + 1000,
			}],
		})
		with self.assertRaises(frappe.ValidationError):
			fee_note.insert()

	def test_line_pointing_at_a_different_matters_time_entry_is_rejected(self):
		matter_one, entry_one = self._make_matter_with_approved_time(label="Matter One")
		matter_two, entry_two = self._make_matter_with_approved_time(label="Matter Two")

		fee_note = frappe.get_doc({
			"doctype": "Fee Note",
			"matter": matter_one.name,
			"cutoff_date": nowdate(),
			"lines": [{
				"time_entry": entry_two.name,
				"hours": entry_two.time,
				"rate": entry_two.approved_rate,
				"amount": entry_two.approved_amount,
			}],
		})
		with self.assertRaises(frappe.ValidationError):
			fee_note.insert()

	def test_moving_to_converted_without_native_invoice_is_rejected(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()

		fee_note.status = "Converted"
		with self.assertRaises(frappe.ValidationError):
			fee_note.save()

	def test_lines_approved_under_different_currencies_are_rejected(self):
		matter, entry_a = self._make_matter_with_approved_time(label="Currency Mismatch")
		client = frappe.db.get_value("Matter", matter.name, "client")
		frappe.db.set_value("Billing Details", {"customer": client}, "billing_currency", "USD")

		employee = frappe.db.get_value("Matter", matter.name, "responsible_solicitor")
		entry_b = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": 1, "billing": "Billable", "notes": "Second currency entry", "employee": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry_b.name, force=True)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry_b.name)
		entry_b.reload()

		self.assertNotEqual(entry_a.approved_currency, entry_b.approved_currency)

		fee_note = frappe.get_doc({
			"doctype": "Fee Note",
			"matter": matter.name,
			"cutoff_date": nowdate(),
			"lines": [
				{"time_entry": entry_a.name, "hours": entry_a.time, "rate": entry_a.approved_rate, "amount": entry_a.approved_amount},
				{"time_entry": entry_b.name, "hours": entry_b.time, "rate": entry_b.approved_rate, "amount": entry_b.approved_amount},
			],
		})
		with self.assertRaises(frappe.ValidationError):
			fee_note.insert()

	def test_converting_an_approved_fee_note_with_stale_hash_is_rejected(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()

		fee_note.lines[0].amount = float(fee_note.lines[0].amount) + 100
		fee_note.status = "Converted"
		with self.assertRaises(frappe.ValidationError):
			fee_note.save()

	def test_hash_is_stable_across_int_and_float_numeric_types(self):
		matter, entry = self._make_matter_with_approved_time(hours=2, rate=80000)
		fee_note = frappe.get_doc({
			"doctype": "Fee Note",
			"matter": matter.name,
			"cutoff_date": nowdate(),
			"lines": [{
				"time_entry": entry.name,
				"hours": 2,
				"rate": 80000,
				"amount": 160000,
			}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)

		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()

		reloaded = frappe.get_doc("Fee Note", fee_note.name)
		self.assertEqual(reloaded.compute_content_hash(), reloaded.approved_hash)
