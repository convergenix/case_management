# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime


class TestSchedulerHeartbeat(FrappeTestCase):
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

	def test_check_for_outage_processes_backlog_on_recovery(self):
		matter = frappe.db.get_value("Matter", {}, "name")
		if not matter:
			self.skipTest("No Matter fixture available")
		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter, "obligation_type": "Other",
			"due_date": frappe.utils.nowdate(), "responsible_user": "Administrator",
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
