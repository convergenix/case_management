// Copyright (c) 2025, masonarmani38@gmail.com and contributors
// For license information, please see license.txt


// frappe.query_reports["Billing Report"] = {
//     filters: [
//         {
//             fieldname: "user",
//             label: "User",
//             fieldtype: "Link",
//             options: "User",
//             default: frappe.session.user
//         },
//         {
//             fieldname: "from_date",
//             label: "From Date",
//             fieldtype: "Date",
//             default: frappe.datetime.add_days(frappe.datetime.get_today(), -7)
//         },
//         {
//             fieldname: "to_date",
//             label: "To Date",
//             fieldtype: "Date",
//             default: frappe.datetime.add_days(frappe.datetime.get_today(), 7)
//         }
//     ]
// };


frappe.query_reports["Billing Report"] = {
    filters: [
        {
            fieldname: "employee",
            label: "Employee",
            fieldtype: "Link",
            options: "Employee"
        },
        {
            fieldname: "matter",
            label: "Matter",
            fieldtype: "Link",
            options: "Matter"
        },
        {
            fieldname: "client",
            label: "Client",
            fieldtype: "Link",
            options: "Customer"
        },
        {
            fieldname: "billing",
            label: "Billing",
            fieldtype: "Select",
            options: ["", "Billable", "Non-Billable"]
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
