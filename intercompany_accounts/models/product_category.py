from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    property_account_income_categ_intercompany = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        string="Income Intercompany Account",
        help="This account will be used when validating a customer invoice."
    )
    property_account_expense_categ_intercompany = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        string="Expense Intercompany Account",
        help="This account will be used when validating a customer invoice."
    )
