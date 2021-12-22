frappe.views.calendar["Matter"] = {
	field_map: {
		"start": "open_date",
		"end": "open_date",
		"id": "name",
		"allDay": "all_day",
		"title": "name",
		"status": "status",
		"color": "blue"
	},
	style_map: {
		"Public": "success",
		"Private": "info"
	},
	filters: [
		{
			'fieldtype': 'Link',
			'fieldname': 'matter',
			'options': 'Matter',
			'label': __('Matter')
		}
	],
	get_events_method: "case_management.case_management.doctype.matter.matter.get_events"
}