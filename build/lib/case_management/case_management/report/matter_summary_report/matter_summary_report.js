// Copyright (c) 2016, masonarmani38@gmail.com and contributors
// For license information, please see license.txt

frappe.query_reports["Matter Summary Report"] = {
    "filters": [
        {
            "fieldname": "opened_from",
            "label": __("Opened From"),
            "fieldtype": "Date",
            "width": "80",
            "reqd": 1,
            "default": dateutil.year_start()
        },
        {
            "fieldname": "opened_to",
            "label": __("Opened To"),
            "fieldtype": "Date",
            "width": "80",
            "reqd": 1,
            "default": dateutil.year_end()
        },
        {
            "fieldname": "responsible_solicitor",
            "label": __("Responsible Solicitor"),
            "fieldtype": "Link",
            "options":"Employee",
            "width": "80",
            "reqd": 0,
            "default": ""
        },
        {
            "fieldname": "matter",
            "label": __("Matter"),
            "fieldtype": "Link",
            "options":"Matter",
            "width": "80",
            "reqd": 0,
            "default": ""
        },
        {
            "fieldname": "client",
            "label": __("Customer"),
            "fieldtype": "Link",
            "options":"Customer",
            "width": "120",
            "reqd": 0,
            "default": ""
        }
    ]
}
