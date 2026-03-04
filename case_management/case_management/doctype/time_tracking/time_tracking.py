# -*- coding: utf-8 -*-
# Copyright (c) 2017, bobzz.zone@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, now_datetime, flt
from erpnext.setup.utils import get_exchange_rate


class TimeTracking(Document):

    def on_submit(self):
        if self.start_time:
            self.status = "Time Tracking Started"
        self.calculate_revenue()

    def before_save(self):
        # Auto-stamp employee from the logged-in user if not already set
        if not self.employee:
            employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
            if employee:
                self.employee = employee

        self.calculate_revenue()

    def calculate_revenue(self):
        """Calculate revenue based on customer's billing currency.
        USD   → format in dollars, convert to naira.
        NGN   → format in naira, no conversion.
        Other → convert to USD first, then to naira.
        """
        if self.billing == "Billable" and self.time:
            customer = self.matter_name

            if customer:
                result = frappe.db.get_value(
                    "Billing Details",
                    {"customer": customer},
                    ["billing_rate", "billing_currency"],
                    as_dict=True
                )
                billing_rate     = flt(result.billing_rate)   if result else 0
                billing_currency = result.billing_currency     if result else "USD"

                if billing_rate:
                    hours = flt(self.time)

                    if billing_currency == "USD":
                        revenue_usd             = round(billing_rate * hours, 2)
                        self.revenue            = f"$ {revenue_usd:,.2f}"
                        usd_to_ngn              = get_exchange_rate("USD", "NGN")
                        self.revenue_in_naira   = round(revenue_usd * flt(usd_to_ngn), 2)
                        self.exchange_rate_used = flt(usd_to_ngn)

                    elif billing_currency == "NGN":
                        revenue_ngn             = round(billing_rate * hours, 2)
                        self.revenue            = f"₦ {revenue_ngn:,.2f}"
                        self.revenue_in_naira   = revenue_ngn
                        self.exchange_rate_used = 1

                    else:
                        rate_to_usd             = get_exchange_rate(billing_currency, "USD")
                        revenue_usd             = round(billing_rate * hours * flt(rate_to_usd), 2)
                        self.revenue            = f"$ {revenue_usd:,.2f}"
                        usd_to_ngn              = get_exchange_rate("USD", "NGN")
                        self.revenue_in_naira   = round(revenue_usd * flt(usd_to_ngn), 2)
                        self.exchange_rate_used = flt(usd_to_ngn)
                    return

        # Fallback
        self.revenue          = "$ 0.00"
        self.revenue_in_naira = 0


# ─── Whitelisted API methods ──────────────────────────────────────────────────

@frappe.whitelist()
def finalize_time_tracking(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)

    doc.end_time = (
        doc.end_time
        if doc.end_time not in (None, "", " ")
        else now_datetime()
    )

    if doc.start_time:
        doc.time = time_diff_in_hours(doc.end_time, doc.start_time)

    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    _send_notification(doc)
    return "Finalized"


@frappe.whitelist()
def stop_time_tracking_now(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)

    doc.end_time = (
        doc.end_time
        if doc.end_time not in (None, "", " ")
        else now_datetime()
    )

    if doc.start_time:
        doc.time = time_diff_in_hours(doc.end_time, doc.start_time)

    doc.status = "Time Tracking Ended"
    doc.calculate_revenue()
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    _send_notification(doc)
    return "Stopped"


@frappe.whitelist()
def end_time_tracking(time_tracking):
    """Legacy endpoint — delegates to finalize."""
    return finalize_time_tracking(time_tracking)


@frappe.whitelist()
def pause_time_tracking(time_tracking):
    frappe.logger().info(f"Timer paused for {time_tracking} by {frappe.session.user}")
    return "Paused"


@frappe.whitelist()
def continue_time_tracking(time_tracking):
    frappe.logger().info(f"Timer resumed for {time_tracking} by {frappe.session.user}")
    return "Continued"


# ─── Internal helper ──────────────────────────────────────────────────────────

def _send_notification(doc):
    client_name = "Unknown Client"
    matter_id   = "Unknown Matter"

    if doc.matter:
        matter      = frappe.get_doc("Matter", doc.matter)
        matter_id   = matter.name
        client_name = matter.client or "Unknown Client"

    message = f"""
        Time Tracking for Matter <b>{matter_id}</b> has ended.<br>
        Client: {client_name}<br>
        Employee: {doc.employee_name or doc.employee or "N/A"}<br>
        Revenue: {doc.revenue or "$ 0.00"}
    """

    frappe.sendmail(
        recipients=["Charles.oyeshomo@odujinrinadefulu.com"],
        subject=f"Time Tracking Ended — {matter_id}",
        message=message
    )

    frappe.publish_realtime(
        event="msgprint",
        message=f"⏰ Time Tracking Ended for Matter {matter_id} (Client: {client_name})"
    )