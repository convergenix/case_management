// Copyright (c) 2020, mymi14s@gmail.com and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Matter Billing"] = {
	"filters": [
        {
            "fieldname": "opened_from",
            "label": __("Transactions From"),
            "fieldtype": "Date",
            "width": "80",
            "reqd": 1,
            "default": dateutil.year_start()
        },
        {
            "fieldname": "opened_to",
            "label": __("Transactions To"),
            "fieldtype": "Date",
            "width": "80",
            "reqd": 1,
            "default": dateutil.year_end()
        },
        {
            "fieldname": "client",
            "label": __("Client"),
            "fieldtype": "Link",
            "options":"Customer",
            "width": "80",
            "reqd": 0,
        },
        {
            "fieldname": "matter",
            "label": __("Matter ID"),
            "fieldtype": "Link",
            "options":"Matter",
            "width": "80",
            "reqd": 0,
        }
	]
};
