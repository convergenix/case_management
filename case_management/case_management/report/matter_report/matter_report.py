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
        conditions += " and open_date  BETWEEN '{0}' and '{1}'".format(
            filters.get("opened_from"), filters.get('opened_to'))

    if filters.get('status'):
        conditions += " and status = '{0}'".format(filters.get("status"))
    if filters.get('client'):
        conditions += " and client = '{0}'".format(filters.get("client"))
    if filters.get('matter'):
        conditions += " and name = '{0}'".format(filters.get("matter"))
    if filters.get('responsible_solicitor'):
        conditions += " and responsible_solicitor = '{0}'".format(filters.get("responsible_solicitor"))
    if filters.get('practice_area'):
        conditions += " and practice_area = '{0}'".format(filters.get("practice_area"))

    # open_date, matter, client , status , practice_area , close_date
    sql = "select open_date, name, client , status , practice_area , close_date ,\
 				solicitor_name, matter_information from `tabMatter` WHERE {0}"
    data = frappe.db.sql(sql.format(conditions))
    return data


def get_column():
    # ["Link:Link/Accident:150", "Data:Data:200", "Currency:Currency:100", "Float:Float:100"]
    return [
        _("Open Date") + ":Data:100",
        "Matter:Link/Matter:100",
        "Client:Link/Customer:100",
        "Status:Data:70",
        "Practice Area:Link/Practice Area:100",
        "Close Date:Date:100",
        "Responsible Solicitor:Link/Employee:100",
        "Information:Data:200",
    ]
