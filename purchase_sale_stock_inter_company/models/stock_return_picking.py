# Copyright 2025 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import UserError


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("skip_intercompany_return_block"):
            return res
        if self.env.context.get("active_model") != "stock.picking":
            return res
        active_id = self.env.context.get("active_id")
        if not active_id:
            return res
        picking = self.env["stock.picking"].sudo().browse(active_id)
        if not picking.exists():
            return res
        if (
            picking.location_dest_id.usage == "customer"
            and picking.picking_type_id.intercompany_sync_returns
            and picking.sale_id.auto_purchase_order_id
        ):
            purchase = picking.sale_id.auto_purchase_order_id
            raise UserError(
                _(
                    "This delivery is part of an intercompany flow. To return "
                    "it, create the return from the PO receipt of "
                    "%(po)s in %(company)s — the matching return will be "
                    "created automatically here.",
                    po=purchase.name,
                    company=purchase.company_id.display_name,
                )
            )
        return res

    def _create_returns(self):
        new_picking_id, picking_type_id = super()._create_returns()
        new_picking = self.env["stock.picking"].browse(new_picking_id)
        new_picking.move_ids.filtered(
            lambda m: m.state == "waiting"
            and all(o.state in ("done", "cancel") for o in m.move_orig_ids)
        )._recompute_state()
        self._create_intercompany_return(new_picking)
        return new_picking_id, picking_type_id

    def _create_intercompany_return(self, new_picking):
        self_sudo = self.sudo()
        original = self_sudo.picking_id
        intercompany_delivery = original.intercompany_picking_id
        if not (
            original.state == "done"
            and intercompany_delivery
            and intercompany_delivery.picking_type_id.intercompany_sync_returns
        ):
            return
        b_company = intercompany_delivery.company_id
        qty_by_so_line = {}
        SaleOrderLine = self.env["sale.order.line"].sudo()
        for return_line in self_sudo.product_return_moves.filtered(
            lambda r: r.quantity
        ):
            po_line = return_line.move_id.purchase_line_id
            if not po_line:
                continue
            so_line = SaleOrderLine.search(
                [("auto_purchase_line_id", "=", po_line.id)], limit=1
            )
            if so_line:
                qty_by_so_line[so_line] = (
                    qty_by_so_line.get(so_line, 0.0) + return_line.quantity
                )
        if not qty_by_so_line:
            return
        intercompany_user = b_company.intercompany_sale_user_id or self.env.user
        ReturnWizard = (
            self.env["stock.return.picking"]
            .with_user(intercompany_user.id)
            .sudo()
            .with_company(b_company)
        )
        src_wizard = ReturnWizard.with_context(
            active_id=intercompany_delivery.id,
            active_model="stock.picking",
            skip_intercompany_return_block=True,
        ).create({"picking_id": intercompany_delivery.id})
        src_wizard._onchange_picking_id()
        for src_line in src_wizard.product_return_moves:
            so_line = src_line.move_id.sale_line_id
            src_line.quantity = qty_by_so_line.get(so_line, 0.0)
        if not any(line.quantity for line in src_wizard.product_return_moves):
            new_picking.message_post(
                body=_(
                    "Intercompany return sync skipped: returned products were "
                    "not present on the linked delivery %(name)s.",
                    name=intercompany_delivery.name,
                )
            )
            return
        intercompany_return_id, __ = src_wizard._create_returns()
        intercompany_return = (
            self.env["stock.picking"].sudo().browse(intercompany_return_id)
        )
        intercompany_return.intercompany_picking_id = new_picking.id
