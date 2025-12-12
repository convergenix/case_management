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
    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
    doc.save()
    frappe.db.commit()

    client_name = "Unknown Client"
    matter_id = "Unknown Matter"

    if doc.matter:
        matter = frappe.get_doc("Matter", doc.matter)
        matter_id = matter.name
        client_name = matter.client or "Unknown Client"

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has ended.<br>
        Client: {client_name}
    """

    # ✅ Always email Charles only
    frappe.sendmail(
        recipients=["Charles.oyeshomo@odujinrinadefulu.com"],
        subject="Time Tracking Ended",
        message=message
    )

    # Optional: still show screen notification to whoever is logged in
    frappe.publish_realtime(
        event="msgprint",
        message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})"
    )

    return "Done"



@frappe.whitelist()
def stop_time_tracking_now(time_tracking):
    from frappe.utils import now_datetime, time_diff_in_hours

    doc = frappe.get_doc("Time Tracking", time_tracking)

    # ✔️ Do NOT override end_time if user has chosen one
    if doc.end_time not in (None, "", " "):
        end_time = doc.end_time
    else:
        end_time = now_datetime()

    doc.end_time = end_time

    # Calculate worked hours
    if doc.start_time:
        hours = time_diff_in_hours(end_time, doc.start_time)
        doc.time = hours

    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Messaging part...
    client_name = "Unknown Client"
    matter_id = "Unknown Matter"

    if doc.matter:
        matter = frappe.get_doc("Matter", doc.matter)
        matter_id = matter.name
        client_name = matter.client or "Unknown Client"

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has been manually stopped.<br>
        Client: {client_name}<br>
        Revenue: {doc.revenue or 0}
    """

    frappe.sendmail(
        recipients=["Charles.oyeshomo@odujinrinadefulu.com"],
        subject="Time Tracking Ended",
        message=message
    )

    frappe.publish_realtime(
        event="msgprint",
        message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})"
    )

    return "Stopped"





@frappe.whitelist()
def finalize_time_tracking(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)

    # ✅ Only set end_time if not already provided
    doc.end_time = doc.end_time if doc.end_time not in (None, "", " ") else frappe.utils.now_datetime()
    
    # Calculate total hours if start_time exists
    if doc.start_time:
        doc.time = frappe.utils.time_diff_in_hours(doc.end_time, doc.start_time)

    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    client_name = "Unknown"
    matter_id = "Unknown"

    if doc.matter:
        matter = frappe.get_doc("Matter", doc.matter)
        matter_id = matter.name
        client_name = matter.client or "Unknown"

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has ended.<br>
        Client: {client_name}
    """

    # ✅ Always email Charles only
    frappe.sendmail(
        recipients=["Charles.oyeshomo@odujinrinadefulu.com"],
        subject="Time Tracking Ended",
        message=message
    )

    frappe.publish_realtime(
        event="msgprint",
        message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})"
    )

    return "Finalized"


@frappe.whitelist()
def pause_time_tracking(time_tracking):
    """Mark timer as paused logically (no data mutation)."""
    doc = frappe.get_doc("Time Tracking", time_tracking)
    # just log that it was paused
    frappe.logger().info(f"Timer paused for {time_tracking}")
    return "Paused"


@frappe.whitelist()
def continue_time_tracking(time_tracking):
    """Mark timer as resumed logically (no data mutation)."""
    doc = frappe.get_doc("Time Tracking", time_tracking)
    frappe.logger().info(f"Timer continued for {time_tracking}")
    return "Continued"


