# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "User", "fieldname": "creator_name", "fieldtype": "Data", "width": 250},
        {"label": "Matter", "fieldname": "matter", "fieldtype": "Link", "options": "Matter", "width": 250},
        {"label": "Client", "fieldname": "client_name", "fieldtype": "Data", "width": 250},  
        {"label": "Total Time (hrs)", "fieldname": "total_time", "fieldtype": "Float", "width": 150},
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

    if filters.get("user"):
        conditions += " AND tt.owner = %(user)s"
        values["user"] = filters["user"]

    return frappe.db.sql(f"""
        SELECT
            tt.matter,
            tt.matter_name AS client_name,
            tt.owner AS creator,
            u.full_name AS creator_name,
            SUM(tt.time) AS total_time
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabUser` u ON tt.owner = u.name
        WHERE {conditions}
        GROUP BY tt.matter, tt.matter_name, tt.owner, u.full_name
        ORDER BY tt.matter ASC
    """, values, as_dict=True)
