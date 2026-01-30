from decimal import Decimal
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum

from .models import PagoTicket, TicketVenta

def _recalcular_ticket(ticket: TicketVenta):
    total_pagado = ticket.pagos.aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
    ticket.a_cuenta = total_pagado
    ticket.saldo = (ticket.total or Decimal("0.00")) - total_pagado
    if ticket.saldo < 0:
        ticket.saldo = Decimal("0.00")
    ticket.save(update_fields=["a_cuenta", "saldo"])

@receiver(post_save, sender=PagoTicket)
def pago_ticket_save(sender, instance, **kwargs):
    _recalcular_ticket(instance.ticket)

@receiver(post_delete, sender=PagoTicket)
def pago_ticket_delete(sender, instance, **kwargs):
    _recalcular_ticket(instance.ticket)
