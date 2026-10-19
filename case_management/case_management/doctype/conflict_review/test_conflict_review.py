# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from case_management.case_management.doctype.conflict_review.conflict_review import (
	run_conflict_search,
	has_permission,
)


def _make_user(testcase, email, roles=None):
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": "Conflict Test",
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in (roles or [])],
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

	def test_run_conflict_search_requires_read_access_to_the_intake(self):
		# Intake grants role "All" blanket read, so the denial has to come from a
		# User Permission scoping the user to one Intake — the configuration
		# frappe.has_permission consults. applicable_for keeps the scope on the
		# Intake doctype itself: without it, the restriction would also reject
		# the Conflict Review's intake link field and the search would fail at
		# insert time regardless of whether the intake was ever readable.
		own_client = self._make_party("Own Search Client")
		own_adverse = self._make_party("Own Search Adversary")
		own_intake = self._make_intake(own_client, own_adverse)

		other_client = self._make_party("Someone Elses Client")
		other_adverse = self._make_party("Someone Elses Adversary")
		other_intake = self._make_intake(other_client, other_adverse)

		user = _make_user(self, "test_intake_scoped_user@example.com")
		scope = frappe.get_doc({
			"doctype": "User Permission",
			"user": user,
			"allow": "Intake",
			"for_value": own_intake.name,
			"applicable_for": "Intake",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User Permission", scope.name, force=True)

		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				run_conflict_search(other_intake.name)

			review_name = run_conflict_search(own_intake.name)
		finally:
			frappe.set_user("Administrator")
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		self.assertEqual(frappe.db.get_value("Conflict Review", review_name, "intake"), own_intake.name)

	def test_only_a_privileged_reviewer_can_decide_a_conflict_review(self):
		client = self._make_party("Self Clearance Client")
		adverse = self._make_party("Self Clearance Adversary")
		intake = self._make_intake(client, adverse)
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)

		requester = _make_user(self, "test_self_clearing_requester@example.com")
		frappe.set_user(requester)
		try:
			review = frappe.get_doc("Conflict Review", review_name)
			review.decision = "Clear"
			with self.assertRaises(frappe.PermissionError):
				review.save()
		finally:
			frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value("Conflict Review", review_name, "decision"))

		reviewer = _make_user(self, "test_conflicts_reviewer@example.com", roles=["Conflicts Reviewer"])
		frappe.set_user(reviewer)
		try:
			review = frappe.get_doc("Conflict Review", review_name)
			review.decision = "Clear"
			review.save()
		finally:
			frappe.set_user("Administrator")

		decided = frappe.db.get_value(
			"Conflict Review", review_name, ["decision", "reviewed_by"], as_dict=True
		)
		self.assertEqual(decided.decision, "Clear")
		self.assertEqual(decided.reviewed_by, reviewer)

	def test_an_edit_that_leaves_the_decision_alone_is_not_blocked(self):
		client = self._make_party("Untouched Decision Client")
		adverse = self._make_party("Untouched Decision Adversary")
		intake = self._make_intake(client, adverse)
		review = self._make_review(intake, "Clear")

		requester = _make_user(self, "test_unrelated_edit_requester@example.com")
		frappe.set_user(requester)
		try:
			reloaded = frappe.get_doc("Conflict Review", review.name)
			reloaded.decision_reason = "Filed under the engagement letter."
			reloaded.save()
		finally:
			frappe.set_user("Administrator")

		self.assertEqual(
			frappe.db.get_value("Conflict Review", review.name, "decision_reason"),
			"Filed under the engagement letter.",
		)

	def test_search_provenance_is_stamped_server_side(self):
		client = self._make_party("Provenance Client")
		adverse = self._make_party("Provenance Adversary")
		intake = self._make_intake(client, adverse)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": "a-hash-the-client-made-up",
			"search_timestamp": "2000-01-01 00:00:00",
			"searched_by": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		self.assertEqual(review.party_set_hash, intake.get_party_set_hash())
		self.assertNotEqual(str(review.search_timestamp), "2000-01-01 00:00:00")

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
