// Copyright (c) 2016, masonarmani38@gmail.com and contributors
// For license information, please see license.txt

frappe.query_reports["Matter Billing Summary"] = {
    "filters": [
        {
            "fieldname": "opened_from",
            "label": __("Invoice From"),
            "fieldtype": "Date",
            "width": "80",
            "reqd": 0
        },
        {
            "fieldname": "opened_to",
            "label": __("Invoice To"),
            "fieldtype": "Date",
            "width": "80",
            "reqd": 0
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
            "fieldtype": "Link", ,
            "options":"Customer",
            "width": "120",
            "reqd": 0,
            "default": ""
        }
    ]
}
