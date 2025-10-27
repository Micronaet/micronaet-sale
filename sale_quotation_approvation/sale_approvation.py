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
    unused = ('*', '/')
    res = ''
    for c in (value or ''):
        if c in unused:
            # Jump unwanted char
            continue
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

    # ------------------------------------------------------------------------------------------------------------------
    # Wizard emulation:
    # ------------------------------------------------------------------------------------------------------------------
    def action_button_send_message_telegram_note(self, cr, uid, ids, context=None):
        """ Send message action
        """
        telegram_message = self.browse(cr, uid, ids, context=context)[0].telegram_message

        # Chatter message:
        self.message_post(cr, uid, ids, body=telegram_message, context=context)

        # Telegram Message:
        telegram_message = clean_ascii(telegram_message)
        self.send_telegram_approvation_message(cr, uid, ids, message=telegram_message,  context=context)

        return True

    def action_button_add_telegram_note(self, cr, uid, ids, context=None):
        """ Open pop up to send Telegram Message
        """
        assert len(ids) == 1, 'Solo un ordine per volta!'
        order_id = ids[0]

        # Clean previous Text Message:
        self.write(cr, uid, ids, {
            'telegram_message': False,
        }, context=context)

        # Open pop up window for Text message
        model_pool = self.pool.get('ir.model.data')
        view_id = model_pool.get_object_reference(
            cr, uid, 'sale_quotation_approvation', 'view_sale_order_telegram_message_form_view')[1]

        return {
            'type': 'ir.actions.act_window',
            'name': _('Messaggio Telegram'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': order_id,
            'res_model': 'sale.order',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'domain': [],
            'context': context,
            'target': 'new',
            'nodestroy': False,
            }
    # ------------------------------------------------------------------------------------------------------------------

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

            partner_id = partner.id
            partner_name = clean_ascii_name(partner)
            order_payment = clean_ascii_name(order.payment_term)
            partner_agent = clean_ascii_name(partner.agent_id)

            # ----------------------------------------------------------------------------------------------------------
            # Order of this partner:
            # ----------------------------------------------------------------------------------------------------------
            # Note: Current sale.order is not approved yet!
            total_order_ids = self.search(cr, uid, [
                ('partner_id', '=', partner_id),
                ('mx_closed', '=', False),
                ('state', 'not in', ('draft', 'sent', 'cancel')),
            ])
            order_number = len(total_order_ids)
            amount_total = sum([o.amount_total for o in self.browse(cr, uid, total_order_ids, context=context)])

            # ----------------------------------------------------------------------------------------------------------
            # FIDO:
            # ----------------------------------------------------------------------------------------------------------
            fido_total = partner.fido_total or 0
            fido_uncovered = partner.uncovered_amount or 0
            fido_date = partner.fido_date or '/'
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
                destination_reference = '{} - {} ({}) - {}'.format(
                    clean_ascii(destination.name),
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
                '{}\n'
                'Ordini totali: # {} Tot. {}\n'
                'FIDO: Tot. {} Dispon. {} ({})\n'
                'Importo: {}'.format(
                    company_name,
                    partner_name, order_payment, partner_agent,
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

    def send_telegram_approvation_message(self, cr, uid, ids, message, context=None):
        """ Sent telegram message
        """
        channel_pool = self.pool.get('telegram.bot.channel')

        # Send message for request confirmation:
        try:
            channel = channel_pool.get_channel_with_code(cr, uid, 'QUOTATION', context=context)

            order_id = ids[0]
            order = self.browse(cr, uid, order_id, context=context)
            if channel:
                channel_pool.send_message(channel, message, item_id=order_id, reference=order.name)
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

    def set_request_approvation_true(self, cr, uid, ids, context=None):
        """ Saw confirmed order
        """
        message = 'Conferma visione amministratore (ordine approvato da un operatore)'
        self.message_post(cr, uid, ids, body=message, context=context)

        return self.write(cr, uid, ids, {
            'request_approvation': False,  # Restored flag (hide deny button)
            'request_approvation_sent': False,
        }, context=context)

    # Override confirm action to send message:
    def action_button_confirm(self, cr, uid, ids, context=None):
        """ Override to send message here:
        """
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        try:
            manager_user = user.has_group('sale_quotation_approvation.group_sale_order_approvation_manager')
            _logger.warning('User is a manager, order is confirmed and saw!')
        except:
            manager_user = True  # todo remove this management try / except

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
                data = {
                    'request_approvation_sent': False,
                }
                if manager_user:  # Also Saw flag:
                    data.update({
                        'request_approvation': False,  # Restored flag (hide deny button)
                    })

                self.write(cr, uid, ids, data, context=context)
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
        'extra_discount_detail': fields.text(
            'Dettagli extra sconti',
            help='Indicare qui il motivo di applicazionie di particolari sconti extra nella offerta / ordine'),
        'telegram_message': fields.text(
            'Telegram Message',
            help='Messaggio temporaneo per inserire un messaggio di Telegram e una nota all\'interno dell\'ordine'),
        'request_approvation': fields.boolean('Richiesta approvazione'),
        'request_approvation_sent': fields.boolean('Richiesta approvazione inviata'),
        }
