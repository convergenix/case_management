# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from case_management.case_management.doctype.conflict_review.conflict_review import (
	run_conflict_search,
	has_permission,
)


def _make_user(testcase, email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": "Conflict Test",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		testcase.addCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
	return email


class TestConflictReview(FrappeTestCase):
	def _make_party(self, name, identifier=None):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
			"identifier": identifier,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def _make_intake(self, client, adverse):
		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Litigation",
			"parties": [
				{"legal_party": client.name, "role": "Proposed Client"},
				{"legal_party": adverse.name, "role": "Adverse Party"},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		return intake

	def test_run_conflict_search_finds_exact_identifier_match(self):
		existing = self._make_party("Already Known Co", identifier="RC-1001")
		client = self._make_party("New Client Co")
		adverse_duplicate = self._make_party("Totally Different Name", identifier="RC-1001")
		intake = self._make_intake(client, adverse_duplicate)

		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)

		review = frappe.get_doc("Conflict Review", review_name)
		self.assertEqual(review.intake, intake.name)
		self.assertEqual(review.party_set_hash, intake.get_party_set_hash())
		matched_names = [row.legal_party for row in review.matches]
		self.assertIn(existing.name, matched_names)

	def test_restricted_match_hidden_from_ordinary_requester(self):
		client = self._make_party("Restricted Test Client")
		adverse = self._make_party("Restricted Test Adversary")
		intake = self._make_intake(client, adverse)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": frappe.utils.now_datetime(),
			"searched_by": "Administrator",
			"decision": "Restricted Match - Escalated",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		self.assertFalse(has_permission(review, user="test_ordinary_requester@example.com"))
		self.assertTrue(has_permission(review, user="Administrator"))

	def _make_review(self, intake, decision):
		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": frappe.utils.now_datetime(),
			"searched_by": "Administrator",
			"decision": decision,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)
		return review

	def test_escalated_review_excluded_from_list_for_non_privileged_user(self):
		client = self._make_party("List Gate Client")
		adverse = self._make_party("List Gate Adversary")
		intake = self._make_intake(client, adverse)
		escalated = self._make_review(intake, "Restricted Match - Escalated")
		cleared = self._make_review(intake, "Clear")
		user = _make_user(self, "test_conflict_list_outsider@example.com")

		frappe.set_user(user)
		try:
			visible = frappe.get_list(
				"Conflict Review",
				filters={"name": ["in", [escalated.name, cleared.name]]},
				pluck="name",
			)
		finally:
			frappe.set_user("Administrator")

		self.assertNotIn(escalated.name, visible)
		self.assertIn(cleared.name, visible)

	def test_restricted_match_hidden_from_the_searcher_themselves(self):
		client = self._make_party("Searcher Test Client")
		adverse = self._make_party("Searcher Test Adversary")
		intake = self._make_intake(client, adverse)

		test_user = frappe.get_doc({
			"doctype": "User",
			"email": "test_non_privileged_searcher@example.com",
			"first_name": "Test Searcher",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", test_user.name, force=True, ignore_permissions=True)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": frappe.utils.now_datetime(),
			"searched_by": test_user.name,
			"decision": "Restricted Match - Escalated",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		self.assertFalse(has_permission(review, user=test_user.name))
