from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    property_account_income_intercompany = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        string="Income Intercompany Account",
        help="Keep this field empty to use the default value from the product category."
    )
    property_account_expense_intercompany = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        string="Expense Intercompany Account",
        help="Keep this field empty to use the default value from the product category."
    )
