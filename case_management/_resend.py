import frappe


def add_desktop():
    # get all admin icons
    # get all users
    # use admin icons to create icons for other user
    all_user = frappe.db.sql("select name from `tabUser` where enabled = 1 "
                             "and name != 'Administrator'" , as_list=1)
    icons = frappe.get_all("Desktop Icon", {'owner': "Administrator"}, ["*"])
    for user in all_user:
        for icon in icons:
            icon = dict(icon)
            new_icon = frappe.new_doc("Desktop Icon")
            new_icon.owner = user
            new_icon.color = icon.get('color')
            new_icon.app = icon.get('app')
            new_icon.idx = icon.get('idx')
            new_icon.blocked = icon.get('blocked')
            new_icon.label = icon.get('label')
            new_icon.force_show = 1
            new_icon.custom = icon.get('custom')
            new_icon.standard = icon.get('standard')
            new_icon.link = icon.get('link')
            new_icon.icon = icon.get('icon')
            new_icon.reverse = icon.get('reverse')
            new_icon.module_name = icon.get('module_name')
            new_icon._report = icon.get('_report')
            new_icon._doctype = icon.get('_doctype')
            new_icon.db_insert()
