import csv
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import Cliente


class Command(BaseCommand):
    help = "Audita e importa clientes desde una base SQLite antigua."

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
            help="Ejecuta la importación real de clientes nuevos.",
        )

    # ==========================================================
    # FUNCIONES DE LIMPIEZA
    # ==========================================================

    def limpiar_texto(self, valor):
        if valor is None:
            return ""

        return str(valor).strip()

    def normalizar_dni(self, valor):
        dni = self.limpiar_texto(valor)

        # Quitar espacios, puntos, guiones y caracteres especiales.
        dni = re.sub(r"[^0-9A-Za-z]", "", dni).upper()

        return dni

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

        if dni in valores_invalidos:
            return False

        # Solo se aceptarán DNI peruanos de 8 dígitos.
        return dni.isdigit() and len(dni) == 8

    def normalizar_nombre(self, valor):
        nombre = self.limpiar_texto(valor).upper()

        # Quitar tildes.
        nombre = unicodedata.normalize("NFKD", nombre)
        nombre = "".join(
            caracter
            for caracter in nombre
            if not unicodedata.combining(caracter)
        )

        # Dejar letras, números y espacios.
        nombre = re.sub(r"[^A-ZÑ0-9 ]", " ", nombre)
        nombre = re.sub(r"\s+", " ", nombre).strip()

        return nombre

    def normalizar_telefono(self, valor):
        telefono = self.limpiar_texto(valor)

        # Dejar únicamente números.
        telefono = re.sub(r"\D", "", telefono)

        # Quitar prefijo de Perú cuando llega como 51 + 9 dígitos.
        if telefono.startswith("51") and len(telefono) == 11:
            telefono = telefono[2:]

        valores_invalidos = {
            "",
            "0",
            "00",
            "000",
            "0000",
            "000000000",
            "999999999",
        }

        if telefono in valores_invalidos:
            return ""

        return telefono

    def convertir_fecha(self, valor):
        texto = self.limpiar_texto(valor)

        if not texto:
            return None

        # Ejemplo: 2024-05-20
        fecha = parse_date(texto)

        if fecha:
            return fecha

        # Ejemplo: 2024-05-20T14:30:00
        fecha_hora = parse_datetime(texto)

        if fecha_hora:
            return fecha_hora.date()

        formatos = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y",
            "%d-%m-%Y %H:%M:%S",
        ]

        for formato in formatos:
            try:
                return datetime.strptime(texto, formato).date()

            except ValueError:
                continue

        return None

    def seleccionar_mejor_registro(self, filas):
        """
        Devuelve el mejor registro de un mismo DNI.

        Prioridad:
        1. Nombre más largo.
        2. Teléfono informado.
        3. Fecha más antigua.
        """

        def criterio(fila):
            nombre = self.normalizar_nombre(fila["nombre"])
            telefono = self.normalizar_telefono(fila["telefono"])
            fecha = self.convertir_fecha(fila["created"])

            return (
                len(nombre),
                1 if telefono else 0,
                -(fecha.toordinal() if fecha else 99999999),
            )

        return max(filas, key=criterio)

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
                f"No se encontró el archivo: {ruta_archivo}"
            )

        if dry_run and confirmar:
            raise CommandError(
                "No uses --dry-run y --confirmar al mismo tiempo."
            )

        if not dry_run and not confirmar:
            raise CommandError(
                "Debes usar --dry-run para auditar o "
                "--confirmar para importar."
            )

        # Protección: la importación real debe apuntar a PostgreSQL.
        if confirmar and connection.vendor != "postgresql":
            raise CommandError(
                "IMPORTACIÓN CANCELADA: Django no está conectado a "
                "PostgreSQL.\n"
                f"Motor actual: {connection.settings_dict['ENGINE']}\n"
                "Configura DATABASE_URL con las credenciales de Heroku "
                "antes de ejecutar --confirmar."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Archivo encontrado: {ruta_archivo}"
            )
        )

        self.stdout.write(
            f"Base de destino: {connection.settings_dict['ENGINE']}"
        )

        self.stdout.write(
            f"Host de destino: "
            f"{connection.settings_dict.get('HOST') or '(local)'}"
        )

        self.stdout.write(
            f"Clientes actuales en destino: {Cliente.objects.count()}"
        )

        # ------------------------------------------------------
        # Leer SQLite antigua
        # ------------------------------------------------------

        conexion_sqlite = sqlite3.connect(ruta_archivo)
        conexion_sqlite.row_factory = sqlite3.Row

        try:
            cursor = conexion_sqlite.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    codigo,
                    nombre,
                    telefono,
                    created
                FROM index_cliente
                ORDER BY id
                """
            )

            clientes_antiguos = cursor.fetchall()

        except sqlite3.Error as error:
            raise CommandError(
                f"Error al leer la base SQLite: {error}"
            )

        finally:
            conexion_sqlite.close()

        self.stdout.write(
            f"Clientes encontrados en SQLite: "
            f"{len(clientes_antiguos)}"
        )

        # ------------------------------------------------------
        # Preparar los DNI existentes en la base principal
        # ------------------------------------------------------

        clientes_principales = {}

        for cliente in Cliente.objects.all().iterator():
            dni_actual = self.normalizar_dni(cliente.DNI)

            if dni_actual:
                clientes_principales[dni_actual] = cliente

        # ------------------------------------------------------
        # Detectar DNI repetidos en SQLite
        # ------------------------------------------------------
        registros_por_dni = {}

        for fila in clientes_antiguos:
            dni = self.normalizar_dni(fila["codigo"])

            if self.dni_es_valido(dni):
                registros_por_dni.setdefault(dni, []).append(fila)

        contador_dni = Counter({
            dni: len(filas)
            for dni, filas in registros_por_dni.items()
        })

        dni_repetidos = {
            dni
            for dni, cantidad in contador_dni.items()
            if cantidad > 1
        }

        registro_principal = {
            dni: self.seleccionar_mejor_registro(filas)
            for dni, filas in registros_por_dni.items()
        }
 

        # ------------------------------------------------------
        # Auditar todos los registros
        # ------------------------------------------------------

        filas_reporte = []

        total_invalidos = 0
        total_sin_nombre = 0
        total_repetidos_antigua = 0
        total_existentes = 0
        total_nuevos = 0
        total_nombre_distinto = 0
        total_telefono_distinto = 0

        for fila in clientes_antiguos:
            dni = self.normalizar_dni(fila["codigo"])
            nombre_antiguo = self.normalizar_nombre(fila["nombre"])
            telefono_antiguo = self.normalizar_telefono(
                fila["telefono"]
            )
            fecha_antigua = self.limpiar_texto(fila["created"])

            estado = ""
            nombre_principal = ""
            telefono_principal = ""
            fecha_principal = ""
            observacion = ""

            if not self.dni_es_valido(dni):
                estado = "DNI_INVALIDO"
                observacion = "No se importará automáticamente."
                total_invalidos += 1

            elif not nombre_antiguo:
                estado = "NOMBRE_VACIO"
                observacion = "No se importará porque no tiene nombre."
                total_sin_nombre += 1

            elif dni in dni_repetidos:

                principal = registro_principal[dni]

                if fila["id"] != principal["id"]:

                    estado = "DUPLICADO_ORIGEN_OMITIDO"

                    observacion = (
                        f"Se utilizará el registro ID "
                        f"{principal['id']} para este DNI."
                    )

                    total_repetidos_antigua += 1

                elif dni in clientes_principales:

                    cliente_actual = clientes_principales[dni]

                    nombre_principal = self.normalizar_nombre(
                        cliente_actual.nombre
                    )

                    telefono_principal = self.normalizar_telefono(
                        cliente_actual.telefono
                    )

                    fecha_principal = self.limpiar_texto(
                        cliente_actual.fecha_registro
                    )

                    estado = "YA_EXISTE"

                    observacion = (
                        f"DNI repetido "
                        f"({contador_dni[dni]} registros), "
                        "pero ya existe en la base principal."
                    )

                    total_existentes += 1

                else:

                    estado = "CLIENTE_NUEVO"

                    observacion = (
                        f"DNI repetido "
                        f"({contador_dni[dni]} registros). "
                        "Se importará únicamente este registro."
                    )

                    total_nuevos += 1

            elif dni in clientes_principales:
                cliente_actual = clientes_principales[dni]

                nombre_principal = self.normalizar_nombre(
                    cliente_actual.nombre
                )

                telefono_principal = self.normalizar_telefono(
                    cliente_actual.telefono
                )

                fecha_principal = self.limpiar_texto(
                    cliente_actual.fecha_registro
                )

                diferencias = []

                if (
                    nombre_antiguo
                    and nombre_principal
                    and nombre_antiguo != nombre_principal
                ):
                    diferencias.append("nombre distinto")
                    total_nombre_distinto += 1

                # El teléfono no se usa para identificar duplicados.
                # Solo se registra como información de auditoría.
                if (
                    telefono_antiguo
                    and telefono_principal
                    and telefono_antiguo != telefono_principal
                ):
                    total_telefono_distinto += 1

                if diferencias:
                    estado = "EXISTE_CON_DIFERENCIAS"
                    observacion = ", ".join(diferencias)

                else:
                    estado = "YA_EXISTE"

                total_existentes += 1

            else:
                estado = "CLIENTE_NUEVO"
                observacion = "Candidato para importación."
                total_nuevos += 1

            filas_reporte.append(
                {
                    "id_antiguo": fila["id"],
                    "dni_codigo": dni,
                    "nombre_antiguo": nombre_antiguo,
                    "telefono_antiguo": telefono_antiguo,
                    "fecha_registro_antigua": fecha_antigua,
                    "nombre_principal": nombre_principal,
                    "telefono_principal": telefono_principal,
                    "fecha_registro_principal": fecha_principal,
                    "estado": estado,
                    "observacion": observacion,
                }
            )

        # ------------------------------------------------------
        # Crear carpeta de reportes
        # ------------------------------------------------------

        carpeta_reportes = Path("importaciones") / "reportes"
        carpeta_reportes.mkdir(parents=True, exist_ok=True)

        ruta_auditoria = (
            carpeta_reportes / "auditoria_clientes.csv"
        )

        columnas_auditoria = [
            "id_antiguo",
            "dni_codigo",
            "nombre_antiguo",
            "telefono_antiguo",
            "fecha_registro_antigua",
            "nombre_principal",
            "telefono_principal",
            "fecha_registro_principal",
            "estado",
            "observacion",
        ]

        self.guardar_csv(
            ruta_auditoria,
            columnas_auditoria,
            filas_reporte,
        )

        # ------------------------------------------------------
        # Mostrar resumen de auditoría
        # ------------------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("AUDITORÍA FINALIZADA")
        )

        self.stdout.write(
            f"Registros leídos: {len(clientes_antiguos)}"
        )

        self.stdout.write(
            f"Clientes nuevos candidatos: {total_nuevos}"
        )

        self.stdout.write(
            f"Clientes que ya existen por DNI: {total_existentes}"
        )

        self.stdout.write(
            f"Registros con DNI inválido: {total_invalidos}"
        )

        self.stdout.write(
            f"Registros sin nombre: {total_sin_nombre}"
        )

        self.stdout.write(
            f"Registros involucrados en DNI repetidos: "
            f"{total_repetidos_antigua}"
        )

        self.stdout.write(
            f"Coincidencias con nombre distinto: "
            f"{total_nombre_distinto}"
        )

        self.stdout.write(
            f"Coincidencias con teléfono distinto: "
            f"{total_telefono_distinto}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte generado en: {ruta_auditoria}"
            )
        )

        # ------------------------------------------------------
        # Modo auditoría
        # ------------------------------------------------------

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Modo auditoría: no se realizó ningún cambio."
                )
            )
            return

        # ------------------------------------------------------
        # Importación real
        # ------------------------------------------------------

        clientes_importados = []
        clientes_omitidos = []

        importados = 0
        omitidos = 0

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "INICIANDO IMPORTACIÓN REAL EN POSTGRESQL"
            )
        )

        try:
            with transaction.atomic():
                candidatos = [
                    fila
                    for fila in filas_reporte
                    if fila["estado"] == "CLIENTE_NUEVO"
                ]

                total_candidatos = len(candidatos)

                for posicion, fila in enumerate(
                    candidatos,
                    start=1,
                ):
                    dni = self.normalizar_dni(
                        fila["dni_codigo"]
                    )

                    nombre = self.normalizar_nombre(
                        fila["nombre_antiguo"]
                    )

                    telefono = self.normalizar_telefono(
                        fila["telefono_antiguo"]
                    )

                    fecha_registro = self.convertir_fecha(
                        fila["fecha_registro_antigua"]
                    )

                    if not self.dni_es_valido(dni):
                        omitidos += 1

                        clientes_omitidos.append(
                            {
                                "id_antiguo": fila["id_antiguo"],
                                "dni": dni,
                                "nombre": nombre,
                                "motivo": "DNI inválido",
                            }
                        )
                        continue

                    if not nombre:
                        omitidos += 1

                        clientes_omitidos.append(
                            {
                                "id_antiguo": fila["id_antiguo"],
                                "dni": dni,
                                "nombre": nombre,
                                "motivo": "Nombre vacío",
                            }
                        )
                        continue

                    # Verificación final contra PostgreSQL.
                    if Cliente.objects.filter(
                        DNI__iexact=dni
                    ).exists():
                        omitidos += 1

                        clientes_omitidos.append(
                            {
                                "id_antiguo": fila["id_antiguo"],
                                "dni": dni,
                                "nombre": nombre,
                                "motivo": (
                                    "El DNI ya existe en la base principal"
                                ),
                            }
                        )
                        continue

                    datos_cliente = {
                        "DNI": dni[:20],
                        "nombre": nombre[:255],
                        "telefono": (
                            telefono[:20]
                            if telefono
                            else None
                        ),
                        "Edad": None,
                        "Optometra": None,
                    }

                    if fecha_registro:
                        datos_cliente["fecha_registro"] = (
                            fecha_registro
                        )

                    else:
                        datos_cliente["fecha_registro"] = (
                            timezone.localdate()
                        )

                    cliente = Cliente.objects.create(
                        **datos_cliente
                    )

                    importados += 1

                    clientes_importados.append(
                        {
                            "id_antiguo": fila["id_antiguo"],
                            "id_principal": cliente.id,
                            "dni": cliente.DNI,
                            "nombre": cliente.nombre,
                            "telefono": cliente.telefono or "",
                            "fecha_registro": (
                                cliente.fecha_registro.isoformat()
                                if cliente.fecha_registro
                                else ""
                            ),
                            "resultado": "IMPORTADO",
                        }
                    )

                    # Mostrar progreso cada 100 registros.
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
                "Ocurrió un error. La transacción fue revertida "
                "y no se guardó ningún cliente."
            )

        # ------------------------------------------------------
        # Generar reportes después del commit exitoso
        # ------------------------------------------------------

        ruta_importados = (
            carpeta_reportes / "clientes_importados.csv"
        )

        columnas_importados = [
            "id_antiguo",
            "id_principal",
            "dni",
            "nombre",
            "telefono",
            "fecha_registro",
            "resultado",
        ]

        self.guardar_csv(
            ruta_importados,
            columnas_importados,
            clientes_importados,
        )

        ruta_omitidos = (
            carpeta_reportes / "clientes_omitidos.csv"
        )

        columnas_omitidos = [
            "id_antiguo",
            "dni",
            "nombre",
            "motivo",
        ]

        self.guardar_csv(
            ruta_omitidos,
            columnas_omitidos,
            clientes_omitidos,
        )

        ruta_resumen = (
            carpeta_reportes / "resumen_importacion.txt"
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
                "IMPORTACIÓN DE CLIENTES\n"
            )
            archivo_resumen.write(
                "========================================\n\n"
            )
            archivo_resumen.write(
                f"Fecha: {timezone.localtime()}\n"
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
                f"Registros leídos: "
                f"{len(clientes_antiguos)}\n"
            )
            archivo_resumen.write(
                f"Clientes candidatos: {total_nuevos}\n"
            )
            archivo_resumen.write(
                f"Clientes importados: {importados}\n"
            )
            archivo_resumen.write(
                f"Clientes omitidos durante importación: "
                f"{omitidos}\n"
            )
            archivo_resumen.write(
                f"DNI inválidos: {total_invalidos}\n"
            )
            archivo_resumen.write(
                f"Nombres vacíos: {total_sin_nombre}\n"
            )
            archivo_resumen.write(
                f"Registros con DNI repetido: "
                f"{total_repetidos_antigua}\n"
            )
            archivo_resumen.write(
                f"Clientes ya existentes: "
                f"{total_existentes}\n"
            )
            archivo_resumen.write(
                "\n========================================\n"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "IMPORTACIÓN FINALIZADA CORRECTAMENTE"
            )
        )

        self.stdout.write(
            f"Clientes importados: {importados}"
        )

        self.stdout.write(
            f"Clientes omitidos durante importación: "
            f"{omitidos}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte de importados: {ruta_importados}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reporte de omitidos: {ruta_omitidos}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Resumen: {ruta_resumen}"
            )
        )