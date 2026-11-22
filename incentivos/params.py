"""
Parámetros de Puntos IC con sus valores iniciales.

Los valores se cambian desde la pantalla /incentivos/configuracion/
(se guarda una fila nueva con fecha de vigencia; nunca se borra la anterior).
Si un parámetro no existe en la base, se usa el valor por defecto de aquí.
"""
from datetime import time
from decimal import Decimal


# clave: (valor por defecto, tipo, descripción)
DEFAULTS = {
    # Meta diaria
    "META_BASE": ("50", "dec", "Meta base de puntos (lunes a viernes y domingo)"),
    "META_BASE_SABADO": ("20", "dec", "Meta base del sábado"),
    "META_POR_TICKET": ("7", "dec", "Puntos que se descuentan de la meta por cada ticket del día"),
    "META_MINIMA": ("10", "dec", "Meta mínima del día"),
    # Pago
    "PAGO_PUNTO_NORMAL": ("0.25", "dec", "S/ por punto hasta la suma de metas del mes"),
    "PAGO_PUNTO_ALTO": ("0.40", "dec", "S/ por punto por encima de la suma de metas"),
    "PAGO_TOPE": ("450", "dec", "Tope de pago por persona y mes (S/)"),
    # Requisitos
    "REQ_DIAS_CUMPLIDOS_PCT": ("90", "dec", "% mínimo de días cumplidos sobre días trabajados"),
    "REQ_FOTOS_MIN": ("80", "int", "Monturas publicadas y aprobadas por mes (si aún hay monturas sin fotos)"),
    "REQ_TICKETS_ACTIVO": ("1", "bool", "Exigir un mínimo de ventas (tickets) por vendedor en el mes"),
    "REQ_TICKETS_MIN": ("78", "int", "Tickets mínimos por vendedor en el mes"),
    "REQ_TICKETS_MONTO": ("100", "dec", "Solo cuentan tickets por más de este monto (S/)"),
    "REQ_VENTA_ACTIVO": ("0", "bool", "Exigir venta de la tienda mayor que el mismo mes del año anterior"),
    "REQ_CAJA_ACTIVO": ("0", "bool", "Exigir caja sin diferencias sin justificar"),
    "REQ_LISTO_ACTIVO": ("0", "bool", "Exigir órdenes con etapa Listo registrada"),
    "REQ_CAJA_TOLERANCIA": ("0.00", "dec", "Diferencia de caja (S/) que se tolera sin justificar"),
    "REQ_LISTO_PCT": ("90", "dec", "% mínimo de órdenes del trabajador con etapa Listo registrada"),
    "REQ_ENTREGAS_ACTIVO": ("0", "bool", "Exigir entregas a tiempo"),
    "REQ_ENTREGAS_PCT": ("75", "dec", "% mínimo de órdenes listas a la hora prometida (POR CONFIRMAR)"),
    # Puntualidad
    "TOLERANCIA_MIN": ("0", "int", "Minutos de tolerancia en la entrada"),
    "PTS_A_TIEMPO": ("1", "dec", "Puntos por entrar a tiempo"),
    "PTS_TARDE_1_5": ("-1", "dec", "Tardanza de 1 a 5 minutos"),
    "PTS_TARDE_6_15": ("-3", "dec", "Tardanza de 6 a 15 minutos"),
    "PTS_TARDE_MAS_15": ("-5", "dec", "Tardanza de más de 15 minutos (el día no cuenta como cumplido)"),
    "PTS_REFRIGERIO_TARDE": ("-2", "dec", "Regreso tarde del refrigerio"),
    "REFRIGERIO_TOLERANCIA_MIN": ("5", "int", "Minutos de tolerancia al volver del refrigerio"),
    "PTS_FALTA": ("-10", "dec", "Falta injustificada"),
    "PTS_MES_SIN_TARDANZAS": ("5", "dec", "Bonus al cierre por mes completo sin tardanzas ni faltas"),
    # Cola
    "ABANDONO_FACTOR": ("3", "dec", "Una tarea en curso vuelve a la cola si supera N veces sus minutos estándar"),
    "FOTO_PRECIO_MARCA": ("190", "dec", "Precio desde el cual una montura es 'de marca' (sale primero)"),
    "WA_RESP_MINUTOS": ("30", "int", "Minutos para responder a un cliente y ganar puntos"),
    "WA_ENVIOS_MIN_DIA": ("20", "int", "Renovaciones + reactivaciones mínimas al día para dar por enviada la lista"),
    "INV_EXHIBIDORES": (
        "Vitrina 1,Vitrina 2,Vitrina 3,Vitrina 4,Exhibidor pared 1,Exhibidor pared 2,Solares,Depósito",
        "list", "Exhibidores que se cuentan (separados por coma)",
    ),
    "INV_FRECUENCIA_DIAS": ("30", "int", "Cada cuántos días se vuelve a contar un exhibidor"),
    "INV_UNIDAD": ("montura", "str", "Unidad del conteo (POR CONFIRMAR: montura o bandeja)"),
    "TEL_LOTE": ("10", "int", "Clientes por tarea de teléfonos"),
    "TEL_LOTES_ABIERTOS": ("3", "int", "Máximo de lotes de teléfonos abiertos a la vez"),
    # Asistencia
    "IPS_TIENDA": ("", "list", "IPs públicas del local permitidas para marcar (opcional, separadas por coma)"),
    "SABADO_ENTRADA": ("09:00", "time", "Entrada del sábado"),
    "SABADO_SALIDA": ("19:45", "time", "Salida del sábado"),
    "SABADO_REFRIGERIO": ("60", "int", "Minutos de refrigerio el sábado"),
    "DOMINGO_ENTRADA": ("10:30", "time", "Entrada del domingo"),
    "DOMINGO_SALIDA": ("18:00", "time", "Salida del domingo"),
    "DOMINGO_REFRIGERIO": ("0", "int", "Minutos de refrigerio el domingo"),
    "LV_REFRIGERIO": ("60", "int", "Minutos de refrigerio de lunes a viernes"),
    # Bono del equipo por venta del mes
    "BONO_T1_VENTA": ("50000", "dec", "Bono de ventas: venta del mes para el tramo 1 (S/)"),
    "BONO_T1_MONTO": ("1000", "dec", "Tramo 1: monto en partes iguales (S/)"),
    "BONO_T2_VENTA": ("55000", "dec", "Tramo 2: venta del mes (S/)"),
    "BONO_T2_ADICIONAL": ("300", "dec", "Tramo 2: adicional repartido por puntos de venta (S/)"),
    "BONO_T3_VENTA": ("65000", "dec", "Tramo 3: venta del mes (S/)"),
    "BONO_T3_ADICIONAL": ("1000", "dec", "Tramo 3: adicional repartido por puntos de venta (S/)"),
    "PV_MONTURA_MARCA": ("3", "dec", "Puntos de venta por montura de marca"),
    "PV_PRECIO_MARCA": ("190", "dec", "Precio desde el cual una montura cuenta como de marca (S/)"),
    "PV_MULTIFOCAL_DIGITAL": ("3", "dec", "Puntos de venta por par multifocal digital"),
    "PV_FOTO": ("1", "dec", "Puntos de venta por luna fotocromática o Foto + Blue"),
    "PV_FOTO_UNIDAD": ("luna", "str", "Fotocromáticas: 'luna' (un par = 2) o 'par' (un par = 1)"),
    "PV_TOPE_PCT": ("100", "dec", "Máximo % del adicional que puede llevarse una persona (100 = sin tope)"),
    # Alertas
    "ALERTA_WA_POR_HORA": ("20", "int", "Respuestas de WhatsApp por hora que generan alerta"),
    "ALERTA_FACTOR_PUNTOS": ("3", "dec", "Alerta si los puntos del día superan N veces el promedio"),
    # Cierre
    "CIERRE_BLOQUEA_PENDIENTES": ("1", "bool", "No cerrar el mes si hay tareas pendientes de revisión"),
    "INICIO_PROGRAMA": ("2026-12-01", "str", "Fecha de inicio de Puntos IC"),
}


def _convertir(valor, tipo):
    if tipo == "dec":
        return Decimal(str(valor).strip() or "0")
    if tipo == "int":
        return int(Decimal(str(valor).strip() or "0"))
    if tipo == "bool":
        return str(valor).strip().lower() in ("1", "si", "sí", "true", "yes")
    if tipo == "list":
        return [v.strip() for v in str(valor).split(",") if v.strip()]
    if tipo == "time":
        h, m = str(valor).strip().split(":")[:2]
        return time(int(h), int(m))
    return str(valor)


def valor_crudo(clave, fecha=None):
    from .models import ParametroIncentivo

    from .tiempo import hoy

    fecha = fecha or hoy()
    fila = (
        ParametroIncentivo.objects.filter(clave=clave, vigente_desde__lte=fecha)
        .order_by("-vigente_desde", "-id")
        .first()
    )
    if fila is not None:
        return fila.valor
    return DEFAULTS[clave][0]


def P(clave, fecha=None):
    """Valor del parámetro ya convertido a su tipo."""
    return _convertir(valor_crudo(clave, fecha), DEFAULTS[clave][1])
