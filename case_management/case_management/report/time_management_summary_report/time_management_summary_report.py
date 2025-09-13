# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

# import frappe

# def execute(filters=None):
#     columns = get_columns()
#     data = get_data(filters)
#     return columns, data

# def get_columns():
#     return [
#         {"label": "User", "fieldname": "creator_name", "fieldtype": "Data", "width": 250},
#         {"label": "Matter", "fieldname": "matter", "fieldtype": "Link", "options": "Matter", "width": 250},
#         {"label": "Client", "fieldname": "client_name", "fieldtype": "Data", "width": 250},  
#         {"label": "Total Time (hrs)", "fieldname": "total_time", "fieldtype": "Float", "width": 150},
#     ]

# def get_data(filters):
#     conditions = "tt.docstatus = 1"
#     values = {}

#     if filters.get("from_date"):
#         conditions += " AND tt.start_time >= %(from_date)s"
#         values["from_date"] = filters["from_date"]

#     if filters.get("to_date"):
#         conditions += " AND tt.end_time <= %(to_date)s"
#         values["to_date"] = filters["to_date"]

#     if filters.get("user"):
#         conditions += " AND tt.owner = %(user)s"
#         values["user"] = filters["user"]

#     return frappe.db.sql(f"""
#         SELECT
#             tt.matter,
#             tt.matter_name AS client_name,
#             tt.owner AS creator,
#             u.full_name AS creator_name,
#             SUM(tt.time) AS total_time
#         FROM `tabTime Tracking` tt
#         LEFT JOIN `tabUser` u ON tt.owner = u.name
#         WHERE {conditions}
#         GROUP BY tt.matter, tt.matter_name, tt.owner, u.full_name
#         ORDER BY tt.matter DESC
#     """, values, as_dict=True)


import frappe
from frappe.utils import date_diff

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Employee", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
        {"label": "Billable Hours", "fieldname": "billable_hours", "fieldtype": "Float", "width": 120},
        # {"label": "Non-Billable Hours", "fieldname": "non_billable_hours", "fieldtype": "Float", "width": 150},
        {"label": "Billable %", "fieldname": "billable_percent", "fieldtype": "Percent", "width": 120},
        # {"label": "Difference (Bill - Non-Bill)", "fieldname": "diff_hours", "fieldtype": "Float", "width": 180},
        {"label": "Amount", "fieldname": "revenue", "fieldtype": "Currency", "width": 150},
        {"label": "Average Daily Hours", "fieldname": "avg_daily_hours", "fieldtype": "Float", "width": 200},
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

    if filters.get("employee"):
        conditions += " AND e.name = %(employee)s"
        values["employee"] = filters["employee"]

    # Fetch totals grouped by employee
    results = frappe.db.sql(f"""
        SELECT
            e.name AS employee,
            e.employee_name,
            SUM(tt.time) AS total_hours,
            SUM(CASE WHEN tt.billing = 'Billable' THEN tt.time ELSE 0 END) AS billable_hours,
            SUM(CASE WHEN tt.billing = 'Non-Billable' THEN tt.time ELSE 0 END) AS non_billable_hours,
            SUM(tt.revenue) AS revenue
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabEmployee` e ON e.user_id = tt.owner
        WHERE {conditions}
        GROUP BY e.name, e.employee_name
    """, values, as_dict=True)

    # Add calculated fields
    for row in results:
        total = row.total_hours or 0
        billable = row.billable_hours or 0
        non_billable = row.non_billable_hours or 0

        row.billable_percent = (billable / total * 100) if total else 0
        row.diff_hours = billable - non_billable

        # Calculate average daily hours
        if filters.get("from_date") and filters.get("to_date"):
            num_days = date_diff(filters["to_date"], filters["from_date"]) + 1
            row.avg_daily_hours = (total / num_days) if num_days > 0 else 0
        else:
            row.avg_daily_hours = 0

    return results
