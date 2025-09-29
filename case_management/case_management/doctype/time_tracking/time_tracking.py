# -*- coding: utf-8 -*-
# Copyright (c) 2017, bobzz.zone@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours
from frappe.utils import now
from frappe.core.doctype.communication.email import make
from frappe.utils import flt
from erpnext.setup.utils import get_exchange_rate

class TimeTracking(Document):
	def on_submit(self):
		if self.start_time:
			self.status = "Time Tracking Started"

		# calculate revenue if applicable
		self.calculate_revenue()

	def before_save(self):
		# recalc revenue on every save if billable
		self.calculate_revenue()
    
	# def calculate_revenue(self):
	# 	"""Calculate revenue only if Billable."""
	# 	if self.billing == "Billable" and self.time:
	# 		# Get employee linked to the user who created this Time Tracking
	# 		user = self.owner  # system user who created the record
	# 		employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

	# 		if employee:
	# 			# Look up billing rate for this employee
	# 			billing_rate = frappe.db.get_value(
	# 				"Billing Details",
	# 				{"employee": employee},
	# 				"billing_rate"
	# 			)

	# 			if billing_rate:
	# 				self.revenue = float(billing_rate) * float(self.time)
	# 			else:
	# 				self.revenue = 0
	# 		else:
	# 			self.revenue = 0
	# 	else:
	# 		# Non-Billable or missing data → no calculation
	# 		self.revenue = 0


	def calculate_revenue(self):
		"""Calculate revenue based on customer's billing currency.
		If USD → store formatted in dollars and also convert to naira.
		If NGN → store formatted in naira and skip conversion.
		"""
		if self.billing == "Billable" and self.time:
			customer = self.matter_name  # assumes Time Tracking has a 'customer' field

			if customer:
				# Fetch billing rate and currency from Billing Details
				billing_rate, billing_currency = frappe.db.get_value(
					"Billing Details",
					{"customer": customer},
					["billing_rate", "billing_currency"]
				) or (0, "USD")

				if billing_rate:
					if billing_currency == "USD":
						# Revenue in USD
						revenue_usd = round(float(billing_rate) * float(self.time), 2)
						self.revenue = f"$ {revenue_usd:,.2f}"

						# Convert to NGN
						usd_to_ngn = get_exchange_rate("USD", "NGN")
						self.revenue_in_naira = round(flt(revenue_usd) * flt(usd_to_ngn), 2)
						self.exchange_rate_used = flt(usd_to_ngn)

					elif billing_currency == "NGN":
						# Revenue in NGN directly
						revenue_ngn = round(float(billing_rate) * float(self.time), 2)
						self.revenue = f"₦ {revenue_ngn:,.2f}"

						# No conversion needed
						self.revenue_in_naira = revenue_ngn
						self.exchange_rate_used = 1

					else:
						# Any other currency → first convert to USD
						rate_to_usd = get_exchange_rate(billing_currency, "USD")
						revenue_usd = round(float(billing_rate) * float(self.time) * flt(rate_to_usd), 2)
						self.revenue = f"$ {revenue_usd:,.2f}"

						# Convert USD → NGN
						usd_to_ngn = get_exchange_rate("USD", "NGN")
						self.revenue_in_naira = round(flt(revenue_usd) * flt(usd_to_ngn), 2)
						self.exchange_rate_used = flt(usd_to_ngn)

				else:
					self.revenue = "$ 0.00"
					self.revenue_in_naira = 0
			else:
				self.revenue = "$ 0.00"
				self.revenue_in_naira = 0
		else:
			self.revenue = "$ 0.00"
			self.revenue_in_naira = 0




@frappe.whitelist()
def end_time_tracking(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)
    # doc.db_set("status", "Time Tracking Ended")
    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
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
    doc.end_time = end_time

    if doc.start_time:
        hours = time_diff_in_hours(end_time, doc.start_time)
        doc.time = hours

    doc.status = "Time Tracking Ended"

    # ✅ Recalculate revenue
    doc.calculate_revenue()

    # Save with all updates
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Notifications
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
        Client: {client_name}<br>
        Revenue: {doc.revenue or 0}
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
	
    return "Stopped"




@frappe.whitelist()
def finalize_time_tracking(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)

    # if not doc.status or doc.status.strip().lower() != "time tracking started":
        
        # frappe.throw("Time tracking is not currently active.")

    doc.end_time = frappe.utils.now_datetime()
    doc.time = frappe.utils.time_diff_in_hours(doc.end_time, doc.start_time)
    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
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
