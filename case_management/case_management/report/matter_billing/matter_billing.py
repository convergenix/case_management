# Copyright (c) 2020, Anthony Emmanuel mymi14s@gmail.com and contributors
# For license information, please see license.txt

# from __future__ import unicode_literals
# # import frappe

# def execute(filters=None):
# 	columns, data = [], []
# 	return columns, data


# Copyright (c) 2013, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

# from __future__ import unicode_literals
# from frappe import _

# import frappe


# def execute(filters=None):
#     return get_column(), get_data(filters)


# def get_data(filters):
#     # conditions = "(1=1) "
#     conditions = " "

#     if filters.get('opened_from') and filters.get('opened_to'):
#         conditions += " AND `tabMatter`.open_date  BETWEEN '{0}' AND '{1}'".format(
#             filters.get("opened_from"), filters.get('opened_to'))

#     if filters.get('client'):
#         conditions += " AND `tabMatter`.client = '{0}'".format(filters.get("client"))
#     if filters.get('matter'):
#         conditions += " AND `tabMatter`.name = '{0}'".format(filters.get("matter"))

#     # open_date, matter, client , status , practice_area , close_date
#     sql = """SELECT `tabMatter`.open_date, `tabMatter`.name, `tabMatter`.client, `tabSales Invoice`.name, 
#     		`tabSales Invoice`.grand_total, `tabSales Invoice`.status, `tabSales Invoice`.total_advance, 
#     		`tabSales Invoice`.outstanding_amount FROM `tabMatter` INNER JOIN `tabSales Invoice` ON 
#     		`tabMatter`.name=`tabSales Invoice`.matter_id {0};"""
#     data = frappe.db.sql(sql.format(conditions))
#     return data


# def get_column():
#     # ["Link:Link/Accident:150", "Data:Data:200", "Currency:Currency:100", "Float:Float:100"]
#     return [
#         _("Open Date") + ":Data:100",
#         "Matter:Link/Matter:120",
#         "Client:Link/Customer:200",
#         "Invoice:Link/Sales Invoice:120",
#         "Invoice Amount:Currency:100",
#         "Invoice Status:Data:70",
#         "Advance Amount:Currency:100",
#         "Outstanding Amount:Currency:100",
#         # "Close Date:Date:100",
#         # "Responsible Solicitor:Link/Employee:100",
#         # "Information:Data:200",
#     ]


from __future__ import unicode_literals
from frappe import _
import frappe

def execute(filters=None):
    return get_columns(), get_data(filters)

def get_data(filters):
    conditions = []
    values = {}

    if filters.get('opened_from') and filters.get('opened_to'):
        conditions.append("m.open_date BETWEEN %(opened_from)s AND %(opened_to)s")
        values["opened_from"] = filters.get("opened_from")
        values["opened_to"] = filters.get("opened_to")

    if filters.get('client'):
        conditions.append("m.client = %(client)s")
        values["client"] = filters.get("client")

    if filters.get('matter'):
        conditions.append("m.name = %(matter)s")
        values["matter"] = filters.get("matter")

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    sql = f"""
        SELECT 
            m.open_date,
            m.name AS matter,
            m.client,
            si.name AS invoice,
            si.grand_total,
            si.status,
            si.total_advance,
            si.outstanding_amount
        FROM `tabMatter` m
        INNER JOIN `tabSales Invoice` si 
            ON m.name = si.matter_id
        {where_clause}
        ORDER BY m.open_date DESC
    """

    return frappe.db.sql(sql, values, as_list=True)

def get_columns():
    return [
        _("Open Date") + ":Date:100",
        _("Matter") + ":Link/Matter:120",
        _("Client") + ":Link/Customer:200",
        _("Invoice") + ":Link/Sales Invoice:120",
        _("Invoice Amount") + ":Currency:100",
        _("Invoice Status") + ":Data:100",
        _("Advance Amount") + ":Currency:100",
        _("Outstanding Amount") + ":Currency:100",
    ]
