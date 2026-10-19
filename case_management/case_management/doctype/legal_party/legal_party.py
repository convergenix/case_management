# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re
import frappe
from frappe.model.document import Document


def normalize_name(value):
	"""Lowercase, strip, collapse whitespace, drop punctuation — used for
	exact/normalized-name conflict matching in Intake and Conflict Review."""
	if not value:
		return ""
	value = value.lower()
	value = re.sub(r"[^\w\s]", "", value)
	value = re.sub(r"\s+", " ", value).strip()
	return value


class LegalParty(Document):
	def before_save(self):
		self.normalized_name = normalize_name(self.party_name)
