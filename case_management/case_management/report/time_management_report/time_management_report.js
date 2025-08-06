// Copyright (c) 2025, masonarmani38@gmail.com and contributors
// For license information, please see license.txt

frappe.query_reports["Time Management Report"] = {
    filters: [
        {
            fieldname: "user",
            label: "User",
            fieldtype: "Link",
            options: "User",
            default: frappe.session.user,
            reqd: 1
        }
    ],
    formatter: function(value, row, column, data, default_formatter) {
        // Bold total row if added
        if (data && data.start_time === "Total") {
            value = `<b>${value}</b>`;
        }
        return value;
    }
};
