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
    """ Model name: SaleOrder
    """
    _inherit = 'sale.order'

    # Override confirm action to send message:
    def action_button_confirm(self, cr, uid, ids, context=None):
        """ Override to send message here:
        """
        # Regular inherited action:
        res = super(SaleOrder, self).action_button_confirm(
            cr, uid, ids, context=context)

        # Send message for request confirmation:
        try:
            telegram_pool = self.pool.get('telegram.bot')
            channel = telegram_pool.get_channel_with_code(
                cr, uid, 'QUOTATION', context=context)

            order_id = ids[0]
            order = self.browse(cr, uid, order_id, context=context)
            message = 'Ordine confermato:'
            if channel:
                telegram_pool.send_message(
                    channel, message,
                    item_id=order_id, reference=order.name)
        except:
            _logger.error('Cannot send Telegram Message\{}'.format(
                sys.exc_info()))
        return res

    def action_button_request_approve(self, cr, uid, ids, context=None):
        """ Set order for request confirmation
        """
        # Send message for request confirmation:
        try:
            channel_pool = self.pool.get('telegram.bot.channel')
            channel = channel_pool.get_channel_with_code(
                cr, uid, 'QUOTATION', context=context)

            order_id = ids[0]
            order = self.browse(cr, uid, order_id, context=context)
            message = 'Richiesta approvazione ordine:'
            if channel:
                channel_pool.send_message(
                    channel, message,
                    item_id=order_id, reference=order.name)
        except:
            _logger.error('Cannot send Telegram Message\{}'.format(
                sys.exc_info()))

        # Check approvation flag:
        return self.write(cr, uid, ids, {
            'request_approvation': True,
        }, context=context)

    _columns = {
        'request_approvation': fields.boolean('Richiesta approvazione'),
        }
