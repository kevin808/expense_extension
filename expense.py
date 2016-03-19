# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2010-2014. All Rights Reserved.
#    Kevin Lee <likan2008@126.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp import api, fields, models, _
from openerp.exceptions import UserError
import openerp.addons.decimal_precision as dp


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    expense_id = fields.Many2one(
        comodel_name='hr.expense',
        string=u'报销')

    order_id = fields.Many2one(
        'sale.order',
        string='Order Reference',
        required=False,
        ondelete='cascade',
        index=True, copy=False)

class HrExpense(models.Model):
    _inherit = 'hr.expense'

    state = fields.Selection([('draft', u'待提交'),
                              ('submit', u'待经理审批'),
                              ('agree', u'待总经理审批'),
                              ('approve', u'已通过'),
                              ('post', u'待付款'),
                              ('done', u'已付款'),
                              ('cancel', u'已拒绝')
                              ], string=u'审批状态', index=True, readonly=True, track_visibility='onchange', copy=False, default='draft', required=True,
                             help=u'提交报销单后，部门经理会先审批，然后总经理审批，全部通过后出纳会付款给申请人')

    product_id = fields.Many2one(required=False)

    quantity = fields.Float(default=0)

    unit_amount = fields.Float(default=0)

    line_ids = fields.One2many(
        comodel_name='sale.order.line',
        inverse_name='expense_id',
        string=u'报销类型', readonly=True, required=True, states={'draft': [('readonly', False)]},)

    @api.depends('line_ids.price_total')
    def _compute_amount(self):
        for expense in self:
            tmp = 0
            for line in expense.line_ids:
                tmp += line.price_total
            expense.total_amount = tmp

    def _prepare_move_line(self, line):
        '''
        This function prepares move line of account.move related to an expense
        '''
        partner_id = self.employee_id.address_home_id.commercial_partner_id.id
        return {
            'date_maturity': line.get('date_maturity'),
            'partner_id': partner_id,
            'name': line['name'][:64],
            'date': self.date,
            'debit': line['price'] > 0 and line['price'],
            'credit': line['price'] < 0 and -line['price'],
            'account_id': line['account_id'],
            'analytic_line_ids': line.get('analytic_line_ids'),
            'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or -abs(line.get('amount_currency')),
            'currency_id': line.get('currency_id'),
            'tax_line_id': line.get('tax_line_id'),
            'ref': line.get('ref'),
            'quantity': line.get('quantity', 1.00),
            'product_id': line.get('product_id'),
            'product_uom_id': line.get('uom_id'),
            'analytic_account_id': line.get('analytic_account_id'),
        }

    @api.multi
    def _move_line_get(self):
        account_move = []
        for expense_pack in self:
            for expense in expense_pack.line_ids:
                if expense.product_id:
                    account = expense.product_id.product_tmpl_id._get_product_accounts()[
                        'expense']
                    if not account:
                        raise UserError(_("No Expense account found for the product %s (or for it's category), please configure one.") % (
                            expense.product_id.name))
                else:
                    account = self.env['ir.property'].with_context(force_company=expense.company_id.id).get(
                        'property_account_expense_categ_id', 'product.category')
                    if not account:
                        raise UserError(
                            _('Please configure Default Expense account for Product expense: `property_account_expense_categ_id`.'))
                move_line = {
                    'type': 'src',
                    'name': expense.name.split('\n')[0][:64],
                    'price_unit': expense.price_unit,
                    'quantity': expense.product_uom_qty,
                    'price': expense.price_total,
                    'account_id': account.id,
                    'product_id': expense.product_id.id,
                    'uom_id': expense.product_uom.id,
                    'analytic_account_id': expense_pack.analytic_account_id.id,
                }
                account_move.append(move_line)
            return account_move

    @api.multi
    def agree_expenses(self):
        self.write({'state': 'agree'})

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'approve':
            return 'hr_expense.mt_expense_approved'
        elif 'state' in init_values and self.state == 'agree':
            return 'hr_expense.mt_expense_agreed'
        elif 'state' in init_values and self.state == 'submit':
            return 'hr_expense.mt_expense_confirmed'
        elif 'state' in init_values and self.state == 'cancel':
            return 'hr_expense.mt_expense_refused'
        return super(HrExpense, self)._track_subtype(init_values)
