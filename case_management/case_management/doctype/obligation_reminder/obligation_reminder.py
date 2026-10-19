# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime, get_datetime


TRANSITIONS = {
	"Queued": {"Delivered", "Superseded"},
	"Delivered": {"Acknowledged", "Superseded"},
	"Acknowledged": {"Completed"},
	"Completed": set(),
	"Superseded": set(),
}

DEFAULT_ADVANCE_DAYS = [7, 1]


class ObligationReminder(Document):
	def validate(self):
		if self.is_new():
			previous_status = "Queued"
			self.status = self.status or "Queued"
			self.queued_at = self.queued_at or now_datetime()
		else:
			previous_status = frappe.db.get_value("Obligation Reminder", self.name, "status")

		if previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(
					f"Cannot move Obligation Reminder from {previous_status} to {self.status}."
				)


def generate_default_reminders(doc, method=None):
	obligation_name = doc.name if hasattr(doc, 'name') else doc

	if frappe.db.exists("Obligation Reminder", {"obligation": obligation_name}):
		return

	obligation = doc if hasattr(doc, 'status') else frappe.get_doc("Legal Obligation", obligation_name)
	if obligation.status != "Active":
		return

	due = get_datetime(obligation.due_date)
	for days_before in DEFAULT_ADVANCE_DAYS:
		scheduled_for = add_days(due, -days_before)
		frappe.get_doc({
			"doctype": "Obligation Reminder",
			"obligation": obligation.name,
			"scheduled_for": scheduled_for,
			"recipient": obligation.responsible_user,
			"escalation_level": "Owner",
		}).insert(ignore_permissions=True)


@frappe.whitelist()
def acknowledge(reminder):
	doc = frappe.get_doc("Obligation Reminder", reminder)
	if doc.status != "Delivered":
		frappe.throw("Only a Delivered reminder can be acknowledged.")
	doc.status = "Acknowledged"
	doc.acknowledged_at = now_datetime()
	doc.acknowledged_by = frappe.session.user
	doc.save(ignore_permissions=True)
	return doc.name
