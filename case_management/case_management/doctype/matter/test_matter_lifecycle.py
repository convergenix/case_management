# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, nowdate


class TestMatterLifecycle(FrappeTestCase):
	def _make_party(self, name):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
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

	def _make_practice_area(self, label):
		practice_area = frappe.get_doc({
			"doctype": "Practice Area",
			"practice_area": f"{label} Practice Area",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)
		return practice_area

	def _get_employee(self):
		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee",
				"employee_name": "Test Solicitor",
				"status": "Active",
			}).insert(ignore_mandatory=True).name
		return employee

	def _matter_base_fields(self, label):
		# Matter already has these as mandatory, native (non-custom) fields
		# unrelated to this task's lifecycle/intake-gate rework; they must be
		# supplied for any Matter.insert() to get past Frappe's mandatory check.
		practice_area = self._make_practice_area(label)
		return {
			"open_date": nowdate(),
			"practice_area": practice_area.name,
			"transaction": f"{label} Transaction",
			"responsible_solicitor": self._get_employee(),
		}

	def _make_approved_intake(self, label):
		client = self._make_party(f"{label} Client")
		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "General advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		review = frappe.get_doc({
			"doctype": "Conflict Review",
			"intake": intake.name,
			"party_set_hash": intake.get_party_set_hash(),
			"search_timestamp": now_datetime(),
			"searched_by": "Administrator",
			"decision": "Clear",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Conflict Review", review.name, force=True)

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		return intake

	def test_matter_cannot_be_opened_without_intake(self):
		customer = self._make_customer("No Intake")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"status": "Open",
			**self._matter_base_fields("No Intake"),
		})
		with self.assertRaises(frappe.ValidationError):
			matter.insert()

	def test_matter_opens_from_approved_intake_and_marks_it_converted(self):
		intake = self._make_approved_intake("Open Flow")
		customer = self._make_customer("Open Flow")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			**self._matter_base_fields("Open Flow"),
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		reloaded_intake = frappe.get_doc("Intake", intake.name)
		self.assertEqual(reloaded_intake.status, "Converted")
		self.assertEqual(reloaded_intake.converted_matter, matter.name)
		self.assertEqual(len(matter.state_log), 1)
		self.assertEqual(matter.state_log[0].new_state, "Open")

	def test_same_intake_cannot_open_a_second_matter(self):
		intake = self._make_approved_intake("Double Conversion")
		customer = self._make_customer("Double Conversion")
		first = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			**self._matter_base_fields("Double Conversion"),
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", first.name, force=True)

		second = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			**self._matter_base_fields("Double Conversion 2"),
		})
		with self.assertRaises(frappe.ValidationError):
			second.insert()

	def test_invalid_status_transition_is_rejected(self):
		intake = self._make_approved_intake("Bad Transition")
		customer = self._make_customer("Bad Transition")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			**self._matter_base_fields("Bad Transition"),
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		matter.status = "Closed"
		with self.assertRaises(frappe.ValidationError):
			matter.save()

	def test_reopen_requires_reason(self):
		intake = self._make_approved_intake("Reopen Flow")
		customer = self._make_customer("Reopen Flow")
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			**self._matter_base_fields("Reopen Flow"),
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		matter.status = "Active"
		matter.save()
		matter.status = "Closing"
		matter.save()
		matter.status = "Closed"
		matter.save()

		matter.status = "Active"
		with self.assertRaises(frappe.ValidationError):
			matter.save()

		matter.reload()
		matter.status = "Active"
		matter.reopen_reason = "Client reinstated the engagement."
		matter.save()
		self.assertEqual(matter.status, "Active")
