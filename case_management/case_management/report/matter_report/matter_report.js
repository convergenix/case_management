// Copyright (c) 2016, masonarmani38@gmail.com and contributors
// For license information, please see license.txt

frappe.query_reports["Matter Report"] = {
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
            "options": ["Closed", "Open"]
        },{
            "fieldname": "matter",
            "label": __("Matter"),
            "fieldtype": "Link",
            "options":"Matter",
            "width": "80",
            "reqd": 0,
        },{
            "fieldname": "client",
            "label": __("Client"),
            "fieldtype": "Link",
            "options":"Customer",
            "width": "80",
            "reqd": 0,
        },{
            "fieldname": "practice_area",
            "label": __("Practice Area"),
            "fieldtype": "Link",
            "options":"Practice Area",
            "width": "80",
            "reqd": 0,
        },{
            "fieldname": "responsible_solicitor",
            "label": __("Solicitor"),
            "fieldtype": "Link",
            "options":"Employee",
            "width": "80",
            "reqd": 0,
        },
        // {
        //     "fieldname": "solicitor",
        //     "label": __("Solicitor"),
        //     "fieldtype": "Link",
        //     "options":"User",
        //     "width": "80",
        //     "reqd": 0,
        // },

    ]
}
