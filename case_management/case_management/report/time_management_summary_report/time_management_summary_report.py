# Copyright (c) 2025, masonarmani38@gmail.com and contributors
# For license information, please see license.txt


# import frappe
# from frappe.utils import date_diff

# def execute(filters=None):
#     columns = get_columns()
#     data = get_data(filters)
#     return columns, data

# def get_columns():
#     return [
#         {"label": "Employee", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
#         {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
#         {"label": "Billable Hours", "fieldname": "billable_hours", "fieldtype": "Float", "width": 120},
#         # {"label": "Non-Billable Hours", "fieldname": "non_billable_hours", "fieldtype": "Float", "width": 150},
#         {"label": "Billable %", "fieldname": "billable_percent", "fieldtype": "Percent", "width": 120},
#         # {"label": "Difference (Bill - Non-Bill)", "fieldname": "diff_hours", "fieldtype": "Float", "width": 180},
#         {"label": "Amount", "fieldname": "revenue", "fieldtype": "Currency", "width": 150},
#         {"label": "Average Daily Hours", "fieldname": "avg_daily_hours", "fieldtype": "Float", "width": 200},
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

#     if filters.get("employee"):
#         conditions += " AND e.name = %(employee)s"
#         values["employee"] = filters["employee"]

#     # Fetch totals grouped by employee
#     results = frappe.db.sql(f"""
#         SELECT
#             e.name AS employee,
#             e.employee_name,
#             SUM(tt.time) AS total_hours,
#             SUM(CASE WHEN tt.billing = 'Billable' THEN tt.time ELSE 0 END) AS billable_hours,
#             SUM(CASE WHEN tt.billing = 'Non-Billable' THEN tt.time ELSE 0 END) AS non_billable_hours,
#             SUM(tt.revenue) AS revenue
#         FROM `tabTime Tracking` tt
#         LEFT JOIN `tabEmployee` e ON e.user_id = tt.owner
#         WHERE {conditions}
#         GROUP BY e.name, e.employee_name
#     """, values, as_dict=True)

#     # Add calculated fields
#     for row in results:
#         total = row.total_hours or 0
#         billable = row.billable_hours or 0
#         non_billable = row.non_billable_hours or 0

#         row.billable_percent = (billable / total * 100) if total else 0
#         row.diff_hours = billable - non_billable

#         # Calculate average daily hours
#         if filters.get("from_date") and filters.get("to_date"):
#             num_days = date_diff(filters["to_date"], filters["from_date"]) + 1
#             row.avg_daily_hours = (total / num_days) if num_days > 0 else 0
#         else:
#             row.avg_daily_hours = 0

#     return results



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
        # {"label": "Non-Billable Hours", "fieldname": "non_billable_hours", "fieldtype": "Float", "width": 140},
        {"label": "Billable %", "fieldname": "billable_percent", "fieldtype": "Percent", "width": 100},
        # {"label": "Difference (Bill - Non-Bill)", "fieldname": "diff_hours", "fieldtype": "Float", "width": 160},
        {"label": "Amount", "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
        {"label": "Average Daily Hours", "fieldname": "avg_daily_hours", "fieldtype": "Float", "width": 200},
    ]

def get_data(filters):
    conditions = "tt.docstatus = 1"
    values = {}

    # date filters (use DATE(...) to compare datetimes against dates)
    if filters.get("from_date"):
        conditions += " AND DATE(tt.start_time) >= %(from_date)s"
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND DATE(tt.end_time) <= %(to_date)s"
        values["to_date"] = filters["to_date"]

    # client filter (checks both tt.matter_name or Matter.client)
    if filters.get("client"):
        conditions += " AND (tt.matter_name = %(client)s OR m.client = %(client)s)"
        values["client"] = filters["client"]

    # If a 'user' filter (system user) is provided, try to resolve to Employee
    # If mapping exists, filter by employee; otherwise filter by tt.owner
    if filters.get("user"):
        emp_name = frappe.db.get_value("Employee", {"user_id": filters["user"]}, "name")
        if emp_name:
            conditions += " AND e.name = %(employee_from_user)s"
            values["employee_from_user"] = emp_name
        else:
            conditions += " AND tt.owner = %(user)s"
            values["user"] = filters["user"]

    # If an explicit 'employee' filter is provided use it (overrides above)
    if filters.get("employee"):
        conditions += " AND e.name = %(employee)s"
        values["employee"] = filters["employee"]

    # Aggregate by employee (fall back to tt.owner if no employee mapping)
    rows = frappe.db.sql(f"""
        SELECT
            COALESCE(e.name, tt.owner) AS employee_id,
            COALESCE(e.employee_name, u.full_name, tt.owner) AS employee_name,
            SUM(IFNULL(tt.time, 0)) AS total_hours,
            SUM(CASE WHEN tt.billing = 'Billable' THEN IFNULL(tt.time, 0) ELSE 0 END) AS billable_hours,
            SUM(CASE WHEN tt.billing = 'Non-Billable' THEN IFNULL(tt.time, 0) ELSE 0 END) AS non_billable_hours,
            SUM(IFNULL(tt.revenue, 0)) AS revenue,
            COUNT(DISTINCT DATE(tt.start_time)) AS working_days
        FROM `tabTime Tracking` tt
        LEFT JOIN `tabUser` u ON tt.owner = u.name
        LEFT JOIN `tabEmployee` e ON e.user_id = tt.owner
        LEFT JOIN `tabMatter` m ON tt.matter = m.name
        WHERE {conditions}
        GROUP BY employee_id, employee_name
        ORDER BY employee_name
    """.format(conditions=conditions), values, as_dict=True)

    # Post-process calculated fields
    for r in rows:
        total = r.get("total_hours") or 0
        billable = r.get("billable_hours") or 0
        non_billable = r.get("non_billable_hours") or 0

        r["billable_percent"] = (billable / total * 100) if total else 0
        r["diff_hours"] = billable - non_billable

        # avg daily hours: if date range provided, divide by date span; otherwise use distinct working days
        if filters.get("from_date") and filters.get("to_date"):
            num_days = date_diff(filters["to_date"], filters["from_date"]) + 1
            r["avg_daily_hours"] = (total / num_days) if num_days > 0 else 0
        else:
            wd = r.get("working_days") or 0
            r["avg_daily_hours"] = (total / wd) if wd > 0 else 0

    return rows
