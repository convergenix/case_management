# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

PRIVILEGED_ROLES = {"System Manager", "Managing Partner", "Conflicts Reviewer"}


class ConflictReview(Document):
	def validate(self):
		if self.decision and not self.reviewed_by:
			self.reviewed_by = frappe.session.user
			self.reviewed_on = now_datetime()


@frappe.whitelist()
def run_conflict_search(intake):
	intake_doc = frappe.get_doc("Intake", intake)

	review = frappe.new_doc("Conflict Review")
	review.intake = intake_doc.name
	review.party_set_hash = intake_doc.get_party_set_hash()
	review.search_timestamp = now_datetime()
	review.searched_by = frappe.session.user
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


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	if PRIVILEGED_ROLES & set(frappe.get_roles(user)):
		return True
	if doc.decision == "Restricted Match - Escalated":
		return False
	return True
