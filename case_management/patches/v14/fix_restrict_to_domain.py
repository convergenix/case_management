import frappe

def execute():
    print("""
        Resetting restrcit to to domain to emppty field
    """)
    frappe.db.sql("""
        UPDATE `tabModule Def` SET restrict_to_domain='';
    """)
    frappe.db.sql("""
        UPDATE `tabModule Def` SET restrict_to_domain='';
    """)