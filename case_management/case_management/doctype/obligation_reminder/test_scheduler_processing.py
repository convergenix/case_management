# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime, nowdate


class TestSchedulerProcessing(FrappeTestCase):
	def _make_matter(self):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Scheduler Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Scheduler Test Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Scheduler Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Scheduler Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Scheduler Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter

	def _make_obligation_stub(self):
		matter = self._make_matter()
		obligation = frappe.get_doc({
			"doctype": "Legal Obligation",
			"matter": matter.name,
			"obligation_type": "Other",
			"due_date": nowdate(),
			"responsible_user": "Administrator",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)
		return obligation

	def _make_reminder(self, obligation_name, scheduled_for, status="Queued"):
		reminder = frappe.get_doc({
			"doctype": "Obligation Reminder",
			"obligation": obligation_name,
			"scheduled_for": scheduled_for,
			"recipient": "Administrator",
			"status": status,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Obligation Reminder", reminder.name, force=True)
		return reminder

	def test_process_due_reminders_delivers_only_due_queued_reminders(self):
		obligation = self._make_obligation_stub()
		due_reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), minutes=-10))
		future_reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), hours=2))

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
		process_due_reminders()

		self.assertEqual(frappe.db.get_value("Obligation Reminder", due_reminder.name, "status"), "Delivered")
		self.assertEqual(frappe.db.get_value("Obligation Reminder", future_reminder.name, "status"), "Queued")

	def test_process_due_reminders_does_not_redeliver_already_delivered(self):
		obligation = self._make_obligation_stub()
		reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), minutes=-10))
		frappe.db.set_value("Obligation Reminder", reminder.name, "status", "Delivered")
		frappe.db.set_value("Obligation Reminder", reminder.name, "delivered_at", add_to_date(now_datetime(), minutes=-5))
		original_delivered_at = frappe.db.get_value("Obligation Reminder", reminder.name, "delivered_at")

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
		process_due_reminders()

		self.assertEqual(
			str(frappe.db.get_value("Obligation Reminder", reminder.name, "delivered_at")),
			str(original_delivered_at),
		)

	def test_process_due_reminders_sets_is_overdue_when_significantly_late(self):
		obligation = self._make_obligation_stub()
		overdue_reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), minutes=-90))

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
		process_due_reminders()

		self.assertEqual(frappe.db.get_value("Obligation Reminder", overdue_reminder.name, "status"), "Delivered")
		self.assertEqual(frappe.db.get_value("Obligation Reminder", overdue_reminder.name, "is_overdue"), 1)

	def test_process_due_reminders_does_not_set_is_overdue_when_slightly_late(self):
		obligation = self._make_obligation_stub()
		slightly_late_reminder = self._make_reminder(obligation.name, add_to_date(now_datetime(), minutes=-10))

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
		process_due_reminders()

		self.assertEqual(frappe.db.get_value("Obligation Reminder", slightly_late_reminder.name, "status"), "Delivered")
		self.assertEqual(frappe.db.get_value("Obligation Reminder", slightly_late_reminder.name, "is_overdue"), 0)
