// Copyright (c) 2016, bobzz.zone@gmail.com and contributors
// For license information, please see license.txt

frappe.query_reports["Matter Expense Summary"] = {
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
            "fieldname": "matter",
            "label": __("Matter ID"),
            "fieldtype": "Link",
            "options":"Matter",
            "width": "80",
            "reqd": 0,
        },
        {
            "fieldname": "expense",
            "label": __("Expense ID"),
            "fieldtype": "Link",
            "options":"Expense Claim",
            "width": "80",
            "reqd": 0,
        },
        {
            "fieldname": "employee",
            "label": __("Employee"),
            "fieldtype": "Link",
            "options":"Employee",
            "width": "80",
            "reqd": 0,
        },
        // {
        //     "fieldname": "expense_type",
        //     "label": __("Expense Type"),
        //     "fieldtype": "Link",
        //     "options":"Expense Claim Type",
        //     "width": "80",
        //     "reqd": 0,
        // },
        // {
        //     "fieldname": "matter",
        //     "label": __("Matter ID"),
        //     "fieldtype": "Link",
        //     "options":"Matter",
        //     "width": "80",
        //     "reqd": 0,
        // }
	]
}
