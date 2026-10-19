# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

TRANSITIONS = {
	"Draft": {"Under Review", "Withdrawn"},
	"Under Review": {"Approved", "Declined", "Withdrawn"},
	"Approved": {"Converted", "Under Review"},
	"Declined": set(),
	"Withdrawn": set(),
	"Converted": set(),
}


class Intake(Document):
	def validate(self):
		previous_status = None
		if not self.is_new():
			previous_status = frappe.db.get_value("Intake", self.name, "status")

		if not self.requested_by:
			self.requested_by = frappe.session.user
		if not self.requested_on:
			self.requested_on = now_datetime()

		if not any(row.role == "Proposed Client" for row in self.parties):
			frappe.throw("Intake must include exactly one party with role 'Proposed Client'.")

		if previous_status and previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(f"Cannot move Intake from {previous_status} to {self.status}.")

		previous_doc = self.get_doc_before_save()
		if (
			previous_status == "Approved"
			and self.status == "Approved"
			and previous_doc
			and previous_doc.get_party_set_hash() != self.get_party_set_hash()
		):
			self.status = "Under Review"
			frappe.msgprint(
				"Party set changed after approval — Intake reverted to Under Review for re-review."
			)

		if self.status == "Approved":
			self._validate_conflict_clearance()

	def get_party_set_hash(self):
		pairs = sorted((row.legal_party, row.role) for row in self.parties)
		raw = "|".join(f"{party}:{role}" for party, role in pairs)
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()

	def _validate_conflict_clearance(self):
		if not frappe.db.table_exists("Conflict Review"):
			frappe.throw(
				"Intake cannot be Approved without a Conflict Review decided Clear or Waiver Granted."
			)
		reviews = frappe.get_all(
			"Conflict Review",
			filters={"intake": self.name, "decision": ["in", ["Clear", "Waiver Granted"]]},
			fields=["name", "party_set_hash"],
			order_by="search_timestamp desc",
			limit=1,
		)
		if not reviews:
			frappe.throw(
				"Intake cannot be Approved without a Conflict Review decided Clear or Waiver Granted."
			)
		if reviews[0].party_set_hash != self.get_party_set_hash():
			frappe.throw(
				"The Conflict Review on file is stale — the party set has changed since it ran. "
				"Run a new conflict search before approving."
			)


def _set_status(intake, status, decision_reason=None):
	doc = frappe.get_doc("Intake", intake)
	doc.status = status
	if decision_reason:
		doc.decision_reason = decision_reason
	doc.save()
	return doc.name


@frappe.whitelist()
def submit_for_review(intake):
	return _set_status(intake, "Under Review")


@frappe.whitelist()
def approve(intake):
	return _set_status(intake, "Approved")


@frappe.whitelist()
def decline(intake, reason=None):
	return _set_status(intake, "Declined", decision_reason=reason)


@frappe.whitelist()
def withdraw(intake):
	return _set_status(intake, "Withdrawn")
