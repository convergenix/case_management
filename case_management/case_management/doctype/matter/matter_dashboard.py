from __future__ import unicode_literals

from frappe import _


def get_data():
	return {
		# 'heatmap': True,
		'heatmap_message': _('This is based on transactions against this Matter. See timeline below for details'),
		'fieldname': 'matter',
		'non_standard_fieldnames': {
			'Sales Invoice': 'matter_id',
			'Expense Claim': 'matter_id',
			'Employee Advance': 'matter_id',
			'Timesheet': 'matter_id',
			# 'Event': 'matter',	
			# 'Case File': 'matter_id',s
		# 	'Payment Entry': 'party',
		# 	'Quotation': 'party_name',
		# 	'Opportunity': 'party_name',
		# 	'Matter': 'client'
		},
		# 'dynamic_links': {
		# 	'party_name': ['Customer', 'quotation_to']
		# },
		'transactions': [

			{
				'label': _('PAYMENTS'),
				'items': ['Sales Invoice',]
			},
			{
				'label': _('EXPENSES'),
				'items': ['Expense Claim', 'Employee Advance',]
			},
			{
				'label': _('ACTIVITIES'),
				'items': ['Timesheet', ]
			},

			# {
			# 	'label': _('Folder'),
			# 	'items': ['Case File',]
			# },
			# {
			# 	'label': _('Orders'),
			# 	'items': ['Sales Order', 'Delivery Note', 'Sales Invoice']
			# },
			# {
			# 	'label': _('Payments'),
			# 	'items': ['Payment Entry']
			# },
			# {
			# 	'label': _('Support'),
			# 	'items': ['Issue']
			# },
			# {
			# 	'label': _('Projects'),
			# 	'items': ['Project']
			# },
			# {
			# 	'label': _('Pricing'),
			# 	'items': ['Pricing Rule']
			# },
			# {
			# 	'label': _('Subscriptions'),
			# 	'items': ['Subscription']
			# },
			# {
			# 	'label': _('Matters'),
			# 	'items': ['Matter']
			# }
		]
	}
