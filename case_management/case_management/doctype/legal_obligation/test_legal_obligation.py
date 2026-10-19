# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestLegalObligation(FrappeTestCase):
	def _make_matter_and_obligation(self, due_date=None, **overrides):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Obligation Test Customer",
			"customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "Obligation Test Client",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Advisory",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Obligation Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Obligation Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"open_date": nowdate(),
			"practice_area": practice_area.name,
			"transaction": "Obligation Test Transaction",
			"responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		fields = {
			"doctype": "Legal Obligation",
			"matter": matter.name,
			"obligation_type": "Filing Deadline",
			"due_date": due_date or add_days(nowdate(), 14),
			"responsible_user": "Administrator",
		}
		fields.update(overrides)
		obligation = frappe.get_doc(fields).insert()
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True)
		return obligation

	def _make_plain_user(self, email):
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": "Obligation Test",
				"send_welcome_email": 0,
				"roles": [{"role": "Lawyer Manager"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", email, force=True)
		return email

	def test_new_obligation_defaults_to_proposed(self):
		obligation = self._make_matter_and_obligation()
		self.assertEqual(obligation.status, "Proposed")

	def test_critical_obligation_requires_verifier_before_verified(self):
		obligation = self._make_matter_and_obligation(is_critical=1)
		obligation.status = "Verified"
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

	def test_rescheduling_active_obligation_requires_reason_and_preserves_old_date(self):
		obligation = self._make_matter_and_obligation(is_critical=0)
		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()

		old_due_date = obligation.due_date
		obligation.due_date = add_days(old_due_date, 7)
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

		obligation.reload()
		obligation.due_date = add_days(old_due_date, 7)
		obligation.reschedule_reason = "Court granted an extension"
		obligation.save()
		self.assertEqual(str(obligation.previous_due_date), str(old_due_date))

	def test_completing_requires_evidence(self):
		obligation = self._make_matter_and_obligation()
		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()
		obligation.status = "Completed"
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

		obligation.reload()
		obligation.status = "Completed"
		obligation.completion_evidence = "Filed stamped copy attached"
		obligation.save()
		self.assertEqual(obligation.status, "Completed")
		self.assertEqual(obligation.completed_by, "Administrator")

	def test_direct_creation_with_verified_critical_without_verifier_fails(self):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Direct Create Test Customer",
			"customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "Direct Create Test Client",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Advisory",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Direct Create Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Direct Create Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"open_date": nowdate(),
			"practice_area": practice_area.name,
			"transaction": "Direct Create Test Transaction",
			"responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		fields = {
			"doctype": "Legal Obligation",
			"matter": matter.name,
			"obligation_type": "Filing Deadline",
			"due_date": add_days(nowdate(), 14),
			"responsible_user": "Administrator",
			"status": "Verified",
			"is_critical": 1,
		}
		obligation = frappe.get_doc(fields)
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True, ignore_missing=True)
		with self.assertRaises(frappe.ValidationError):
			obligation.insert()

	def test_direct_creation_with_active_status_fails(self):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Active Create Test Customer",
			"customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": "Active Create Test Client",
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake",
			"proposed_client": client.name,
			"scope": "Advisory",
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

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Active Create Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": "Active Create Test Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"open_date": nowdate(),
			"practice_area": practice_area.name,
			"transaction": "Active Create Test Transaction",
			"responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		fields = {
			"doctype": "Legal Obligation",
			"matter": matter.name,
			"obligation_type": "Filing Deadline",
			"due_date": add_days(nowdate(), 14),
			"responsible_user": "Administrator",
			"status": "Active",
		}
		obligation = frappe.get_doc(fields)
		self.addCleanup(frappe.delete_doc, "Legal Obligation", obligation.name, force=True, ignore_missing=True)
		with self.assertRaises(frappe.ValidationError):
			obligation.insert()

	def test_direct_creation_with_verified_non_critical_succeeds(self):
		obligation = self._make_matter_and_obligation(status="Verified", is_critical=0)
		self.assertEqual(obligation.status, "Verified")
		self.assertEqual(obligation.verified_by, "Administrator")

	def test_marking_an_already_verified_obligation_critical_requires_a_verifier(self):
		obligation = self._make_matter_and_obligation(is_critical=0)
		obligation.status = "Verified"
		obligation.save()

		obligation.is_critical = 1
		with self.assertRaises(frappe.ValidationError):
			obligation.save()

	def test_only_the_named_verifier_can_perform_the_verified_transition(self):
		verifier = self._make_plain_user("obligation_named_verifier@example.com")
		impostor = self._make_plain_user("obligation_impostor@example.com")
		obligation = self._make_matter_and_obligation(is_critical=1, verifier=verifier)

		obligation.status = "Verified"
		frappe.set_user(impostor)
		try:
			with self.assertRaises(frappe.ValidationError) as caught:
				obligation.save()
		finally:
			frappe.set_user("Administrator")
		self.assertIn("Only the named Verifier", str(caught.exception))

	def test_verifier_must_be_independent_of_the_owner(self):
		obligation = self._make_matter_and_obligation(is_critical=1, verifier="Administrator")
		self.assertEqual(obligation.responsible_user, "Administrator")

		obligation.status = "Verified"
		with self.assertRaises(frappe.ValidationError) as caught:
			obligation.save()
		self.assertIn("independent", str(caught.exception))

	def test_second_reschedule_requires_its_own_fresh_reason(self):
		obligation = self._make_matter_and_obligation(is_critical=0)
		obligation.status = "Verified"
		obligation.save()
		obligation.status = "Active"
		obligation.save()

		original_due_date = obligation.due_date
		obligation.due_date = add_days(original_due_date, 7)
		obligation.reschedule_reason = "Court granted an extension"
		obligation.save()
		self.assertFalse(frappe.db.get_value("Legal Obligation", obligation.name, "reschedule_reason"))

		obligation.due_date = add_days(original_due_date, 14)
		with self.assertRaises(frappe.ValidationError):
			obligation.save()
