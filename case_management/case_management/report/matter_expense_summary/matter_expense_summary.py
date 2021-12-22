# Copyright (c) 2013, Anthony Emmanuel mymi14s@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from frappe import _

import frappe


def execute(filters=None):
    return get_column(), get_data(filters)


def get_data(filters):
    # conditions = "(1=1) "
    conditions = " "

    if filters.get('opened_from') and filters.get('opened_to'):
        conditions += " AND `tabExpense Claim`.posting_date  BETWEEN '{0}' AND '{1}'".format(
            filters.get("opened_from"), filters.get('opened_to'))

    if filters.get('client'):
        conditions += " AND `tabMatter`.client = '{0}'".format(filters.get("client"))
    if filters.get('matter'):
        conditions += " AND `tabMatter`.name = '{0}'".format(filters.get("matter"))
    if filters.get('employee'):
        conditions += " AND `tabExpense Claim`.employee = '{0}'".format(filters.get("employee"))
    if filters.get('expense'):
        conditions += " AND `tabExpense Claim`.name = '{0}'".format(filters.get("expense"))

    # open_date, matter, client , status , practice_area , close_date
    sql = """SELECT `tabExpense Claim`.posting_date, `tabMatter`.name, `tabMatter`.client, 
    		`tabExpense Claim`.employee, `tabExpense Claim`.name, `tabExpense Claim`.grand_total, 
    		`tabExpense Claim`.total_advance_amount, `tabExpense Claim`.total_claimed_amount, 
    		`tabExpense Claim`.total_amount_reimbursed, `tabExpense Claim`.status FROM `tabMatter` 
    		INNER JOIN `tabExpense Claim` ON `tabExpense Claim`.matter_id=`tabMatter`.name {0};"""
    data = frappe.db.sql(sql.format(conditions))
    return data


def get_column():
    # ["Link:Link/Accident:150", "Data:Data:200", "Currency:Currency:100", "Float:Float:100"]
    return [
        _("Expense Date") + ":Data:100",
        "Matter ID:Link/Matter:120",
        "Client:Link/Customer:150",
        "Employee:Link/Employee:100",
        "Expense ID:Link/Expense Claim:120",
        "Total Amount:Currency:100",
        "Advance Amount:Currency:100",
        "Claimed Amount:Currency:100",
        "Reimbursed Amount:Currency:100",
        "Status:Data:70",
    ]













# def execute(filters=None):
# 	return get_column(), get_data(filters)


# def get_data(filters):
# 	# Expense Claims|
# 	pi_conditions = ec_conditions = "(1=1) "
# 	if filters.get('date_from') and filters.get('date_to'):
# 		ec_conditions += " and posting_date  BETWEEN DATE('{0}') and DATE('{1}')" .format(filters.get("date_from"),filters.get('date_to'))
# 		pi_conditions += " and posting_date  BETWEEN DATE('{0}') and DATE('{1}')" .format(filters.get("date_from"),filters.get('date_to'))

# 	if filters.get('matter'):
# 		ec_conditions += " and matter = '{0}'" .format(filters.get("matter"))
# 		pi_conditions += " and matter = '{0}'" .format(filters.get("matter"))


# 	# Expense Claims
# 	sql = "select posting_date, matter, name, remark,total_claimed_amount from `tabExpense Claim` WHERE {0} and (docstatus = 1 and status='Paid')"
# 	ec_sql = sql.format(ec_conditions)

# 	# Purchase Invoice
# 	sql = "select posting_date, matter, name, supplier, base_grand_total from `tabPurchase Invoice` WHERE {0} and (docstatus = 1 and status='Paid')"
# 	pi_sql = sql.format(pi_conditions)

# 	data = frappe.db.sql("{0} UNION {1}".format(ec_sql, pi_sql))
# 	return  data


# def get_column():
# 	# Examples:
# 	# "Link:Link/Accident:150", "Data:Data:200", "Currency:Currency:100", "Float:Float:100"
# 	return [
# 		"Transaction Date:Date:100",
# 		"Matter:Link/Matter:100",
# 		"Document ID:Data:150",
# 		"Description:Data:250",
# 		"Amount:Currency:150",
# 	]
