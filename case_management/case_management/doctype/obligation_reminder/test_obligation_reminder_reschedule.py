# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestObligationReminderReschedule(FrappeTestCase):
	def _make_active_obligation(self, due_date=None):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Reschedule Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Reschedule Test Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Reschedule Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Reschedule Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Reschedule Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Filing Deadline",
			"due_date": due_date or add_days(nowdate(), 14), "responsible_user": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		return obligation

	def test_rescheduling_supersedes_old_reminders_and_creates_new_ones(self):
		obligation = self._make_active_obligation()
		original_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, pluck="name"
		)
		for r in original_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(original_reminders), 2)

		old_due_date = obligation.due_date
		obligation.due_date = add_days(old_due_date, 10)
		obligation.reschedule_reason = "Hearing adjourned"
		obligation.save()

		for r in original_reminders:
			self.assertEqual(
				frappe.db.get_value("Obligation Reminder", r, "status"), "Superseded"
			)

		new_reminders = frappe.get_all(
			"Obligation Reminder",
			filters={"obligation": obligation.name, "status": "Queued"},
			pluck="name",
		)
		for r in new_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(new_reminders), 2)

	def test_rescheduling_does_not_supersede_already_delivered_reminders(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")

		obligation.due_date = add_days(obligation.due_date, 5)
		obligation.reschedule_reason = "Minor date shift"
		obligation.save()

		self.assertEqual(
			frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Delivered"
		)

		new_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name, "status": "Queued"}, pluck="name"
		)
		for r in new_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(new_reminders), 2)

	def test_unrelated_edit_after_reschedule_does_not_create_duplicate_reminders(self):
		obligation = self._make_active_obligation()
		original_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, pluck="name"
		)
		for r in original_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		old_due_date = obligation.due_date
		obligation.due_date = add_days(old_due_date, 10)
		obligation.reschedule_reason = "Hearing adjourned"
		obligation.save()

		post_reschedule_reminders = frappe.get_all(
			"Obligation Reminder",
			filters={"obligation": obligation.name, "status": "Queued"},
			pluck="name",
		)
		self.assertEqual(len(post_reschedule_reminders), 2)

		obligation.source_reference = "Updated source reference"
		obligation.save()

		final_reminders = frappe.get_all(
			"Obligation Reminder",
			filters={"obligation": obligation.name, "status": "Queued"},
			pluck="name",
		)
		for r in final_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		self.assertEqual(len(final_reminders), 2)
		self.assertEqual(set(post_reschedule_reminders), set(final_reminders))
