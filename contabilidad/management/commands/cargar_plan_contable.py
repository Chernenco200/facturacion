from django.core.management.base import BaseCommand
from django.db import transaction

from contabilidad.models import (
    CuentaContable,
    CategoriaGerencial,
    CentroCosto,
    ConceptoOperacion,
)


class Command(BaseCommand):
    help = "Carga el Plan Contable Maestro de Óptica IC"

    @transaction.atomic
    def handle(self, *args, **options):

        self.stdout.write(
            self.style.WARNING(
                "\nIniciando carga del Plan Contable Maestro "
                "de Óptica IC...\n"
            )
        )

        # ====================================================
        # 1. CENTROS DE COSTO
        # ====================================================

        centros = [
            (
                "ADM",
                "Administración",
                "Gestión administrativa y soporte general.",
            ),
            (
                "COM",
                "Comercial / Ventas",
                "Ventas, atención comercial, marketing y distribución.",
            ),
            (
                "OPT",
                "Optometría",
                "Medición de vista y atención optométrica.",
            ),
            (
                "TAL",
                "Taller",
                "Biselado, montaje y procesos del taller óptico.",
            ),
        ]

        for codigo, nombre, descripcion in centros:
            CentroCosto.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "activo": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "✓ Centros de costo cargados"
            )
        )

        # ====================================================
        # 2. CATEGORÍAS GERENCIALES
        # ====================================================

        categorias = [
            # COSTO DE VENTAS
            ("91000", "Costo de ventas y servicios", None),
            ("91100", "Mercadería vendida", "91000"),
            ("91200", "Taller óptico propio", "91000"),

            ("91300", "Procesos ópticos tercerizados", "91000"),
            ("91301", "Biselado externo", "91300"),
            ("91302", "Coloreado", "91300"),
            ("91303", "Soldadura", "91300"),
            ("91304", "Cambio de Flex", "91300"),
            ("91305", "Medida de vista tercerizada", "91300"),
            ("91399", "Otros procesos ópticos tercerizados", "91300"),

            ("91400", "Garantías, mermas y errores", "91000"),
            ("91401", "Garantía - Error de taller", "91400"),
            ("91402", "Garantía - Error de medida de vista", "91400"),
            ("91403", "Garantía - Defecto de montura", "91400"),
            ("91404", "Garantía - Defecto de lunas", "91400"),
            ("91405", "Garantía - Adaptación", "91400"),
            ("91499", "Otras garantías", "91400"),

            # ADMINISTRACIÓN
            ("92000", "Gastos administrativos", None),
            ("92100", "Personal administrativo", "92000"),
            ("92200", "Servicios administrativos", "92000"),
            ("92300", "Oficina y suministros", "92000"),
            ("92400", "Mantenimiento y reparaciones", "92000"),
            ("92500", "Bienestar, botiquín y SST", "92000"),
            ("92600", "Licencias, permisos y certificaciones", "92000"),
            ("92700", "Software, sistemas y servicios web", "92000"),
            (
                "92800",
                "Servicios profesionales, notariales y registrales",
                "92000",
            ),
            (
                "92900",
                "Seguros, capacitación, movilidad y saneamiento",
                "92000",
            ),

            # COMERCIAL
            ("93000", "Gastos comerciales", None),
            ("93100", "Personal comercial", "93000"),
            ("93200", "Optometría propia", "93000"),
            ("93300", "Empaque y atención al cliente", "93000"),
            ("93400", "Distribución y delivery", "93000"),
            ("93500", "Marketing e imagen", "93000"),
            ("93600", "Medios de pago", "93000"),

            # FINANCIERO
            ("94000", "Resultado financiero", None),
            ("94100", "Intereses y financiamiento", "94000"),
            ("94200", "Comisiones y gastos bancarios", "94000"),
        ]

        for codigo, nombre, padre_codigo in categorias:

            padre = None

            if padre_codigo:
                padre = CategoriaGerencial.objects.get(
                    codigo=padre_codigo
                )

            CategoriaGerencial.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "categoria_padre": padre,
                    "activo": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "✓ Categorías gerenciales cargadas"
            )
        )

        # ====================================================
        # 3. CUENTAS CONTABLES
        # ====================================================
        #
        # Formato:
        #
        # codigo
        # nombre
        # padre
        # tipo
        # naturaleza
        # PCGE
        # EEFF
        # acepta_movimientos
        #

        cuentas = [

            # ------------------------------------------------
            # ACTIVO
            # ------------------------------------------------

            (
                "10",
                "Efectivo y equivalentes de efectivo",
                None,
                "ACTIVO",
                "DEUDORA",
                "10",
                "ESF",
                False,
            ),

            (
                "10101",
                "Caja Óptica IC",
                "10",
                "ACTIVO",
                "DEUDORA",
                "101",
                "ESF",
                True,
            ),

            (
                "10401",
                "Banco principal",
                "10",
                "ACTIVO",
                "DEUDORA",
                "104",
                "ESF",
                True,
            ),

            (
                "10402",
                "Otras cuentas bancarias",
                "10",
                "ACTIVO",
                "DEUDORA",
                "104",
                "ESF",
                True,
            ),

            # CUENTAS POR COBRAR

            (
                "12",
                "Cuentas por cobrar comerciales",
                None,
                "ACTIVO",
                "DEUDORA",
                "12",
                "ESF",
                False,
            ),

            (
                "12101",
                "Clientes - Ventas de óptica",
                "12",
                "ACTIVO",
                "DEUDORA",
                "121",
                "ESF",
                True,
            ),

            (
                "12102",
                "Clientes - Servicio de biselado",
                "12",
                "ACTIVO",
                "DEUDORA",
                "121",
                "ESF",
                True,
            ),

            (
                "12103",
                "Clientes - Servicio de venta/suministro de lunas",
                "12",
                "ACTIVO",
                "DEUDORA",
                "121",
                "ESF",
                True,
            ),

            (
                "12104",
                "Otras cuentas por cobrar comerciales",
                "12",
                "ACTIVO",
                "DEUDORA",
                "121",
                "ESF",
                True,
            ),

            (
                "14",
                "Cuentas por cobrar al personal",
                None,
                "ACTIVO",
                "DEUDORA",
                "14",
                "ESF",
                False,
            ),

            (
                "14101",
                "Adelantos de remuneraciones",
                "14",
                "ACTIVO",
                "DEUDORA",
                "14",
                "ESF",
                True,
            ),

            (
                "16",
                "Otras cuentas por cobrar",
                None,
                "ACTIVO",
                "DEUDORA",
                "16",
                "ESF",
                False,
            ),

            (
                "16101",
                "Préstamos al personal",
                "16",
                "ACTIVO",
                "DEUDORA",
                "16",
                "ESF",
                True,
            ),

            (
                "16102",
                "Entregas a rendir",
                "16",
                "ACTIVO",
                "DEUDORA",
                "16",
                "ESF",
                True,
            ),

            (
                "16103",
                "Reclamaciones a terceros",
                "16",
                "ACTIVO",
                "DEUDORA",
                "16",
                "ESF",
                True,
            ),

            # INVENTARIOS

            (
                "20",
                "Existencias / Mercaderías",
                None,
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                False,
            ),

            (
                "20101",
                "Monturas",
                "20",
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                True,
            ),

            (
                "20102",
                "Lunas oftálmicas",
                "20",
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                True,
            ),

            (
                "20103",
                "Lentes de contacto",
                "20",
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                True,
            ),

            (
                "20105",
                "Estuches y cofres",
                "20",
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                True,
            ),

            (
                "20106",
                "Accesorios para venta",
                "20",
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                True,
            ),

            (
                "20107",
                "Líquidos y soluciones ópticas",
                "20",
                "ACTIVO",
                "DEUDORA",
                "20",
                "ESF",
                True,
            ),

            # ACTIVOS FIJOS

            (
                "33",
                "Propiedad, planta y equipo",
                None,
                "ACTIVO",
                "DEUDORA",
                "33",
                "ESF",
                False,
            ),

            ("33601", "Computadoras", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33602", "Impresoras", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33603", "Equipos POS", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33604", "Cámaras de video", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33605", "Biseladoras", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33606", "Autorrefractómetros", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33607", "Cajas de pruebas", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33608", "Mobiliario", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33609", "Ranuradoras", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33610", "Calentadoras", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33611", "Pulidoras", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33612", "Forópteros", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33613", "Otros equipos ópticos", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),
            ("33699", "Otros equipos diversos", "33", "ACTIVO", "DEUDORA", "33", "ESF", True),

            # INTANGIBLES

            (
                "34",
                "Activos intangibles",
                None,
                "ACTIVO",
                "DEUDORA",
                "34",
                "ESF",
                False,
            ),

            (
                "34101",
                "Software adquirido capitalizable",
                "34",
                "ACTIVO",
                "DEUDORA",
                "34",
                "ESF",
                True,
            ),

            (
                "34102",
                "Desarrollo de sistemas capitalizable",
                "34",
                "ACTIVO",
                "DEUDORA",
                "34",
                "ESF",
                True,
            ),

            # ------------------------------------------------
            # PASIVO
            # ------------------------------------------------

            (
                "40",
                "Tributos y aportes por pagar",
                None,
                "PASIVO",
                "ACREEDORA",
                "40",
                "ESF",
                False,
            ),

            ("40111", "IGV por pagar", "40", "PASIVO", "ACREEDORA", "4011", "ESF", True),
            ("40171", "Impuesto a la renta por pagar", "40", "PASIVO", "ACREEDORA", "4017", "ESF", True),
            ("40301", "ESSALUD por pagar", "40", "PASIVO", "ACREEDORA", "403", "ESF", True),
            ("40302", "ONP por pagar", "40", "PASIVO", "ACREEDORA", "403", "ESF", True),

            (
                "41",
                "Remuneraciones y participaciones por pagar",
                None,
                "PASIVO",
                "ACREEDORA",
                "41",
                "ESF",
                False,
            ),

            ("41101", "Remuneraciones por pagar", "41", "PASIVO", "ACREEDORA", "411", "ESF", True),
            ("41102", "Gratificaciones por pagar", "41", "PASIVO", "ACREEDORA", "411", "ESF", True),
            ("41103", "Vacaciones por pagar", "41", "PASIVO", "ACREEDORA", "411", "ESF", True),
            ("41104", "Liquidaciones por pagar", "41", "PASIVO", "ACREEDORA", "411", "ESF", True),

            (
                "42",
                "Cuentas por pagar comerciales",
                None,
                "PASIVO",
                "ACREEDORA",
                "42",
                "ESF",
                False,
            ),

            ("42101", "Proveedores de monturas", "42", "PASIVO", "ACREEDORA", "421", "ESF", True),
            ("42102", "Proveedores de lunas", "42", "PASIVO", "ACREEDORA", "421", "ESF", True),
            ("42103", "Proveedores de lentes de contacto", "42", "PASIVO", "ACREEDORA", "421", "ESF", True),
            ("42104", "Proveedores de accesorios y estuches", "42", "PASIVO", "ACREEDORA", "421", "ESF", True),
            ("42105", "Proveedores de procesos ópticos", "42", "PASIVO", "ACREEDORA", "421", "ESF", True),
            ("42106", "Otros proveedores", "42", "PASIVO", "ACREEDORA", "421", "ESF", True),

            # DEUDA

            (
                "45",
                "Obligaciones financieras",
                None,
                "PASIVO",
                "ACREEDORA",
                "45",
                "ESF",
                False,
            ),

            ("45101", "Préstamos bancarios - Corto plazo", "45", "PASIVO", "ACREEDORA", "45", "ESF", True),
            ("45102", "Préstamos bancarios - Largo plazo", "45", "PASIVO", "ACREEDORA", "45", "ESF", True),
            ("45201", "Tarjetas de crédito empresariales", "45", "PASIVO", "ACREEDORA", "45", "ESF", True),
            ("45202", "Otros financiamientos", "45", "PASIVO", "ACREEDORA", "45", "ESF", True),

            (
                "46",
                "Anticipos de clientes",
                None,
                "PASIVO",
                "ACREEDORA",
                "46",
                "ESF",
                False,
            ),

            ("46101", "Anticipos de clientes", "46", "PASIVO", "ACREEDORA", "46", "ESF", True),

            # ------------------------------------------------
            # PATRIMONIO
            # ------------------------------------------------

            ("50", "Capital", None, "PATRIMONIO", "ACREEDORA", "50", "ESF", False),
            ("50101", "Capital aportado", "50", "PATRIMONIO", "ACREEDORA", "50", "ESF", True),

            ("59", "Resultados acumulados", None, "PATRIMONIO", "ACREEDORA", "59", "ESF", False),
            ("59101", "Utilidades acumuladas", "59", "PATRIMONIO", "ACREEDORA", "59", "ESF", True),
            ("59201", "Pérdidas acumuladas", "59", "PATRIMONIO", "DEUDORA", "59", "ESF", True),
            ("59901", "Resultado del ejercicio", "59", "PATRIMONIO", "ACREEDORA", "59", "ESF", True),

            ("44120", "Dividendos por pagar", None, "PASIVO", "ACREEDORA", "4412", "ESF", True),

            # ------------------------------------------------
            # GASTOS
            # ------------------------------------------------

            ("62", "Gastos de personal", None, "GASTO", "DEUDORA", "62", "ER", False),

            ("62101", "Remuneración biselador", "62", "GASTO", "DEUDORA", "62", "ER", True),
            ("62102", "Sueldos - Administración", "62", "GASTO", "DEUDORA", "62", "ER", True),
            ("62103", "Sueldos - Ventas", "62", "GASTO", "DEUDORA", "62", "ER", True),
            ("62104", "Remuneración optómetra", "62", "GASTO", "DEUDORA", "62", "ER", True),
            ("62105", "Comisiones por ventas", "62", "GASTO", "DEUDORA", "62", "ER", True),
            ("62106", "Beneficios sociales y liquidaciones", "62", "GASTO", "DEUDORA", "62", "ER", True),

            ("63", "Servicios prestados por terceros", None, "GASTO", "DEUDORA", "63", "ER", False),

            ("63101", "Alquiler del local", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63102", "Servicios básicos", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63103", "Seguridad", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63104", "Mantenimiento y reparaciones", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63105", "Delivery, courier y mensajería", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63106", "Publicidad y marketing", "63", "GASTO", "DEUDORA", "63", "ER", True),
#            ("63107", "Procesos ópticos tercerizados", "63", "GASTO", "DEUDORA", "63", "ER", True),
# PRODUCCIÓN / PROCESOS ÓPTICOS ENCARGADOS A TERCEROS
            ("63301", "Biselado externo", "63", "GASTO", "DEUDORA", "633", "ER", True),

            (
                "63302",
                "Coloreado externo",
                "63",
                "GASTO",
                "DEUDORA",
                "633",
                "ER",
                True
            ),

            (
                "63303",
                "Soldadura externa",
                "63",
                "GASTO",
                "DEUDORA",
                "633",
                "ER",
                True
            ),

            (
                "63304",
                "Cambio de Flex externo",
                "63",
                "GASTO",
                "DEUDORA",
                "633",
                "ER",
                True
            ),

            (
                "63309",
                "Otros procesos ópticos tercerizados",
                "63",
                "GASTO",
                "DEUDORA",
                "633",
                "ER",
                True
            ),

            # SERVICIO DE OPTOMETRÍA TERCERIZADO

            (
                "63901",
                "Medida de vista tercerizada",
                "63",
                "GASTO",
                "DEUDORA",
                "639",
                "ER",
                True
            ),

            ("63108", "Servicios de limpieza", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63109", "Licencias, permisos y autorizaciones", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63110", "Certificaciones e inspecciones técnicas", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63111", "Software y suscripciones", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63112", "Desarrollo y mantenimiento de sistemas", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63113", "Dominio, hosting y servicios web", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63114", "Asesoría y servicios profesionales", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63115", "Servicios notariales y registrales", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63116", "Comisiones por medios de pago", "63", "GASTO", "DEUDORA", "63", "ER", True),
            ("63117", "Fumigación y saneamiento", "63", "GASTO", "DEUDORA", "63", "ER", True),

            ("65", "Otros gastos de gestión", None, "GASTO", "DEUDORA", "65", "ER", False),

            ("65101", "Papelería, talonarios y útiles de oficina", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65102", "Artículos de limpieza", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65103", "Botiquín y primeros auxilios", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65104", "Seguridad y salud en el trabajo", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65105", "Bienestar e integración del personal", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65106", "Bolsas de papel y plástico", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65107", "Paños de microfibra", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65108", "Uniformes", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65109", "Obsequios y regalos promocionales", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65110", "Líquidos entregados gratuitamente", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65111", "Insumos y repuestos menores de taller", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65112", "Garantías, mermas y errores", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65113", "Recetarios y material de optometría", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65114", "Seguros", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65115", "Capacitación", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65116", "Movilidad y viáticos", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65117", "Atención y cortesías a clientes", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65118", "Decoración y ambientación", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65119", "Multas, sanciones y penalidades", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65120", "Accesorios y equipos menores no capitalizables", "65", "GASTO", "DEUDORA", "65", "ER", True),
            ("65199", "Otros gastos de gestión", "65", "GASTO", "DEUDORA", "65", "ER", True),

            # FINANCIEROS

            ("67", "Gastos financieros", None, "GASTO", "DEUDORA", "67", "ER", False),

            ("67101", "Intereses de préstamos", "67", "GASTO", "DEUDORA", "67", "ER", True),
            ("67102", "Intereses de tarjetas y otros créditos", "67", "GASTO", "DEUDORA", "67", "ER", True),
            ("67103", "Intereses moratorios", "67", "GASTO", "DEUDORA", "67", "ER", True),
            ("67104", "Otros gastos por financiamiento", "67", "GASTO", "DEUDORA", "67", "ER", True),
            ("67105", "Pérdida por diferencia de cambio", "67", "GASTO", "DEUDORA", "67", "ER", True),
            ("67106", "Comisiones y gastos bancarios", "67", "GASTO", "DEUDORA", "67", "ER", True),

            (
                "68",
                "Depreciación y amortización del periodo",
                None,
                "GASTO",
                "DEUDORA",
                "68",
                "ER",
                True,
            ),

            # COSTO DE VENTAS

            ("69", "Costo de ventas", None, "COSTO", "DEUDORA", "69", "ER", False),

            ("69101", "Costo de ventas - Monturas", "69", "COSTO", "DEUDORA", "69", "ER", True),
            ("69102", "Costo de ventas - Lunas oftálmicas", "69", "COSTO", "DEUDORA", "69", "ER", True),
            ("69103", "Costo de ventas - Lentes de contacto", "69", "COSTO", "DEUDORA", "69", "ER", True),
            ("69105", "Costo de ventas - Estuches y cofres", "69", "COSTO", "DEUDORA", "69", "ER", True),
            ("69106", "Costo de ventas - Accesorios", "69", "COSTO", "DEUDORA", "69", "ER", True),
            ("69107", "Costo de ventas - Líquidos y soluciones", "69", "COSTO", "DEUDORA", "69", "ER", True),

            # ------------------------------------------------
            # INGRESOS
            # ------------------------------------------------

            ("70", "Ventas e ingresos operacionales", None, "INGRESO", "ACREEDORA", "70", "ER", False),

            ("70101", "Venta de monturas", "70", "INGRESO", "ACREEDORA", "70", "ER", True),
            ("70102", "Venta de lunas oftálmicas", "70", "INGRESO", "ACREEDORA", "70", "ER", True),
            ("70103", "Venta de lentes de contacto", "70", "INGRESO", "ACREEDORA", "70", "ER", True),
            ("70104", "Venta de líquidos y soluciones ópticas", "70", "INGRESO", "ACREEDORA", "70", "ER", True),
            ("70105", "Venta de accesorios", "70", "INGRESO", "ACREEDORA", "70", "ER", True),

            ("70401", "Servicio de biselado a terceros", "70", "INGRESO", "ACREEDORA", "70", "ER", True),
            ("70402", "Servicio de venta/suministro de lunas", "70", "INGRESO", "ACREEDORA", "70", "ER", True),
            ("70403", "Otros servicios ópticos", "70", "INGRESO", "ACREEDORA", "70", "ER", True),

            ("77", "Ingresos financieros", None, "INGRESO", "ACREEDORA", "77", "ER", True),
        ]

        # Se crean respetando el orden:
        # primero padres y luego hijos.

        for (
            codigo,
            nombre,
            padre_codigo,
            tipo,
            naturaleza,
            codigo_pcge,
            eeff,
            acepta_movimientos,
        ) in cuentas:

            cuenta_padre = None

            if padre_codigo:
                cuenta_padre = CuentaContable.objects.get(
                    codigo=padre_codigo
                )

            nivel = 1

            if cuenta_padre:
                nivel = cuenta_padre.nivel + 1

            # ====================================================
            # CLASIFICACIÓN PARA EL BALANCE GENERAL
            # ====================================================

            clasificacion_balance = "NO_APLICA"

            if tipo == "ACTIVO":

                if codigo.startswith(
                    ("10", "12", "14", "16", "18", "20")
                ):
                    clasificacion_balance = "ACTIVO_CORRIENTE"

                elif codigo.startswith(
                    (
                        "30", "31", "32", "33", "34",
                        "35", "36", "37", "38", "39"
                    )
                ):
                    clasificacion_balance = "ACTIVO_NO_CORRIENTE"

            elif tipo == "PASIVO":

                if codigo.startswith(
                    ("40", "41", "42", "43", "44", "46", "47")
                ):
                    clasificacion_balance = "PASIVO_CORRIENTE"

                elif codigo.startswith("45"):
                    clasificacion_balance = "PASIVO_NO_CORRIENTE"

            elif tipo == "PATRIMONIO":

                clasificacion_balance = "PATRIMONIO"

            # ====================================================
            # CREAR / ACTUALIZAR CUENTA
            # ====================================================

            CuentaContable.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "codigo_pcge": codigo_pcge,
                    "cuenta_padre": cuenta_padre,
                    "tipo": tipo,
                    "naturaleza": naturaleza,
                    "estado_financiero": eeff,
                    "clasificacion_balance": clasificacion_balance,
                    "nivel": nivel,
                    "acepta_movimientos": acepta_movimientos,
                    "activo": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "✓ Cuentas contables cargadas"
            )
        )

        # ====================================================
        # 4. CONCEPTOS OPERATIVOS
        # ====================================================

        ADM = CentroCosto.objects.get(codigo="ADM")
        COM = CentroCosto.objects.get(codigo="COM")
        OPT = CentroCosto.objects.get(codigo="OPT")
        TAL = CentroCosto.objects.get(codigo="TAL")

        def categoria(codigo):
            if not codigo:
                return None
            return CategoriaGerencial.objects.get(codigo=codigo)

        def cuenta(codigo):
            return CuentaContable.objects.get(codigo=codigo)        # ----------------------------------------------------
        # GRUPOS PRINCIPALES
        # ----------------------------------------------------

        grupos = [
            ("GRP-ADM", "Administración", None),
            ("GRP-COM", "Comercial / Ventas", None),
            ("GRP-OPT", "Optometría", None),
            ("GRP-TAL", "Taller", None),

            ("GRP-ADM-OFI", "Oficina y suministros", "GRP-ADM"),
            ("GRP-ADM-MAN", "Mantenimiento", "GRP-ADM"),
            ("GRP-ADM-LIC", "Licencias y permisos", "GRP-ADM"),
            ("GRP-ADM-SIS", "Software y sistemas", "GRP-ADM"),
            ("GRP-ADM-PRO", "Servicios profesionales", "GRP-ADM"),
            ("GRP-ADM-PER", "Personal administrativo", "GRP-ADM"),
            ("GRP-ADM-SER", "Servicios administrativos", "GRP-ADM"),
            ("GRP-ADM-BIE", "Bienestar, botiquín y SST", "GRP-ADM"),

            ("GRP-COM-PER", "Personal comercial", "GRP-COM"),
            ("GRP-COM-MKT", "Marketing e imagen", "GRP-COM"),
            ("GRP-COM-ATE", "Atención al cliente", "GRP-COM"),
            ("GRP-COM-DEL", "Distribución y delivery", "GRP-COM"),

            ("GRP-OPT-PER", "Personal de optometría", "GRP-OPT"),
            ("GRP-TAL-PER", "Personal de taller", "GRP-TAL"),

            (
                "GRP-TAL-TER",
                "Procesos ópticos tercerizados",
                "GRP-TAL",
            ),

            (
                "GRP-TAL-INS",
                "Insumos de taller",
                "GRP-TAL",
            ),

            (
                "GRP-OPT-GAR",
                "Garantías de optometría",
                "GRP-OPT",
            ),

            ("GRP-ACT", "Activos fijos e intangibles", None),
            ("GRP-ACT-EQUIP", "Equipos y mobiliario", "GRP-ACT"),
            ("GRP-ACT-INT", "Intangibles", "GRP-ACT"),
        ]

        for codigo, nombre, padre_codigo in grupos:

            padre = None

            if padre_codigo:
                padre = ConceptoOperacion.objects.get(
                    codigo=padre_codigo
                )

            ConceptoOperacion.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "concepto_padre": padre,
                    "es_grupo": True,
                    "tipo_operacion": "OTRO",
                    "activo": True,
                },
            )

        # ----------------------------------------------------
        # CONCEPTOS FINALES
        # ----------------------------------------------------
        #
        # codigo
        # nombre
        # grupo padre
        # cuenta
        # categoría
        # centro
        # palabras clave
        # sinónimos
        # tipo
        #

        conceptos = [

            # ================================================
            # ADMINISTRACIÓN - PERSONAL Y SERVICIOS GENERALES
            # ================================================

            (
                "ADM-PER-SUELDO",
                "Sueldos - Administración",
                "GRP-ADM-PER",
                "62102",
                "92100",
                ADM,
                "sueldo, remuneracion, administracion, planilla",
                "sueldo administrativo, remuneración administración",
                "GASTO",
                False, False, False, True, False,
            ),

            (
                "ADM-PER-LIQ",
                "Liquidaciones y beneficios sociales",
                "GRP-ADM-PER",
                "62106",
                "92100",
                ADM,
                "liquidacion, beneficios sociales, cese, gratificacion, vacaciones",
                "liquidación trabajador, beneficios laborales",
                "GASTO",
                False, False, False, False, True,
            ),

            (
                "ADM-SER-ALQ",
                "Alquiler del local",
                "GRP-ADM-SER",
                "63101",
                "92200",
                ADM,
                "alquiler, arrendamiento, renta, local, tienda",
                "alquiler local, renta local, arrendamiento del local",
                "GASTO",
                True, False, True, True, False,
            ),

            (
                "ADM-SER-BAS",
                "Servicios básicos",
                "GRP-ADM-SER",
                "63102",
                "92200",
                ADM,
                "luz, agua, electricidad, telefono, internet, servicios basicos",
                "energía eléctrica, agua, teléfono, internet",
                "GASTO",
                True, False, True, True, False,
            ),

            (
                "ADM-SER-SEG",
                "Seguridad",
                "GRP-ADM-SER",
                "63103",
                "92200",
                ADM,
                "seguridad, vigilancia, alarma, monitoreo",
                "vigilancia, servicio de seguridad",
                "GASTO",
                True, False, True, True, False,
            ),

            (
                "ADM-SER-LIMP",
                "Servicios de limpieza",
                "GRP-ADM-SER",
                "63108",
                "92200",
                ADM,
                "limpieza, servicio limpieza, aseo",
                "servicio de limpieza",
                "GASTO",
                True, False, True, False, True,
            ),

            (
                "ADM-BIE-BOT",
                "Botiquín y primeros auxilios",
                "GRP-ADM-BIE",
                "65103",
                "92500",
                ADM,
                "botiquin, primeros auxilios, medicina basica",
                "botiquín",
                "GASTO",
                True, False, False, False, True,
            ),

            (
                "ADM-BIE-SST",
                "Seguridad y salud en el trabajo",
                "GRP-ADM-BIE",
                "65104",
                "92500",
                ADM,
                "sst, seguridad trabajo, salud ocupacional",
                "seguridad y salud ocupacional",
                "GASTO",
                True, False, False, False, True,
            ),

            (
                "ADM-BIE-BIEN",
                "Bienestar e integración del personal",
                "GRP-ADM-BIE",
                "65105",
                "92500",
                ADM,
                "bienestar, integracion, personal, cumpleaños",
                "actividad de integración",
                "GASTO",
                True, False, False, False, True,
            ),

            (
                "ADM-SER-SEGUR",
                "Seguros",
                "GRP-ADM-SER",
                "65114",
                "92900",
                ADM,
                "seguro, poliza, prima",
                "póliza de seguro",
                "GASTO",
                True, False, True, True, False,
            ),

            (
                "ADM-SER-CAP",
                "Capacitación",
                "GRP-ADM-SER",
                "65115",
                "92900",
                ADM,
                "capacitacion, curso, taller, formacion",
                "curso, capacitación del personal",
                "GASTO",
                True, False, False, False, True,
            ),

            (
                "ADM-SER-MOV",
                "Movilidad y viáticos",
                "GRP-ADM-SER",
                "65116",
                "92900",
                ADM,
                "movilidad, taxi, pasaje, viatico, transporte",
                "taxi, pasajes, viáticos",
                "GASTO",
                False, False, False, False, True,
            ),

            (
                "ADM-SER-FUM",
                "Fumigación y saneamiento",
                "GRP-ADM-SER",
                "63117",
                "92900",
                ADM,
                "fumigacion, saneamiento, desinfeccion, control plagas",
                "fumigación del local",
                "GASTO",
                True, False, True, False, True,
            ),

            (
                "ADM-SER-MULTA",
                "Multas, sanciones y penalidades",
                "GRP-ADM-SER",
                "65119",
                "92900",
                ADM,
                "multa, sancion, penalidad",
                "multa administrativa",
                "GASTO",
                False, False, True, False, True,
            ),

            # ================================================
            # ADMINISTRACIÓN - OFICINA
            # ================================================

            (
                "ADM-OFI-PAPEL",
                "Hojas de papel",
                "GRP-ADM-OFI",
                "65101",
                "92300",
                ADM,
                "papel, hojas, bond, resma, a4, oficina",
                "papel bond, resma, hojas A4",
                "GASTO",
            ),

            (
                "ADM-OFI-TALON",
                "Talonarios",
                "GRP-ADM-OFI",
                "65101",
                "92300",
                ADM,
                "talonario, comprobante, recibo, papel",
                "talonarios",
                "GASTO",
            ),

            (
                "ADM-OFI-TINTA",
                "Tintas y tóner",
                "GRP-ADM-OFI",
                "65101",
                "92300",
                ADM,
                "tinta, toner, impresora, cartucho",
                "tóner, cartucho impresora",
                "GASTO",
            ),

            (
                "ADM-OFI-PILAS",
                "Pilas y baterías menores",
                "GRP-ADM-OFI",
                "65101",
                "92300",
                ADM,
                "pilas, bateria, baterias",
                "pilas",
                "GASTO",
            ),

            (
                "ADM-OFI-UTILES",
                "Útiles de oficina",
                "GRP-ADM-OFI",
                "65101",
                "92300",
                ADM,
                "lapiceros, folders, archivadores, sobres, útiles",
                "utiles oficina",
                "GASTO",
            ),

            (
                "ADM-OFI-LIMP",
                "Artículos de limpieza",
                "GRP-ADM-OFI",
                "65102",
                "92300",
                ADM,
                "articulos limpieza, detergente, lejia, papel higienico, aseo",
                "productos de limpieza",
                "GASTO",
                True, False, False, False, True,
            ),

            (
                "ADM-OFI-EQMEN",
                "Accesorios y equipos menores no capitalizables",
                "GRP-ADM-OFI",
                "65120",
                "92300",
                ADM,
                "equipo menor, accesorio, adaptador, cable, herramienta menor",
                "equipos menores, accesorios de oficina",
                "GASTO",
                True, False, False, False, True,
            ),

            # ================================================
            # ADMINISTRACIÓN - LICENCIAS
            # ================================================

            (
                "ADM-LIC-FUNC",
                "Licencia de funcionamiento",
                "GRP-ADM-LIC",
                "63109",
                "92600",
                ADM,
                "licencia, municipalidad, funcionamiento",
                "licencia municipal",
                "GASTO",
            ),

            (
                "ADM-LIC-ACT",
                "Actualización o renovación de licencia",
                "GRP-ADM-LIC",
                "63109",
                "92600",
                ADM,
                "renovacion, actualización, licencia",
                "actualizar licencia",
                "GASTO",
            ),

            (
                "ADM-POZO",
                "Pozo a tierra - medición o certificado",
                "GRP-ADM-LIC",
                "63110",
                "92600",
                ADM,
                "pozo tierra, certificado, telurometro, medicion",
                "pozo a tierra, certificado pozo tierra",
                "GASTO",
            ),

            (
                "ADM-ITSE",
                "ITSE / Inspección de seguridad",
                "GRP-ADM-LIC",
                "63110",
                "92600",
                ADM,
                "itse, defensa civil, inspeccion seguridad",
                "certificado itse",
                "GASTO",
            ),

            # ================================================
            # SOFTWARE
            # ================================================

            (
                "ADM-SIS-SOFT",
                "Software y suscripciones",
                "GRP-ADM-SIS",
                "63111",
                "92700",
                ADM,
                "software, licencia software, suscripcion, app",
                "programa, aplicación",
                "GASTO",
            ),

            (
                "ADM-SIS-DES",
                "Desarrollo y mantenimiento de sistemas",
                "GRP-ADM-SIS",
                "63112",
                "92700",
                ADM,
                "django, programación, desarrollo, sistema, mantenimiento",
                "programador, desarrollo web",
                "GASTO",
            ),

            (
                "ADM-SIS-HOST",
                "Hosting / Heroku / Cloud",
                "GRP-ADM-SIS",
                "63113",
                "92700",
                ADM,
                "hosting, heroku, cloud, servidor",
                "servidor web",
                "GASTO",
            ),

            (
                "ADM-SIS-DOM",
                "Dominio web",
                "GRP-ADM-SIS",
                "63113",
                "92700",
                ADM,
                "dominio, web, cloudflare",
                "dominio internet",
                "GASTO",
            ),

            (
                "ADM-SIS-CORREO",
                "Correo corporativo",
                "GRP-ADM-SIS",
                "63113",
                "92700",
                ADM,
                "correo, email, corporativo, microsoft, google",
                "correo empresa",
                "GASTO",
            ),

            # ================================================
            # SERVICIOS PROFESIONALES
            # ================================================

            (
                "ADM-PRO-CONT",
                "Contabilidad externa",
                "GRP-ADM-PRO",
                "63114",
                "92800",
                ADM,
                "contador, contabilidad, honorarios",
                "servicio contable",
                "GASTO",
            ),

            (
                "ADM-PRO-LEGAL",
                "Asesoría legal",
                "GRP-ADM-PRO",
                "63114",
                "92800",
                ADM,
                "abogado, legal, asesoria",
                "honorarios abogado",
                "GASTO",
            ),

            (
                "ADM-PRO-NOT",
                "Notaría y registros",
                "GRP-ADM-PRO",
                "63115",
                "92800",
                ADM,
                "notaria, sunarp, registros",
                "notarial, registro público",
                "GASTO",
            ),

            # ================================================
            # MANTENIMIENTO
            # ================================================

            (
                "ADM-MAN-LOCAL",
                "Arreglo o mantenimiento del local",
                "GRP-ADM-MAN",
                "63104",
                "92400",
                ADM,
                "arreglo local, mantenimiento local, reparación local",
                "reparacion tienda",
                "GASTO",
            ),

            (
                "TAL-MAN-BIS",
                "Mantenimiento de biseladora",
                "GRP-TAL",
                "63104",
                "92400",
                TAL,
                "biseladora, mantenimiento, reparación",
                "servicio biseladora",
                "GASTO",
            ),

            # ================================================
            # TALLER - TERCERIZADOS
            # ================================================

            (
                "TAL-TER-BIS",
                "Biselado externo",
                "GRP-TAL-TER",
                "63301",
                "91301",
                TAL,
                "biselado, externo, tercerizado",
                "biselar afuera",
                "GASTO",
            ),

            (
                "TAL-TER-COL",
                "Coloreado",
                "GRP-TAL-TER",
                "63302",
                "91302",
                TAL,
                "coloreado, colorear, tintado",
                "color de lunas",
                "GASTO",
            ),

            (
                "TAL-TER-SOL",
                "Soldadura",
                "GRP-TAL-TER",
                "63303",
                "91303",
                TAL,
                "soldadura, reparar montura",
                "soldar",
                "GASTO",
            ),

            (
                "TAL-TER-FLEX",
                "Cambio de Flex",
                "GRP-TAL-TER",
                "63304",
                "91304",
                TAL,
                "flex, patilla, cambio, reparación",
                "cambiar flex",
                "GASTO",
            ),

            (
                "OPT-TER-MEDIDA",
                "Medida de vista tercerizada",
                "GRP-TAL-TER",
                "63901",
                "91305",
                OPT,
                "medida vista, refracción, optometra externa",
                "examen vista externo",
                "GASTO",
            ),

            # ================================================
            # TALLER - INSUMOS
            # ================================================

            (
                "TAL-INS-PEG",
                "Pegatinas",
                "GRP-TAL-INS",
                "65111",
                "91200",
                TAL,
                "pegatinas, sticker, taller",
                "pegatina",
                "GASTO",
            ),

            (
                "TAL-INS-TOR",
                "Tornillos",
                "GRP-TAL-INS",
                "65111",
                "91200",
                TAL,
                "tornillo, tornillos, montura",
                "",
                "GASTO",
            ),

            (
                "TAL-INS-PLA",
                "Plaquetas",
                "GRP-TAL-INS",
                "65111",
                "91200",
                TAL,
                "plaqueta, plaquetas, nariz",
                "",
                "GASTO",
            ),

            (
                "TAL-INS-TOP",
                "Topes",
                "GRP-TAL-INS",
                "65111",
                "91200",
                TAL,
                "tope, topes, taller",
                "",
                "GASTO",
            ),

            # ================================================
            # GARANTÍAS
            # ================================================

            (
                "TAL-GAR-ERR",
                "Garantía - Error de taller",
                "GRP-TAL",
                "65112",
                "91401",
                TAL,
                "error taller, garantia, reposicion, luna rota",
                "falla taller",
                "GASTO",
            ),

            (
                "OPT-GAR-MED",
                "Garantía - Error de medida de vista",
                "GRP-OPT-GAR",
                "65112",
                "91402",
                OPT,
                "error medida, garantia, optometra, reposicion lunas",
                "medida equivocada",
                "GASTO",
            ),

            (
                "TAL-GAR-MONT",
                "Garantía - Defecto de montura",
                "GRP-TAL",
                "65112",
                "91403",
                TAL,
                "garantia, defecto montura, reposicion montura",
                "montura defectuosa",
                "GASTO",
            ),

            (
                "TAL-GAR-LUNA",
                "Garantía - Defecto de lunas",
                "GRP-TAL",
                "65112",
                "91404",
                TAL,
                "garantia, defecto lunas, reposicion lunas",
                "lunas defectuosas",
                "GASTO",
            ),

            (
                "OPT-GAR-ADAP",
                "Garantía - Adaptación",
                "GRP-OPT-GAR",
                "65112",
                "91405",
                OPT,
                "garantia, adaptacion, cambio lunas",
                "problema de adaptación",
                "GASTO",
            ),

            (
                "TAL-TER-OTR",
                "Otros procesos ópticos tercerizados",
                "GRP-TAL-TER",
                "63309",
                "91399",
                TAL,
                "proceso optico, tercerizado, externo",
                "otros trabajos externos",
                "GASTO",
            ),

            # ================================================
            # PERSONAL DE TALLER Y OPTOMETRÍA
            # ================================================

            (
                "TAL-PER-BIS",
                "Remuneración biselador",
                "GRP-TAL-PER",
                "62101",
                "91200",
                TAL,
                "biselador, sueldo, remuneracion, taller",
                "sueldo biselador",
                "GASTO",
                False, False, False, True, False,
            ),

            (
                "OPT-PER-OPT",
                "Remuneración optómetra",
                "GRP-OPT-PER",
                "62104",
                "93200",
                OPT,
                "optometra, sueldo, remuneracion, optometria",
                "sueldo optómetra",
                "GASTO",
                False, False, False, True, False,
            ),

            (
                "OPT-MAT-REC",
                "Recetarios y material de optometría",
                "GRP-OPT",
                "65113",
                "93200",
                OPT,
                "recetario, optometria, material optometrico",
                "recetas, material de optometría",
                "GASTO",
                True, False, False, False, True,
            ),

            # ================================================
            # COMERCIAL
            # ================================================

            (
                "COM-PER-SUELDO",
                "Sueldos - Ventas",
                "GRP-COM-PER",
                "62103",
                "93100",
                COM,
                "sueldo, vendedor, ventas, remuneracion",
                "sueldo vendedores",
                "GASTO",
                False, False, False, True, False,
            ),

            (
                "COM-PER-COM",
                "Comisiones por ventas",
                "GRP-COM-PER",
                "62105",
                "93100",
                COM,
                "comision venta, vendedor, incentivo",
                "comisiones vendedores",
                "GASTO",
                False, False, False, False, True,
            ),

            (
                "COM-MKT-PUB",
                "Publicidad y marketing",
                "GRP-COM-MKT",
                "63106",
                "93500",
                COM,
                "facebook, instagram, meta, publicidad, marketing",
                "meta ads, facebook ads",
                "GASTO",
            ),

            (
                "COM-MKT-UNI",
                "Uniformes",
                "GRP-COM-MKT",
                "65108",
                "93500",
                COM,
                "uniforme, ropa, personal",
                "uniformes personal",
                "GASTO",
            ),

            (
                "COM-MKT-REG",
                "Regalos y obsequios promocionales",
                "GRP-COM-MKT",
                "65109",
                "93500",
                COM,
                "regalo, obsequio, campaña, madre, padre",
                "regalos clientes",
                "GASTO",
            ),

            (
                "COM-ATE-BOL",
                "Bolsas de papel o plástico",
                "GRP-COM-ATE",
                "65106",
                "93300",
                COM,
                "bolsa, bolsas, papel, plastico, empaque",
                "bolsa cliente",
                "GASTO",
            ),

            (
                "COM-ATE-PANO",
                "Paños de microfibra",
                "GRP-COM-ATE",
                "65107",
                "93300",
                COM,
                "paño, microfibra, limpiar lentes",
                "pañito",
                "GASTO",
            ),

            (
                "COM-ATE-LIQ",
                "Líquidos entregados gratuitamente",
                "GRP-COM-ATE",
                "65110",
                "93300",
                COM,
                "liquido gratis, obsequio liquido",
                "líquido de cortesía",
                "GASTO",
            ),

            (
                "COM-DEL",
                "Delivery a clientes",
                "GRP-COM-DEL",
                "63105",
                "93400",
                COM,
                "delivery, motorizado, envío, courier",
                "envio cliente",
                "GASTO",
            ),

            (
                "COM-POS",
                "Comisión POS / pasarela de pago",
                "GRP-COM",
                "63116",
                "93600",
                COM,
                "pos, izipay, niubiz, visa, mastercard, comisión",
                "comision tarjeta",
                "GASTO",
            ),

            (
                "COM-ATE-CORT",
                "Atención y cortesías a clientes",
                "GRP-COM-ATE",
                "65117",
                "93300",
                COM,
                "cortesia, cliente, atencion, agua, cafe, detalle",
                "atención clientes, cortesías",
                "GASTO",
                True, False, False, False, True,
            ),

            (
                "COM-MKT-DEC",
                "Decoración y ambientación",
                "GRP-COM-MKT",
                "65118",
                "93500",
                COM,
                "decoracion, ambientacion, vitrina, campaña",
                "decoración local, ambientación",
                "GASTO",
                True, False, False, False, True,
            ),

            # ================================================
            # FINANCIERO
            # ================================================

            (
                "FIN-INT-PRES",
                "Intereses de préstamos",
                "GRP-ADM",
                "67101",
                "94100",
                ADM,
                "interes, préstamo, banco, financiamiento",
                "intereses deuda",
                "GASTO",
            ),

            (
                "FIN-COM-BAN",
                "Comisiones y gastos bancarios",
                "GRP-ADM",
                "67106",
                "94200",
                ADM,
                "banco, comisión bancaria, mantenimiento cuenta",
                "gasto bancario",
                "GASTO",
            ),

            # ================================================
            # ACTIVOS FIJOS E INTANGIBLES
            # ================================================

            ("ACT-COMP", "Compra de computadora", "GRP-ACT-EQUIP", "33601", None, ADM, "computadora, laptop, pc", "equipo de cómputo", "ACTIVO", True, False, True, True, False),
            ("ACT-IMP", "Compra de impresora", "GRP-ACT-EQUIP", "33602", None, ADM, "impresora, printer", "impresora", "ACTIVO", True, False, True, True, False),
            ("ACT-POS", "Compra de equipo POS", "GRP-ACT-EQUIP", "33603", None, COM, "pos, terminal pago", "equipo POS", "ACTIVO", True, False, True, True, False),
            ("ACT-CAM", "Compra de cámara de video", "GRP-ACT-EQUIP", "33604", None, ADM, "camara, video, seguridad", "cámara de seguridad", "ACTIVO", True, False, True, True, False),
            ("ACT-BIS", "Compra de biseladora", "GRP-ACT-EQUIP", "33605", None, TAL, "biseladora, maquina biselado", "biseladora", "ACTIVO", True, False, True, True, False),
            ("ACT-AUTO", "Compra de autorrefractómetro", "GRP-ACT-EQUIP", "33606", None, OPT, "autorrefractometro, refraccion", "autorrefractómetro", "ACTIVO", True, False, True, True, False),
            ("ACT-CAJA-PRUEBA", "Compra de caja de pruebas", "GRP-ACT-EQUIP", "33607", None, OPT, "caja pruebas, lunas prueba", "caja de pruebas", "ACTIVO", True, False, True, True, False),
            ("ACT-MOB", "Compra de mobiliario", "GRP-ACT-EQUIP", "33608", None, ADM, "mueble, escritorio, silla, vitrina, mobiliario", "mobiliario", "ACTIVO", True, False, True, True, False),
            ("ACT-RAN", "Compra de ranuradora", "GRP-ACT-EQUIP", "33609", None, TAL, "ranuradora, taller", "ranuradora", "ACTIVO", True, False, True, True, False),
            ("ACT-CAL", "Compra de calentadora", "GRP-ACT-EQUIP", "33610", None, TAL, "calentadora, taller", "calentadora", "ACTIVO", True, False, True, True, False),
            ("ACT-PUL", "Compra de pulidora", "GRP-ACT-EQUIP", "33611", None, TAL, "pulidora, taller", "pulidora", "ACTIVO", True, False, True, True, False),
            ("ACT-FOR", "Compra de foróptero", "GRP-ACT-EQUIP", "33612", None, OPT, "foroptero, optometria", "foróptero", "ACTIVO", True, False, True, True, False),
            ("ACT-EQ-OPT", "Compra de otro equipo óptico", "GRP-ACT-EQUIP", "33613", None, OPT, "equipo optico, optometria", "otro equipo óptico", "ACTIVO", True, False, True, True, False),
            ("ACT-EQ-OTR", "Compra de otro equipo diverso", "GRP-ACT-EQUIP", "33699", None, ADM, "equipo diverso, activo fijo", "otro equipo", "ACTIVO", True, False, True, True, False),
            ("ACT-SOFT", "Software adquirido capitalizable", "GRP-ACT-INT", "34101", None, ADM, "software capitalizable, licencia perpetua", "software adquirido", "ACTIVO", True, False, True, True, False),
            ("ACT-DES-SIS", "Desarrollo de sistemas capitalizable", "GRP-ACT-INT", "34102", None, ADM, "desarrollo sistema capitalizable, software propio", "desarrollo de sistemas", "ACTIVO", True, False, True, True, False),
        ]

        for item in conceptos:

            (
                codigo,
                nombre,
                padre_codigo,
                cuenta_codigo,
                categoria_codigo,
                centro,
                palabras_clave,
                sinonimos,
                tipo_operacion,
            ) = item[:9]

            # Campos opcionales por concepto.
            # Si no se especifican, se conservan los valores V1 por defecto.
            requiere_proveedor = item[9] if len(item) > 9 else True
            requiere_cliente = item[10] if len(item) > 10 else False
            requiere_comprobante = item[11] if len(item) > 11 else False
            es_fijo = item[12] if len(item) > 12 else False
            es_variable = item[13] if len(item) > 13 else True

            padre = ConceptoOperacion.objects.get(
                codigo=padre_codigo
            )

            ConceptoOperacion.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "concepto_padre": padre,
                    "es_grupo": False,
                    "tipo_operacion": tipo_operacion,
                    "cuenta_contable": cuenta(cuenta_codigo),
                    "categoria_gerencial": categoria(
                        categoria_codigo
                    ),
                    "centro_costo": centro,
                    "palabras_clave": palabras_clave,
                    "sinonimos": sinonimos,
                    "requiere_proveedor": requiere_proveedor,
                    "requiere_cliente": requiere_cliente,
                    "requiere_comprobante": requiere_comprobante,
                    "requiere_centro_costo": False,
                    "permite_cambiar_cuenta": False,
                    "es_fijo": es_fijo,
                    "es_variable": es_variable,
                    "activo": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "✓ Conceptos operativos cargados"
            )
        )

        # ====================================================
        # RESUMEN
        # ====================================================

        self.stdout.write("\n-------------------------------------")
        self.stdout.write(
            self.style.SUCCESS(
                "PLAN CONTABLE CARGADO CORRECTAMENTE"
            )
        )
        self.stdout.write("-------------------------------------")

        self.stdout.write(
            f"Cuentas contables: "
            f"{CuentaContable.objects.count()}"
        )

        self.stdout.write(
            f"Categorías gerenciales: "
            f"{CategoriaGerencial.objects.count()}"
        )

        self.stdout.write(
            f"Centros de costo: "
            f"{CentroCosto.objects.count()}"
        )

        self.stdout.write(
            f"Conceptos operativos totales: "
            f"{ConceptoOperacion.objects.count()}"
        )

        self.stdout.write(
            f"Conceptos seleccionables: "
            f"{ConceptoOperacion.objects.filter(es_grupo=False, activo=True).count()}"
        )

        self.stdout.write("-------------------------------------\n")