"""
Asigna proveedor / trabajador (Tercero) a los documentos y a las
líneas de asiento de cuentas 41 y 42 registradas antes de que
existiera el auxiliar de terceros.

Uso:

    python manage.py asignar_terceros --dry-run   # solo muestra
    python manage.py asignar_terceros             # aplica

Es seguro ejecutarlo varias veces: solo toca lo que aún no
tiene tercero.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from contabilidad.models import (
    AsientoContable,
    CompraDirectaVenta,
    DetalleAsiento,
    OperacionContable,
    PagoOperacionContable,
    PagoProveedor,
    ServicioTerceroVenta,
    Tercero,
)
from contabilidad.services import tipo_tercero_para_cuenta


CENTIMO = Decimal("0.01")


class _Simulacion(Exception):
    """Se lanza para deshacer todo en modo --dry-run."""


def _q(valor):
    return Decimal(valor).quantize(CENTIMO, rounding=ROUND_HALF_UP)


class Command(BaseCommand):

    help = (
        "Asigna proveedores y trabajadores a documentos y "
        "líneas de cuentas 41/42 que aún no los tienen."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que haría sin guardar cambios.",
        )

    def handle(self, *args, **opciones):

        dry_run = opciones["dry_run"]

        try:
            with transaction.atomic():
                self._ejecutar()

                if dry_run:
                    raise _Simulacion()

        except _Simulacion:
            self.stdout.write(
                self.style.WARNING(
                    "\nModo --dry-run: no se guardó ningún cambio."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS("\nCambios guardados."))

    # --------------------------------------------------------
    # PASOS
    # --------------------------------------------------------

    def _ejecutar(self):

        self.stdout.write("1. Documentos")
        self._asignar_documentos()

        self.stdout.write("\n2. Líneas de asiento (cuentas 41 y 42)")
        self._asignar_lineas()

    def _vincular(self, documento, cuenta):

        if documento.tercero_id:
            return documento.tercero

        tercero = Tercero.obtener_o_crear(
            documento.proveedor_nombre,
            tipo_tercero_para_cuenta(cuenta),
        )

        if tercero:
            documento.tercero = tercero
            documento.save(update_fields=["tercero"])

        return tercero

    def _asignar_documentos(self):

        grupos = [
            (
                "Compras directas",
                CompraDirectaVenta.objects.filter(
                    tercero__isnull=True,
                    cuenta_proveedor__isnull=False,
                ).select_related("cuenta_proveedor"),
                "cuenta_proveedor",
            ),
            (
                "Servicios de terceros al crédito",
                ServicioTerceroVenta.objects.filter(
                    tercero__isnull=True,
                    forma_pago=ServicioTerceroVenta.FormaPago.CREDITO,
                    cuenta_proveedor__isnull=False,
                ).select_related("cuenta_proveedor"),
                "cuenta_proveedor",
            ),
            (
                "Operaciones con cuenta por pagar",
                OperacionContable.objects.filter(
                    tercero__isnull=True,
                    cuenta_por_pagar__isnull=False,
                ).select_related("cuenta_por_pagar"),
                "cuenta_por_pagar",
            ),
        ]

        for etiqueta, queryset, campo_cuenta in grupos:

            asignados = 0
            sin_nombre = []

            for documento in queryset:

                tercero = self._vincular(
                    documento,
                    getattr(documento, campo_cuenta),
                )

                if tercero:
                    asignados += 1
                else:
                    sin_nombre.append(documento.id)

            self.stdout.write(f"   {etiqueta}: {asignados} asignados")

            if sin_nombre:
                self.stdout.write(
                    self.style.WARNING(
                        f"     Sin nombre de proveedor (ids): "
                        f"{', '.join(map(str, sin_nombre))}"
                    )
                )

    def _asignar_lineas(self):

        lineas = (
            DetalleAsiento.objects
            .filter(
                Q(cuenta__codigo__startswith="41")
                | Q(cuenta__codigo__startswith="42"),
                tercero__isnull=True,
            )
            .exclude(asiento__estado=AsientoContable.Estado.ANULADO)
            .select_related("asiento", "cuenta")
            .order_by("asiento__fecha", "asiento__numero", "secuencia")
        )

        asignadas = 0
        pendientes = []

        # Candidatos ya usados en asientos de costo de venta,
        # para no asignar dos líneas al mismo documento.
        usados = set()

        for linea in lineas:

            tercero = self._tercero_para_linea(linea, usados)

            if tercero:
                linea.tercero = tercero
                linea.save(update_fields=["tercero"])
                asignadas += 1
            else:
                pendientes.append(linea)

        self.stdout.write(f"   Líneas asignadas: {asignadas}")

        if pendientes:
            self.stdout.write(
                self.style.WARNING(
                    f"   Líneas sin poder asignar: {len(pendientes)} "
                    "(asígnelas en el admin del asiento)"
                )
            )

            for linea in pendientes:
                importe = linea.haber or linea.debe
                self.stdout.write(
                    f"     Asiento {linea.asiento.numero} "
                    f"({linea.asiento.periodo}) "
                    f"línea {linea.secuencia} · "
                    f"{linea.cuenta.codigo} · "
                    f"S/ {importe:.2f} · "
                    f"{linea.asiento.origen or 'sin origen'} · "
                    f"{linea.asiento.glosa[:60]}"
                )

    def _tercero_para_linea(self, linea, usados):

        asiento = linea.asiento
        origen = asiento.origen
        origen_id = asiento.origen_id

        if not origen_id:
            return None

        if origen == "OPERACION_CONTABLE":
            operacion = (
                OperacionContable.objects
                .filter(id=origen_id)
                .select_related("cuenta_por_pagar")
                .first()
            )
            if operacion:
                return self._vincular(
                    operacion, operacion.cuenta_por_pagar
                )

        if origen == "PAGO_OPERACION_CONTABLE":
            pago = (
                PagoOperacionContable.objects
                .filter(id=origen_id)
                .select_related("operacion__cuenta_por_pagar")
                .first()
            )
            if pago:
                return self._vincular(
                    pago.operacion,
                    pago.operacion.cuenta_por_pagar,
                )

        if origen == "PAGO_PROVEEDOR":
            pago = (
                PagoProveedor.objects
                .filter(id=origen_id)
                .select_related("compra__cuenta_proveedor")
                .first()
            )
            if pago:
                return self._vincular(
                    pago.compra,
                    pago.compra.cuenta_proveedor,
                )

        if origen == "COSTO_VENTA":
            return self._tercero_costo_venta(linea, usados)

        return None

    def _tercero_costo_venta(self, linea, usados):
        """
        En el asiento de costo de venta (origen_id = ticket) se
        busca la compra o el servicio al crédito de ese ticket
        con la misma cuenta por pagar y el mismo importe.
        """

        ticket_id = linea.asiento.origen_id
        importe = _q(linea.haber)

        candidatos = []

        compras = (
            CompraDirectaVenta.objects
            .filter(
                detalle_costo__propuesta__ticket_id=ticket_id,
                cuenta_proveedor=linea.cuenta,
            )
            .select_related("detalle_costo", "cuenta_proveedor")
        )

        for compra in compras:

            pagado = compra.monto_pagado or Decimal("0.00")

            # Importe según la compra y según la propuesta
            # (los asientos antiguos usaban el de la propuesta).
            importes = {
                _q(compra.costo_total) - pagado,
                _q(compra.detalle_costo.costo_total) - pagado,
            }

            candidatos.append((("compra", compra.id), compra, importes))

        servicios = ServicioTerceroVenta.objects.filter(
            propuesta__ticket_id=ticket_id,
            forma_pago=ServicioTerceroVenta.FormaPago.CREDITO,
            cuenta_proveedor=linea.cuenta,
        ).select_related("cuenta_proveedor")

        for servicio in servicios:
            candidatos.append(
                (("servicio", servicio.id), servicio, {_q(servicio.costo)})
            )

        libres = [c for c in candidatos if c[0] not in usados]

        elegido = next(
            (c for c in libres if importe in c[2]),
            None,
        )

        # Si no coincide el importe pero hay un único candidato
        # con esa cuenta en el ticket, es ese.
        if elegido is None and len(libres) == 1:
            elegido = libres[0]

        if elegido is None:
            return None

        clave, documento, _ = elegido
        usados.add(clave)

        return self._vincular(documento, documento.cuenta_proveedor)
