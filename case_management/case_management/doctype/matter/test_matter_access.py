# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, nowdate


class TestMatterAccessControl(FrappeTestCase):
	def setUp(self):
		if not frappe.db.exists("Role", "Conflicts Reviewer"):
			frappe.get_doc({"doctype": "Role", "role_name": "Conflicts Reviewer"}).insert(
				ignore_permissions=True
			)

	def _make_party(self, name):
		party = frappe.get_doc({
			"doctype": "Legal Party",
			"party_name": name,
			"party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", party.name, force=True)
		return party

	def _make_customer(self, label):
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

	def _make_matter_owned_by(self, user, label):
		# Mirrors the ownership dance explained in
		# test_restricted_matter_excluded_from_list_for_unrelated_user: the user
		# opens the matter themselves while it is still unrestricted, so the only
		# thing that changes between the "before" and "after" assertions is
		# is_restricted.
		intake = self._make_approved_intake(label)
		customer = self._make_customer(label)
		frappe.set_user(user)
		try:
			matter = frappe.get_doc({
				"doctype": "Matter",
				"client": customer.name,
				"intake": intake.name,
				"status": "Open",
				"is_restricted": 0,
				**self._matter_base_fields(label),
			}).insert()
		finally:
			frappe.set_user("Administrator")
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter

	def _make_outsider(self, email):
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": "Outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Lawyer Manager"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", email, force=True)
		return email

	def _make_employee_for(self, user, label):
		existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
		if existing:
			return frappe.get_doc("Employee", existing)
		template = frappe.get_doc("Employee", self._get_employee())
		employee = frappe.get_doc({
			"doctype": "Employee",
			"employee_name": label,
			"status": "Active",
			"user_id": user,
			"company": template.company,
			"date_of_joining": template.date_of_joining,
			"date_of_birth": template.date_of_birth,
			"gender": template.gender,
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Employee", employee.name, force=True)
		return employee

	def test_known_limitation_team_member_without_ownership_cannot_see_matter(self):
		"""Documented, known gap — not a regression.

		Frappe ANDs role-level DocPerm conditions with
		permission_query_conditions. Matter's pre-existing DocPerm for "Lawyer
		Manager" carries if_owner=1, and the only unrestricted-read role,
		"Partners", is disabled in this bench's Role data (User.validate()
		strips disabled roles). So a user who is on a matter's team but did not
		personally create it is filtered out by the base role permission before
		is_restricted or team membership is ever consulted, which makes the
		Matter Team Item allowance this branch built unreachable in practice.

		The DENY side of the ethical wall works; the ALLOW side does not.
		Closing it means removing if_owner from Lawyer Manager's DocPerm or
		enabling the Partners role — base permission configuration with
		app-wide blast radius, left for a human decision. See the M1
		access-control section of the R0 foundation design spec.
		"""
		team_user = self._make_outsider("test_team_member_non_owner@example.com")
		team_employee = self._make_employee_for(team_user, "Team Member Under Test")

		intake = self._make_approved_intake("Team Allowance")
		customer = self._make_customer("Team Allowance")
		base_fields = self._matter_base_fields("Team Allowance")
		# Must not be the team member, or the responsible_solicitor path would
		# grant the access this test is showing to be unreachable.
		base_fields["responsible_solicitor"] = frappe.db.get_value(
			"Employee", {"name": ["!=", team_employee.name]}, "name"
		)
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"is_restricted": 1,
			"legal_team": [{
				"employee": team_employee.name,
				"employee_type": frappe.db.get_value("Designation", {}, "name"),
			}],
			**base_fields,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		self.assertNotEqual(matter.owner, team_user)
		self.assertNotEqual(matter.responsible_solicitor, team_employee.name)

		open_intake = self._make_approved_intake("Team Allowance Control")
		open_customer = self._make_customer("Team Allowance Control")
		control_fields = self._matter_base_fields("Team Allowance Control")
		control_fields["responsible_solicitor"] = base_fields["responsible_solicitor"]
		unrestricted = frappe.get_doc({
			"doctype": "Matter",
			"client": open_customer.name,
			"intake": open_intake.name,
			"status": "Open",
			"is_restricted": 0,
			**control_fields,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", unrestricted.name, force=True)

		from case_management.case_management.doctype.matter.matter import has_permission
		self.assertTrue(has_permission(matter, user=team_user))

		frappe.set_user(team_user)
		try:
			visible = frappe.get_list(
				"Matter", filters={"name": ["in", [matter.name, unrestricted.name]]}, pluck="name"
			)
		finally:
			frappe.set_user("Administrator")

		self.assertNotIn(matter.name, visible)
		# Not caused by is_restricted: a matter they do not own is invisible either way.
		self.assertNotIn(unrestricted.name, visible)

	def test_responsible_solicitor_can_see_their_own_restricted_matter(self):
		solicitor_user = self._make_outsider("test_responsible_solicitor@example.com")
		employee = self._make_employee_for(solicitor_user, "Responsible Solicitor Under Test")

		intake = self._make_approved_intake("Solicitor Access")
		customer = self._make_customer("Solicitor Access")
		base_fields = self._matter_base_fields("Solicitor Access")
		base_fields["responsible_solicitor"] = employee.name
		matter = frappe.get_doc({
			"doctype": "Matter",
			"client": customer.name,
			"intake": intake.name,
			"status": "Open",
			"is_restricted": 1,
			**base_fields,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		self.assertFalse(
			frappe.db.exists("Matter Team Item", {"parent": matter.name, "employee": employee.name})
		)

		from case_management.case_management.doctype.matter.matter import (
			get_permission_query_conditions,
			has_permission,
		)
		self.assertTrue(has_permission(matter, user=solicitor_user))
		self.assertIn(
			matter.name,
			frappe.db.sql_list(
				"select name from `tabMatter` where name = %s and {0}".format(
					get_permission_query_conditions(solicitor_user)
				),
				matter.name,
			),
		)

	def test_restricted_matter_excluded_from_calendar_events(self):
		from case_management.case_management.doctype.matter.matter import get_events

		outsider = self._make_outsider("test_calendar_outsider@example.com")
		matter = self._make_matter_owned_by(outsider, "Restricted Calendar")
		start = add_days(nowdate(), -1)
		end = add_days(nowdate(), 1)

		frappe.set_user(outsider)
		try:
			before = [row.name for row in get_events(start, end)]
			self.assertIn(matter.name, before)
		finally:
			frappe.set_user("Administrator")

		matter.reload()
		matter.is_restricted = 1
		matter.save()

		frappe.set_user(outsider)
		try:
			after = [row.name for row in get_events(start, end)]
			self.assertNotIn(matter.name, after)
		finally:
			frappe.set_user("Administrator")

	def test_restricted_matter_excluded_from_matter_status_report(self):
		from case_management.case_management.report.matter_status_report.matter_status_report import execute

		outsider = self._make_outsider("test_report_outsider@example.com")
		matter = self._make_matter_owned_by(outsider, "Restricted Report")
		filters = {"opened_from": add_days(nowdate(), -1), "opened_to": add_days(nowdate(), 1)}

		frappe.set_user(outsider)
		try:
			before = [row[1] for row in execute(filters)[1]]
			self.assertIn(matter.name, before)
		finally:
			frappe.set_user("Administrator")

		matter.reload()
		matter.is_restricted = 1
		matter.save()

		frappe.set_user(outsider)
		try:
			after = [row[1] for row in execute(filters)[1]]
			self.assertNotIn(matter.name, after)
		finally:
			frappe.set_user("Administrator")

	def test_restricted_matter_excluded_from_list_for_unrelated_user(self):
		# Matter's own pre-existing DocPerm for "Lawyer Manager" has if_owner=1
		# (that role can only read Matters it personally owns), and "Partners"
		# (unrestricted read) cannot be assigned to any user because it's marked
		# disabled in this bench's Role data (User.validate() silently strips
		# disabled roles on every save). So: the outsider creates the matter
		# themselves WHILE IT'S NOT YET RESTRICTED (has_permission allows
		# creating a non-restricted matter, and if_owner is satisfied since
		# they'll own it) — then Administrator flips is_restricted=1 on the
		# existing document afterward (Administrator bypasses all permission
		# checks). This isolates exactly what we're testing: does is_restricted
		# exclude the outsider via the real permission-checked frappe.get_list
		# path, even though they still own the record and have if_owner read
		# access to their own documents in general.
		outsider = "test_outsider_user@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc({
				"doctype": "User",
				"email": outsider,
				"first_name": "Outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Lawyer Manager"}],
			}).insert(ignore_permissions=True)
			self.addCleanup(frappe.delete_doc, "User", outsider, force=True)

		intake = self._make_approved_intake("Restricted List")
		customer = self._make_customer("Restricted List")

		frappe.set_user(outsider)
		try:
			matter = frappe.get_doc({
				"doctype": "Matter",
				"client": customer.name,
				"intake": intake.name,
				"status": "Open",
				"is_restricted": 0,
				**self._matter_base_fields("Restricted List"),
			}).insert()
		finally:
			frappe.set_user("Administrator")
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		frappe.set_user(outsider)
		try:
			visible_before = frappe.get_list("Matter", filters={"name": matter.name}, pluck="name")
			self.assertIn(matter.name, visible_before)
		finally:
			frappe.set_user("Administrator")

		matter.reload()
		matter.is_restricted = 1
		matter.save()

		frappe.set_user(outsider)
		try:
			visible_after = frappe.get_list("Matter", filters={"name": matter.name}, pluck="name")
			self.assertNotIn(matter.name, visible_after)
		finally:
			frappe.set_user("Administrator")

		from case_management.case_management.doctype.matter.matter import has_permission
		self.assertFalse(has_permission(matter, user=outsider))
		self.assertTrue(has_permission(matter, user="Administrator"))
