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
        {"label": "Solicitor", "fieldname": "responsible_solicitor", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": "Solicitor Name", "fieldname": "solicitor_name", "fieldtype": "Data", "width": 150},
        {"label": "Time (hrs)", "fieldname": "time", "fieldtype": "Float", "width": 100},
        {"label": "Matter", "fieldname": "matter", "fieldtype": "Link", "options": "Matter", "width": 200},
        {"label": "Client", "fieldname": "client_name", "fieldtype": "Data", "width": 200},
        {"label": "Notes", "fieldname": "notes", "fieldtype": "Data", "width": 400},
    ]

def get_data(filters):
    conditions = "tt.docstatus = 1"
    values = {}

    if filters.get("from_date"):
        conditions += " AND tt.start_time >= %(from_date)s"
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions += " AND tt.end_time <= %(to_date)s"
        values["to_date"] = filters["to_date"]

    if filters.get("responsible_solicitor"):
        conditions += " AND m.responsible_solicitor = %(responsible_solicitor)s"
        values["responsible_solicitor"] = filters["responsible_solicitor"]

    return frappe.db.sql(f"""
        SELECT
            m.responsible_solicitor,
            e.employee_name AS solicitor_name,
            tt.time,
            tt.matter,
            tt.matter_name AS client_name,
            tt.notes
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabMatter` m ON tt.matter = m.name
        LEFT JOIN `tabEmployee` e ON m.responsible_solicitor = e.name
        WHERE {conditions}
        ORDER BY tt.start_time ASC
    """, values, as_dict=True)
