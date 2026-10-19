# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, now_datetime, nowdate


class TestSchedulerHeartbeat(FrappeTestCase):
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

	def tearDown(self):
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat", None)
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_outage_detected", None)
		frappe.db.commit()

	def test_record_heartbeat_sets_timestamp(self):
		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import record_heartbeat
		record_heartbeat()
		stored = frappe.db.get_single_value("Scheduler Heartbeat", "last_heartbeat")
		self.assertIsNotNone(stored)

	def test_check_for_outage_detects_stale_heartbeat(self):
		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-45),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		outage_detected = check_for_outage(expected_interval_minutes=10, grace_minutes=20)
		self.assertTrue(outage_detected)
		self.assertIsNotNone(frappe.db.get_single_value("Scheduler Heartbeat", "last_outage_detected"))

	def test_check_for_outage_false_when_heartbeat_recent(self):
		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-5),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		outage_detected = check_for_outage(expected_interval_minutes=10, grace_minutes=20)
		self.assertFalse(outage_detected)

	def test_heartbeat_tick_detects_outage_against_old_heartbeat_then_refreshes_it(self):
		stale = add_to_date(now_datetime(), minutes=-45)
		frappe.db.set_value("Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat", stale)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import heartbeat_tick
		self.assertTrue(heartbeat_tick(expected_interval_minutes=10, grace_minutes=20))

		refreshed = frappe.db.get_single_value("Scheduler Heartbeat", "last_heartbeat")
		self.assertGreater(get_datetime(refreshed), get_datetime(stale))

	def test_check_for_outage_processes_backlog_on_recovery(self):
		matter = self._make_matter()
		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Other",
			"due_date": nowdate(), "responsible_user": "Administrator",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		overdue_reminder = frappe.get_doc({
			"doctype": "Obligation Reminder", "obligation": obligation.name,
			"scheduled_for": add_to_date(now_datetime(), hours=-2),
			"recipient": "Administrator",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Obligation Reminder", overdue_reminder.name, force=True)

		frappe.db.set_value(
			"Scheduler Heartbeat", "Scheduler Heartbeat", "last_heartbeat",
			add_to_date(now_datetime(), minutes=-45),
		)
		frappe.db.commit()

		from case_management.case_management.doctype.scheduler_heartbeat.scheduler_heartbeat import check_for_outage
		check_for_outage(expected_interval_minutes=10, grace_minutes=20)

		self.assertEqual(
			frappe.db.get_value("Obligation Reminder", overdue_reminder.name, "status"), "Delivered"
		)
		self.assertEqual(
			frappe.db.get_value("Obligation Reminder", overdue_reminder.name, "is_overdue"), 1
		)
