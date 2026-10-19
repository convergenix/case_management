# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate, now_datetime


class TestObligationReminder(FrappeTestCase):
	def _make_active_obligation(self, due_date=None):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Reminder Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Reminder Test Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Reminder Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Reminder Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Reminder Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		obligation = frappe.get_doc({
			"doctype": "Legal Obligation", "matter": matter.name, "obligation_type": "Filing Deadline",
			"due_date": due_date or add_days(nowdate(), 14), "responsible_user": "Administrator",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)

		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		return obligation

	def _make_plain_user(self, email):
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": "Reminder Test",
				"send_welcome_email": 0,
				"roles": [{"role": "Lawyer Manager"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", email, force=True)
		return email

	def test_restricted_matter_hides_its_reminders_from_an_unrelated_user(self):
		outsider = self._make_plain_user("reminder_access_outsider@example.com")
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		frappe.set_user(outsider)
		try:
			visible_before = frappe.get_list(
				"Obligation Reminder", filters={"name": ["in", reminders]}, pluck="name"
			)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(sorted(visible_before), sorted(reminders))

		matter = frappe.get_doc("Matter", obligation.matter)
		matter.is_restricted = 1
		matter.save()

		frappe.set_user(outsider)
		try:
			visible_after = frappe.get_list(
				"Obligation Reminder", filters={"name": ["in", reminders]}, pluck="name"
			)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(visible_after, [])

	def test_activating_obligation_generates_default_reminders(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all(
			"Obligation Reminder", filters={"obligation": obligation.name}, fields=["name", "status", "recipient"]
		)
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r.name, force=True)
		self.assertEqual(len(reminders), 2)
		self.assertTrue(all(r.status == "Queued" for r in reminders))
		self.assertTrue(all(r.recipient == "Administrator" for r in reminders))

	def test_activation_is_idempotent_no_duplicate_reminders(self):
		obligation = self._make_active_obligation()
		reminders_first = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name})
		for r in reminders_first:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r.name, force=True)

		obligation.source_reference = "Updated via an unrelated field edit"
		obligation.save()

		reminders_second = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name})
		self.assertEqual(len(reminders_first), len(reminders_second))

	def test_acknowledge_requires_delivered_status(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import acknowledge
		with self.assertRaises(frappe.ValidationError):
			acknowledge(reminders[0])

		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")
		result = acknowledge(reminders[0])
		self.assertEqual(result, reminders[0])
		self.assertEqual(frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Acknowledged")

	def test_completing_an_obligation_supersedes_its_queued_reminders(self):
		obligation = self._make_active_obligation()
		reminders = frappe.get_all(
			"Obligation Reminder",
			filters={"obligation": obligation.name, "status": "Queued"},
			pluck="name",
		)
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		self.assertEqual(len(reminders), 2)

		obligation.status = "Completed"
		obligation.completion_evidence = "Filed stamped copy attached"
		obligation.save()

		for r in reminders:
			self.assertEqual(frappe.db.get_value("Obligation Reminder", r, "status"), "Superseded")

	def test_only_the_recipient_can_acknowledge_a_reminder(self):
		outsider = self._make_plain_user("reminder_ack_outsider@example.com")
		obligation = self._make_active_obligation()
		reminders = frappe.get_all("Obligation Reminder", filters={"obligation": obligation.name}, pluck="name")
		for r in reminders:
			self.addCleanup(frappe.delete_doc, "Obligation Reminder", r, force=True)
		frappe.db.set_value("Obligation Reminder", reminders[0], "status", "Delivered")

		from case_management.case_management.doctype.obligation_reminder.obligation_reminder import acknowledge
		frappe.set_user(outsider)
		try:
			with self.assertRaises(frappe.ValidationError) as caught:
				acknowledge(reminders[0])
		finally:
			frappe.set_user("Administrator")
		self.assertIn("Only the recipient", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Obligation Reminder", reminders[0], "status"), "Delivered")

	def test_direct_creation_with_invalid_status_is_rejected(self):
		obligation = self._make_active_obligation()
		reminder_name = None
		try:
			reminder = frappe.get_doc({
				"doctype": "Obligation Reminder",
				"obligation": obligation.name,
				"scheduled_for": now_datetime(),
				"recipient": "Administrator",
				"status": "Completed",
			})
			reminder.insert()
			reminder_name = reminder.name
			self.fail("Expected ValidationError when creating Obligation Reminder with status=Completed")
		except frappe.ValidationError as e:
			self.assertIn("Cannot move Obligation Reminder from Queued to Completed", str(e))
		finally:
			if reminder_name:
				self.addCleanup(frappe.delete_doc, "Obligation Reminder", reminder_name, force=True)
