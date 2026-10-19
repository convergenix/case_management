# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

PRIVILEGED_ROLES = {"System Manager", "Managing Partner", "Conflicts Reviewer"}


class ConflictReview(Document):
	def before_insert(self):
		# Search provenance is the server's record of what was searched and by
		# whom, and it is never refreshed afterwards — the Intake and Matter
		# gates compare this hash against the live party set to detect a stale
		# clearance, so recomputing it on update would silently revalidate one.
		if self.intake:
			self.party_set_hash = frappe.get_doc("Intake", self.intake).get_party_set_hash()
		self.search_timestamp = now_datetime()
		self.searched_by = frappe.session.user

	def validate(self):
		self._validate_decision_authority()

	def _validate_decision_authority(self):
		previous_decision = None
		if not self.is_new():
			previous_decision = frappe.db.get_value("Conflict Review", self.name, "decision")
		if (self.decision or "") == (previous_decision or ""):
			return

		if not PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user)):
			frappe.throw(
				"Only a Conflicts Reviewer, Managing Partner or System Manager can decide a Conflict Review.",
				frappe.PermissionError,
			)

		if self.decision:
			self.reviewed_by = frappe.session.user
			self.reviewed_on = now_datetime()
		else:
			self.reviewed_by = None
			self.reviewed_on = None


@frappe.whitelist()
def run_conflict_search(intake):
	frappe.has_permission("Intake", "read", intake, throw=True)
	intake_doc = frappe.get_doc("Intake", intake)

	review = frappe.new_doc("Conflict Review")
	review.intake = intake_doc.name
	review.total_records_searched = frappe.db.count("Legal Party")

	all_parties = frappe.get_all(
		"Legal Party",
		fields=["name", "identifier", "normalized_name"],
	)
	already_matched = set()
	for intake_party in intake_doc.parties:
		this_party = frappe.get_doc("Legal Party", intake_party.legal_party)
		for other in all_parties:
			if other.name == this_party.name or other.name in already_matched:
				continue
			match_type = None
			if this_party.identifier and other.identifier and this_party.identifier == other.identifier:
				match_type = "Exact Identifier"
			elif this_party.normalized_name and other.normalized_name == this_party.normalized_name:
				match_type = "Normalized Name"
			if match_type:
				review.append("matches", {
					"legal_party": other.name,
					"match_type": match_type,
				})
				already_matched.add(other.name)

	review.insert()
	return review.name


def get_permission_query_conditions(user=None):
	if not user:
		user = frappe.session.user
	if PRIVILEGED_ROLES & set(frappe.get_roles(user)):
		return ""
	return "ifnull(`tabConflict Review`.decision, '') != 'Restricted Match - Escalated'"


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	if PRIVILEGED_ROLES & set(frappe.get_roles(user)):
		return True
	if doc.decision == "Restricted Match - Escalated":
		return False
	return True
