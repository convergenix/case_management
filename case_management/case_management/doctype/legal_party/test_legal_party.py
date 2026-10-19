# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestLegalParty(FrappeTestCase):
	def test_normalized_name_is_computed_on_save(self):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "  Acme   Holdings, LLC ",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)

		self.assertEqual(party.normalized_name, "acme holdings llc")

	def test_linked_customer_is_not_auto_populated(self):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "Jane Doe",
			"party_type": "Person",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)

		self.assertFalse(party.linked_customer)
