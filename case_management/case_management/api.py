from __future__ import unicode_literals
import frappe

translations = {
    "Legal": [
        ("Sales Invoice", "Service Invoice",),
        ("Vehicle", "Vehicle",),
        ("Sales Order", "Service Request",)
    ],
    "Services": [
        ("Sales Invoice", "Service Invoice",),
        ("Vehicle", "Motor",),
        ("Sales Order", "Service Request",)
    ]

}


def set_translation(doc, trigger):
    translation = translations.get(doc.domain)
    if translation:
        for dc in translation:
            # load custom translation
            set_name_translation(dc, dc[1])


def get_name_translation(translation=[]):
    '''Get translation object if exists of current doctype name in the default language'''
    return frappe.get_value('Translation',
                            {'source_name': translation[0], 'language': frappe.local.lang or 'en'},
                            ['name', 'target_name'], as_dict=True)


def set_name_translation(translation, label):
    '''Create, update custom translation for this doctype'''
    current = get_name_translation(translation)
    if current:
        if label and current != label:
            frappe.db.set_value('Translation', translation[0], 'target_name', label)
            frappe.translate.clear_cache()
        else:
            # clear translation
            frappe.delete_doc('Translation', current.name)

    else:
        if label:
            frappe.get_doc(dict(doctype='Translation',
                                source_name=translation[0],
                                target_name=label,
                                language_code=frappe.local.lang or 'en')).insert()

