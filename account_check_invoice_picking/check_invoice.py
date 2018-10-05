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
import xlsxwriter
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

class AccountInvoice(orm.Model):
    """ Model name: AccountInvoice
    """
    
    _inherit = 'account.invoice'

    # -------------------------------------------------------------------------
    # Schedule operation: 
    # -------------------------------------------------------------------------
    def check_invoice_line_scheduled(self, cr, uid, context=None):
        ''' Search this year invoice and check them
        '''
        invoice_ids = self.search(cr, uid, [
            ('date_invoice', '>=', '2018-01-01'), # TODO
            ], order='number', context=context)
        return self.check_invoice_line(cr, uid, invoice_ids, context=context)

    # -------------------------------------------------------------------------
    # Utility: 
    # -------------------------------------------------------------------------
    def check_invoice_line(self, cr, uid, ids, context=None):
        ''' Check invoice line
        '''
        # ---------------------------------------------------------------------
        # Parameters:
        # ---------------------------------------------------------------------
        invoice_extra = [ # Code not used # TODO parametrize
            'LOCAZIONE',
            'SBANC',
            'VARIE',
            'PALLET',
            'SC.EXTRA',
            'BANNER',
            ]
        
        # ---------------------------------------------------------------------
        # Utility:
        # ---------------------------------------------------------------------
        def write_line(WS, page, counter, line):
            ''' Write line and 
            '''
            sheet = WS[page]
            row = counter[page]
            counter[page] += 1
            col = 0
            for item in line:                
                sheet.write(row, col, item)
                col += 1
            return     
        
        # ---------------------------------------------------------------------
        # Generate log file:
        # ---------------------------------------------------------------------
        user_proxy = self.pool.get('res.users').browse(
            cr, uid, uid, context=context)
        company_name = user_proxy.company_id.partner_id.name
        filename = '/home/administrator/photo/xls/invoice/check_%s.xlsx' % (
            company_name,
            )
        _logger.info('Check invoice: %s' % filename)
        
        # Open file and write header
        WB = xlsxwriter.Workbook(filename)
        
        # Create WS:
        WS = {
            'linked': WB.add_worksheet('OK Collegate'),
            'changed': WB.add_worksheet('Collegate ma cambiate'),
            'invoiced': WB.add_worksheet('Solo fattura (aggiunte)'),
            'invoiced_extra': WB.add_worksheet('Solo fattura (normale)'),
            'move_empty': WB.add_worksheet('Movimento eliminato dopo'),
            'unlinked': WB.add_worksheet('Movimenti non fatturati'),
            }

        counter = {
            'linked': 0,
            'changed': 0,
            'invoiced': 0,
            'invoiced_extra': 0,
            'move_empty': 0,
            'unlinked': 0,
            }

        # Write header:
        line = [
            'Fattura', 'Prelievo', 
            'Prod. Fatt.', 'Prod. prel.', 
            'Q. Fatt.', 'Q. prel.',
            'State', 
            ]                
        write_line(WS, 'linked', counter, line)
        write_line(WS, 'changed', counter, line)
        write_line(WS, 'invoiced', counter, line)
        write_line(WS, 'invoiced_extra', counter, line)
        write_line(WS, 'move_empty', counter, line)
        write_line(WS, 'unlinked', counter, line)

        # ---------------------------------------------------------------------
        # Picking invoiced:
        # ---------------------------------------------------------------------
        _logger.info('Invoice: %s' % len(ids))    
        picking_pool = self.pool.get('stock.picking')
        picking_ids = picking_pool.search(cr, uid, [
            ('invoice_id', 'in', ids)], context=context)
        _logger.info('Picking: %s' % len(picking_ids))    
            
        # ---------------------------------------------------------------------
        # Read all stock move (for save data)
        # ---------------------------------------------------------------------
        move_pool = self.pool.get('stock.move')
        move_ids = move_pool.search(cr, uid, [
            ('picking_id', 'in', picking_ids)], context=context)
        move_db = {}    
        _logger.info('Move: %s' % len(move_ids))    
        for move in move_pool.browse(cr, uid, move_ids, context=context):
            move_db[move.id] = move
            
        # ---------------------------------------------------------------------
        # Read all invoice line and check move line:
        # ---------------------------------------------------------------------
        for invoice in self.browse(
                cr, uid, ids, context=context):
            for line in invoice.invoice_line:
                # Readability:
                move = line.generator_move_id
                generator_move_id = move.id
                
                if not generator_move_id:
                    # 1. no picking line (only invoice)
                    default_code = line.product_id.default_code or ''
                    if default_code in invoice_extra: # normal
                        write_line(WS, 'invoiced_extra', counter, [
                            invoice.number,
                            move.picking_id.name,
                            default_code,
                            '', #move.product_id.default_code,
                            '', #line.product_qty,
                            '', #move.product_uom_qty,
                            'No picking!',
                            ])
                    else: # error:
                        write_line(WS, 'invoiced', counter, [
                            invoice.number,
                            move.picking_id.name,
                            default_code,
                            '', #move.product_id.default_code,
                            '', #line.product_qty,
                            '', #move.product_uom_qty,
                            'No picking!',
                            ])
                    
                elif generator_move_id in move_db:
                    # 2. linked (OK line-move linked)
                    
                    # TODO test Q. and product
                    invoice_code = line.product_id.default_code 
                    move_code = move.product_id.default_code
                    invoice_qty = line.quantity
                    move_qty = move.product_uom_qty
                    state = ''
                    if move_code != invoice_code:
                        state += 'Errore codice'                        
                    if move_qty != invoice_qty:
                        state += 'Errore quant.'
                    if state: # With error
                        write_line(WS, 'changed', counter, [
                            invoice.number,
                            move.picking_id.name,
                            invoice_code,
                            move_code,
                            invoice_qty,
                            move_qty,
                            state,
                            ])
                    else:    
                        write_line(WS, 'linked', counter, [
                            invoice.number,
                            move.picking_id.name,
                            invoice_code,
                            move_code,
                            invoice_qty,
                            move_qty,
                            state,
                            ])                      
                    
                    # Clean move database:
                    del move_db[generator_move_id]                    
                    
                else:
                    # 3. not linked but movement was present
                    write_line(WS, 'move_empty', counter, [
                        invoice.number,
                        '', #move.picking_id.name,
                        line.product_id.default_code,
                        '', #move.product_id.default_code,
                        line.quantity,
                        '', # move.product_uom_qty,
                        'Move not existent!',
                        ])

        for move in move_db.values():
            write_line(WS, 'unlinked', counter, [
                '',#invoice.number,
                move.picking_id.name,
                '',#line.product_id.default_code,
                move.product_id.default_code,
                '',#line.quantity,
                move.product_uom_qty,
                'Move not invoiced!',
                ])

        WB.close()
        return True
            
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
