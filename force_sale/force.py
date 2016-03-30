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

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
