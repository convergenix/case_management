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
			self.status = self.status or "Proposed"
			return

		previous = frappe.db.get_value(
			"Legal Obligation", self.name, ["status", "due_date"], as_dict=True
		)

		if previous.status != self.status:
			if self.status not in TRANSITIONS.get(previous.status, set()):
				frappe.throw(
					f"Cannot move Legal Obligation from {previous.status} to {self.status}."
				)
			if self.status == "Verified":
				if self.is_critical and not self.verifier:
					frappe.throw(
						"Critical obligations require a Verifier before they can be Verified."
					)
				self.verified_by = frappe.session.user
				self.verified_on = now_datetime()
			if self.status == "Completed":
				if not self.completion_evidence:
					frappe.throw(
						"Completing an obligation requires completion evidence."
					)
				self.completed_by = frappe.session.user
				self.completed_on = now_datetime()

		if previous.due_date and self.due_date and str(previous.due_date) != str(self.due_date):
			if previous.status in ("Verified", "Active"):
				if not self.reschedule_reason:
					frappe.throw(
						"Rescheduling a Verified/Active obligation requires a reason "
						"in 'Reschedule Reason'."
					)
				self.previous_due_date = previous.due_date
