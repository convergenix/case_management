# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime
from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search


class TestM1Acceptance(FrappeTestCase):
	def _make_party(self, name, identifier=None):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
			"identifier": identifier,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def _make_customer(self, label):
		# ignore_mandatory works around a pre-existing, unrelated broken Custom
		# Field ("Customer-custom_crm_id", reqd=1, no default) on this site that
		# would otherwise block creation of any Customer record.
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": f"{label} Customer",
			"customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		return customer

	def test_stale_clearance_blocks_matter_opening_after_party_set_change(self):
		client = self._make_party("Stale Flow Client")
		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		self.assertEqual(intake.status, "Approved")

		new_adverse = self._make_party("Newly Added Adversary")
		intake.append("parties", {"legal_party": new_adverse.name, "role": "Adverse Party"})
		intake.save()
		self.assertEqual(intake.status, "Under Review")

		customer = self._make_customer("Stale Flow")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
		})
		with self.assertRaises(frappe.ValidationError):
			matter.insert()

	def test_direct_insert_cannot_bypass_intake_gate(self):
		customer = self._make_customer("Bypass Attempt")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"status": "Open",
		})
		with self.assertRaises(frappe.ValidationError):
			matter.insert(ignore_permissions=True)

	def test_restricted_conflict_match_does_not_leak_to_requester(self):
		existing = self._make_party("Confidential Existing Party", identifier="RC-9999")
		client = self._make_party("Discloser Client")
		adverse = self._make_party("Disclosure Test Adversary", identifier="RC-9999")

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

		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		self.assertTrue(any(row.legal_party == existing.name for row in review.matches))

		review.decision = "Restricted Match - Escalated"
		review.save()

		from case_management.case_management.doctype.conflict_review.conflict_review import has_permission
		self.assertFalse(has_permission(review, user="test_requester_no_access@example.com"))
