// Copyright (c) 2016, masonarmani38@gmail.com and contributors
// For license information, please see license.txt
frappe.query_reports["Matter Status Report"] = {
    "filters": [
        {
            "fieldname": "opened_from",
            "label": __("Opened From"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.year_start()
        },
        {
            "fieldname": "opened_to",
            "label": __("Opened To"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.year_end()
        },
        {
            "fieldname": "status",
            "label": __("Status"),
            "fieldtype": "Select",
            "default": "",
            "options": [
                "", "Draft", "Open", "Pending Document", "Awaiting Filing",
                "On-Hold", "Filed", "In Mediation/Arbitration",
                "Awaiting Judgement/ Ruling", "Pending", "Closed"
            ]
        },
        {
            "fieldname": "responsible_solicitor",
            "label": __("Responsible Solicitor"),
            "fieldtype": "Link",
            "options": "Employee",  // allows picking an Employee ID
            "default": ""
        }
    ]
};
