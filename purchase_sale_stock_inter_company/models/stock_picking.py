# Copyright 2018 Tecnativa - Carlos Dauden
# Copyright 2018 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    intercompany_picking_id = fields.Many2one(comodel_name="stock.picking", copy=False)
    intercompany_create_lots_mode = fields.Selection(
        related="picking_type_id.intercompany_create_lots_mode"
    )

    def _get_product_intercompany_qty_done_dict(self, sale_move_lines, po_move_lines):
        product = po_move_lines[0].product_id
        qty_done = sum(sale_move_lines.mapped("qty_done"))
        res = {product: qty_done}
        return res

    def _get_intercompany_move_lots(self, sale_move_lines, po_moves_open, **kwargs):
        po_move_lots = self.env["stock.lot"]
        lot_creation_mode = self.intercompany_create_lots_mode
        if lot_creation_mode == "same":
            for sale_lot in sale_move_lines.lot_id:
                po_move_lots |= sale_lot.get_inter_company_lot(
                    po_moves_open.company_id, **kwargs
                )
        elif lot_creation_mode == "manual":
            po_move_lots |= po_moves_open.mapped("lot_ids")
        return po_move_lots

    def _check_manual_lots(self, move, product):
        self.ensure_one()
        lot_names = move.move_line_ids.mapped("lot_name")
        lot_ids = move.lot_ids
        if (
            self.intercompany_create_lots_mode == "manual"
            and product.tracking != "none"
            and move.quantity_done
            and not lot_names
            and not lot_ids
        ):
            raise UserError(
                _(
                    "To validate the delivery, you must first assign lot/serial numbers"
                    " manually on the receipt of the intercompany purchase."
                )
            )

    def _get_intercompany_target_moves(self):
        if self.location_dest_id.usage == "customer":
            for sale_line in self.move_line_ids.move_id.sale_line_id:
                source_lines = self.move_line_ids.filtered(
                    lambda ml: ml.move_id.sale_line_id == sale_line
                )
                target_moves = sale_line.auto_purchase_line_id.move_ids.filtered(
                    lambda sm: sm.state not in ["draft", "done", "cancel"]
                )
                yield source_lines, target_moves, sale_line.product_id.name
        elif self.location_dest_id.usage == "supplier":
            SaleOrderLine = self.env["sale.order.line"].sudo()
            for po_line in self.move_line_ids.move_id.purchase_line_id:
                source_lines = self.move_line_ids.filtered(
                    lambda ml: ml.move_id.purchase_line_id == po_line
                )
                so_line = SaleOrderLine.search(
                    [("auto_purchase_line_id", "=", po_line.id)], limit=1
                )
                target_moves = so_line.move_ids.filtered(
                    lambda sm: sm.state not in ["draft", "done", "cancel"]
                )
                yield source_lines, target_moves, po_line.product_id.name

    def _set_intercompany_picking_qty(self, purchase):
        po_picks = self.browse()
        for (
            source_lines,
            target_moves,
            product_name,
        ) in self._get_intercompany_target_moves():
            if not target_moves:
                raise UserError(
                    _(
                        "There's no corresponding line in PO %(po)s for assigning "
                        "qty from %(pick_name)s for product %(product)s"
                    )
                    % (
                        {
                            "po": purchase.name,
                            "pick_name": self.name,
                            "product": product_name,
                        }
                    )
                )
            target_moves.picking_id.action_assign()
            product_qty_done = self._get_product_intercompany_qty_done_dict(
                source_lines, target_moves.move_line_ids
            )
            target_lots = self._get_intercompany_move_lots(source_lines, target_moves)
            for product, qty_done in product_qty_done.items():
                product_target_moves = target_moves.filtered(
                    lambda x: x.product_id == product
                )
                product_target_lots = target_lots.filtered(
                    lambda x: x.product_id == product
                )
                for target_move in product_target_moves:
                    if target_move.product_uom_qty >= qty_done:
                        target_move.quantity_done = qty_done
                        if product_target_lots:
                            target_move.lot_ids = product_target_lots
                        qty_done = 0.0
                    else:
                        target_move.quantity_done = target_move.product_uom_qty
                        if product_target_lots:
                            qty = int(target_move.product_uom_qty)
                            target_move.lot_ids = product_target_lots[:qty]
                            product_target_lots = product_target_lots[qty:]
                        qty_done -= target_move.product_uom_qty
                    self._check_manual_lots(target_move, product)
                    po_picks |= target_move.picking_id
                if qty_done and product_target_moves:
                    product_target_moves[-1:].quantity_done += qty_done
                    if product_target_lots:
                        product_target_moves[-1:].lot_ids |= product_target_lots
                    self._check_manual_lots(product_target_moves[-1:], product)
        return po_picks

    def _action_done(self):
        cross_company_picks = self.browse()
        for pick in self.sudo():
            # Forward deliveries (Company B → Company A)
            if pick.location_dest_id.usage == "customer":
                purchase = pick.sale_id.auto_purchase_order_id
                if not purchase:
                    continue
                synced = pick._set_intercompany_picking_qty(purchase)
                synced.write({"intercompany_picking_id": pick.id})
                cross_company_picks |= synced
            # Returns initiated from Company A (back to supplier Company B)
            elif pick.location_dest_id.usage == "supplier":
                linked = (
                    self.env["stock.picking"]
                    .sudo()
                    .search(
                        [
                            ("intercompany_picking_id", "=", pick.id),
                            ("state", "not in", ["done", "cancel"]),
                        ],
                        limit=1,
                    )
                )
                if not linked:
                    continue
                purchase = pick.move_ids.purchase_line_id.order_id[:1]
                if not purchase:
                    continue
                cross_company_picks |= pick._set_intercompany_picking_qty(purchase)
        for ic_pick in cross_company_picks.sudo():
            ic_pick._action_done()
        return super()._action_done()
