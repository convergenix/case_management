# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Matter", "fieldname": "matter", "fieldtype": "Link", "options": "Matter", "width": 200},
        {"label": "Client", "fieldname": "client", "fieldtype": "Link", "options": "Customer", "width": 200},
        {"label": "Billing", "fieldname": "billing", "fieldtype": "Select", "options": "Billable\nNon-Billable", "width": 120},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
        {"label": "Billable Hours", "fieldname": "billable_hours", "fieldtype": "Float", "width": 140},
        {"label": "Revenue", "fieldname": "revenue", "fieldtype": "Currency", "width": 140},
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

    if filters.get("employee"):
        conditions += " AND m.responsible_solicitor = %(employee)s"
        values["employee"] = filters["employee"]

    if filters.get("matter"):
        conditions += " AND tt.matter = %(matter)s"
        values["matter"] = filters["matter"]

    if filters.get("client"):
        conditions += " AND m.client = %(client)s"
        values["client"] = filters["client"]

    if filters.get("billing"):
        conditions += " AND tt.billing = %(billing)s"
        values["billing"] = filters["billing"]

    results = frappe.db.sql(f"""
        SELECT
            m.responsible_solicitor AS employee,
            e.employee_name AS employee_name,
            tt.matter,
            m.client,
            tt.billing,
            SUM(tt.time) AS total_hours,
            SUM(CASE WHEN tt.billing = 'Billable' THEN tt.time ELSE 0 END) AS billable_hours,
            SUM(CASE WHEN tt.billing = 'Billable' THEN tt.revenue ELSE 0 END) AS revenue,
            COUNT(DISTINCT DATE(tt.start_time)) AS working_days
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabMatter` m ON tt.matter = m.name
        LEFT JOIN `tabEmployee` e ON m.responsible_solicitor = e.name
        WHERE {conditions}
        GROUP BY m.responsible_solicitor, e.employee_name, tt.matter, m.client, tt.billing
        ORDER BY e.employee_name, m.client, tt.matter
    """, values, as_dict=True)

    for row in results:
        if row.get("working_days"):
            row["avg_daily_hours"] = row["total_hours"] / row["working_days"]
        else:
            row["avg_daily_hours"] = 0

    return results
