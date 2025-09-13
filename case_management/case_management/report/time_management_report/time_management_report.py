# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt


import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Description", "fieldname": "notes", "fieldtype": "Data", "width": 300},
        {"label": "Duration", "fieldname": "time", "fieldtype": "Float", "width": 100},
        {"label": "Member", "fieldname": "creator_name", "fieldtype": "Data", "width": 200},
        {"label": "Start Date", "fieldname": "creation", "fieldtype": "Date", "width": 180},
        {"label": "Matter", "fieldname": "matter", "fieldtype": "Link", "options": "Matter", "width": 200},
        {"label": "Client", "fieldname": "client_name", "fieldtype": "Data", "width": 200},
        # {"label": "User", "fieldname": "creator", "fieldtype": "Link", "options": "User", "width": 180},  
    ]

def get_data(filters):
    conditions = "tt.docstatus = 1"
    values = {}

    if filters.get("from_date"):
        # compare dates to DATETIME safely
        conditions += " AND DATE(tt.start_time) >= %(from_date)s"
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions += " AND DATE(tt.end_time) <= %(to_date)s"
        values["to_date"] = filters["to_date"]

    if filters.get("user"):
        conditions += " AND tt.owner = %(user)s"
        values["user"] = filters["user"]

    if filters.get("client"):
        # Handles both cases:
        #  - Time Tracking stores client in tt.matter_name
        #  - or Matter has a client link m.client
        conditions += " AND (tt.matter_name = %(client)s OR m.client = %(client)s)"
        values["client"] = filters["client"]

    # Make sure we join Matter so m.client is available
    return frappe.db.sql(f"""
        SELECT
            tt.creation,
            tt.owner AS creator,
            u.full_name AS creator_name,
            tt.time,
            tt.matter,
            tt.matter_name AS client_name,
            tt.notes
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabUser` u ON tt.owner = u.name
        LEFT JOIN `tabMatter` m ON tt.matter = m.name
        WHERE {conditions}
        ORDER BY tt.creation DESC
    """, values, as_dict=True)

