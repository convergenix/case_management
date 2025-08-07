// Copyright (c) 2025, masonarmani38@gmail.com and contributors
// For license information, please see license.txt


frappe.query_reports["Time Management Summary Report"] = {
    filters: [
        {
            fieldname: "responsible_solicitor",
            label: "Responsible Solicitor",
            fieldtype: "Link",
            options: "Employee"
        },
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -7)
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.get_today()
        }
    ]
};
