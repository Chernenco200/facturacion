from decimal import Decimal
from datetime import datetime, time

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Producto,
    KardexMovimiento,
    DetalleCompra,
    DetalleTicketVenta,
)


# ============================================================
# FECHAS DE LOS EVENTOS
# ============================================================

def _compra_dt(compra):
    """
    Compra.fecha es DateField.

    Se registra al inicio del día para conservar
    la lógica actual del Kardex.
    """

    if getattr(compra, "fecha", None):

        return datetime.combine(
            compra.fecha,
            time(0, 0),
        )

    return timezone.now()


def _ticket_dt(ticket):
    """
    TicketVenta:
    fecha_emision + hora_emision.
    """

    fecha = getattr(
        ticket,
        "fecha_emision",
        None,
    )

    hora = getattr(
        ticket,
        "hora_emision",
        None,
    )

    if fecha and hora:

        return datetime.combine(
            fecha,
            hora,
        )

    if fecha:

        return datetime.combine(
            fecha,
            time(12, 0),
        )

    return timezone.now()


def _nota_credito_dt(nota):
    """
    NotaCredito solo tiene fecha_emision.

    Se ubica al final del día para asegurar que,
    cuando la NC tenga la misma fecha que la venta,
    la salida original ocurra antes del reingreso.
    """

    fecha = getattr(
        nota,
        "fecha_emision",
        None,
    )

    if fecha:

        return datetime.combine(
            fecha,
            time(23, 59, 59),
        )

    return timezone.now()


# ============================================================
# RECALCULAR KARDEX DE UN PRODUCTO
# ============================================================

@transaction.atomic
def recalcular_kardex_producto(
    producto: Producto,
):

    # ========================================================
    # 1. BORRAR EL KARDEX CALCULADO ACTUAL
    # ========================================================

    KardexMovimiento.objects.filter(
        producto=producto
    ).delete()

    stock = Decimal("0")
    costo_prom = Decimal("0")

    eventos = []

    # ========================================================
    # 2. ENTRADAS POR COMPRAS
    # ========================================================

    compras = (
        DetalleCompra.objects
        .filter(
            producto=producto
        )
        .select_related(
            "compra"
        )
    )

    for detalle_compra in compras:

        cantidad = Decimal(
            str(
                detalle_compra.cantidad
                or 0
            )
        )

        costo_in = Decimal(
            str(
                detalle_compra.precio_compra
                or 0
            )
        )

        fecha_dt = _compra_dt(
            detalle_compra.compra
        )

        eventos.append({
            "tipo": "IN_COMPRA",
            "fecha": fecha_dt,
            "cantidad": cantidad,
            "costo_in": costo_in,
            "compra": detalle_compra.compra,
            "ticket": None,
            "detalle_ticket_id": None,
            "nota_credito": None,
        })

    # ========================================================
    # 3. SALIDAS POR VENTAS
    # ========================================================

    ventas = (
        DetalleTicketVenta.objects
        .filter(
            producto=producto
        )
        .select_related(
            "ticket_numero"
        )
    )

    cantidades_vendidas = {}

    for detalle_venta in ventas:

        cantidad = Decimal(
            str(
                detalle_venta.cantidad
                or 0
            )
        )

        fecha_dt = _ticket_dt(
            detalle_venta.ticket_numero
        )

        cantidades_vendidas[
            detalle_venta.id
        ] = cantidad

        eventos.append({
            "tipo": "OUT_VENTA",
            "fecha": fecha_dt,
            "cantidad": cantidad,
            "costo_in": None,
            "compra": None,
            "ticket": detalle_venta.ticket_numero,
            "detalle_ticket_id": detalle_venta.id,
            "nota_credito": None,
        })

    # ========================================================
    # 4. DEVOLUCIONES POR NOTAS DE CRÉDITO
    #
    # Se usa apps.get_model() para evitar dependencia circular
    # entre core y contabilidad.
    # ========================================================

    DetalleNotaCredito = apps.get_model(
        "contabilidad",
        "DetalleNotaCredito",
    )

    devoluciones = (
        DetalleNotaCredito.objects
        .filter(
            detalle_ticket__producto=producto,
            devuelve_stock=True,
            nota_credito__estado="CONTABILIZADA",
        )
        .select_related(
            "nota_credito",
            "detalle_ticket",
            "detalle_ticket__ticket_numero",
        )
    )

    for detalle_nc in devoluciones:

        cantidad = Decimal(
            str(
                detalle_nc.cantidad
                or 0
            )
        )

        fecha_dt = _nota_credito_dt(
            detalle_nc.nota_credito
        )

        eventos.append({
            "tipo": "IN_DEVOLUCION",
            "fecha": fecha_dt,
            "cantidad": cantidad,
            "costo_in": None,
            "compra": None,
            "ticket": detalle_nc.detalle_ticket.ticket_numero,
            "detalle_ticket_id": detalle_nc.detalle_ticket_id,
            "nota_credito": detalle_nc.nota_credito,
        })

    # ========================================================
    # 5. ORDEN CRONOLÓGICO
    # ========================================================

    eventos.sort(
        key=lambda evento: evento["fecha"]
    )

    # ========================================================
    # 6. COSTO ORIGINAL DE CADA SALIDA
    #
    # Guardaremos el costo que tenía cada línea de venta
    # en el momento exacto en que salió.
    # ========================================================

    costos_salida = {}

    cantidades_devueltas = {}

    # ========================================================
    # 7. PROCESAR EVENTOS
    # ========================================================

    for evento in eventos:

        tipo = evento["tipo"]

        fecha_dt = evento["fecha"]

        cantidad = evento["cantidad"]

        if cantidad <= Decimal("0"):

            continue

        # ====================================================
        # ENTRADA POR COMPRA
        # ====================================================

        if tipo == "IN_COMPRA":

            costo_in = evento["costo_in"]

            if costo_in < Decimal("0"):

                raise ValidationError(
                    (
                        f"El producto {producto} tiene "
                        "una compra con costo negativo."
                    )
                )

            nuevo_stock = (
                stock
                + cantidad
            )

            nuevo_costo_prom = (
                (
                    (
                        stock
                        * costo_prom
                    )
                    +
                    (
                        cantidad
                        * costo_in
                    )
                )
                / nuevo_stock
                if nuevo_stock > 0
                else Decimal("0")
            )

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="IN",
                cantidad=cantidad,
                costo_unitario=costo_in,
                costo_total=(
                    cantidad
                    * costo_in
                ),
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=nuevo_costo_prom,
                compra=evento["compra"],
            )

            stock = nuevo_stock

            costo_prom = nuevo_costo_prom

        # ====================================================
        # SALIDA POR VENTA
        # ====================================================

        elif tipo == "OUT_VENTA":

            detalle_ticket_id = (
                evento[
                    "detalle_ticket_id"
                ]
            )

            costo_salida = costo_prom

            # Guardamos el costo histórico real de esta salida.

            costos_salida[
                detalle_ticket_id
            ] = costo_salida

            nuevo_stock = (
                stock
                - cantidad
            )

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="OUT",
                cantidad=cantidad,
                costo_unitario=costo_salida,
                costo_total=(
                    cantidad
                    * costo_salida
                ),
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=costo_prom,
                ticket=evento["ticket"],
            )

            stock = nuevo_stock

        # ====================================================
        # ENTRADA POR DEVOLUCIÓN / NOTA DE CRÉDITO
        # ====================================================

        elif tipo == "IN_DEVOLUCION":

            detalle_ticket_id = (
                evento[
                    "detalle_ticket_id"
                ]
            )

            # ------------------------------------------------
            # VALIDAR QUE EXISTA LA VENTA ORIGINAL
            # ------------------------------------------------

            if (
                detalle_ticket_id
                not in costos_salida
            ):

                nota = evento[
                    "nota_credito"
                ]

                raise ValidationError(
                    (
                        f"No se encontró el costo original "
                        f"de salida para la devolución "
                        f"de la nota de crédito "
                        f"{nota.numero:06d}."
                    )
                )

            costo_original = (
                costos_salida[
                    detalle_ticket_id
                ]
            )

            # ------------------------------------------------
            # CONTROLAR DEVOLUCIONES ACUMULADAS
            #
            # Evita devolver mediante varias NC una cantidad
            # superior a la cantidad vendida.
            # ------------------------------------------------

            cantidad_vendida = (
                cantidades_vendidas.get(
                    detalle_ticket_id,
                    Decimal("0"),
                )
            )

            ya_devuelto = (
                cantidades_devueltas.get(
                    detalle_ticket_id,
                    Decimal("0"),
                )
            )

            total_devuelto = (
                ya_devuelto
                + cantidad
            )

            if (
                total_devuelto
                > cantidad_vendida
            ):

                nota = evento[
                    "nota_credito"
                ]

                raise ValidationError(
                    (
                        f"La nota de crédito "
                        f"{nota.numero:06d} produciría "
                        f"una devolución acumulada de "
                        f"{total_devuelto} unidades, "
                        f"pero solo se vendieron "
                        f"{cantidad_vendida}."
                    )
                )

            cantidades_devueltas[
                detalle_ticket_id
            ] = total_devuelto

            # ------------------------------------------------
            # REINGRESO AL INVENTARIO
            #
            # Se utiliza el costo ORIGINAL de la salida.
            # ------------------------------------------------

            nuevo_stock = (
                stock
                + cantidad
            )

            nuevo_costo_prom = (
                (
                    (
                        stock
                        * costo_prom
                    )
                    +
                    (
                        cantidad
                        * costo_original
                    )
                )
                / nuevo_stock
                if nuevo_stock > 0
                else Decimal("0")
            )

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="IN",
                cantidad=cantidad,
                costo_unitario=costo_original,
                costo_total=(
                    cantidad
                    * costo_original
                ),
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=nuevo_costo_prom,

                # No usamos compra porque es devolución.
                compra=None,

                # Conservamos el ticket original como referencia.
                ticket=evento["ticket"],
            )

            stock = nuevo_stock

            costo_prom = nuevo_costo_prom

    # ========================================================
    # 8. SINCRONIZAR STOCK DEL PRODUCTO
    # ========================================================

    producto.stock = int(
        stock
    )

    producto.save(
        update_fields=[
            "stock",
        ]
    )


# ============================================================
# RECALCULAR TODO EL KARDEX
# ============================================================

def recalcular_kardex_todo():

    for producto in Producto.objects.all():

        recalcular_kardex_producto(
            producto
        )