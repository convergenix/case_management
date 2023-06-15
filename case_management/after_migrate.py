import frappe

def update_translation():
    print("Updating Translation")
    translations = frappe.get_all("Translation")
    settings = frappe.get_single("System Settings")
    for i in translations:
        doc = frappe.get_doc("Translation", i.name)
        new_doc = frappe.get_doc(doc.as_dict())
        doc.delete()
        new_doc.language = settings.language
        new_doc.context = ""
        new_doc.insert(ignore_permissions=1)
