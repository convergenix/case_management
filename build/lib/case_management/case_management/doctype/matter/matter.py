# -*- coding: utf-8 -*-
# Copyright (c) 2015, bobzz.zone@gmail.com , masonarmani38@gmail.com and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt


class Matter(Document):
    def before_submit(self):
        self.status = "Close"
        self.close_date = frappe.utils.nowdate()

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
    # update without checking permissions
    frappe.db.sql("update `tab%s` set status = 'Closed' , docstatus=1 where name = '%s'" % (doctype, docname))
    return True

@frappe.whitelist()
def reopen(doctype, docname):
    # update without checking permissions
    frappe.db.sql("update `tab%s` set status = 'Open' , docstatus=0 where name = '%s'" % (doctype, docname))
    return True
