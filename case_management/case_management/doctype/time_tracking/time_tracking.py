# -*- coding: utf-8 -*-
# Copyright (c) 2017, bobzz.zone@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours
from frappe.core.doctype.communication.email import make

class TimeTracking(Document):
	def on_submit(self):
		if self.start_time and self.end_time:
			self.time = time_diff_in_hours(self.end_time, self.start_time)
			self.status = "Time Tracking Started"


@frappe.whitelist()
def end_time_tracking(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)
    # doc.db_set("status", "Time Tracking Ended")
    doc.status = "Time Tracking Ended"
    doc.save()
    frappe.db.commit()

    user_email = None
    client_name = "Unknown Client"
    matter_id = "Unknown Matter"

    if doc.matter:
        matter = frappe.get_doc("Matter", doc.matter)
        matter_id = matter.name
        client_name = matter.client or "Unknown Client"

        if matter.responsible_solicitor:
            employee = frappe.get_doc("Employee", matter.responsible_solicitor)
            user_email = employee.user_id  # This is the system user

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has ended.<br>
        Client: {client_name}
    """

    # ✅ Send screen + email notification to the responsible solicitor's user account
    if user_email:
        # Screen notification
        frappe.publish_realtime(
            event="msgprint",
            message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})",
            user=user_email,
        )

        # Email notification
        frappe.sendmail(
            recipients=[user_email],
            subject="Time Tracking Ended",
            message=message
        )
    else:
        frappe.log_error(f"No user found for responsible solicitor in Matter {matter_id}")

    return "Done"



