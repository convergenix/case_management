# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe import _


def get_data():
    return [
        {
            "module_name": "Case Management",
            "color": "rgb(14, 96, 134)",
            "icon": "octicon octicon-law",
            "label": _("Case Management"),
            "link": "modules/Case Management",
            "type": "module",
            "hidden": 0
        },
        {
            "module_name": 'core',
            "category": "Modules",
            "label": _('File Manager'),
            "icon": "octicon octicon-file-directory",
            "type": "link",
            "link": "#List/File/Home",
            "color": '#FF4136',
            'standard': 1,
            'idx': 99
        },
        {
            "module_name": "Matter",
            "_doctype":"Matter",
            "color": "rgb(14, 131, 52)",
            "icon": "octicon octicon-briefcase",
            "type": "list",
            "label":"Matter",
            "link": "List/Matter"
        },
        {
            "module_name": "Event",
            "color": "rgb(14, 121, 52)",
            "icon": "octicon octicon-calendar",
            "type": "list",
            "label":"Calendar",
            "link": "List/Event"
        },

        {
            "module_name": "Timesheet",
            "color": "#8d99b6",
            "icon": "octicon octicon-checklist",
            "label": _("Timesheet"),
            "link": "List/Timesheet",
            "_doctype": "Timesheet",
            "type": "list"
        },
        {
            "module_name": "Time Tracking",
            "color": "#8d62b6",
            "icon": "octicon octicon-watch",
            "label": _("Time Tracking"),
            "link": "List/Time Tracking",
            "_doctype": "Time Tracking",
            "type": "list"
        },
        {
            "module_name": "Expense Claim",
            "color": "#8d63c6",
            "icon": "fa fa-money",
            "label": _("Expense Claim"),
            "link": "List/Expense Claim",
            "_doctype": "Expense Claim",
            "type": "list"
        },
    ]
