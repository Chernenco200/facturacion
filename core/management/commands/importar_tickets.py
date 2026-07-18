import csv
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import (
    Cliente,
    TicketVenta,
    DetalleTicketVenta,
)


class Command(BaseCommand):
    help = (
        "Audita e importa TicketVenta y DetalleTicketVenta "
        "desde una base SQLite antigua."
    )

    NUMERO_BASE_HISTORICO = 1000_000_000

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            type=str,
            required=True,
            help="Ruta del archivo SQLite antiguo.",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Audita y genera reportes sin modificar la base principal.",
        )

        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Ejecuta la importación real de tickets y detalles.",
        )

    # ==========================================================
    # LIMPIEZA Y CONVERSIÓN
    # ==========================================================

    def limpiar_texto(self, valor):
        if valor is None:
            return ""

        return str(valor).strip()

    def normalizar_dni(self, valor):
        dni = self.limpiar_texto(valor)
        return re.sub(r"[^0-9A-Za-z]", "", dni).upper()

    def dni_es_valido(self, dni):
        if not dni:
            return False

        valores_invalidos = {
            "0",
            "00",
            "000",
            "0000",
            "00000",
            "000000",
            "0000000",
            "00000000",
            "11111111",
            "99999999",
            "SINDNI",
            "NODNI",
            "CL1",
            "SN",
        }

        return (
            dni not in valores_invalidos
            and dni.isdigit()
            and len(dni) == 8
        )

    def convertir_decimal(self, valor):
        try:
            numero = Decimal(str(valor or 0))
            return numero.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")

    def convertir_cantidad(self, valor):
        try:
            cantidad = int(
                Decimal(str(valor or 0))
            )

            if cantidad <= 0:
                return None

            return cantidad

        except (
            InvalidOperation,
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

    def convertir_fecha_hora(self, valor):
        texto = self.limpiar_texto(valor)

        if not texto:
            return None

        fecha_hora = parse_datetime(texto)

        if fecha_hora:
            return fecha_hora

        fecha = parse_date(texto)

        if fecha:
            return datetime.combine(fecha, time.min)

        formatos = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y",
        ]

        for formato in formatos:
            try:
                return datetime.strptime(texto, formato)

            except ValueError:
                continue

        return None

    def obtener_fecha_emision(self, fecha_pedido, created):
        fecha_hora = (
            self.convertir_fecha_hora(fecha_pedido)
            or self.convertir_fecha_hora(created)
        )

        if fecha_hora:
            return fecha_hora.date()

        return timezone.localdate()

    def obtener_hora_emision(self, created, fecha_pedido):
        fecha_hora = (
            self.convertir_fecha_hora(created)
            or self.convertir_fecha_hora(fecha_pedido)
        )

        if fecha_hora:
            return fecha_hora.time().replace(
                microsecond=0
            )

        return time(0, 0)

    def extraer_vendedor(self, comentarios):
        texto = self.limpiar_texto(comentarios).upper()

        vendedores = {
            "HELLEN": "Hellen",
            "ROSMERY": "Rosmery",
            "GRECIA": "Grecia",
            "ANA": "Ana",
            "LUCITA": "Lucita",
            "JERRY": "Jerry",
        }

        for clave, nombre in vendedores.items():
            if clave in texto:
                return nombre

        return "Histórico"

    def construir_descripcion(self, producto):
        if not producto:
            return "Producto histórico"

        codigo = self.limpiar_texto(
            producto["codigo"]
        )

        descripcion = self.limpiar_texto(
            producto["descripcion"]
        )

        if descripcion:
            return descripcion

        if codigo:
            return f"Producto histórico {codigo}"

        return "Producto histórico"

    # ==========================================================
    # REPORTES
    # ==========================================================

    def guardar_csv(self, ruta, columnas, filas):
        with open(
            ruta,
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as archivo_csv:
            escritor = csv.DictWriter(
                archivo_csv,
                fieldnames=columnas,
            )

            escritor.writeheader()
            escritor.writerows(filas)

    # ==========================================================
    # COMANDO PRINCIPAL
    # ==========================================================

    def handle(self, *args, **options):
        ruta_archivo = Path(options["archivo"])
        dry_run = options["dry_run"]
        confirmar = options["confirmar"]

        # ------------------------------------------------------
        # Validaciones iniciales
        # ------------------------------------------------------

        if not ruta_archivo.exists():
            raise CommandError(
                f"No se encontró el archivo: "
                f"{ruta_archivo}"
            )

        if dry_run and confirmar:
            raise CommandError(
                "No uses --dry-run y --confirmar "
                "al mismo tiempo."
            )

        if not dry_run and not confirmar:
            raise CommandError(
                "Debes usar --dry-run para auditar "
                "o --confirmar para importar."
            )

        if confirmar and connection.vendor != "postgresql":
            raise CommandError(
                "IMPORTACIÓN CANCELADA: Django no está "
                "conectado a PostgreSQL.\n"
                f"Motor actual: "
                f"{connection.settings_dict['ENGINE']}\n"
                "Configura DATABASE_URL con las credenciales "
                "de Heroku antes de usar --confirmar."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Archivo encontrado: {ruta_archivo}"
            )
        )

        self.stdout.write(
            f"Base de destino: "
            f"{connection.settings_dict['ENGINE']}"
        )

        self.stdout.write(
            f"Host de destino: "
            f"{connection.settings_dict.get('HOST') or '(local)'}"
        )

        self.stdout.write(
            f"Tickets actuales en destino: "
            f"{TicketVenta.objects.count()}"
        )

        # ------------------------------------------------------
        # Leer SQLite
        # ------------------------------------------------------

        conexion_sqlite = sqlite3.connect(
            ruta_archivo
        )
        conexion_sqlite.row_factory = sqlite3.Row

        try:
            cursor = conexion_sqlite.cursor()

            clientes_origen = {
                fila["id"]: fila
                for fila in cursor.execute(
                    """
                    SELECT
                        id,
                        codigo,
                        nombre
                    FROM index_cliente
                    """
                ).fetchall()
            }

            productos_origen = {
                fila["id"]: fila
                for fila in cursor.execute(
                    """
                    SELECT
                        id,
                        codigo,
                        descripcion
                    FROM index_producto
                    """
                ).fetchall()
            }

            egresos = cursor.execute(
                """
                SELECT
                    id,
                    fecha_pedido,
                    comentarios,
                    created,
                    cliente_id,
                    pagado,
                    total
                FROM index_egreso
                ORDER BY id
                """
            ).fetchall()

            detalles = cursor.execute(
                """
                SELECT
                    id,
                    cantidad,
                    subtotal,
                    created,
                    egreso_id,
                    producto_id,
                    precio,
                    entregado,
                    devolucion,
                    iva,
                    total
                FROM index_productosegreso
                ORDER BY id
                """
            ).fetchall()

        except sqlite3.Error as error:
            raise CommandError(
                f"Error al leer SQLite: {error}"
            )

        finally:
            conexion_sqlite.close()

        self.stdout.write(
            f"Egresos encontrados en SQLite: "
            f"{len(egresos)}"
        )

        self.stdout.write(
            f"Detalles encontrados en SQLite: "
            f"{len(detalles)}"
        )

        # ------------------------------------------------------
        # Agrupar detalles por egreso
        # ------------------------------------------------------

        detalles_por_egreso = defaultdict(list)

        for detalle in detalles:
            detalles_por_egreso[
                detalle["egreso_id"]
            ].append(detalle)

        # ------------------------------------------------------
        # Preparar clientes de PostgreSQL por DNI
        # ------------------------------------------------------

        clientes_destino = {}

        for cliente in Cliente.objects.all().iterator():
            dni = self.normalizar_dni(
                cliente.DNI
            )

            if dni and dni not in clientes_destino:
                clientes_destino[dni] = cliente

        # ------------------------------------------------------
        # Auditar egresos
        # ------------------------------------------------------

        filas_auditoria = []
        tickets_importables = []

        total_importables = 0
        total_dni_invalido = 0
        total_sin_cliente_origen = 0
        total_cliente_no_encontrado = 0
        total_sin_detalles = 0
        total_sin_detalles_validos = 0
        total_ya_existentes = 0
        total_detalles_invalidos = 0

        for egreso in egresos:
            id_egreso = egreso["id"]

            numero_historico = (
                self.NUMERO_BASE_HISTORICO
                + id_egreso
            )

            cliente_origen = clientes_origen.get(
                egreso["cliente_id"]
            )

            dni = ""
            nombre_cliente_origen = ""
            cliente_destino = None
            estado = ""
            observacion = ""

            detalles_egreso = detalles_por_egreso.get(
                id_egreso,
                [],
            )

            detalles_validos = []

            for detalle in detalles_egreso:
                cantidad = self.convertir_cantidad(
                    detalle["cantidad"]
                )

                if cantidad is None:
                    total_detalles_invalidos += 1
                    continue

                detalles_validos.append(detalle)

            if not cliente_origen:
                estado = "SIN_CLIENTE_ORIGEN"
                observacion = (
                    "El cliente_id no existe en "
                    "index_cliente."
                )
                total_sin_cliente_origen += 1

            else:
                dni = self.normalizar_dni(
                    cliente_origen["codigo"]
                )

                nombre_cliente_origen = (
                    self.limpiar_texto(
                        cliente_origen["nombre"]
                    )
                )

                if not self.dni_es_valido(dni):
                    estado = "DNI_INVALIDO"
                    observacion = (
                        "El ticket no se importará."
                    )
                    total_dni_invalido += 1

                else:
                    cliente_destino = (
                        clientes_destino.get(dni)
                    )

                    if not cliente_destino:
                        estado = "CLIENTE_NO_ENCONTRADO"
                        observacion = (
                            "El DNI no existe en "
                            "core_cliente."
                        )
                        total_cliente_no_encontrado += 1

                    elif TicketVenta.objects.filter(
                        numero=numero_historico
                    ).exists():
                        estado = "TICKET_YA_EXISTE"
                        observacion = (
                            "El ticket histórico ya "
                            "fue importado."
                        )
                        total_ya_existentes += 1

                    elif not detalles_egreso:
                        estado = "SIN_DETALLES"
                        observacion = (
                            "El egreso no tiene "
                            "productos asociados."
                        )
                        total_sin_detalles += 1

                    elif not detalles_validos:
                        estado = "SIN_DETALLES_VALIDOS"
                        observacion = (
                            "Todos sus detalles tienen "
                            "cantidad inválida."
                        )
                        total_sin_detalles_validos += 1

                    else:
                        estado = "IMPORTABLE"
                        observacion = (
                            "Ticket listo para importar."
                        )
                        total_importables += 1

                        tickets_importables.append(
                            {
                                "egreso": egreso,
                                "cliente": cliente_destino,
                                "dni": dni,
                                "numero_historico": (
                                    numero_historico
                                ),
                                "detalles": detalles_validos,
                            }
                        )

            filas_auditoria.append(
                {
                    "egreso_id": id_egreso,
                    "numero_historico": numero_historico,
                    "cliente_id_origen": (
                        egreso["cliente_id"]
                    ),
                    "dni_cliente": dni,
                    "nombre_cliente_origen": (
                        nombre_cliente_origen
                    ),
                    "cliente_id_destino": (
                        cliente_destino.id
                        if cliente_destino
                        else ""
                    ),
                    "fecha_pedido": (
                        egreso["fecha_pedido"]
                    ),
                    "created": egreso["created"],
                    "comentarios": self.limpiar_texto(
                        egreso["comentarios"]
                    ),
                    "vendedor_detectado": (
                        self.extraer_vendedor(
                            egreso["comentarios"]
                        )
                    ),
                    "pagado_origen": (
                        self.convertir_decimal(
                            egreso["pagado"]
                        )
                    ),
                    "total_origen": (
                        self.convertir_decimal(
                            egreso["total"]
                        )
                    ),
                    "cantidad_detalles": (
                        len(detalles_egreso)
                    ),
                    "cantidad_detalles_validos": (
                        len(detalles_validos)
                    ),
                    "estado": estado,
                    "observacion": observacion,
                }
            )

        # ------------------------------------------------------
        # Crear reporte de auditoría
        # ------------------------------------------------------

        carpeta_reportes = (
            Path("importaciones") / "reportes"
        )

        carpeta_reportes.mkdir(
            parents=True,
            exist_ok=True,
        )

        ruta_auditoria = (
            carpeta_reportes
            / "auditoria_tickets.csv"
        )

        columnas_auditoria = [
            "egreso_id",
            "numero_historico",
            "cliente_id_origen",
            "dni_cliente",
            "nombre_cliente_origen",
            "cliente_id_destino",
            "fecha_pedido",
            "created",
            "comentarios",
            "vendedor_detectado",
            "pagado_origen",
            "total_origen",
            "cantidad_detalles",
            "cantidad_detalles_validos",
            "estado",
            "observacion",
        ]

        self.guardar_csv(
            ruta_auditoria,
            columnas_auditoria,
            filas_auditoria,
        )

        # ------------------------------------------------------
        # Resumen de auditoría
        # ------------------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "AUDITORÍA DE TICKETS FINALIZADA"
            )
        )

        self.stdout.write(
            f"Egresos encontrados: {len(egresos)}"
        )

        self.stdout.write(
            f"Detalles encontrados: {len(detalles)}"
        )

        self.stdout.write(
            f"Tickets importables: "
            f"{total_importables}"
        )

        self.stdout.write(
            f"Tickets con DNI inválido: "
            f"{total_dni_invalido}"
        )

        self.stdout.write(
            f"Tickets sin cliente de origen: "
            f"{total_sin_cliente_origen}"
        )

        self.stdout.write(
            f"Tickets con cliente no encontrado: "
            f"{total_cliente_no_encontrado}"
        )

        self.stdout.write(
            f"Tickets sin detalles: "
            f"{total_sin_detalles}"
        )

        self.stdout.write(
            f"Tickets sin detalles válidos: "
            f"{total_sin_detalles_validos}"
        )

        self.stdout.write(
            f"Tickets históricos ya existentes: "
            f"{total_ya_existentes}"
        )

        self.stdout.write(
            f"Detalles con cantidad inválida: "
            f"{total_detalles_invalidos}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte generado en: "
                f"{ruta_auditoria}"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Modo auditoría: no se creó ni "
                    "modificó ningún ticket."
                )
            )
            return

        # ------------------------------------------------------
        # Importación real
        # ------------------------------------------------------

        tickets_importados = []
        tickets_omitidos = []

        total_tickets_creados = 0
        total_detalles_creados = 0
        total_omitidos_importacion = 0

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "INICIANDO IMPORTACIÓN REAL DE TICKETS"
            )
        )

        try:
            with transaction.atomic():
                total_candidatos = len(
                    tickets_importables
                )

                for posicion, datos in enumerate(
                    tickets_importables,
                    start=1,
                ):
                    egreso = datos["egreso"]
                    cliente = datos["cliente"]
                    dni = datos["dni"]

                    numero_historico = (
                        datos["numero_historico"]
                    )

                    if TicketVenta.objects.filter(
                        numero=numero_historico
                    ).exists():
                        total_omitidos_importacion += 1

                        tickets_omitidos.append(
                            {
                                "egreso_id": egreso["id"],
                                "numero_historico": (
                                    numero_historico
                                ),
                                "dni": dni,
                                "motivo": (
                                    "El ticket ya existe"
                                ),
                            }
                        )
                        continue

                    fecha_emision = (
                        self.obtener_fecha_emision(
                            egreso["fecha_pedido"],
                            egreso["created"],
                        )
                    )

                    hora_emision = (
                        self.obtener_hora_emision(
                            egreso["created"],
                            egreso["fecha_pedido"],
                        )
                    )

                    vendedor = self.extraer_vendedor(
                        egreso["comentarios"]
                    )

                    total = self.convertir_decimal(
                        egreso["total"]
                    )

                    ticket = TicketVenta.objects.create(
                        numero=numero_historico,
                        cliente=cliente,
                        vendedor=vendedor[:100],
                        fecha_emision=fecha_emision,
                        fecha_entrega=(
                            fecha_emision.strftime(
                                "%d/%m/%Y"
                            )
                        ),
                        hora_entrega=(
                            hora_emision.strftime(
                                "%H:%M"
                            )
                        ),
                        total=total,
                        a_cuenta=Decimal("0.00"),
                        saldo=Decimal("0.00"),
                        puntos_ic=0,
                    )

                    # auto_now_add asigna la hora actual.
                    # La reemplazamos por la hora histórica.
                    TicketVenta.objects.filter(
                        pk=ticket.pk
                    ).update(
                        hora_emision=hora_emision
                    )

                    detalles_creados_ticket = 0

                    for detalle in datos["detalles"]:
                        cantidad = (
                            self.convertir_cantidad(
                                detalle["cantidad"]
                            )
                        )

                        if cantidad is None:
                            continue

                        producto_origen = (
                            productos_origen.get(
                                detalle["producto_id"]
                            )
                        )

                        descripcion = (
                            self.construir_descripcion(
                                producto_origen
                            )
                        )

                        precio = self.convertir_decimal(
                            detalle["precio"]
                        )

                        DetalleTicketVenta.objects.create(
                            ticket_numero=ticket,
                            producto=None,
                            descripcion=descripcion,
                            cantidad=cantidad,
                            precio=precio,
                        )

                        detalles_creados_ticket += 1
                        total_detalles_creados += 1

                    if detalles_creados_ticket == 0:
                        raise ValueError(
                            f"El ticket histórico "
                            f"{numero_historico} quedó "
                            f"sin detalles."
                        )

                    total_tickets_creados += 1

                    tickets_importados.append(
                        {
                            "egreso_id": egreso["id"],
                            "ticket_id_destino": ticket.id,
                            "numero_historico": (
                                numero_historico
                            ),
                            "dni_cliente": dni,
                            "cliente_destino": (
                                cliente.nombre
                            ),
                            "fecha_emision": (
                                fecha_emision.isoformat()
                            ),
                            "hora_emision": (
                                hora_emision.strftime(
                                    "%H:%M:%S"
                                )
                            ),
                            "vendedor": vendedor,
                            "total": total,
                            "detalles_creados": (
                                detalles_creados_ticket
                            ),
                            "resultado": "IMPORTADO",
                        }
                    )

                    if (
                        posicion % 100 == 0
                        or posicion == total_candidatos
                    ):
                        self.stdout.write(
                            f"Procesados: {posicion}/"
                            f"{total_candidatos}"
                        )

        except Exception as error:
            self.stdout.write(
                self.style.ERROR(
                    f"Importación cancelada: {error}"
                )
            )

            raise CommandError(
                "Ocurrió un error. La transacción fue "
                "revertida y no se guardó ningún ticket "
                "ni detalle."
            )

        # ------------------------------------------------------
        # Reportes finales
        # ------------------------------------------------------

        ruta_importados = (
            carpeta_reportes
            / "tickets_importados.csv"
        )

        columnas_importados = [
            "egreso_id",
            "ticket_id_destino",
            "numero_historico",
            "dni_cliente",
            "cliente_destino",
            "fecha_emision",
            "hora_emision",
            "vendedor",
            "total",
            "detalles_creados",
            "resultado",
        ]

        self.guardar_csv(
            ruta_importados,
            columnas_importados,
            tickets_importados,
        )

        ruta_omitidos = (
            carpeta_reportes
            / "tickets_omitidos.csv"
        )

        columnas_omitidos = [
            "egreso_id",
            "numero_historico",
            "dni",
            "motivo",
        ]

        self.guardar_csv(
            ruta_omitidos,
            columnas_omitidos,
            tickets_omitidos,
        )

        ruta_resumen = (
            carpeta_reportes
            / "resumen_importacion_tickets.txt"
        )

        with open(
            ruta_resumen,
            "w",
            encoding="utf-8",
        ) as archivo_resumen:
            archivo_resumen.write(
                "========================================\n"
            )
            archivo_resumen.write(
                "IMPORTACIÓN DE TICKETS HISTÓRICOS\n"
            )
            archivo_resumen.write(
                "========================================\n\n"
            )

            archivo_resumen.write(
                f"Fecha de ejecución: "
                f"{timezone.localtime()}\n"
            )

            archivo_resumen.write(
                f"Base de destino: "
                f"{connection.settings_dict['ENGINE']}\n"
            )

            archivo_resumen.write(
                f"Host: "
                f"{connection.settings_dict.get('HOST')}\n\n"
            )

            archivo_resumen.write(
                f"Egresos encontrados: "
                f"{len(egresos)}\n"
            )

            archivo_resumen.write(
                f"Detalles encontrados: "
                f"{len(detalles)}\n"
            )

            archivo_resumen.write(
                f"Tickets candidatos: "
                f"{total_importables}\n"
            )

            archivo_resumen.write(
                f"Tickets importados: "
                f"{total_tickets_creados}\n"
            )

            archivo_resumen.write(
                f"Detalles importados: "
                f"{total_detalles_creados}\n"
            )

            archivo_resumen.write(
                f"Tickets omitidos durante importación: "
                f"{total_omitidos_importacion}\n"
            )

            archivo_resumen.write(
                f"Tickets con DNI inválido: "
                f"{total_dni_invalido}\n"
            )

            archivo_resumen.write(
                f"Tickets sin cliente de origen: "
                f"{total_sin_cliente_origen}\n"
            )

            archivo_resumen.write(
                f"Tickets con cliente no encontrado: "
                f"{total_cliente_no_encontrado}\n"
            )

            archivo_resumen.write(
                f"Tickets sin detalles: "
                f"{total_sin_detalles}\n"
            )

            archivo_resumen.write(
                f"Tickets sin detalles válidos: "
                f"{total_sin_detalles_validos}\n"
            )

            archivo_resumen.write(
                "\n========================================\n"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "IMPORTACIÓN DE TICKETS FINALIZADA "
                "CORRECTAMENTE"
            )
        )

        self.stdout.write(
            f"Tickets importados: "
            f"{total_tickets_creados}"
        )

        self.stdout.write(
            f"Detalles importados: "
            f"{total_detalles_creados}"
        )

        self.stdout.write(
            f"Tickets omitidos durante importación: "
            f"{total_omitidos_importacion}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte de importados: "
                f"{ruta_importados}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte de omitidos: "
                f"{ruta_omitidos}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Resumen: {ruta_resumen}"
            )
        )