# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        # {"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 200},
        {"label": "User Name", "fieldname": "user_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 150},
        {"label": "Billable Hours", "fieldname": "billable_hours", "fieldtype": "Float", "width": 150},
        {"label": "Revenue", "fieldname": "revenue", "fieldtype": "Currency", "width": 150},
        {"label": "Average Daily Hours", "fieldname": "avg_daily_hours", "fieldtype": "Float", "width": 180},
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

    results = frappe.db.sql(f"""
        SELECT
            tt.owner AS user,
            u.full_name AS user_name,
            SUM(tt.time) AS total_hours,
            SUM(CASE WHEN tt.billing = 'Billable' THEN tt.time ELSE 0 END) AS billable_hours,
            SUM(CASE WHEN tt.billing = 'Billable' THEN tt.revenue ELSE 0 END) AS revenue,
            COUNT(DISTINCT DATE(tt.start_time)) AS working_days
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabUser` u ON tt.owner = u.name
        WHERE {conditions}
        GROUP BY tt.owner, u.full_name
    """, values, as_dict=True)

    # Calculate average daily hours
    for row in results:
        if row.get("working_days"):
            row["avg_daily_hours"] = row["total_hours"] / row["working_days"]
        else:
            row["avg_daily_hours"] = 0

    return results
