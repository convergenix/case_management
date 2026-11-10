# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt

PRIVILEGED_ROLES = {"Managing Partner", "System Manager"}


class PurchaseRequisition(Document):
	def before_insert(self):
		# Desk Amend copies no_copy fields too, so an amendment would otherwise
		# inherit the cancelled original's decision.
		if self.amended_from:
			self.approval_status = "Pending"
			self.rejection_reason = None

	def validate(self):
		self._compute_amounts()
		self._validate_requester_identity()
		self._validate_independence()
		self._validate_approver_matter_access()
		self._validate_approval_transition()

	def before_update_after_submit(self):
		# Approving/rejecting a submitted requisition only touches
		# allow_on_submit fields, so Frappe routes the save through the
		# "update_after_submit" action rather than "save" -- validate() is
		# never called on that path, so the approval gate has to live here.
		self._validate_approval_transition()

	def before_cancel(self):
		if _is_privileged():
			return
		if frappe.session.user not in (_user_of(self.employee), _user_of(self.approver)):
			frappe.throw(
				"Only the requester, the named Approver, or a Managing Partner/System Manager "
				"can cancel this requisition."
			)

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
		if not self.employee or _is_privileged():
			return
		if frappe.session.user != _user_of(self.employee):
			frappe.throw(
				"You can only create or save a Purchase Requisition naming yourself as the "
				"Employee, unless you hold the Managing Partner or System Manager role."
			)

	def _validate_independence(self):
		if not (self.employee and self.approver) or _is_privileged():
			return
		# One person can hold several Employee records sharing a user_id (e.g. a
		# Left record plus a rehire), so distinct Link values prove nothing.
		requester_user = _user_of(self.employee)
		same_person = self.employee == self.approver or (
			requester_user and requester_user == _user_of(self.approver)
		)
		if same_person:
			frappe.throw(
				"The requester cannot also be the approver on the same requisition, "
				"unless you hold the Managing Partner or System Manager role."
			)

	def _validate_approver_matter_access(self):
		if not (self.matter and self.approver):
			return
		from case_management.case_management.doctype.matter.matter import has_permission as matter_has_permission
		matter_doc = frappe.get_cached_doc("Matter", self.matter)
		if not matter_doc.is_restricted:
			return
		approver_user = _user_of(self.approver)
		# matter_has_permission falls back to the session user when user is None.
		if not approver_user or not matter_has_permission(matter_doc, user=approver_user):
			frappe.throw(
				f"The Approver has no access to restricted Matter {self.matter}; choose an Approver "
				"on that matter's team."
			)

	def _validate_approval_transition(self):
		if self.is_new():
			previous_approval_status, previous_rejection_reason = "Pending", None
		else:
			previous_approval_status, previous_rejection_reason = frappe.db.get_value(
				"Purchase Requisition", self.name, ["approval_status", "rejection_reason"]
			)

		if previous_approval_status == self.approval_status:
			decided = previous_approval_status in ("Approved", "Rejected")
			reason_changed = (self.rejection_reason or "") != (previous_rejection_reason or "")
			if decided and reason_changed and not _is_privileged():
				frappe.throw(
					f"Purchase Requisition is already {previous_approval_status}; its Rejection Reason "
					"can only be changed by a Managing Partner or System Manager."
				)
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

		if not _is_privileged():
			if frappe.session.user != _user_of(self.approver):
				frappe.throw(
					"Only the named Approver (or a Managing Partner/System Manager) "
					"can approve or reject this requisition."
				)
			if frappe.session.user == _user_of(self.employee):
				frappe.throw("You cannot approve or reject your own Purchase Requisition.")

		if self.approval_status == "Rejected" and not self.rejection_reason:
			frappe.throw(
				"Rejecting a Purchase Requisition requires a reason in 'Rejection Reason'."
			)


def _is_privileged():
	return bool(PRIVILEGED_ROLES & set(frappe.get_roles(frappe.session.user)))


def _user_of(employee):
	return frappe.db.get_value("Employee", employee, "user_id") if employee else None


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
