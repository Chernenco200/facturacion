"""
Reglas de seguimiento comercial por WhatsApp (Óptica IC).

Este módulo concentra en un solo lugar las reglas de renovación y
reactivación. Las usan:

  - La pantalla seguimiento_whatsapp (para armar los listados).
  - enviar_renovacion_anual() y enviar_reactivacion() (para volver a
    verificar justo antes de enviar).

Así la pantalla y el envío nunca aplican reglas distintas.

REGLAS
------
  Renovación:   cliente adulto (o sin edad) cuya ÚLTIMA COMPRA tiene
                12 meses o más, pero menos de 18 meses. Se controla por
                cliente: no exige orden de trabajo, así que incluye a los
                clientes con compras históricas importadas.
  Reactivación: cliente cuya ÚLTIMA COMPRA tiene 18 meses o más.

  Ambas campañas comparten un plazo común: si el cliente recibió una
  renovación o una reactivación en los últimos 12 meses, no aparece en
  ninguna de las dos.

  Controles de menores: una sola fila por menor (ver
  controles_menores_qs).

  Las encuestas NO se controlan aquí.
"""

from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import DecimalField, Exists, F, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Cliente, OrdenTrabajo, TicketVenta


MESES_INICIO_RENOVACION = 12
MESES_INICIO_REACTIVACION = 18
MESES_ENTRE_CAMPANAS = 12


# ==============================================================
# FECHAS Y CATEGORÍAS
# ==============================================================

def fechas_referencia(hoy=None):
    hoy = hoy or timezone.localdate()

    return {
        "hoy": hoy,
        # Última compra en esta fecha o antes => ya cumplió 12 meses
        "inicio_renovacion": hoy - relativedelta(months=MESES_INICIO_RENOVACION),
        # Última compra en esta fecha o antes => ya cumplió 18 meses
        "inicio_reactivacion": hoy - relativedelta(months=MESES_INICIO_REACTIVACION),
        # Último mensaje comercial en esta fecha o antes => ya puede recibir otro
        "limite_campanas": hoy - relativedelta(months=MESES_ENTRE_CAMPANAS),
    }


def categoria_por_monto(monto):
    """Categoría comercial según la mayor compra acumulada en un día."""

    monto = monto or Decimal("0.00")

    if monto >= Decimal("800"):
        return "BLUE"
    if monto >= Decimal("300"):
        return "BLACK"
    if monto >= Decimal("150"):
        return "RED"
    if monto >= Decimal("100"):
        return "WHITE"
    return "BROWN"


def maxima_compra_dia_cliente(cliente):
    fila = (
        TicketVenta.objects
        .filter(cliente=cliente)
        .values("fecha_emision")
        .annotate(total_dia=Sum("total"))
        .order_by("-total_dia")
        .first()
    )

    if not fila:
        return Decimal("0.00")

    return fila.get("total_dia") or Decimal("0.00")


# ==============================================================
# CONSULTAS BASE
# ==============================================================

def _clientes_comerciales(hoy=None):
    """
    Clientes con teléfono y al menos una compra, que NO recibieron
    renovación ni reactivación en los últimos 12 meses.
    Anota ultima_compra (fecha del ticket más reciente).
    """

    f = fechas_referencia(hoy)

    return (
        Cliente.objects
        .filter(telefono__isnull=False)
        .exclude(telefono="")
        .annotate(ultima_compra=Max("ticketventa__fecha_emision"))
        .filter(ultima_compra__isnull=False)
        .filter(
            Q(fecha_ultima_renovacion__isnull=True)
            | Q(fecha_ultima_renovacion__lte=f["limite_campanas"])
        )
        .filter(
            Q(fecha_ultima_reactivacion__isnull=True)
            | Q(fecha_ultima_reactivacion__lte=f["limite_campanas"])
        )
    )


# ==============================================================
# RENOVACIÓN
# ==============================================================

def clientes_renovacion_qs(hoy=None):
    """
    Clientes adultos (o sin edad) cuya última compra tiene entre 12 y
    menos de 18 meses. Primero los que están más cerca de cumplir
    18 meses (luego pasarían a reactivación).
    """

    f = fechas_referencia(hoy)

    ultimo_ticket = (
        TicketVenta.objects
        .filter(cliente_id=OuterRef("pk"))
        .order_by("-fecha_emision", "-id")
        .values("numero")[:1]
    )

    return (
        _clientes_comerciales(hoy)
        .filter(Q(Edad__gte=18) | Q(Edad__isnull=True))
        .filter(
            ultima_compra__lte=f["inicio_renovacion"],
            ultima_compra__gt=f["inicio_reactivacion"],
        )
        # Retirado manualmente de la lista: vuelve solo si compra después
        .filter(
            Q(renovacion_descartada__isnull=True)
            | Q(renovacion_descartada__lt=F("ultima_compra"))
        )
        .annotate(ultimo_ticket=Subquery(ultimo_ticket))
        .order_by("ultima_compra", "nombre")
    )


def cliente_apto_renovacion(cliente, hoy=None):
    return clientes_renovacion_qs(hoy).filter(pk=cliente.pk).exists()


# ==============================================================
# REACTIVACIÓN
# ==============================================================

def clientes_reactivacion_qs(hoy=None):
    """Clientes cuya última compra tiene 18 meses o más."""

    f = fechas_referencia(hoy)

    compras_diarias = (
        TicketVenta.objects
        .filter(cliente_id=OuterRef("pk"))
        .values("cliente_id", "fecha_emision")
        .annotate(total_dia=Sum("total"))
        .order_by("-total_dia")
    )

    return (
        _clientes_comerciales(hoy)
        .filter(
            excluir_reactivacion=False,
            ultima_compra__lte=f["inicio_reactivacion"],
        )
        .annotate(
            maxima_compra_dia=Coalesce(
                Subquery(
                    compras_diarias.values("total_dia")[:1],
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Decimal("0.00"),
            ),
        )
        .order_by("-maxima_compra_dia", "ultima_compra")
    )


def clientes_reactivacion_lista(hoy=None):
    """Formato que espera seguimiento_whatsapp.html."""

    resultado = []

    for cliente in clientes_reactivacion_qs(hoy):
        monto = cliente.maxima_compra_dia or Decimal("0.00")

        resultado.append({
            "cliente": cliente,
            "ultima_compra": cliente.ultima_compra,
            "maxima_compra_dia": monto,
            "categoria": categoria_por_monto(monto),
        })

    return resultado


def cliente_apto_reactivacion(cliente, hoy=None):
    return clientes_reactivacion_qs(hoy).filter(pk=cliente.pk).exists()


# ==============================================================
# CONTROLES DE MENORES
# ==============================================================

def controles_menores_qs(hoy=None):
    """
    Órdenes entregadas a menores hace 6 a 9 meses, con una sola fila
    por cliente (su orden más reciente dentro de ese rango).

    No aparece el menor si cualquiera de sus órdenes recibió un control
    en los últimos 6 meses.
    """

    hoy = hoy or timezone.localdate()

    control_desde = hoy - relativedelta(months=9)
    control_hasta = hoy - relativedelta(months=6)

    candidatas = (
        OrdenTrabajo.objects
        .filter(
            estado="ENTREGADO",
            ts_entregado__date__gte=control_desde,
            ts_entregado__date__lte=control_hasta,
            ticket__cliente__Edad__lt=18,
            ticket__cliente__telefono__isnull=False,
            # No mostrar controles enviados o eliminados manualmente
            control_menor_enviado=False,
        )
        .filter(
            Q(fecha_ultimo_control_menor__isnull=True)
            | Q(fecha_ultimo_control_menor__lte=control_hasta)
        )
        .exclude(ticket__cliente__telefono="")
    )

    control_reciente = OrdenTrabajo.objects.filter(
        ticket__cliente_id=OuterRef("ticket__cliente_id"),
        fecha_ultimo_control_menor__gt=control_hasta,
    )

    mas_reciente = (
        candidatas
        .filter(ticket__cliente_id=OuterRef("ticket__cliente_id"))
        .order_by("-ts_entregado", "-id")
        .values("id")[:1]
    )

    return (
        candidatas
        .select_related("ticket", "ticket__cliente")
        .filter(id=Subquery(mas_reciente))
        .exclude(Exists(control_reciente))
        .order_by("-ts_entregado")
    )


def marcar_controles_menor_del_cliente(orden, hoy=None):
    """
    Al eliminar un control de la lista, se marcan también las demás
    órdenes del mismo menor dentro del rango, para que no reaparezca
    con otra orden.
    """

    hoy = hoy or timezone.localdate()
    control_hasta = hoy - relativedelta(months=6)

    cliente_id = orden.ticket.cliente_id

    if not cliente_id:
        orden.control_menor_enviado = True
        orden.save(update_fields=["control_menor_enviado"])
        return 1

    return (
        OrdenTrabajo.objects
        .filter(
            Q(pk=orden.pk)
            | Q(
                ticket__cliente_id=cliente_id,
                estado="ENTREGADO",
                ts_entregado__date__lte=control_hasta,
            )
        )
        .update(control_menor_enviado=True)
    )
