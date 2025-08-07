# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Matter", "fieldname": "matter", "fieldtype": "Link", "options": "Matter", "width": 250},
        {"label": "Client", "fieldname": "client_name", "fieldtype": "Data", "width": 250},
        {"label": "Solicitor", "fieldname": "responsible_solicitor", "fieldtype": "Link", "options": "Employee", "width": 200},
        {"label": "Solicitor Name", "fieldname": "solicitor_name", "fieldtype": "Data", "width": 250},
        {"label": "Total Time (hrs)", "fieldname": "total_time", "fieldtype": "Float", "width": 250},
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
            tt.matter,
            tt.matter_name AS client_name,
            m.responsible_solicitor,
            e.employee_name AS solicitor_name,
            SUM(tt.time) AS total_time
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabMatter` m ON tt.matter = m.name
        LEFT JOIN `tabEmployee` e ON m.responsible_solicitor = e.name
        WHERE {conditions}
        GROUP BY tt.matter, tt.matter_name, m.responsible_solicitor, e.employee_name
        ORDER BY tt.matter ASC
    """, values, as_dict=True)

