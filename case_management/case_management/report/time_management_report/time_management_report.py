# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import get_datetime

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Start Time", "fieldname": "start_time", "fieldtype": "Datetime", "width": 250},
        {"label": "End Time", "fieldname": "end_time", "fieldtype": "Datetime", "width": 250},
        {"label": "Time (hrs)", "fieldname": "time", "fieldtype": "Float", "width": 100},
        {"label": "Note", "fieldname": "notes", "fieldtype": "Data", "width": 600},
    ]

def get_data(filters):
    conditions = ""
    if filters.get("user"):
        conditions += f" AND owner = '{filters['user']}'"

    entries = frappe.db.sql(f"""
        SELECT
            start_time,
            end_time,
            time,
            notes
        FROM `tabTime Tracking`
        WHERE docstatus = 1
        {conditions}
        ORDER BY start_time ASC
    """, as_dict=True)

    return entries
