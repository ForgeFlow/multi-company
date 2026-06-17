# Copyright 2025 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import Form

from .test_inter_company_purchase_sale_stock import TestPurchaseSaleStockInterCompany


class TestPurchaseSaleStockInterCompanyReturn(TestPurchaseSaleStockInterCompany):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product.type = "product"
        cls.partner_company_b.company_id = False

    def _do_forward_flow(self, qty=3.0):
        self.purchase_company_a.order_line.product_qty = qty
        sale = self._approve_po()
        sale.action_confirm()
        sale_picking = sale.picking_ids
        sale_picking.sudo().action_confirm()
        sale_picking.sudo().action_assign()
        sale_picking.move_ids.quantity_done = qty
        sale_picking.sudo().button_validate()
        purchase_receipt = self.purchase_company_a.picking_ids.filtered(
            lambda p: p.intercompany_picking_id == sale_picking
        )
        return sale, sale_picking, purchase_receipt

    def _create_a_return(self, purchase_receipt, qty_per_product):
        wizard = (
            self.env["stock.return.picking"]
            .with_context(active_id=purchase_receipt.id, active_model="stock.picking")
            .sudo()
            .create({"picking_id": purchase_receipt.id})
        )
        wizard._onchange_picking_id()
        for line in wizard.product_return_moves:
            line.quantity = qty_per_product.get(line.product_id, 0.0)
        new_picking_id, __ = wizard._create_returns()
        return self.env["stock.picking"].sudo().browse(new_picking_id)

    def test_return_simple_no_lot(self):
        sale, sale_picking, purchase_receipt = self._do_forward_flow(qty=3.0)
        self.assertEqual(purchase_receipt.state, "done")
        self.assertEqual(purchase_receipt.intercompany_picking_id, sale_picking)
        co_a_return = self._create_a_return(purchase_receipt, {self.product: 3.0})
        co_b_return = (
            self.env["stock.picking"]
            .sudo()
            .search([("intercompany_picking_id", "=", co_a_return.id)])
        )
        self.assertEqual(len(co_b_return), 1)
        self.assertEqual(co_b_return.company_id, self.company_b)
        self.assertEqual(sum(co_b_return.move_ids.mapped("product_uom_qty")), 3.0)
        self.assertNotIn(co_b_return.state, ("done", "cancel"))
        co_a_return.move_ids.quantity_done = 3.0
        co_a_return.sudo().button_validate()
        self.assertEqual(co_a_return.state, "done")
        self.assertEqual(co_b_return.state, "done")
        self.assertEqual(sum(co_b_return.move_line_ids.mapped("qty_done")), 3.0)

    def test_return_partial_qty(self):
        sale, sale_picking, purchase_receipt = self._do_forward_flow(qty=3.0)
        co_a_return = self._create_a_return(purchase_receipt, {self.product: 1.0})
        co_b_return = (
            self.env["stock.picking"]
            .sudo()
            .search([("intercompany_picking_id", "=", co_a_return.id)])
        )
        self.assertEqual(len(co_b_return), 1)
        self.assertEqual(sum(co_b_return.move_ids.mapped("product_uom_qty")), 1.0)

    def test_block_direct_return_on_company_b(self):
        sale, sale_picking, purchase_receipt = self._do_forward_flow(qty=3.0)
        with self.assertRaises(UserError):
            self.env["stock.return.picking"].with_context(
                active_id=sale_picking.id, active_model="stock.picking"
            ).sudo().create({"picking_id": sale_picking.id})

    def test_return_sync_disabled_allows_b_side_return(self):
        sale, sale_picking, purchase_receipt = self._do_forward_flow(qty=3.0)
        sale_picking.picking_type_id.sudo().intercompany_sync_returns = False
        wizard = (
            self.env["stock.return.picking"]
            .with_context(active_id=sale_picking.id, active_model="stock.picking")
            .sudo()
            .create({"picking_id": sale_picking.id})
        )
        wizard._onchange_picking_id()
        for line in wizard.product_return_moves:
            line.quantity = 3.0
        new_picking_id, __ = wizard._create_returns()
        b_return = self.env["stock.picking"].sudo().browse(new_picking_id)
        self.assertEqual(b_return.company_id, self.company_b)
        co_a_return_search = (
            self.env["stock.picking"]
            .sudo()
            .search([("intercompany_picking_id", "=", b_return.id)])
        )
        self.assertFalse(co_a_return_search)

    def test_return_sync_disabled_on_a_side(self):
        sale, sale_picking, purchase_receipt = self._do_forward_flow(qty=3.0)
        sale_picking.picking_type_id.sudo().intercompany_sync_returns = False
        co_a_return = self._create_a_return(purchase_receipt, {self.product: 3.0})
        co_b_return = (
            self.env["stock.picking"]
            .sudo()
            .search([("intercompany_picking_id", "=", co_a_return.id)])
        )
        self.assertFalse(co_b_return)

    def test_return_with_lot_same_mode(self):
        self.product.tracking = "serial"
        serial01 = self.env["stock.lot"].create(
            {
                "name": "Serial01",
                "product_id": self.product.id,
                "company_id": self.company_b.id,
            }
        )
        self.purchase_company_a.order_line.product_qty = 1.0
        sale = self._approve_po()
        sale.action_confirm()
        self.env["stock.quant"]._update_available_quantity(
            self.product, sale.warehouse_id.lot_stock_id, 1, lot_id=serial01
        )
        sale_picking = sale.picking_ids
        sale_picking.picking_type_id.sudo().intercompany_create_lots_mode = "same"
        sale_picking.sudo().action_confirm()
        sale_picking.sudo().action_assign()
        sale_picking.move_ids.quantity_done = 1.0
        sale_picking.sudo().button_validate()
        purchase_receipt = self.purchase_company_a.picking_ids.filtered(
            lambda p: p.intercompany_picking_id == sale_picking
        )
        self.assertEqual(purchase_receipt.state, "done")
        co_a_return = self._create_a_return(purchase_receipt, {self.product: 1.0})
        co_b_return = (
            self.env["stock.picking"]
            .sudo()
            .search([("intercompany_picking_id", "=", co_a_return.id)])
        )
        self.assertEqual(len(co_b_return), 1)
        co_a_lot = co_a_return.move_line_ids.lot_id
        self.assertEqual(len(co_a_lot), 1)
        self.assertEqual(co_a_lot.name, "Serial01")
        self.assertEqual(co_a_lot.company_id, self.company_a)
        co_a_return.move_ids.quantity_done = 1.0
        co_a_return.sudo().button_validate()
        self.assertEqual(co_b_return.state, "done")
        co_b_lot = co_b_return.move_line_ids.lot_id
        self.assertEqual(co_b_lot, serial01)

    def test_forward_link_scoped_to_touched_receipt(self):
        self.purchase_company_a.order_line.product_qty = 3.0
        sale = self._approve_po()
        sale.action_confirm()
        sale_picking = sale.picking_ids[0]
        sale_picking.sudo().action_confirm()
        sale_picking.move_ids.quantity_done = 1.0
        res_dict = sale_picking.sudo().button_validate()
        backorder_wizard = Form(
            self.env[res_dict["res_model"]].with_context(**res_dict["context"])
        ).save()
        backorder_wizard.process()
        sale_picking2 = sale.picking_ids.filtered(lambda p: p.state != "done")
        receipt_done = self.purchase_company_a.picking_ids.filtered(
            lambda p: p.state == "done"
        )
        receipt_open = self.purchase_company_a.picking_ids - receipt_done
        self.assertEqual(receipt_done.intercompany_picking_id, sale_picking)
        self.assertFalse(receipt_open.intercompany_picking_id)
        sale_picking2.move_ids.quantity_done = 2.0
        sale_picking2.sudo().action_confirm()
        sale_picking2.sudo().button_validate()
        self.assertEqual(receipt_open.intercompany_picking_id, sale_picking2)
        self.assertEqual(receipt_done.intercompany_picking_id, sale_picking)
