# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


TRANSITIONS = {
	"Draft": {"Partner Review", "Returned"},
	"Partner Review": {"Finance Review", "Returned"},
	"Finance Review": {"Approved", "Returned"},
	"Approved": {"Converted", "Superseded"},
	"Converted": set(),
	"Returned": {"Draft"},
	"Superseded": set(),
}


class FeeNote(Document):
	def validate(self):
		if self.is_new():
			previous_status = "Draft"
			self.status = self.status or "Draft"
		else:
			previous = frappe.db.get_value("Fee Note", self.name, ["status", "approved_hash"], as_dict=True)
			previous_status = previous.status

		self.total_amount = sum(flt(row.amount) for row in self.lines)

		if previous_status != self.status:
			if self.status not in TRANSITIONS.get(previous_status, set()):
				frappe.throw(f"Cannot move Fee Note from {previous_status} to {self.status}.")
			if previous_status == "Approved" and self.compute_content_hash() != previous.approved_hash:
				frappe.throw(
					"This Fee Note has changed since it was approved; re-approve before converting or superseding."
				)
			if self.status == "Approved":
				self.approved_by = frappe.session.user
				self.approved_on = now_datetime()
				self.approved_hash = self.compute_content_hash()
				self._reserve_lines()
			if previous_status == "Approved" and self.status in ("Superseded",):
				self._release_lines()
		elif previous_status == "Approved" and not self.is_new():
			# A material edit to an already-Approved note (content changed
			# without an explicit status transition) invalidates the
			# approval -- drop back to Finance Review rather than silently
			# keeping a stale hash.
			if self.compute_content_hash() != previous.approved_hash:
				self.status = "Finance Review"
				self.approved_hash = None
				self.approved_by = None
				self.approved_on = None
				self._release_lines()

	def _reserve_lines(self):
		for row in self.lines:
			frappe.db.sql(
				"""update `tabTime Tracking` set wip_status='Reserved', fee_note=%(fee_note)s
				   where name=%(name)s and wip_status='Approved'""",
				{"fee_note": self.name, "name": row.time_entry},
			)
			claimed = frappe.db.sql("select ROW_COUNT()")[0][0]
			if not claimed:
				frappe.throw(
					f"Time entry {row.time_entry} is no longer available for billing "
					f"(already reserved, billed, or written off elsewhere)."
				)

	def _release_lines(self):
		for row in self.lines:
			frappe.db.sql(
				"""update `tabTime Tracking` set wip_status='Approved', fee_note=NULL
				   where name=%(name)s and wip_status='Reserved' and fee_note=%(fee_note)s""",
				{"name": row.time_entry, "fee_note": self.name},
			)

	def compute_content_hash(self):
		parts = sorted(
			f"{row.time_entry}:{flt(row.hours)}:{flt(row.rate)}:{flt(row.amount)}" for row in self.lines
		)
		raw = "|".join(parts) + f"|{self.matter}|total:{flt(self.total_amount)}"
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_permission_query_conditions(user=None):
	from case_management.case_management.doctype.matter.matter import get_matter_access_condition
	return get_matter_access_condition("`tabFee Note`.matter", user)


def has_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	from case_management.case_management.doctype.matter.matter import has_permission as matter_has_permission
	matter_doc = frappe.get_cached_doc("Matter", doc.matter)
	return matter_has_permission(matter_doc, user=user, permission_type=permission_type)
