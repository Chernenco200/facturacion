import csv
import re
import sqlite3
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Cliente, TicketVenta


class Command(BaseCommand):
    help = "Audita tickets y detalles desde una base SQLite antigua."

    NUMERO_BASE_HISTORICO = 9_000_000

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            type=str,
            required=True,
            help="Ruta del archivo SQLite antiguo.",
        )

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

        invalidos = {
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
            dni not in invalidos
            and dni.isdigit()
            and len(dni) == 8
        )

    def convertir_decimal(self, valor):
        try:
            return Decimal(str(valor or 0))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0.00")

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

        return "HISTÓRICO"

    def handle(self, *args, **options):
        ruta_archivo = Path(options["archivo"])

        if not ruta_archivo.exists():
            raise CommandError(
                f"No se encontró el archivo: {ruta_archivo}"
            )

        conexion = sqlite3.connect(ruta_archivo)
        conexion.row_factory = sqlite3.Row

        try:
            cursor = conexion.cursor()

            clientes_origen = {
                fila["id"]: fila
                for fila in cursor.execute(
                    """
                    SELECT id, codigo, nombre
                    FROM index_cliente
                    """
                ).fetchall()
            }

            productos_origen = {
                fila["id"]: fila
                for fila in cursor.execute(
                    """
                    SELECT id, codigo, descripcion
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
                    egreso_id,
                    producto_id,
                    precio,
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
            conexion.close()

        detalles_por_egreso = Counter(
            detalle["egreso_id"]
            for detalle in detalles
        )

        clientes_destino = {}

        for cliente in Cliente.objects.all().iterator():
            dni = self.normalizar_dni(cliente.DNI)

            if dni and dni not in clientes_destino:
                clientes_destino[dni] = cliente

        filas_reporte = []

        total_validos = 0
        total_sin_cliente_origen = 0
        total_dni_invalido = 0
        total_cliente_no_encontrado = 0
        total_sin_detalles = 0
        total_ya_existente = 0
        total_importables = 0

        for egreso in egresos:
            id_egreso = egreso["id"]
            numero_historico = (
                self.NUMERO_BASE_HISTORICO + id_egreso
            )

            cliente_origen = clientes_origen.get(
                egreso["cliente_id"]
            )

            dni = ""
            nombre_origen = ""
            cliente_destino = None
            estado = ""
            observacion = ""

            if not cliente_origen:
                estado = "SIN_CLIENTE_ORIGEN"
                observacion = (
                    "El cliente_id no existe en index_cliente."
                )
                total_sin_cliente_origen += 1

            else:
                dni = self.normalizar_dni(
                    cliente_origen["codigo"]
                )

                nombre_origen = self.limpiar_texto(
                    cliente_origen["nombre"]
                )

                if not self.dni_es_valido(dni):
                    estado = "DNI_INVALIDO"
                    observacion = (
                        "El ticket no se importará."
                    )
                    total_dni_invalido += 1

                else:
                    cliente_destino = clientes_destino.get(dni)

                    if not cliente_destino:
                        estado = "CLIENTE_NO_ENCONTRADO"
                        observacion = (
                            "El DNI válido no existe en core_cliente."
                        )
                        total_cliente_no_encontrado += 1

                    elif TicketVenta.objects.filter(
                        numero=numero_historico
                    ).exists():
                        estado = "TICKET_YA_EXISTE"
                        observacion = (
                            "El ticket histórico ya fue importado."
                        )
                        total_ya_existente += 1

                    elif detalles_por_egreso[id_egreso] == 0:
                        estado = "SIN_DETALLES"
                        observacion = (
                            "El egreso no tiene productos asociados."
                        )
                        total_sin_detalles += 1

                    else:
                        estado = "IMPORTABLE"
                        observacion = (
                            "Ticket listo para importar."
                        )
                        total_importables += 1
                        total_validos += 1

            filas_reporte.append(
                {
                    "egreso_id": id_egreso,
                    "numero_historico": numero_historico,
                    "cliente_id_origen": egreso["cliente_id"],
                    "dni_cliente": dni,
                    "nombre_cliente_origen": nombre_origen,
                    "cliente_id_destino": (
                        cliente_destino.id
                        if cliente_destino
                        else ""
                    ),
                    "fecha_pedido": egreso["fecha_pedido"],
                    "created": egreso["created"],
                    "comentarios": self.limpiar_texto(
                        egreso["comentarios"]
                    ),
                    "vendedor_detectado": self.extraer_vendedor(
                        egreso["comentarios"]
                    ),
                    "pagado_origen": self.convertir_decimal(
                        egreso["pagado"]
                    ),
                    "total_origen": self.convertir_decimal(
                        egreso["total"]
                    ),
                    "cantidad_detalles": (
                        detalles_por_egreso[id_egreso]
                    ),
                    "estado": estado,
                    "observacion": observacion,
                }
            )

        productos_faltantes = 0

        for detalle in detalles:
            if detalle["producto_id"] not in productos_origen:
                productos_faltantes += 1

        carpeta_reportes = Path("importaciones") / "reportes"
        carpeta_reportes.mkdir(parents=True, exist_ok=True)

        ruta_reporte = (
            carpeta_reportes / "auditoria_tickets.csv"
        )

        columnas = [
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
            "estado",
            "observacion",
        ]

        with open(
            ruta_reporte,
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as archivo_csv:
            escritor = csv.DictWriter(
                archivo_csv,
                fieldnames=columnas,
            )
            escritor.writeheader()
            escritor.writerows(filas_reporte)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("AUDITORÍA DE TICKETS FINALIZADA")
        )

        self.stdout.write(
            f"Egresos encontrados: {len(egresos)}"
        )

        self.stdout.write(
            f"Detalles encontrados: {len(detalles)}"
        )

        self.stdout.write(
            f"Tickets importables: {total_importables}"
        )

        self.stdout.write(
            f"Tickets con DNI inválido: {total_dni_invalido}"
        )

        self.stdout.write(
            f"Tickets sin cliente de origen: "
            f"{total_sin_cliente_origen}"
        )

        self.stdout.write(
            f"Tickets con cliente no encontrado en destino: "
            f"{total_cliente_no_encontrado}"
        )

        self.stdout.write(
            f"Tickets sin detalles: {total_sin_detalles}"
        )

        self.stdout.write(
            f"Tickets históricos ya existentes: "
            f"{total_ya_existente}"
        )

        self.stdout.write(
            f"Detalles cuyo producto no existe en index_producto: "
            f"{productos_faltantes}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte generado en: {ruta_reporte}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                "Esta auditoría no creó ni modificó tickets."
            )
        )