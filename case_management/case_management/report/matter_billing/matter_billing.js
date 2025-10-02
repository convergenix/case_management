// Copyright (c) 2020, mymi14s@gmail.com and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Matter Billing"] = {
    "filters": [
        {
            "fieldname": "opened_from",
            "label": __("Transactions From"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.year_start()
        },
        {
            "fieldname": "opened_to",
            "label": __("Transactions To"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.year_end()
        },
        {
            "fieldname": "client",
            "label": __("Client"),
            "fieldtype": "Link",
            "options": "Customer"
        },
        {
            "fieldname": "matter",
            "label": __("Matter ID"),
            "fieldtype": "Link",
            "options": "Matter"
        }
    ]
};

