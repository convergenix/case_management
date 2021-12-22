# Copyright (c) 2013, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from frappe import _

import frappe


def execute(filters=None):
	return get_column(), get_data(filters)


def get_data(filters):
	conditions = "(1=1) "
	if filters.get('opened_from') and filters.get('opened_to'):
		conditions += " and si.posting_date  BETWEEN '{0}' and '{1}'".format(
			filters.get("opened_from"), filters.get('opened_to'))

	if filters.get('status'):
		conditions += " and matter.status = '{0}'".format(filters.get("status"))

	if filters.get('client'):
		conditions += " and matter.client = '{0}'".format(filters.get("client"))

	if filters.get('matter'):
		conditions += " and matter.name = '{0}'".format(filters.get("matter"))


	# open_date, matter, client , status , practice_area , responsible_solicitor, close_date
	sql = "select matter.open_date, matter.name, matter.client , matter.matter_information , IFNULL(si.name,'No Invoice'), " \
		  "IFNULL(si.grand_total,0),IFNULL((si.grand_total - si.outstanding_amount),0) paid, IFNULL(si.outstanding_amount,0), \
 				matter_information from `tabMatter` matter left outer join `tabSales Invoice` si" \
		  " ON(si.matter_id = matter.name) WHERE {0}"
	frappe.errprint(sql.format(conditions))

	data = frappe.db.sql(sql.format(conditions))
	return data


def get_column():
	return [
		"Open Date:Data:100",
		"Matter:Link/Matter:130",
		"Client:Link/Customer:130",
		"Description:Data:170",
		"Invoice:Data:140",
		"Invoice Amount:Currency:140",
		"Paid Amount:Currency:140",
		"Outstanding Amount:Currency:140"
	]
