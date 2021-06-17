from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _prepare_invoice_line(self, qty):
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)

        our_companies = self.env['res.company'].search([('partner_id', '=', self.order_id.partner_id.id)])
        if our_companies and (self.product_id.property_account_income_intercompany or self.product_id.categ_id.property_account_income_categ_intercompany):
            account = self.product_id.property_account_income_intercompany or self.product_id.categ_id.property_account_income_categ_intercompany
            res.update({'account_id': account.id})
        return res
