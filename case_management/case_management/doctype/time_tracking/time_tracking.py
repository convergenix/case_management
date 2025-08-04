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
		if self.start_time:
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



@frappe.whitelist()
def stop_time_tracking_now(time_tracking):
    from frappe.utils import now_datetime, time_diff_in_hours

    doc = frappe.get_doc("Time Tracking", time_tracking)

    end_time = now_datetime()
    doc.db_set("end_time", end_time)

    if doc.start_time:
        hours = time_diff_in_hours(end_time, doc.start_time)
        doc.db_set("time", hours)

    doc.db_set("status", "Time Tracking Ended")

    # Optional: Send notifications like before
    user_email = None
    client_name = "Unknown Client"
    matter_id = "Unknown Matter"

    if doc.matter:
        matter = frappe.get_doc("Matter", doc.matter)
        matter_id = matter.name
        client_name = matter.client or "Unknown Client"

        if matter.responsible_solicitor:
            employee = frappe.get_doc("Employee", matter.responsible_solicitor)
            user_email = employee.user_id

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has been manually stopped.<br>
        Client: {client_name}
    """

    if user_email:
        frappe.publish_realtime(
            event="msgprint",
            message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})",
            user=user_email,
        )

        frappe.sendmail(
            recipients=[user_email],
            subject="Time Tracking Ended",
            message=message
        )

    frappe.db.commit()
    return "Stopped"



from frappe.utils import now

@frappe.whitelist()
def finalize_time_tracking(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)

    # if not doc.status or doc.status.strip().lower() != "time tracking started":
        
        # frappe.throw("Time tracking is not currently active.")

    doc.end_time = frappe.utils.now_datetime()
    doc.time = frappe.utils.time_diff_in_hours(doc.end_time, doc.start_time)
    doc.status = "Time Tracking Ended"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Notify responsible solicitor if assigned
    user_email = None
    matter_id = "Unknown"
    client_name = "Unknown"

    if doc.matter:
        matter = frappe.get_doc("Matter", doc.matter)
        matter_id = matter.name
        client_name = matter.client or "Unknown"

        if matter.responsible_solicitor:
            emp = frappe.get_doc("Employee", matter.responsible_solicitor)
            user_email = emp.user_id

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has ended.<br>
        Client: {client_name}
    """

    if user_email:
        frappe.publish_realtime(
            event="msgprint",
            message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})",
            user=user_email,
        )

        frappe.sendmail(
            recipients=[user_email],
            subject="Time Tracking Ended",
            message=message
        )
