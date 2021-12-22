from __future__ import unicode_literals
from frappe import _


def get_data():
    return [
        {
            "label": _("Matter Management"),
            "items": [
                {
                    "type": "doctype",
                    "name": "Matter",
                    "description": _("Matter Documents")
                },
                {
                    "type": "doctype",
                    "name": "Matter Activity",
                    "description": _("Matter Activities")
                },
                {
                    "type": "doctype",
                    "name": "Matter Custom Check List",
                    "description": _("Matter Custom Check List")
                },
                {
                    "type": "doctype",
                    "name": "Practice Area",
                    "description": _("Practice Area")
                }
            ]
        },

        {
            "label": _("Tools"),
            "items": [
                {
                    "type": "doctype",
                    "name": "Time Tracking",
                    "description": _("Practice Area")
                },
                {
                    "type": "doctype",
                    "name": "Timesheet",
                    "description": _("Timesheet")
                },
                {
                    "type": "doctype",
                    "name": "Event",
                    "label":"Event",
                    "description": _("Event")
                },
                {
                    "type": "doctype",
                    "name": "Notes",
                    "description": _("Notes")
                },
                {
                    "type": "doctype",
                    "name": "Task",
                    "description": _("Task")
                },
                {
                    "type": "doctype",
                    "name": "Note",
                    "description": _("Note")
                },
            ]
        },
        {
            "label": _("Reports"),
            "items": [

                {
                    "type": "report",
                    "name": "Matter Expense Summary",
                    "doctype": "Matter",
                    "is_query_report": True
                },
                {
                    "type": "report",
                    "name": "Matter Report",
                    "doctype": "Matter",
                    "is_query_report": True
                },
                {
                    "type": "report",
                    "name": "Matter Status Report",
                    "doctype": "Matter",
                    "is_query_report": True
                },
                {
                    "type": "report",
                    "name": "Matter Billing Report",
                    "doctype": "Matter",
                    "is_query_report": True
                },
                {
                    "type": "report",
                    "name": "Matter Summary Report",
                    "doctype": "Matter",
                    "is_query_report": True
                }
            ]
        }
    ]
