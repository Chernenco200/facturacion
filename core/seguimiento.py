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
                12 meses o más, pero menos de 18 meses.
  Reactivación: cliente cuya ÚLTIMA COMPRA tiene 18 meses o más.

  Ambas campañas comparten un plazo común: si el cliente recibió una
  renovación o una reactivación en los últimos 12 meses, no aparece en
  ninguna de las dos.

  Las encuestas y los controles de menores NO se controlan aquí.
"""

from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import DecimalField, Max, OuterRef, Q, Subquery, Sum
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
    Clientes con teléfono que NO recibieron renovación ni reactivación
    en los últimos 12 meses, anotados con:

      ultima_compra:      fecha del ticket más reciente
      ultima_renovacion:  fecha de renovación más reciente (cualquier orden)
    """

    f = fechas_referencia(hoy)

    ultima_renovacion = (
        OrdenTrabajo.objects
        .filter(
            ticket__cliente_id=OuterRef("pk"),
            fecha_ultima_renovacion__isnull=False,
        )
        .order_by("-fecha_ultima_renovacion")
        .values("fecha_ultima_renovacion")[:1]
    )

    return (
        Cliente.objects
        .filter(telefono__isnull=False)
        .exclude(telefono="")
        .annotate(
            ultima_compra=Max("ticketventa__fecha_emision"),
            ultima_renovacion=Subquery(ultima_renovacion),
        )
        .filter(ultima_compra__isnull=False)
        .filter(
            Q(ultima_renovacion__isnull=True)
            | Q(ultima_renovacion__lte=f["limite_campanas"])
        )
        .filter(
            Q(fecha_ultima_reactivacion__isnull=True)
            | Q(fecha_ultima_reactivacion__lte=f["limite_campanas"])
        )
    )


# ==============================================================
# RENOVACIÓN
# ==============================================================

def ordenes_renovacion(hoy=None):
    """
    Una orden por cliente: la orden ENTREGADA más reciente de cada
    cliente adulto cuya última compra tiene entre 12 y menos de 18 meses.
    """

    f = fechas_referencia(hoy)

    orden_mas_reciente = (
        OrdenTrabajo.objects
        .filter(
            ticket__cliente_id=OuterRef("pk"),
            estado="ENTREGADO",
        )
        .order_by("-ticket__fecha_emision", "-ts_entregado", "-id")
        .values("id")[:1]
    )

    ids_ordenes = (
        _clientes_comerciales(hoy)
        .filter(Q(Edad__gte=18) | Q(Edad__isnull=True))
        .filter(
            ultima_compra__lte=f["inicio_renovacion"],
            ultima_compra__gt=f["inicio_reactivacion"],
        )
        .annotate(orden_renovacion_id=Subquery(orden_mas_reciente))
        .filter(orden_renovacion_id__isnull=False)
        .values("orden_renovacion_id")
    )

    return (
        OrdenTrabajo.objects
        .select_related("ticket", "ticket__cliente")
        .filter(
            id__in=ids_ordenes,
            # Renovación ya enviada o eliminada manualmente de la lista
            renovacion_enviada=False,
        )
        .order_by("-ts_entregado")
    )


def orden_apta_renovacion(orden, hoy=None):
    return ordenes_renovacion(hoy).filter(pk=orden.pk).exists()


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
