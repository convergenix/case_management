# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestIntake(FrappeTestCase):
	def _make_party(self, name):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def test_requires_a_proposed_client_party_row(self):
		client = self._make_party("Test Client Co")

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [
				{"legal_party": client.name, "role": "Affiliate"},
			],
		})
		with self.assertRaises(frappe.ValidationError):
			intake.insert()

	def test_party_set_hash_is_stable_for_same_parties(self):
		client = self._make_party("Hash Test Client")
		adverse = self._make_party("Hash Test Adversary")

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

		first_hash = intake.get_party_set_hash()
		reloaded = frappe.get_doc("Intake", intake.name)
		self.assertEqual(first_hash, reloaded.get_party_set_hash())

	def test_cannot_approve_without_clear_conflict_review(self):
		client = self._make_party("Gate Test Client")

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [
				{"legal_party": client.name, "role": "Proposed Client"},
			],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			intake.save()
