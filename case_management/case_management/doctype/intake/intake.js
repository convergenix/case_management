// Copyright (c) 2026, Convergenix and contributors
// For license information, please see license.txt

frappe.ui.form.on('Intake', {
    refresh: function (frm) {
        if (frm.doc.__islocal) {
            return;
        }

        var call = function (method, args, on_success) {
            frappe.call({
                method: "case_management.case_management.doctype.intake.intake." + method,
                args: Object.assign({intake: frm.doc.name}, args || {}),
                callback: function (r) {
                    if (on_success) {
                        on_success(r);
                    }
                    frm.reload_doc();
                }
            });
        };

        if (frm.doc.status === "Draft") {
            frm.add_custom_button(__('Submit for Review'), function () {
                call("submit_for_review");
            });
        }

        if (frm.doc.status === "Under Review") {
            frm.add_custom_button(__('Run Conflict Search'), function () {
                frappe.call({
                    method: "case_management.case_management.doctype.conflict_review.conflict_review.run_conflict_search",
                    args: {intake: frm.doc.name},
                    callback: function (r) {
                        if (r.message) {
                            frappe.msgprint(__('Conflict Review {0} created.', [r.message]));
                        }
                        frm.reload_doc();
                    }
                });
            });

            frm.add_custom_button(__('Approve'), function () {
                call("approve");
            });

            frm.add_custom_button(__('Decline'), function () {
                frappe.prompt([{
                    fieldname: "reason",
                    label: __("Decision Reason"),
                    fieldtype: "Small Text",
                    reqd: 1
                }], function (values) {
                    call("decline", {reason: values.reason});
                }, __("Decline Intake"), __("Decline"));
            });
        }

        if (["Draft", "Under Review"].includes(frm.doc.status)) {
            frm.add_custom_button(__('Withdraw'), function () {
                call("withdraw");
            });
        }
    }
});
