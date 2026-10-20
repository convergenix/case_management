# -*- coding: utf-8 -*-
# Copyright (c) 2017, bobzz.zone@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, now_datetime, flt
from erpnext.setup.utils import get_exchange_rate


class TimeTracking(Document):

    def validate(self):
        if self.is_new():
            previous_wip_status = "Draft"
            # Nothing can be created pre-approved -- force a clean Draft slate
            # regardless of what the caller supplied.
            self.wip_status = "Draft"
            self.approved_rate = None
            self.approved_currency = None
            self.approved_amount = None
            self.approved_by = None
            self.approved_on = None
        else:
            previous = frappe.db.get_value(
                "Time Tracking", self.name,
                ["wip_status", "approved_rate", "approved_currency", "approved_amount", "time"],
                as_dict=True,
            )
            previous_wip_status = previous.wip_status

            if previous_wip_status != "Draft":
                # Once approval has happened the WIP snapshot is immutable; only
                # approve_time_entry (Draft->Approved) or the backend release/billing
                # paths (raw SQL, bypassing validate()) may ever touch these fields.
                for fieldname in ("approved_rate", "approved_currency", "approved_amount", "time"):
                    old_value, new_value = previous.get(fieldname), self.get(fieldname)
                    changed = (
                        flt(old_value) != flt(new_value)
                        if fieldname != "approved_currency"
                        else old_value != new_value
                    )
                    if changed:
                        frappe.throw(
                            f"Cannot modify {fieldname} after Time Tracking approval; the WIP snapshot is locked."
                        )

        wip_transitions = {
            "Draft": {"Approved"},
            "Approved": {"Reserved", "Written Off"},
            # Reserved -> Approved is deliberately NOT a legal validate()-gated
            # transition: release back to Approved happens only via _release_lines'
            # raw SQL in fee_note.py (which bypasses validate() entirely), specifically
            # so a stale in-memory .save() can never double-spend a live reservation.
            "Reserved": {"Billed"},
            "Billed": set(),
            "Written Off": set(),
        }
        if previous_wip_status != self.wip_status:
            if self.wip_status not in wip_transitions.get(previous_wip_status, set()):
                frappe.throw(
                    f"Cannot move Time Tracking WIP status from {previous_wip_status} to {self.wip_status}."
                )

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


@frappe.whitelist()
def approve_time_entry(time_tracking):
    doc = frappe.get_doc("Time Tracking", time_tracking)
    if doc.docstatus == 1:
        frappe.throw(
            "Cannot approve a submitted Time Tracking entry for WIP billing; approval must "
            "happen before submission. This is a deliberate draft-only design decision for "
            "this thin slice, not a workaround."
        )
    if doc.billing != "Billable":
        frappe.throw("Only Billable time entries can be approved for WIP.")
    if doc.wip_status != "Draft":
        frappe.throw(f"Only a Draft entry can be approved (current WIP status: {doc.wip_status}).")

    customer = doc.matter_name
    rate_info = frappe.db.get_value(
        "Billing Details", {"customer": customer}, ["billing_rate", "billing_currency"], as_dict=True
    )
    if not rate_info or not rate_info.billing_rate:
        frappe.throw(f"No Billing Details rate configured for {customer}.")

    doc.wip_status = "Approved"
    doc.approved_rate = rate_info.billing_rate
    doc.approved_currency = rate_info.billing_currency
    doc.approved_amount = flt(doc.time) * flt(rate_info.billing_rate)
    doc.approved_by = frappe.session.user
    doc.approved_on = now_datetime()
    doc.save(ignore_permissions=True)
    return doc.name


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