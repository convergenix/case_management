# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestFeeNoteReservation(FrappeTestCase):
	def _make_matter_with_approved_time(self, label="Reservation Test", hours=3.5, rate=80000):
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
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		return fee_note

	def _approve(self, fee_note):
		fee_note.status = "Partner Review"
		fee_note.save()
		fee_note.status = "Finance Review"
		fee_note.save()
		fee_note.status = "Approved"
		fee_note.save()
		fee_note.reload()
		return fee_note

	def test_approving_reserves_the_line_time_entries(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		self._approve(fee_note)

		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "wip_status"), "Reserved")
		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "fee_note"), fee_note.name)

	def test_stale_save_cannot_move_a_reserved_entry_back_to_approved(self):
		matter, entry = self._make_matter_with_approved_time()
		# Loaded before the Fee Note approval below reserves it via raw SQL (which
		# does not bump `modified`), so this in-memory copy looks "current" to
		# check_if_latest even once the entry has actually moved on.
		stale_entry = frappe.get_doc("Time Tracking", entry.name)

		fee_note = self._make_fee_note(matter, entry)
		self._approve(fee_note)
		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "wip_status"), "Reserved")

		stale_entry.wip_status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			stale_entry.save()

		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "wip_status"), "Reserved")
		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "fee_note"), fee_note.name)

	def test_two_fee_notes_cannot_both_reserve_the_same_time_entry(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note_a = self._make_fee_note(matter, entry)
		fee_note_b = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [{"time_entry": entry.name, "hours": entry.time, "rate": entry.approved_rate, "amount": entry.approved_amount}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note_b.name, force=True)

		self._approve(fee_note_a)

		fee_note_b.status = "Partner Review"
		fee_note_b.save()
		fee_note_b.status = "Finance Review"
		fee_note_b.save()
		fee_note_b.status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			fee_note_b.save()

	def test_returning_an_approved_fee_note_releases_the_reservation(self):
		matter, entry = self._make_matter_with_approved_time()
		fee_note = self._make_fee_note(matter, entry)
		self._approve(fee_note)

		fee_note.status = "Superseded"
		fee_note.save()

		self.assertEqual(frappe.db.get_value("Time Tracking", entry.name, "wip_status"), "Approved")
		self.assertFalse(frappe.db.get_value("Time Tracking", entry.name, "fee_note"))

	def test_removing_a_line_from_an_approved_fee_note_still_releases_its_reservation(self):
		matter, entry_one = self._make_matter_with_approved_time(label="Removed Line Test")

		entry_two = frappe.get_doc({
			"doctype": "Time Tracking", "matter": matter.name, "date": nowdate(),
			"time": 2, "billing": "Billable", "notes": "Review",
			"employee": frappe.db.get_value("Matter", matter.name, "responsible_solicitor"),
		}).insert()
		self.addCleanup(frappe.delete_doc, "Time Tracking", entry_two.name, force=True)

		from case_management.case_management.doctype.time_tracking.time_tracking import approve_time_entry
		approve_time_entry(entry_two.name)
		entry_two.reload()

		fee_note = frappe.get_doc({
			"doctype": "Fee Note", "matter": matter.name, "cutoff_date": nowdate(),
			"lines": [
				{"time_entry": entry_one.name, "hours": entry_one.time, "rate": entry_one.approved_rate, "amount": entry_one.approved_amount},
				{"time_entry": entry_two.name, "hours": entry_two.time, "rate": entry_two.approved_rate, "amount": entry_two.approved_amount},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Fee Note", fee_note.name, force=True)
		self._approve(fee_note)

		self.assertEqual(frappe.db.get_value("Time Tracking", entry_one.name, "wip_status"), "Reserved")
		self.assertEqual(frappe.db.get_value("Time Tracking", entry_two.name, "wip_status"), "Reserved")

		# Remove entry_two's line entirely, still at status "Approved" -- this is a
		# material edit (it changes the content hash), not an explicit status transition.
		fee_note.lines = [row for row in fee_note.lines if row.time_entry != entry_two.name]
		fee_note.save()

		self.assertEqual(fee_note.status, "Finance Review")
		self.assertEqual(frappe.db.get_value("Time Tracking", entry_one.name, "wip_status"), "Approved")
		self.assertFalse(frappe.db.get_value("Time Tracking", entry_one.name, "fee_note"))
		self.assertEqual(frappe.db.get_value("Time Tracking", entry_two.name, "wip_status"), "Approved")
		self.assertFalse(frappe.db.get_value("Time Tracking", entry_two.name, "fee_note"))
