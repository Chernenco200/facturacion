from django.utils import timezone
from django.db import transaction
from datetime import datetime
from decimal import Decimal

from .models import CajaDia, MovimientoCaja, PagoTicket

def get_or_create_caja(fecha=None):
    if fecha is None:
        fecha = timezone.localdate()
    caja, _ = CajaDia.objects.get_or_create(fecha=fecha)
    return caja

@transaction.atomic
def importar_cobros_a_caja(fecha=None):
    """
    Importa a Caja los cobros (pagos) realizados ese día, por medio de pago.
    Rebuild: elimina los movimientos fuente=TICKET para esa caja y los recrea.
    """
    if fecha is None:
        fecha = timezone.localdate()

    caja = get_or_create_caja(fecha)

    # rebuild: borra lo importado previamente
    MovimientoCaja.objects.filter(caja=caja, fuente="TICKET").delete()

    pagos = PagoTicket.objects.filter(fecha_hora__date=fecha).select_related("ticket", "ticket__cliente")

    for p in pagos:
        desc = f"Cobro ticket #{p.ticket.numero}"
        if p.ticket.cliente_id:
            try:
                desc += f" - {p.ticket.cliente.nombre}"
            except Exception:
                pass

        # ✅ AQUÍ va el paso 3.2
        categoria = "VENTA" if p.ticket.fecha_emision == fecha else "COBRANZA"

        MovimientoCaja.objects.create(
            caja=caja,
            fecha_hora=p.fecha_hora,
            tipo="IN",
            medio_pago=p.medio_pago,
            categoria=categoria,   # ✅ aquí
            descripcion=desc,
            monto=p.monto,
            ticket=p.ticket,
            fuente="TICKET",
        )


    return caja

@transaction.atomic
def importar_ventas_a_caja2(fecha=None):
    """
    Importa los tickets del día como ingresos por el monto efectivamente cobrado = a_cuenta.
    Rebuild seguro: elimina lo importado (fuente=TICKET) de ese día y lo recrea.
    """
    if fecha is None:
        fecha = timezone.localdate()

    caja = get_or_create_caja(fecha)

    # 1) Rebuild: borra importación anterior del día (evita duplicados y actualiza si editaron tickets)
    MovimientoCaja.objects.filter(caja=caja, fuente="TICKET").delete()

    # 2) Tickets del día (por fecha_emision)
    tickets = TicketVenta.objects.filter(fecha_emision=fecha).select_related("cliente")

    for t in tickets:
        monto = Decimal(str(t.a_cuenta or 0))
        if monto <= 0:
            continue

        # Fecha/hora real del ticket
        try:
            fh = datetime.combine(t.fecha_emision, t.hora_emision)
        except Exception:
            fh = timezone.now()

        desc = f"Venta ticket #{t.numero}"
        if t.cliente_id:
            # si tu Cliente tiene 'nombre' (según __str__), ok
            try:
                desc += f" - {t.cliente.nombre}"
            except Exception:
                pass

        MovimientoCaja.objects.create(
            caja=caja,
            fecha_hora=fh,
            tipo="IN",
            medio_pago="EFECTIVO",  # por ahora, porque no tienes medio en TicketVenta
            categoria = categoria,
            descripcion=desc,
            monto=monto,
            ticket=p.ticket,
            fuente="TICKET",
        )

    return caja


def caja_cobrar_saldo(request, fecha, ticket_id):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    caja = get_or_create_caja(fecha_dt)
    ticket = get_object_or_404(TicketVenta, pk=ticket_id)

    if request.method == "POST":
        if caja.cerrada:
            messages.error(request, "La caja está cerrada.")
            return redirect("caja_detalle", fecha=fecha)

        monto = Decimal(request.POST.get("monto") or "0")
        medio = request.POST.get("medio_pago") or "EFECTIVO"

        if monto <= 0:
            messages.error(request, "Monto inválido.")
            return redirect("caja_detalle", fecha=fecha)

        MovimientoCaja.objects.create(
            caja=caja,
            tipo="IN",
            medio_pago=medio,
            categoria=categoria,
            descripcion=f"Cobro saldo ticket #{ticket.numero}",
            monto=monto,
            ticket=ticket,
            fuente="MANUAL",
        )

        return redirect("caja_detalle", fecha=fecha)

    return redirect("caja_detalle", fecha=fecha)