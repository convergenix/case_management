# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


TRANSITIONS = {
	"Proposed": {"Verified", "Cancelled"},
	"Verified": {"Active", "Superseded", "Cancelled"},
	"Active": {"Completed", "Superseded", "Cancelled"},
	"Completed": set(),
	"Superseded": set(),
	"Cancelled": set(),
}


class LegalObligation(Document):
	def validate(self):
		if self.is_new():
			previous_status = "Proposed"
			previous_due_date = None
			self.status = self.status or "Proposed"
		else:
			previous = frappe.db.get_value(
				"Legal Obligation",
				self.name,
				["status", "due_date", "last_reminder_sync_date"],
				as_dict=True,
			)
			previous_status = previous.status
			previous_due_date = previous.due_date
			# Only generate_default_reminders may move this field, and it does so
			# with frappe.db.set_value, which never reaches validate(). Anything a
			# caller submits here is discarded, otherwise pre-stamping it would
			# suppress reminder generation for the matching due date.
			self.last_reminder_sync_date = previous.last_reminder_sync_date

		if previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(
					f"Cannot move Legal Obligation from {previous_status} to {self.status}."
				)
			if self.status == "Verified":
				self.verified_by = frappe.session.user
				self.verified_on = now_datetime()
			if self.status == "Completed":
				if not self.completion_evidence:
					frappe.throw(
						"Completing an obligation requires completion evidence."
					)
				self.completed_by = frappe.session.user
				self.completed_on = now_datetime()

		# Checked unconditionally rather than only on transition: otherwise
		# is_critical can be flipped to 1 on a save that doesn't also change
		# status, which never re-enters the transition-gated block above.
		if self.is_critical and self.status in ("Verified", "Active"):
			if not self.verifier:
				frappe.throw(
					"Critical obligations require a Verifier before they can be Verified or Active."
				)
			if self.verifier == self.responsible_user:
				frappe.throw(
					"The Verifier must be independent of the obligation's Owner."
				)

		# The gate above only checks that a verifier is NAMED; this checks that
		# the right person is the one acting.
		if previous_status != self.status and self.status == "Verified":
			privileged = {"System Manager", "Managing Partner"} & set(frappe.get_roles(frappe.session.user))
			if frappe.session.user != self.verifier and not privileged:
				frappe.throw(
					"Only the named Verifier (or a Managing Partner/System Manager) "
					"can move this obligation to Verified."
				)

		if previous_due_date and self.due_date and str(previous_due_date) != str(self.due_date):
			if previous_status in ("Verified", "Active"):
				if not self.reschedule_reason:
					frappe.throw(
						"Rescheduling a Verified/Active obligation requires a reason "
						"in 'Reschedule Reason'."
					)
				self.previous_due_date = previous_due_date
				# Preserve the reason that justified THIS reschedule before
				# clearing the working field, so a later reschedule can't
				# pass the gate on stale text AND the original reason stays
				# auditable (spec requires preserving "the old date and
				# reason").
				self.previous_reschedule_reason = self.reschedule_reason
				self.reschedule_reason = None


def get_permission_query_conditions(user=None):
	from case_management.case_management.doctype.matter.matter import get_matter_access_condition
	return get_matter_access_condition("`tabLegal Obligation`.matter", user)


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	from case_management.case_management.doctype.matter.matter import has_permission as matter_has_permission
	matter_doc = frappe.get_cached_doc("Matter", doc.matter)
	return matter_has_permission(matter_doc, user=user, permission_type=permission_type)
