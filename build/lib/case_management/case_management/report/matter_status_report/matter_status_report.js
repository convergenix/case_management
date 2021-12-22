// Copyright (c) 2016, masonarmani38@gmail.com and contributors
// For license information, please see license.txt

frappe.query_reports["Matter Status Report"] = {
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
        }, {
            "fieldname": "status",
            "label": __("Status"),
            "fieldtype": "Select",
            "width": "80",
            "reqd": 0,
            "default": "",
            "options": [
                "Draft", "Closed", "Open"
            ]
        },
    ]
};
