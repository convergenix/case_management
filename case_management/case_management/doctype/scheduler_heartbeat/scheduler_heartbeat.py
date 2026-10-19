# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, time_diff_in_seconds


class SchedulerHeartbeat(Document):
	pass


def record_heartbeat():
	frappe.db.set_single_value("Scheduler Heartbeat", "last_heartbeat", now_datetime())


def check_for_outage(expected_interval_minutes=10, grace_minutes=20):
	last_heartbeat = frappe.db.get_single_value("Scheduler Heartbeat", "last_heartbeat")
	if not last_heartbeat:
		return False

	allowed_gap_seconds = (expected_interval_minutes + grace_minutes) * 60
	gap_seconds = time_diff_in_seconds(now_datetime(), get_datetime(last_heartbeat))

	if gap_seconds <= allowed_gap_seconds:
		return False

	frappe.db.set_single_value("Scheduler Heartbeat", "last_outage_detected", now_datetime())

	from case_management.case_management.doctype.obligation_reminder.obligation_reminder import process_due_reminders
	process_due_reminders(mark_overdue_after_minutes=expected_interval_minutes)

	return True


def heartbeat_tick(expected_interval_minutes=10, grace_minutes=20):
	"""Combined scheduler entry point: check for an outage against the
	PREVIOUS heartbeat before recording a new one, so the two operations
	can never race against each other as separate cron jobs would.
	"""
	outage_detected = check_for_outage(expected_interval_minutes, grace_minutes)
	record_heartbeat()
	return outage_detected
