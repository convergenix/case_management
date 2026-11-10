# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt

PRIVILEGED_ROLES = {"Managing Partner", "System Manager"}


class PurchaseRequisition(Document):
	def validate(self):
		self._compute_amounts()
		self._validate_requester_identity()
		self._validate_independence()
		self._validate_approval_transition()

	def before_update_after_submit(self):
		# Approving/rejecting a submitted requisition only touches
		# allow_on_submit fields, so Frappe routes the save through the
		# "update_after_submit" action rather than "save" -- validate() is
		# never called on that path, so the approval gate has to live here.
		self._validate_approval_transition()

	def _compute_amounts(self):
		for row in self.items:
			row.estimated_amount = flt(row.qty) * flt(row.estimated_rate)
		self.total_estimated_amount = sum(flt(row.estimated_amount) for row in self.items)

	def _validate_requester_identity(self):
		# employee != approver alone proves nothing if employee itself can be
		# set to an arbitrary Employee -- an ordinary user may only name
		# themselves as the requester; a privileged user may submit on
		# someone else's behalf (e.g. an assistant entering a request for an
		# executive).
		if not self.employee:
			return
		if PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user)):
			return
		requester_user = frappe.db.get_value("Employee", self.employee, "user_id")
		if frappe.session.user != requester_user:
			frappe.throw(
				"You can only create or save a Purchase Requisition naming yourself as the "
				"Employee, unless you hold the Managing Partner or System Manager role."
			)

	def _validate_independence(self):
		if self.employee and self.approver and self.employee == self.approver:
			if not (PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user))):
				frappe.throw(
					"The requester cannot also be the approver on the same requisition, "
					"unless you hold the Managing Partner or System Manager role."
				)

	def _validate_approval_transition(self):
		previous_approval_status = "Pending" if self.is_new() else frappe.db.get_value(
			"Purchase Requisition", self.name, "approval_status"
		)

		if previous_approval_status == self.approval_status:
			return

		if previous_approval_status in ("Approved", "Rejected"):
			frappe.throw(
				f"Purchase Requisition is already {previous_approval_status} and cannot be changed."
			)

		if self.docstatus != 1:
			frappe.throw(
				"A Purchase Requisition must be submitted before it can be approved or rejected."
			)

		if self.approval_status not in ("Approved", "Rejected"):
			frappe.throw(
				f"Cannot move Purchase Requisition from {previous_approval_status} to {self.approval_status}."
			)

		approver_user = frappe.db.get_value("Employee", self.approver, "user_id")
		if frappe.session.user != approver_user:
			if not (PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user))):
				frappe.throw(
					"Only the named Approver (or a Managing Partner/System Manager) "
					"can approve or reject this requisition."
				)

		if self.approval_status == "Rejected" and not self.rejection_reason:
			frappe.throw(
				"Rejecting a Purchase Requisition requires a reason in 'Rejection Reason'."
			)


def get_permission_query_conditions(user=None):
	from case_management.case_management.doctype.matter.matter import get_matter_access_condition
	return get_matter_access_condition("`tabPurchase Requisition`.matter", user)


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	if not doc.matter:
		return True
	from case_management.case_management.doctype.matter.matter import has_permission as matter_has_permission
	matter_doc = frappe.get_cached_doc("Matter", doc.matter)
	return matter_has_permission(matter_doc, user=user, permission_type=permission_type)
