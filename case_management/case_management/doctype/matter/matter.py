# -*- coding: utf-8 -*-
# Copyright (c) 2015, bobzz.zone@gmail.com , masonarmani38@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt


TRANSITIONS = {
    "Open": {"Active", "On Hold", "Closing"},
    "Active": {"On Hold", "Closing"},
    "On Hold": {"Active", "Closing"},
    "Closing": {"Closed", "Active"},
    "Closed": {"Archived"},
    "Archived": set(),
}

REOPEN_ROLES = {"Partner", "Managing Partner", "System Manager"}


def _state_log_fingerprint(row):
    # changed_at arrives as a datetime when loaded from the DB and as a string
    # when it comes off an API payload, so it is normalized before comparison.
    return (
        row.previous_state or "",
        row.new_state or "",
        row.changed_by or "",
        frappe.utils.get_datetime(row.changed_at) if row.changed_at else None,
        row.reason or "",
    )


class Matter(Document):
    def validate(self):
        if self.is_new():
            self._validate_intake_gate()
        else:
            self._enforce_append_only_state_log()
            self._enforce_state_transition()

    def _enforce_append_only_state_log(self):
        # read_only on the Table field is a UI restriction; without this an API
        # caller with Matter write access could rewrite the transition history.
        previous = self.get_doc_before_save()
        if not previous:
            return

        current_rows = {row.name: row for row in self.state_log if row.name}
        for old_row in previous.state_log:
            current_row = current_rows.get(old_row.name)
            if not current_row:
                frappe.throw("The Matter state history is append-only — existing entries cannot be removed.")
            if _state_log_fingerprint(current_row) != _state_log_fingerprint(old_row):
                frappe.throw("The Matter state history is append-only — existing entries cannot be edited.")

    def _validate_intake_gate(self):
        if not self.intake:
            frappe.throw("A Matter cannot be opened without an approved Intake.")
        intake = frappe.get_doc("Intake", self.intake)
        if intake.status != "Approved":
            frappe.throw(f"Intake {intake.name} is not Approved (current status: {intake.status}).")
        if intake.converted_matter:
            frappe.throw(f"Intake {intake.name} has already been converted to Matter {intake.converted_matter}.")
        reviews = frappe.get_all(
            "Conflict Review",
            filters={"intake": intake.name, "decision": ["in", ["Clear", "Waiver Granted"]]},
            fields=["party_set_hash"],
            order_by="search_timestamp desc",
            limit=1,
        )
        if not reviews or reviews[0].party_set_hash != intake.get_party_set_hash():
            frappe.throw(
                "Conflict clearance for this Intake is missing or stale. "
                "Re-run the conflict search before opening the matter."
            )

    def _enforce_state_transition(self):
        previous_status = frappe.db.get_value("Matter", self.name, "status")
        if previous_status == self.status:
            return

        allowed = TRANSITIONS.get(previous_status, set())
        reopening = previous_status in ("Closed", "Archived") and self.status in ("Open", "Active")

        if self.status not in allowed and not reopening:
            frappe.throw(f"Invalid Matter status transition: {previous_status} -> {self.status}.")

        if reopening:
            if not self.reopen_reason:
                frappe.throw("Reopening a Closed/Archived matter requires a reason in 'Reopen Reason'.")
            if not REOPEN_ROLES & set(frappe.get_roles(frappe.session.user)):
                frappe.throw("You are not authorized to reopen this matter.")

        self.append("state_log", {
            "previous_state": previous_status,
            "new_state": self.status,
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": self.reopen_reason if reopening else "",
        })

        if reopening:
            self.reopen_reason = None

    def after_insert(self):
        row = self.append("state_log", {
            "previous_state": "",
            "new_state": self.status,
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": "Matter opened",
        })
        row.db_insert()

        frappe.db.set_value("Intake", self.intake, {
            "status": "Converted",
            "converted_matter": self.name,
        })

    def before_submit(self):
        previous_status = frappe.db.get_value("Matter", self.name, "status")
        self.status = "Closed"
        self.close_date = frappe.utils.nowdate()
        self.append("state_log", {
            "previous_state": previous_status,
            "new_state": "Closed",
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": "Matter closed via submit",
        })

    def on_trash(self):
        file = frappe.db.sql("select name from `tabFile` where file_name = \"Home/Clients/{0}\"".format(self.name))
        if len(file) > 0:
            frappe.throw("Sorry, Matter cannot be deleted. Case files exist for matter.")


    def autoname(self):
        if self.original_matter_id is not None:
            self.name = str(self.original_matter_id).replace('"','')
        self.name = self.name

    def get_custom_field(self):
        if self.custom_field:
            data = frappe.db.sql(
                """select title from `tabMatter Custom Check List Item` where parent="{}" """
                    .format(self.custom_field), as_list=1)
            self.check_list = []
            for row in data:
                dt = self.append('check_list', {})
                dt.title = row[0]
        else:
            frappe.throw("""Please select a Custom Field Preset. """)


# Known limitation: Frappe ANDs role-level DocPerm conditions with
# permission_query_conditions, and Matter's base DocPerm for "Lawyer Manager"
# carries if_owner=1 while the only unrestricted-read role ("Partners") is
# disabled. A team member who does not personally own a matter is therefore
# filtered out before the allowances below are consulted, so the DENY side of
# the ethical wall holds but the ALLOW side cannot currently grant anyone
# access to a matter they did not create. See the M1 access-control section of
# docs/superpowers/specs/2026-10-19-lawerp-r0-foundation-design.md.
def get_permission_query_conditions(user=None):
    if not user:
        user = frappe.session.user
    if {"System Manager", "Managing Partner"} & set(frappe.get_roles(user)):
        return ""
    return """(`tabMatter`.is_restricted = 0 or `tabMatter`.name in (
        select mti.parent from `tabMatter Team Item` mti
        inner join `tabEmployee` emp on emp.name = mti.employee
        where emp.user_id = {user}
    ) or `tabMatter`.responsible_solicitor in (
        select emp.name from `tabEmployee` emp where emp.user_id = {user}
    ))""".format(user=frappe.db.escape(user))


def get_matter_access_condition(matter_column, user=None):
    """SQL fragment limiting a Matter-name column to the matters `user` may see.

    `permission_query_conditions` only reaches get_list/get_all and desk list
    views. Raw SQL — the Matter calendar and the Script Reports — has to apply
    the same restriction itself, through here. The empty/null branch keeps rows
    whose Matter link is blank (unbilled time entries, for instance) in reports
    that outer-join Matter.
    """
    condition = get_permission_query_conditions(user)
    if not condition:
        return ""
    return "(ifnull({column}, '') = '' or {column} in (select `tabMatter`.name from `tabMatter` where {condition}))".format(
        column=matter_column, condition=condition
    )


# Subject to the same base-DocPerm limitation documented above
# get_permission_query_conditions.
def has_permission(doc, user=None, permission_type=None):
    if not user:
        user = frappe.session.user
    if not doc.is_restricted:
        return True
    if {"System Manager", "Managing Partner"} & set(frappe.get_roles(user)):
        return True
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return False
    if doc.responsible_solicitor == employee:
        return True
    return bool(frappe.db.exists("Matter Team Item", {"parent": doc.name, "employee": employee}))


def create_new_folder(file_name, folder):
    file = frappe.new_doc("File")
    file.file_name = file_name
    file.is_folder = 1
    file.folder = folder
    file.insert()


@frappe.whitelist()
def get_events(start, end, filters=None):
    """Returns events for Gantt / Calendar view rendering.

    :param start: Start date-time.
    :param end: End date-time.
    :param filters: Filters (JSON).
    """
    from frappe.desk.calendar import get_event_conditions
    conditions = get_event_conditions("Matter", filters)

    access_condition = get_permission_query_conditions()
    if access_condition:
        conditions += " and " + access_condition

    data = frappe.db.sql("""select name,CONCAT(name," ",client) as title , open_date,
		close_date, status from `tabMatter` where
		((ifnull(open_date, '0000-00-00') != '0000-00-00')  and (open_date <= %(end)s and open_date >= %(start)s))
		{conditions}
		""".format(conditions=conditions), {
        "start": start,
        "end": end
    }, as_dict=True)
    return data


@frappe.whitelist()
def get_lawyer(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""select u.name, concat(u.first_name, ' ', u.last_name) from tabUser u, `tabHas Role` r where
    u.name = r.parent and r.role = 'Lawyer' and u.enabled = 1 and u.name like %s""", ("%" + txt + "%"))


@frappe.whitelist()
def make_invoice(source_name, target_doc=None):
    def set_missing_values(source, target):
        pass

    def update_item(source, target, source_parent):
        pass

    target_doc = get_mapped_doc("Matter", source_name, {
        "Matter": {
            "doctype": "Sales Invoice",
            "field_map": {
                "client": "customer",
                "matter_id": "name",
            }
        },

    }, target_doc, set_missing_values)

    return target_doc


@frappe.whitelist()
def make_expense(source_name, target_doc=None):
    def set_missing_values(source, target):
        pass

    def update_item(source, target, source_parent):
        pass

    target_doc = get_mapped_doc("Matter", source_name, {
        "Matter": {
            "doctype": "Expense Claim",
            "field_map": {
                "matter": "name",
            }
        },

    }, target_doc, set_missing_values)

    return target_doc

@frappe.whitelist()
def make_advance(source_name, target_doc=None):
    def set_missing_values(source, target):
        pass

    def update_item(source, target, source_parent):
        pass

    target_doc = get_mapped_doc("Matter", source_name, {
        "Matter": {
            "doctype": "Employee Advance",
            "field_map": {
                "matter": "name",
            }
        },

    }, target_doc, set_missing_values)

    return target_doc


@frappe.whitelist()
def make_task(source_name, target_doc=None):
    def set_missing_values(source, target):
        pass

    def update_item(source, target, source_parent):
        pass

    target_doc = get_mapped_doc("Matter", source_name, {
        "Matter": {
            "doctype": "Task",
            "field_map": {
                "client": "customer",
                "matter": "name",
            }
        },

    }, target_doc, set_missing_values)

    return target_doc



@frappe.whitelist()
def make_timesheet(source_name, target_doc=None):
    def set_missing_values(source, target):
        pass

    def update_item(source, target, source_parent):
        pass

    target_doc = get_mapped_doc("Matter", source_name, {
        "Matter": {
            "doctype": "Timesheet",
            "field_map": {
                "matter": "name",
            }
        },

    }, target_doc, set_missing_values)

    return target_doc


def invoice_update(doc, method):
    if not doc.matter_id:
        return
    if method == "on_submit":
        record = frappe.new_doc("Matter Invoice")
        # frappe.throw(doc.name)
        record.update({"parent": doc.matter_id, "parenttype": "Matter", "parentfield": "invoice", "status": doc.status,
                       "invoice": doc.name, "total": flt(doc.grand_total)})
        record.insert()
        record.save()
    else:
        frappe.db.sql(
            """delete from `tabMatter Invoice` where parent="{}" and invoice="{}" """.format(doc.matter_id, doc.name))


def payment_update(doc, method):
    for row in doc.references:
        if row.allocated_amount == row.outstanding_amount and row.reference_doctype == "Sales Invoice":
            frappe.db.sql(
                """update `tabMatter Invoice` set status="Paid" where invoice="{}" """.format(row.reference_name))

        if row.allocated_amount == row.outstanding_amount and row.reference_doctype == "Expense Claim":
            frappe.db.sql(
                """update `tabMatter Expense` set status="Paid" where expense="{}" """.format(row.reference_name))


def payment_cancel(doc, method):
    for row in doc.references:
        if row.reference_doctype == "Sales Invoice":
            frappe.db.sql(
                """update `tabMatter Invoice` set status="Unpaid" where  invoice="{}" """.format(row.reference_name))

        if row.reference_doctype == "Expense Claim":
            frappe.db.sql(
                """update `tabMatter Expense` set status="Unpaid" where  expense="{}" """.format(row.reference_name))


def expense_update(doc, method):
    if not doc.matter_id:
        return
    if method == "on_submit":
        record = frappe.new_doc("Matter Expense")
        # frappe.throw(doc.name)
        record.update({"parent": doc.matter_id, "parenttype": "Matter", "parentfield": "expense", "status": doc.status,
                       "expense": doc.name, "total": flt(doc.total_sanctioned_amount)})
        record.insert()
        record.save()
    else:
        frappe.db.sql(
            """delete from `tabMatter Expense` where parent="{}" and expense="{}" """.format(doc.matter_id, doc.name))


def timesheet_update(doc, method):
    if not doc.matter_id:
        return
    # frappe.throw(method)
    if method == "on_submit":
        record = frappe.new_doc("Matter Timesheet")
        record.update(
            {"parent": doc.matter_id, "parenttype": "Matter", "parentfield": "activities", "time_sheet": doc.name,
             "total_hours": flt(doc.total_hours), "employee": doc.employee, "employee_name": doc.employee_name})
        record.insert()
        record.save()
    else:
        frappe.db.sql(
            """delete from `tabMatter Timesheet` where parent="{}" and time_sheet="{}" """.format(doc.matter_id, doc.name))


@frappe.whitelist()
def resolve(doctype, docname):
    doc = frappe.get_doc(doctype, docname)
    doc.status = "Closed"
    doc.save()
    return True


@frappe.whitelist()
def reopen(doctype, docname, reason=None):
    doc = frappe.get_doc(doctype, docname)
    doc.status = "Active"
    if reason:
        doc.reopen_reason = reason
    doc.save()
    return True
