import frappe


def set_default_workspace():
    if frappe.db.exists("Workspace", "LawERP"):
        frappe.defaults.set_default("desktop:home_page", "LawERP", "__default")
        if not frappe.db.get_single_value("System Settings", "default_app"):
            frappe.db.set_single_value("System Settings", "default_app", "case_management")


def update_translation():
    print("Updating Translation")
    translations = frappe.get_all("Translation")
    settings = frappe.get_single("System Settings")
    for i in translations:
        doc = frappe.get_doc("Translation", i.name)
        new_doc = frappe.get_doc(doc.as_dict())
        doc.delete()
        new_doc.language = settings.language or "en"
        new_doc.context = ""
        new_doc.insert(ignore_permissions=1)
