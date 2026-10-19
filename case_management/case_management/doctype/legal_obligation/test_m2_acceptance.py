# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, nowdate, now_datetime


class TestM2Acceptance(FrappeTestCase):
	def _make_active_obligation(self, due_date=None):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "M2 Acceptance Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "M2 Acceptance Client", "party_type": "Organization",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "M2 Acceptance Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "M2 Acceptance Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "M2 Acceptance Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Court Hearing",
			"due_date": due_date or add_days(nowdate(), 14), "responsible_user": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		return obligation

	def test_amended_date_preserves_old_date_and_supersedes_obsolete_reminders(self):
		obligation = self._make_active_obligation()
		original_due_date = obligation.due_date
		original_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, pluck="name"
		)
		for r in original_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		obligation.due_date = add_days(original_due_date, 21)
		obligation.reschedule_reason = "Court rescheduled the hearing"
		obligation.save()

		self.assertEqual(str(obligation.previous_due_date), str(original_due_date))
		for r in original_reminders:
			self.assertEqual(frappe.db.get_value("Obligation Reminder", r, "status"), "Superseded")

		new_reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name, "status": "Queued"}, pluck="name"
		)
		for r in new_reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(new_reminders), 2)

	def test_stopped_scheduler_is_detected_and_recovered_without_duplicating_delivered(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		overdue_reminder = reminders[0]
		frappe.db.set_value("Obligation Reminder", overdue_reminder, "scheduled_for", add_to_date(now_datetime(), hours=-3))

		already_delivered = reminders[1]
		frappe.db.set_value("Obligation Reminder", already_delivered, "status", "Delivered")
		frappe.db.set_value("Obligation Reminder", already_delivered, "delivered_at", add_to_date(now_datetime(), hours=-1))
		delivered_at_before_recovery = frappe.db.get_value("Obligation Reminder", already_delivered, "delivered_at")

		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-50),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		outage_detected = check_for_outage(expected_interval_minutes=10, grace_minutes=20)
		self.assertTrue(outage_detected)

		self.assertEqual(frappe.db.get_value("Obligation Reminder", overdue_reminder, "status"), "Delivered")
		self.assertEqual(frappe.db.get_value("Obligation Reminder", overdue_reminder, "is_overdue"), 1)

		self.assertEqual(
			str(frappe.db.get_value("Obligation Reminder", already_delivered, "delivered_at")),
			str(delivered_at_before_recovery),
		)

		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat", None)
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_outage_detected", None)
		frappe.db.commit()

	def test_completing_a_reminder_does_not_complete_the_obligation(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import acknowledge
		acknowledge(reminders[0])

		reminder_doc = frappe.get_doc("Obligation Reminder", reminders[0])
		reminder_doc.status = "Completed"
		reminder_doc.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Completed")
		self.assertEqual(frappe.db.get_value("Legal Obligation", obligation.name, "status"), "Active")
