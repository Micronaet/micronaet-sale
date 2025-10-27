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


def clean_ascii(value):
    """ Remove not ascii char
    """
    res = ''
    for c in (value or ''):
        if ord(c) < 127:
            res += c
        else:
            res += '?'
    return res

def clean_ascii_name(object):
    """ Return name of linked object
    """
    name = object.name or ''
    if not name:
        return name
    return clean_ascii(name)

class SaleOrder(orm.Model):
    """ Model name: SaleOrder
    """
    _inherit = 'sale.order'

    def scheduled_sent_approve_order_list(self, cr, uid, context=None):
        """ Return list of order pending
        """
        user_pool = self.pool.get('res.users')
        user = user_pool.browse(cr, uid, uid, context=context)
        company_name = user.company_id.name

        order_ids = self.search(cr, uid, [
            ('request_approvation', '=', True),
            ('request_approvation_sent', '=', False),
        ], context=context)

        for order in self.browse(cr, uid, order_ids, context=context):
            order_id = order.id
            partner = order.partner_id
            destination = order.destination_partner_id

            partner_name = clean_ascii_name(partner)
            partner_payment = clean_ascii_name(partner.property_payment_term)
            partner_agent = clean_ascii_name(partner.agent_id)

            # ----------------------------------------------------------------------------------------------------------
            # Order of this partner:
            # ----------------------------------------------------------------------------------------------------------
            total_order_ids = self.search(cr, uid, [
                # ('id', '!=', order_id),  # Esclude this!
                ('partner_id', '=', partner_id),
                ('mx_closed', '=', False),
                ('state', 'not in', ('draft', 'sent', 'cancel')),
            ])
            order_number = len(total_order_ids)
            amount_total = sum([o.amount_total for o in self.browse(cr, uid, total_order_ids, context=context)])

            # ----------------------------------------------------------------------------------------------------------
            # FIDO:
            # ----------------------------------------------------------------------------------------------------------
            fido_total = partner.fido_total
            fido_uncovered = partner.uncovered_amount
            fido_date = partner.fido_date
            # uncovered_state (colors)
            # fido_ko (rimosso)

            # ----------------------------------------------------------------------------------------------------------
            # Partner:
            # ----------------------------------------------------------------------------------------------------------
            partner_reference = '{} ({}) - {}'.format(
                clean_ascii(partner.city),
                clean_ascii_name(partner.state_id),
                clean_ascii_name(partner.country_id),
            )

            if destination:
                destination_reference = '{} ({}) - {}'.format(
                    clean_ascii(destination.city),
                    clean_ascii_name(destination.state_id),
                    clean_ascii_name(destination.country_id),
                )
            else:
                destination_reference = ''
            amount = order.amount_total

            # ----------------------------------------------------------------------------------------------------------
            # Send Telegram Message:
            # ----------------------------------------------------------------------------------------------------------
            message = (
                '[{}] Richiesta approvazione ordine\n'
                'Cliente: {}\nPagamento: {}\nAgente: {}\n' 
                'Indirizzo: {}'
                '{}'
                'Ordini totali: # {} Tot. {}\n'
                'FIDO: Tot. {} Scop. {} ({})\n'
                'Importo: {}'.format(
                    company_name,
                    partner_name, partner_payment, partner_agent,
                    partner_reference,
                    '\nDestinazione: {}'.format(destination_reference) if destination_reference else '',
                    order_number, amount_total,
                    fido_total, fido_uncovered, fido_date,
                    amount,
                    ))

            if self.send_telegram_approvation_message(cr, uid, [order_id], message=message,  context=context):
                # Update order with chatter and remove new sent
                self.write(cr, uid, [order.id], {
                    'request_approvation_sent': True,
                    }, context=context)
                self.message_post(
                    cr, uid, [order.id],
                    body='Richiesta approvazione inviata via Telegram',
                    context=context)
        return True

    def send_telegram_approvation_message(
            self, cr, uid, ids, message, context=None):
        """ Sent telegram message
        """
        channel_pool = self.pool.get('telegram.bot.channel')

        # Send message for request confirmation:
        try:
            channel = channel_pool.get_channel_with_code(
                cr, uid, 'QUOTATION', context=context)

            order_id = ids[0]
            order = self.browse(cr, uid, order_id, context=context)
            if channel:
                channel_pool.send_message(
                    channel, message,
                    item_id=order_id, reference=order.name)
        except:
            _logger.error('Cannot send Telegram Message\{}'.format(sys.exc_info()))
            return False
        return True

    def action_button_request_approve_deny(self, cr, uid, ids, context=None):
        """ Deny approvation
        """
        # Send Message
        self.send_telegram_approvation_message(
            cr, uid, ids,
            message='Offerta non confermata!:',
            context=context)

        return self.write(cr, uid, ids, {
            'request_approvation': False,  # Restored flag (hide deny button)
        }, context=context)

    # Override confirm action to send message:
    def action_button_confirm(self, cr, uid, ids, context=None):
        """ Override to send message here:
        """

        # Regular inherited action:
        res = super(SaleOrder, self).action_button_confirm(cr, uid, ids, context=context)

        # Send Message (only if request approve)
        order = self.browse(cr, uid, ids, context=context)[0]
        if order.request_approvation:
            partner = clean_ascii(order.partner_id.name or '')
            amount = order.amount_total
            if self.send_telegram_approvation_message(
                    cr, uid, ids,
                    message='Ordine confermato (da inviare)\nCliente: {}\nImporto: {}'.format(partner, amount),
                    context=context):
                # Restore flag:
                self.write(cr, uid, ids, {
                    'request_approvation': False,  # Restored flag (hide deny button)
                    'request_approvation_sent': False,
                }, context=context)

        return res

    def action_button_request_approve(self, cr, uid, ids, context=None):
        """ Set order for request confirmation
        """
        # Check flag:
        return self.write(cr, uid, ids, {
            'request_approvation': True,
            'request_approvation_sent': False,
        }, context=context)

    _columns = {
        'request_approvation': fields.boolean('Richiesta approvazione'),
        'request_approvation_sent': fields.boolean('Richiesta approvazione inviata'),
        }
