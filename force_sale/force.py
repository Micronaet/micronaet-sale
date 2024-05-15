# -*- coding: utf-8 -*-
###############################################################################
#
#    Copyright (C) 2001-2014 Micronaet SRL (<http://www.micronaet.it>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import os
import sys
import logging
import openerp
import openerp.netsvc as netsvc
import openerp.addons.decimal_precision as dp
from openerp.osv import fields, osv, expression, orm
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from openerp import SUPERUSER_ID, api
from openerp import tools
from openerp.tools.translate import _
from openerp.tools.float_utils import float_round as round
from openerp.tools import (DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_DATETIME_FORMAT,
    DATETIME_FORMATS_MAP,
    float_compare)


_logger = logging.getLogger(__name__)


class StockPicking(orm.Model):
    """ Model name: StockPicking
    """

    _inherit = 'stock.picking'

    _columns = {
        'force_pick_ref': fields.char('Pick ref', size=10),
        }


class SaleOrderLineError(orm.Model):
    """ Model name: SaleOrderLineError
        History error calculating discount
    """
    _name = 'sale.order.line.error'
    _description = 'Line error unload'

    def get_force_pick(self, cr, uid, force_pick_ref, context=None):
        """
        """
        pick_pool = self.pool.get('stock.picking')
        pick_ids = pick_pool.search(cr, uid, [
            ('force_pick_ref', '=', force_pick_ref),
            ], context=context)
        if pick_ids:
            return pick_ids[0]

        # todo create picking header document with move type:
        return pick_pool.create(cr, uid, {
            'force_pick_ref': force_pick_ref,
            }, context=context)

    def link_sl_document(self, cr, uid, context=None):
        """ Link SL document
        """
        error_ids = self.search(cr, uid, [
            ('sl_id', '=', False),
            ], context=context)
        pick_ids = {}

        for line in self.browse(cr, uid, error_ids, context=context):
            date = line.date
            force_pick_ref = '%s%s' % (date[5:7], date[:4])
            if force_pick_ref not in pick_ids:
                pick_ids[force_pick_ref] = self.get_force_pick(
                    cr, uid, force_pick_ref, context=context)
            pick_id = pick_ids[force_pick_ref]
            # todo Create move for that picking:
            # todo Create quants for that picking:
        return True

    _columns = {
        'error_qty': fields.float('Error value', digits=(8, 2)),
        'product_id': fields.many2one('product.product', 'Product'),
        'date': fields.date('Date'),
        'note': fields.text('Note'),
        'sl_id': fields.many2one(
            'stock.picking', 'SL link'),
        }


class SaleOrder(orm.Model):
    """ Model name: SaleOrderLine
    """
    _inherit = 'sale.order'

    def readability_sale_force(self, cr, uid, ids, context=None):
        """ Reload OC9 data
        """
        self.write(cr, uid, ids, {
            'mx_closed': False,
            }, context=context)
        sol_pool = self.pool.get('sale.order.line')
        sol_ids = sol_pool.search(cr, uid, [
            ('order_id', '=', ids[0])], context=context)
        sol_pool.write(cr, uid, sol_ids, {
            'mx_closed': False,
            }, context=context)
        return self.force_parameter_for_delivery_one(
            cr, uid, ids, context=context)

    def get_message_list(self, cr, uid, ids, context=None):
        """
        """
        assert len(ids) == 1, 'Force once order a time!'

        mail_pool = self.pool.get('mail.message')
        mail_ids = mail_pool.search(cr, uid, [
            ('res_id', '=', ids[0]),
            ('model', '=', 'sale.order'),
            ], context=context)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Message for order'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            # 'res_id': 1,
            'res_model': 'mail.message',
            # 'view_id': view_id, # False
            'views': [(False, 'tree'), (False, 'form')],
            'domain': [('id', 'in', mail_ids)],
            'context': context,
            # 'target': 'current', # 'new'
            'nodestroy': False,
            }

    def set_force_value(self, cr, uid, ids, context=None):
        """
        """
        assert len(ids) == 1, 'Force once order a time!'

        order_proxy = self.browse(cr, uid, ids, context=context)[0]
        force_value = order_proxy.force_value or 0.0  # default 100%

        # pool used:
        sol_pool = self.pool.get('sale.order.line')

        # Search line used:
        sol_ids = sol_pool.search(cr, uid, [
            ('order_id', '=', ids[0]),
            ], context=context)

        # Update line quantity:
        sol_update = {}

        for line in sol_pool.browse(cr, uid, sol_ids, context=context):
            sol_update[line.id] = round(
                line.product_uom_qty * force_value / 100.0, 0)

        for item_id in sol_update:  # update context to force CL (SL?)
            sol_pool.write(cr, uid, [item_id], {
                'product_uom_force_qty': sol_update[item_id],
                }, context=context)
        self.write(cr, uid, ids, {
            'force_value': False,
        }, context=context)
        return True

    def update_setted_force(self, cr, uid, ids, context=None):
        """
        """
        assert len(ids) == 1, 'Force once order a time!'

        # pool used:
        sol_pool = self.pool.get('sale.order.line')
        error_pool = self.pool.get('sale.order.line.error')

        # Check list:
        sol_all = []
        sol_partial = []

        sol_ids = sol_pool.search(cr, uid, [
            ('order_id', '=', ids[0]),
            # ('product_uom_force_qty', '>', 0), # not filter for check list!
            ], context=context)

        ctx = context.copy()
        sol_update = {}
        for line in sol_pool.browse(cr, uid, sol_ids, context=context):
            force_qty = line.product_uom_force_qty
            order_qty = line.product_uom_qty
            qty = order_qty - force_qty  # total discount qty

            # Write error line (use in TX):
            error_pool.create(cr, uid, {
                'product_id': line.product_id.id,
                'date': datetime.now().strftime(DEFAULT_SERVER_DATE_FORMAT),
                'error_qty': force_qty,  # error extra
                'note': False,
                }, context=context)

            if not force_qty:
                # Remain the same
                sol_partial.append(line.id)
                continue

            # Check force value for line analysis
            if qty:  # discount qty
                sol_partial.append(line.id)
            else:  # no discount = all forced
                sol_all.append(line.id)

            # todo check that is product or
            # ctx['force_persistent'] = True
            # sol_pool._recreate_production_sol_move(cr, uid, [line.id],
            #    context=ctx)

            # No extra sale forced down:
            sol_update[line.id] = qty
            # No extra production forced down:

        # update context to force CL (SL?)
        for item_id in sol_update:
            qty = sol_update[item_id]
            sol_pool.write(cr, uid, [item_id], {
                'product_uom_qty': qty,
                'product_uom_maked_sync_qty': qty,
                'product_uom_force_qty': 0,
                }, context=context)

        # Clean line:
        if sol_all:
            sol_pool.unlink(cr, uid, sol_all, context=context)

        # Clean order:
        if sol_partial:
            self.readability_sale_force(cr, uid, ids, context=context)
        else:
            # Put in cancel state for unlink operation:
            self.write(cr, uid, ids, {
                'state': 'cancel'}, context=context)
            self.unlink(cr, uid, ids, context=context)
        return True

    _columns = {
        'force_value': fields.float(
            'Force discount', digits=(8, 2),
            help='Set order force value es.: OC 10, value 10%, force OC to 9'),
        }
