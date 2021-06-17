from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    def _anglo_saxon_sale_move_lines(self, i_line):
        res = super(AccountInvoice, self)._anglo_saxon_sale_move_lines(i_line)
        our_companies = self.env['res.company'].search([('partner_id', '=', self.partner_id.id)])
        if our_companies and (i_line.product_id.property_account_expense_intercompany or i_line.product_id.categ_id.property_account_expense_categ_intercompany):
            accounts = i_line.product_id.product_tmpl_id.get_product_accounts()
            for item in res:
                if item["account_id"] == accounts["expense"].id:
                    item["account_id"] = i_line.product_id.property_account_expense_intercompany.id or i_line.product_id.categ_id.property_account_expense_categ_intercompany.id
        return res
