# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "case_management"
app_title = "Case Management"
app_publisher = "masonarmani38@gmail.com"
app_description = "Case Management"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "masonarmani38@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/case_management/css/case_management.css"
# app_include_js = "/assets/case_management/js/case_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/case_management/css/case_management.css"
# web_include_js = "/assets/case_management/js/case_management.js"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "case_management.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Fixtures
#fixtures = ['Custom Field', 'Translation']
fixtures = ["Custom Field", "Role", "Translation", "Folder", "Folder Structure", "Naming Series"]
# Installation
# ------------

# before_install = "case_management.install.before_install"
# after_install = "case_management.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "case_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

calendars = ["Matter"]


doc_events = {
    "Sales Invoice": {
        "on_submit": "case_management.case_management.doctype.matter.matter.invoice_update",
        "on_cancel": "case_management.case_management.doctype.matter.matter.invoice_update"
    },
    "Expense Claim": {
        "on_submit": "case_management.case_management.doctype.matter.matter.expense_update",
        "on_cancel": "case_management.case_management.doctype.matter.matter.expense_update"
    },
    "Payment Entry": {
        "on_submit": "case_management.case_management.doctype.matter.matter.payment_update",
        "on_cancel": "case_management.case_management.doctype.matter.matter.payment_cancel"
    },
    "Timesheet": {
        "on_submit": "case_management.case_management.doctype.matter.matter.timesheet_update",
        "on_cancel": "case_management.case_management.doctype.matter.matter.timesheet_update"
    },
    "Company": {
        "on_change": "case_management.case_management.api.set_translation",
    },
    "Customer": {
        "on_update": "case_management.client.update_all"
    },
    "Matter": {
        "on_update": "case_management.client.update_all_matter"
    },
    "File": {
        "validate": "case_management.client.validate_update_tabfile_private"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"case_management.tasks.all"
# 	],
# 	"daily": [
# 		"case_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"case_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"case_management.tasks.weekly"
# 	]
# 	"monthly": [
# 		"case_management.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "case_management.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "case_management.event.get_events"
# }

after_migrate = [
    "case_management.after_migrate.update_translation"
]