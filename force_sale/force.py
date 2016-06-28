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

class SaleOrder(orm.Model):
    """ Model name: SaleOrderLine
    """    
    _inherit = 'sale.order'

    def get_message_list(self, cr, uid, ids, context=None):
        '''
        '''
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
            #'res_id': 1,
            'res_model': 'mail.message',
            #'view_id': view_id, # False
            'views': [(False, 'tree'), (False, 'form')],
            'domain': [('id', 'in', mail_ids)],
            'context': context,
            #'target': 'current', # 'new'
            'nodestroy': False,
            }

    def set_force_value(self, cr, uid, ids, context=None):
        '''
        '''
        assert len(ids) == 1, 'Force once order a time!'
        
        order_proxy = self.browse(cr, uid, ids, context=context)[0]
        force_value = order_proxy.force_value or 0.0 # default 100%

        # pool used:
        sol_pool = self.pool.get('sale.order.line')
        
        sol_ids = sol_pool.search(cr, uid, [
            ('order_id', '=', ids[0]),
            ], context=context)

        sol_update = {}
        for line in sol_pool.browse(cr, uid, sol_ids, context=context):
            sol_update[line.id] = round(
                line.product_uom_qty * force_value / 100.0, 0)
        
        # upate context to force CL (SL?)
        for item_id in sol_update:
            sol_pool.write(cr, uid, [item_id], {
                'product_uom_force_qty': sol_update[item_id], 
                }, context=context)
        self.write(cr, uid, ids, {
            'force_value': False}, context=context)        
        return True

    def update_setted_force(self, cr, uid, ids, context=None):
        '''
        '''
        assert len(ids) == 1, 'Force once order a time!'

        # pool used:
        sol_pool = self.pool.get('sale.order.line')
        
        sol_ids = sol_pool.search(cr, uid, [
            ('order_id', '=', ids[0]),
            ('product_uom_force_qty', '>', 0),
            ], context=context)

        ctx = context.copy()
        sol_update = {}
        for line in sol_pool.browse(cr, uid, sol_ids, context=context):
            # TODO check that is product or 
            ctx['force_persistent'] = True
            sol_pool._recreate_production_sol_move(cr, uid, [line.id], 
                context=ctx)

            # No extra sale forced down:
            sol_update[
                line.id] = line.product_uom_qty - line.product_uom_force_qty
            # No extra production forced down:
        
        # upate context to force CL (SL?)
        for item_id in sol_update:
            qty = sol_update[item_id]
            sol_pool.write(cr, uid, [item_id], {
                'product_uom_qty': qty,
                'product_uom_maked_sync_qty': qty,                
                'product_uom_force_qty': 0, 
                }, context=context)
        return True

    _columns = {
        'force_value': fields.float('Force value', digits=(8, 2),
            help='Set order force value es.: OC 10, value 60%, force 6'), 
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
