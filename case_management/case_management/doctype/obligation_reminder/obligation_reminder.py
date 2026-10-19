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
	obligation = frappe.get_doc("Legal Obligation", obligation_name)

	if obligation.status in ("Completed", "Cancelled", "Superseded"):
		frappe.db.sql(
			"""update `tabObligation Reminder` set status='Superseded'
			   where obligation=%(obligation)s and status='Queued'""",
			{"obligation": obligation_name},
		)
		return

	if obligation.status != "Active":
		return

	if obligation.last_reminder_sync_date and str(obligation.last_reminder_sync_date) == str(obligation.due_date):
		return

	existing_queued = frappe.get_all(
		"Obligation Reminder",
		filters={"obligation": obligation_name, "status": ["in", ["Queued"]]},
		pluck="name",
	)
	for reminder_name in existing_queued:
		frappe.db.set_value("Obligation Reminder", reminder_name, "status", "Superseded")

	due = get_datetime(obligation.due_date)
	for days_before in DEFAULT_ADVANCE_DAYS:
		scheduled_for = add_days(due, -days_before)
		frappe.get_doc({
			"doctype": "Obligation Reminder",
			"obligation": obligation_name,
			"scheduled_for": scheduled_for,
			"recipient": obligation.responsible_user,
			"escalation_level": "Owner",
		}).insert(ignore_permissions=True)

	frappe.db.set_value("Legal Obligation", obligation_name, "last_reminder_sync_date", obligation.due_date, update_modified=False)
	if hasattr(doc, "last_reminder_sync_date"):
		doc.last_reminder_sync_date = obligation.due_date


def process_due_reminders(mark_overdue_after_minutes=60):
	now = now_datetime()
	due = frappe.get_all(
		"Obligation Reminder",
		filters={"status": "Queued", "scheduled_for": ["<=", now]},
		fields=["name", "scheduled_for"],
	)
	for row in due:
		minutes_late = (now - get_datetime(row.scheduled_for)).total_seconds() / 60
		doc = frappe.get_doc("Obligation Reminder", row.name)
		doc.status = "Delivered"
		doc.delivered_at = now
		if minutes_late > mark_overdue_after_minutes:
			doc.is_overdue = 1
		doc.save(ignore_permissions=True)
	return len(due)


@frappe.whitelist()
def acknowledge(reminder):
	doc = frappe.get_doc("Obligation Reminder", reminder)
	user = frappe.session.user
	privileged = {"System Manager", "Managing Partner"} & set(frappe.get_roles(user))
	if user != doc.recipient and not privileged:
		frappe.throw("Only the recipient (or a Managing Partner/System Manager) can acknowledge this reminder.")
	if doc.status != "Delivered":
		frappe.throw("Only a Delivered reminder can be acknowledged.")
	doc.status = "Acknowledged"
	doc.acknowledged_at = now_datetime()
	doc.acknowledged_by = user
	doc.save(ignore_permissions=True)
	return doc.name


def get_permission_query_conditions(user=None):
	from case_management.case_management.doctype.matter.matter import get_permission_query_conditions as matter_condition
	condition = matter_condition(user)
	if not condition:
		return ""
	return "`tabObligation Reminder`.obligation in (select `tabLegal Obligation`.name from `tabLegal Obligation` where `tabLegal Obligation`.matter in (select `tabMatter`.name from `tabMatter` where {condition}))".format(condition=condition)


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	from case_management.case_management.doctype.legal_obligation.legal_obligation import has_permission as obligation_has_permission
	obligation_doc = frappe.get_cached_doc("Legal Obligation", doc.obligation)
	return obligation_has_permission(obligation_doc, user=user, permission_type=permission_type)
