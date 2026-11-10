# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PurchaseRequisition(Document):
	def validate(self):
		self._compute_amounts()

	def _compute_amounts(self):
		for row in self.items:
			row.estimated_amount = flt(row.qty) * flt(row.estimated_rate)
		self.total_estimated_amount = sum(flt(row.estimated_amount) for row in self.items)
