"""
Lógica de Puntos IC: cola de tareas, libro de puntos, asistencia,
proceso diario, requisitos y cierre mensual.

Todas las funciones que escriben usan transacciones cortas y no tocan
tickets, detalles de venta ni kardex.
"""
import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Count, Max, Min, Q, Sum

from .models import (
    Alerta,
    Asistencia,
    CierreMensual,
    MovimientoPuntos,
    Tarea,
    TipoTarea,
    Trabajador,
    Turno,
)
from .params import P
from .tiempo import (
    a_lima,
    ahora,
    combinar,
    dias_del_mes,
    fecha_local,
    LIMA,
    hoy,
    mismo_mes_anio_anterior,
    primer_dia,
    rango_dia,
    ultimo_dia,
)

log = logging.getLogger(__name__)
User = get_user_model()

D0 = Decimal("0")
TICKET_SISTEMA_ANTIGUO = 1_000_000_000
MONTURAS = ("Monturas oftálmicas", "Monturas Solares", "Monturas de Marca")
CAMPOS_FICHA = ("marca", "material", "forma", "color", "talla_luna", "puente", "largo", "precio_venta")
GRUPO_GERENCIA = "Gerencia IC"


def q2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =====================================================================
# Usuarios
# =====================================================================

def es_gerencia(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or user.groups.filter(name=GRUPO_GERENCIA).exists()


def trabajador_de(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return Trabajador.objects.filter(usuario=user, participa=True).first()


def trabajadores():
    return list(Trabajador.objects.filter(participa=True).select_related("usuario"))


# =====================================================================
# Ventas (solo lectura)
# =====================================================================

def _filtro_sistema(anio):
    """Tickets del sistema nuevo desde 2026; antes, los del sistema antiguo."""
    if anio >= 2026:
        return Q(numero__lt=TICKET_SISTEMA_ANTIGUO)
    return Q(numero__gte=TICKET_SISTEMA_ANTIGUO)


def tickets_del_dia(nombre_vendedor, fecha):
    from core.models import TicketVenta

    return (
        TicketVenta.objects.filter(_filtro_sistema(fecha.year), fecha_emision=fecha,
                                   vendedor__iexact=nombre_vendedor.strip())
        .count()
    )


def tickets_mes(nombre_vendedor, periodo, hasta, monto_minimo):
    from core.models import TicketVenta

    return TicketVenta.objects.filter(
        _filtro_sistema(periodo.year), fecha_emision__gte=periodo, fecha_emision__lte=hasta,
        vendedor__iexact=nombre_vendedor.strip(), total__gt=monto_minimo,
    ).count()


def venta_vendedor(nombre_vendedor, periodo, hasta):
    """Suma del total de los tickets (con IGV) emitidos por el vendedor en el mes."""
    from core.models import TicketVenta

    return TicketVenta.objects.filter(
        _filtro_sistema(periodo.year), fecha_emision__gte=periodo, fecha_emision__lte=hasta,
        vendedor__iexact=nombre_vendedor.strip(),
    ).aggregate(s=Sum("total"))["s"] or D0


def venta_tienda(desde, hasta):
    from core.models import TicketVenta

    total = D0
    for anio in range(desde.year, hasta.year + 1):
        total += (
            TicketVenta.objects.filter(_filtro_sistema(anio), fecha_emision__gte=max(desde, date(anio, 1, 1)),
                                       fecha_emision__lte=min(hasta, date(anio, 12, 31)))
            .aggregate(s=Sum("total"))["s"] or D0
        )
    return total


# =====================================================================
# Libro de puntos
# =====================================================================

def mes_cerrado(fecha):
    return CierreMensual.objects.filter(periodo=primer_dia(fecha)).exists()


def registrar_movimiento(usuario, fecha, puntos, tipo, *, tarea=None, detalle="", clave=None,
                         creado_por=None, reversa_de=None):
    """Crea un movimiento. Si el mes de 'fecha' ya está cerrado, se carga a hoy."""
    puntos = q2(puntos)
    if mes_cerrado(fecha):
        detalle = f"{detalle} (de {fecha:%d/%m/%Y}, mes cerrado)".strip()
        fecha = hoy()
        while mes_cerrado(fecha):  # si se cerró antes de terminar el mes, pasa al siguiente mes abierto
            fecha = ultimo_dia(fecha) + timedelta(days=1)
    if clave:
        mov, creado = MovimientoPuntos.objects.get_or_create(
            clave=clave,
            defaults=dict(usuario=usuario, fecha=fecha, puntos=puntos, tipo=tipo, tarea=tarea,
                          detalle=detalle[:255], creado_por=creado_por, reversa_de=reversa_de),
        )
        return mov
    return MovimientoPuntos.objects.create(
        usuario=usuario, fecha=fecha, puntos=puntos, tipo=tipo, tarea=tarea,
        detalle=detalle[:255], creado_por=creado_por, reversa_de=reversa_de,
    )


def revertir_movimiento(mov, motivo, por=None):
    if mov.puntos == 0 or MovimientoPuntos.objects.filter(reversa_de=mov).exists():
        return None
    return registrar_movimiento(
        mov.usuario, mov.fecha, -mov.puntos, MovimientoPuntos.REVERSION,
        tarea=mov.tarea, detalle=f"Reversión: {motivo}", creado_por=por, reversa_de=mov,
    )


def revertir_tarea(tarea, motivo, por=None):
    n = 0
    for mov in tarea.movimientos.filter(reversa_de__isnull=True).exclude(tipo=MovimientoPuntos.REVERSION):
        if revertir_movimiento(mov, motivo, por):
            n += 1
    return n


def puntos_usuario(usuario, desde, hasta):
    return MovimientoPuntos.suma(usuario=usuario, fecha__gte=desde, fecha__lte=hasta)


# =====================================================================
# Generación de tareas
# =====================================================================

def tipo(codigo):
    return TipoTarea.objects.get(codigo=codigo)


def _vacio(campo):
    return Q(**{f"{campo}__isnull": True}) | Q(**{campo: ""})


def monturas_sin_fotos():
    from core.models import Producto

    return (
        Producto.objects.filter(tipo__in=MONTURAS, stock__gt=0)
        .exclude(activo=False)
        .filter(_vacio("imagenF") | _vacio("imagenD") | _vacio("imagenL"))
    )


def monturas_sin_ficha():
    from core.models import Producto

    q = Q()
    for c in CAMPOS_FICHA:
        q |= Q(**{f"{c}__isnull": True})
        if c != "precio_venta":
            q |= Q(**{c: ""})
    return Producto.objects.filter(tipo__in=MONTURAS, stock__gt=0).exclude(activo=False).filter(q)


def _generar_foto():
    t = tipo(TipoTarea.FOTO)
    if not t.activo:
        return 0
    precio_marca = P("FOTO_PRECIO_MARCA")
    sin_fotos = monturas_sin_fotos()
    ids_sin_fotos = set(sin_fotos.values_list("id", flat=True))
    # Quitar tareas pendientes que ya no hacen falta (fotos subidas por otra vía o sin stock)
    Tarea.objects.filter(tipo=t, estado=Tarea.PENDIENTE, inicio__isnull=True).exclude(
        producto_id__in=ids_sin_fotos).delete()
    con_tarea = set(
        Tarea.objects.filter(tipo=t, estado__in=[Tarea.PENDIENTE, Tarea.EN_CURSO, Tarea.TERMINADA])
        .values_list("producto_id", flat=True)
    )
    nuevas = []
    for p in sin_fotos.exclude(id__in=con_tarea).only("id", "precio_venta", "tipo", "nuevo"):
        if (p.precio_venta or 0) > precio_marca or p.tipo == "Monturas de Marca":
            prio = 10
        elif p.nuevo:
            prio = 20
        else:
            prio = 30
        nuevas.append(Tarea(tipo=t, producto_id=p.id, prioridad=prio))
    Tarea.objects.bulk_create(nuevas)
    return len(nuevas)


def _generar_cod():
    t = tipo(TipoTarea.COD)
    if not t.activo:
        return 0
    ids = set(monturas_sin_ficha().values_list("id", flat=True))
    Tarea.objects.filter(tipo=t, estado=Tarea.PENDIENTE, inicio__isnull=True).exclude(producto_id__in=ids).delete()
    con_tarea = set(Tarea.objects.filter(tipo=t, estado__in=Tarea.ABIERTAS).values_list("producto_id", flat=True))
    nuevas = [Tarea(tipo=t, producto_id=i, prioridad=20) for i in ids - con_tarea]
    Tarea.objects.bulk_create(nuevas)
    return len(nuevas)


def trabajadores_con_turno(fecha):
    ids = set(Turno.objects.filter(fecha=fecha).values_list("usuario_id", flat=True))
    return [t for t in trabajadores() if t.usuario_id in ids]


def _reasignar_wa_lista(fecha):
    """Si el asignado no marcó entrada 30 min después de su turno, la lista pasa a otro presente."""
    tarea = Tarea.objects.filter(tipo__codigo=TipoTarea.WA_LISTA, fecha_objetivo=fecha,
                                 estado=Tarea.PENDIENTE).select_related("asignada_a").first()
    if not tarea or not tarea.asignada_a_id:
        return 0
    if Asistencia.objects.filter(usuario=tarea.asignada_a, fecha=fecha, entrada__isnull=False).exists():
        return 0
    turno = Turno.objects.filter(usuario=tarea.asignada_a, fecha=fecha).first()
    if turno and ahora() < combinar(fecha, turno.hora_entrada) + timedelta(minutes=30):
        return 0
    presentes = [t for t in trabajadores() if Asistencia.objects.filter(
        usuario=t.usuario, fecha=fecha, entrada__isnull=False).exists()]
    if not presentes:
        return 0
    nuevo = presentes[fecha.toordinal() % len(presentes)]
    Tarea.objects.filter(pk=tarea.pk).update(asignada_a=nuevo.usuario)
    return 1


def puede_enviar_lista_wa(user, fecha=None):
    """
    Seguimiento WhatsApp: si hoy hay lista asignada en Puntos IC, solo la envía esa persona
    (y la gerencia o un ADMIN/SUPERVISOR). Sin tarea del día, todos pueden enviar.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if es_gerencia(user):
        return True
    rol = (getattr(getattr(user, "profile", None), "rol", "") or "").upper()
    if rol in ("ADMIN", "SUPERVISOR"):
        return True
    fecha = fecha or hoy()
    tarea = Tarea.objects.filter(tipo__codigo=TipoTarea.WA_LISTA, fecha_objetivo=fecha).first()
    if tarea is None or tarea.asignada_a_id is None:
        return True
    return tarea.asignada_a_id == user.pk


def _generar_wa_lista(fecha):
    t = tipo(TipoTarea.WA_LISTA)
    if not t.activo:
        return 0
    if Tarea.objects.filter(tipo=t, fecha_objetivo=fecha).exists():
        return _reasignar_wa_lista(fecha)
    candidatos = trabajadores_con_turno(fecha) or trabajadores()
    if not candidatos:
        return 0
    elegido = candidatos[fecha.toordinal() % len(candidatos)]
    Tarea.objects.create(tipo=t, fecha_objetivo=fecha, asignada_a=elegido.usuario, prioridad=1)
    return 1


def _ultimos9(numero):
    dig = re.sub(r"\D", "", numero or "")
    return dig[-9:]


def _variantes(numero):
    n9 = _ultimos9(numero)
    return {numero, n9, "51" + n9, "+51" + n9}


def _generar_wa_resp(fecha):
    from whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

    t = tipo(TipoTarea.WA_RESP)
    if not t.activo:
        return 0
    ini, fin = rango_dia(fecha)
    limite = ahora() - timedelta(minutes=2)  # da tiempo al bot a contestar
    ult_entrante = dict(
        MensajeWhatsApp.objects.filter(tipo="ENTRANTE", creado__gte=ini, creado__lt=fin)
        .values_list("numero").annotate(m=Max("creado")).values_list("numero", "m")
    )
    if not ult_entrante:
        return 0
    ult_saliente = {}
    for num, m in (MensajeWhatsApp.objects.filter(tipo="SALIENTE", creado__gte=ini, creado__lt=fin)
                   .values_list("numero").annotate(m=Max("creado")).values_list("numero", "m")):
        k = _ultimos9(num)
        ult_saliente[k] = max(m, ult_saliente.get(k, m))
    sin_respuesta = {}
    for num, m in ult_entrante.items():
        k = _ultimos9(num)
        if m <= limite and (k not in ult_saliente or ult_saliente[k] < m):
            sin_respuesta[k] = m
    # Tareas pendientes que alguien ya respondió sin tomar la tarea: se quitan
    for tarea in Tarea.objects.filter(tipo=t, estado=Tarea.PENDIENTE, inicio__isnull=True).select_related(
            "conversacion"):
        k = _ultimos9(tarea.conversacion.numero if tarea.conversacion else "")
        if k not in sin_respuesta:
            tarea.delete()
    abiertas = set(
        _ultimos9(n) for n in Tarea.objects.filter(tipo=t, estado__in=Tarea.ABIERTAS)
        .values_list("conversacion__numero", flat=True) if n
    )
    convs = {}
    buscar = set()
    for k in sin_respuesta:
        buscar |= _variantes(k)
    for c in ConversacionWhatsApp.objects.filter(numero__in=buscar).only("id", "numero"):
        convs.setdefault(_ultimos9(c.numero), c)
    creadas = 0
    for k, m in sin_respuesta.items():
        if k in abiertas or k not in convs:
            continue
        # primer mensaje del cliente sin responder (para medir los 30 minutos)
        desde = ult_saliente.get(k)
        q = MensajeWhatsApp.objects.filter(tipo="ENTRANTE", numero__in=_variantes(k), creado__gte=ini, creado__lt=fin)
        if desde:
            q = q.filter(creado__gt=desde)
        ref = q.aggregate(m=Min("creado"))["m"] or m
        Tarea.objects.create(tipo=t, conversacion=convs[k], referencia=ref, prioridad=1)
        creadas += 1
    return creadas


def _generar_inv(fecha):
    t = tipo(TipoTarea.INV)
    if not t.activo:
        return 0
    frecuencia = P("INV_FRECUENCIA_DIAS")
    desde = ahora() - timedelta(days=frecuencia)
    creadas = 0
    for ex in P("INV_EXHIBIDORES"):
        hay = Tarea.objects.filter(tipo=t, exhibidor=ex).filter(
            Q(estado__in=Tarea.ABIERTAS) | Q(estado__in=[Tarea.TERMINADA, Tarea.APROBADA], fin__gte=desde)
        ).exists()
        if not hay:
            Tarea.objects.create(tipo=t, exhibidor=ex, prioridad=50)
            creadas += 1
    return creadas


TEL_VALIDO = r"^\s*(\+?51)?\s*9[0-9]{8}\s*$"


def telefono_normalizado(texto):
    dig = re.sub(r"\D", "", texto or "")
    if dig.startswith("51") and len(dig) == 11:
        dig = dig[2:]
    return dig if re.fullmatch(r"9\d{8}", dig) else None


def _generar_tel():
    from core.models import Cliente

    t = tipo(TipoTarea.TEL)
    if not t.activo:
        return 0
    abiertas = list(Tarea.objects.filter(tipo=t, estado__in=Tarea.ABIERTAS))
    faltan = P("TEL_LOTES_ABIERTOS") - len(abiertas)
    if faltan <= 0:
        return 0
    ocupados = set()
    for ta in abiertas:
        ocupados.update(ta.datos.get("clientes", []))
    # clientes ya trabajados en los últimos 60 días (para no repetirlos si no se pudo corregir)
    for ta in Tarea.objects.filter(tipo=t, fin__gte=ahora() - timedelta(days=60)):
        ocupados.update(ta.datos.get("clientes", []))
    lote = P("TEL_LOTE")
    ids = list(
        Cliente.objects.exclude(telefono__isnull=True).exclude(telefono="")
        .exclude(telefono__regex=TEL_VALIDO).exclude(id__in=ocupados)
        .order_by("-fecha_registro", "-id").values_list("id", flat=True)[: lote * faltan]
    )
    creadas = 0
    for i in range(0, len(ids), lote):
        Tarea.objects.create(tipo=t, datos={"clientes": ids[i:i + lote]}, prioridad=60)
        creadas += 1
    return creadas


def generar_tareas(fecha=None, forzar=False):
    """Crea las tareas que faltan. Se llama sola cada pocos minutos."""
    fecha = fecha or hoy()
    if not forzar and cache.get("ic_generar_tareas"):
        # WhatsApp sí se revisa siempre: es lo más urgente
        try:
            return {"WA_RESP": _generar_wa_resp(fecha)}
        except Exception:
            log.exception("Puntos IC: error generando WA_RESP")
            return {}
    cache.set("ic_generar_tareas", 1, 300)
    res = {}
    for nombre, fn in (("FOTO", _generar_foto), ("COD", _generar_cod),
                       ("WA_LISTA", lambda: _generar_wa_lista(fecha)),
                       ("WA_RESP", lambda: _generar_wa_resp(fecha)),
                       ("INV", lambda: _generar_inv(fecha)), ("TEL", _generar_tel)):
        try:
            with transaction.atomic():
                res[nombre] = fn()
        except Exception:
            log.exception("Puntos IC: error generando %s", nombre)
            res[nombre] = "error"
    return res


# =====================================================================
# Cola: tomar, pausar, terminar
# =====================================================================

def tarea_en_curso(usuario):
    return Tarea.objects.filter(asignada_a=usuario, estado=Tarea.EN_CURSO).select_related("tipo").first()


def _devolver_a_cola(tarea, motivo_alerta=None):
    tarea.estado = Tarea.PENDIENTE
    tarea.inicio = None
    tarea.pausada_en = None
    tarea.segundos_pausa = 0
    if tarea.tipo.codigo != TipoTarea.WA_LISTA:
        usuario = tarea.asignada_a
        tarea.asignada_a = None
    else:
        usuario = tarea.asignada_a
    tarea.save(update_fields=["estado", "inicio", "pausada_en", "segundos_pausa", "asignada_a"])
    if motivo_alerta:
        Tarea.objects.filter(pk=tarea.pk).update(veces_abandonada=tarea.veces_abandonada + 1)
        Alerta.objects.create(fecha=hoy(), usuario=usuario, tipo=Alerta.ABANDONO, tarea=tarea,
                              detalle=motivo_alerta[:255])


def liberar_abandonadas():
    factor = P("ABANDONO_FACTOR")
    n = 0
    for t in Tarea.objects.filter(estado=Tarea.EN_CURSO, pausada_en__isnull=True).select_related("tipo", "asignada_a"):
        limite = float(factor) * (t.tipo.minutos_estandar or 0)
        if limite and t.minutos_trabajados > limite:
            _devolver_a_cola(t, f"{t.tipo.codigo} #{t.pk} superó {limite:.0f} min y volvió a la cola")
            n += 1
    return n


def siguiente_tarea(usuario):
    """Devuelve la tarea en curso o asigna la de mayor prioridad disponible."""
    actual = tarea_en_curso(usuario)
    if actual:
        return actual, False
    liberar_abandonadas()
    generar_tareas()
    skip = connection.features.has_select_for_update_skip_locked
    base = Tarea.objects.filter(estado=Tarea.PENDIENTE, tipo__activo=True, tipo__codigo__in=TipoTarea.EN_COLA)
    hoy_ = hoy()
    candidatos = [
        base.filter(asignada_a=usuario).filter(Q(fecha_objetivo__isnull=True) | Q(fecha_objetivo=hoy_)),
        base.filter(asignada_a__isnull=True, tipo__codigo=TipoTarea.WA_RESP).order_by("referencia", "id"),
        base.filter(asignada_a__isnull=True).exclude(tipo__codigo=TipoTarea.WA_RESP)
        .order_by("tipo__prioridad", "prioridad", "id"),
    ]
    with transaction.atomic():
        for qs in candidatos:
            qs = qs.order_by(*(qs.query.order_by or ["id"]))
            if skip:
                # of=("self",): bloquea solo la fila de la tarea, no el tipo de tarea
                of = ("self",) if connection.features.has_select_for_update_of else ()
                qs = qs.select_for_update(skip_locked=True, of=of)
            else:
                qs = qs.select_for_update()
            t = qs.first()
            if t:
                t.estado = Tarea.EN_CURSO
                t.asignada_a = usuario
                t.inicio = ahora()
                t.pausada_en = None
                t.segundos_pausa = 0
                t.save(update_fields=["estado", "asignada_a", "inicio", "pausada_en", "segundos_pausa"])
                return t, True
    return None, False


def pausar(tarea):
    if tarea.estado == Tarea.EN_CURSO and not tarea.pausada_en:
        tarea.pausada_en = ahora()
        tarea.save(update_fields=["pausada_en"])


def reanudar(tarea):
    if tarea.estado == Tarea.EN_CURSO and tarea.pausada_en:
        tarea.segundos_pausa += int((ahora() - tarea.pausada_en).total_seconds())
        tarea.pausada_en = None
        tarea.save(update_fields=["segundos_pausa", "pausada_en"])


def devoluciones_hoy(usuario):
    return Alerta.objects.filter(usuario=usuario, tipo=Alerta.DEVOLUCION, fecha=hoy()).count()


def soltar(tarea):
    """
    El trabajador devuelve la tarea a la cola. Máximo DEVOLUCIONES_MAX_DIA al día:
    así nadie escoge solo las tareas fáciles. Devuelve (ok, mensaje).
    """
    if tarea.estado != Tarea.EN_CURSO:
        return False, "La tarea ya no está en curso."
    usuario = tarea.asignada_a
    maximo = P("DEVOLUCIONES_MAX_DIA")
    usadas = devoluciones_hoy(usuario)
    if usadas >= maximo:
        clave = f"devol-limite-{usuario.pk}-{hoy()}"
        if not cache.get(clave):
            cache.set(clave, 1, 6 * 3600)
            Alerta.objects.create(fecha=hoy(), usuario=usuario, tipo=Alerta.OTRO, tarea=tarea,
                                  detalle=f"Intentó devolver más de {maximo} tareas hoy")
        return False, f"Ya devolviste {maximo} tareas hoy. Termina esta o pide ayuda a la gerencia."
    _devolver_a_cola(tarea)
    Alerta.objects.create(fecha=hoy(), usuario=usuario, tipo=Alerta.DEVOLUCION, tarea=tarea, vista=True,
                          detalle=f"Devolvió {tarea.tipo.codigo} #{tarea.pk} ({usadas + 1} de {maximo} hoy)")
    return True, f"La tarea volvió a la cola ({usadas + 1} de {maximo} devoluciones hoy)."


def acreditar(tarea, puntos, detalle="", evidencia=None, datos=None):
    """Cierra una tarea del trabajador y registra sus puntos (provisionales si requiere aprobación)."""
    if tarea.pausada_en:
        reanudar(tarea)
    tarea.fin = ahora()
    tarea.puntos = q2(puntos)
    if evidencia is not None:
        tarea.evidencia = evidencia
    if datos:
        tarea.datos = {**(tarea.datos or {}), **datos}
    tarea.estado = Tarea.TERMINADA if tarea.tipo.requiere_aprobacion else Tarea.APROBADA
    if tarea.estado == Tarea.APROBADA:
        tarea.aprobada_en = tarea.fin
    tarea.save()
    if tarea.puntos:
        registrar_movimiento(
            tarea.asignada_a, fecha_local(tarea.fin), tarea.puntos, MovimientoPuntos.TAREA, tarea=tarea,
            detalle=detalle or str(tarea), clave=f"tarea-{tarea.pk}",
        )
    _alerta_rapida(tarea)
    return tarea


def _alerta_rapida(tarea):
    std = tarea.tipo.minutos_estandar or 0
    if std and tarea.tipo.codigo in (TipoTarea.FOTO, TipoTarea.COD, TipoTarea.INV, TipoTarea.TEL):
        if tarea.minutos_trabajados < std / 3:
            Alerta.objects.create(
                fecha=hoy(), usuario=tarea.asignada_a, tipo=Alerta.TAREA_RAPIDA, tarea=tarea,
                detalle=f"{tarea.tipo.codigo} #{tarea.pk} en {tarea.minutos_trabajados} min (estándar {std})",
            )


# ---------- Completar por tipo ----------

def hash_archivo(f):
    h = hashlib.sha1()
    for chunk in f.chunks():
        h.update(chunk)
    f.seek(0)
    return h.hexdigest()


def completar_foto(tarea, archivos):
    """archivos: dict {'imagenF': UploadedFile, ...}. Guarda en el producto y acredita."""
    p = tarea.producto
    hashes = []
    campos = []
    for campo in ("imagenF", "imagenD", "imagenL"):
        f = archivos.get(campo)
        if f:
            hashes.append(hash_archivo(f))
            setattr(p, campo, f)
            campos.append(campo)
    faltan = [c for c in ("imagenF", "imagenD", "imagenL") if not getattr(p, c)]
    if faltan:
        return False, "Faltan fotos: " + ", ".join(faltan)
    if campos:
        p.save(update_fields=campos)
    for h in hashes:
        try:
            otra = Tarea.objects.filter(tipo__codigo=TipoTarea.FOTO, datos__hashes__contains=[h]).exclude(
                producto=p).first()
        except Exception:
            otra = None
        if otra:
            Alerta.objects.create(
                fecha=hoy(), usuario=tarea.asignada_a, tipo=Alerta.FOTO_REPETIDA, tarea=tarea,
                detalle=f"Foto igual a la del producto {otra.producto} (tarea #{otra.pk})",
            )
    acreditar(tarea, tarea.tipo.puntos, f"Fotos de {p.cod}", datos={"hashes": hashes})
    return True, "Fotos guardadas. Quedan pendientes de revisión."


def completar_cod(tarea):
    p = tarea.producto
    faltan = [c for c in CAMPOS_FICHA if getattr(p, c) in (None, "")]
    if faltan:
        return False, "Falta completar: " + ", ".join(faltan)
    acreditar(tarea, tarea.tipo.puntos, f"Ficha de {p.cod}")
    return True, "Ficha completa."


def pendientes_lista_wa(fecha=None):
    """Lo que queda por enviar en Seguimiento WhatsApp (misma lógica que esa pantalla)."""
    from core.models import OrdenTrabajo, ReactivacionWhatsApp
    from core.seguimiento import clientes_reactivacion_lista, clientes_renovacion_qs, controles_menores_qs

    fecha = fecha or hoy()
    encuestas = OrdenTrabajo.objects.filter(
        estado="ENTREGADO", ts_entregado__date__gte=fecha - timedelta(days=30),
        ts_entregado__date__lte=fecha - timedelta(days=7), encuesta_enviada=False,
        ticket__cliente__telefono__isnull=False,
    ).exclude(ticket__cliente__telefono="").count()
    controles = len(list(controles_menores_qs(fecha)))
    renovaciones = len(list(clientes_renovacion_qs(fecha)))
    reactivacion_pend = len(list(clientes_reactivacion_lista(fecha)))
    from core.models import Cliente

    ini, fin = rango_dia(fecha)
    react_hoy = ReactivacionWhatsApp.objects.filter(fecha_envio__gte=ini, fecha_envio__lt=fin).count()
    renov_hoy = Cliente.objects.filter(fecha_ultima_renovacion=fecha).count()
    minimo = P("WA_ENVIOS_MIN_DIA", fecha)
    envios_ok = (renov_hoy + react_hoy) >= minimo or (renovaciones == 0 and reactivacion_pend == 0)
    return {
        "encuestas": encuestas, "controles": controles, "renovaciones": renovaciones,
        "reactivaciones_pendientes": reactivacion_pend, "reactivaciones_hoy": react_hoy,
        "renovaciones_hoy": renov_hoy, "minimo": minimo,
        "completa": encuestas == 0 and controles == 0 and envios_ok,
    }


def completar_wa_lista(tarea):
    estado = pendientes_lista_wa(tarea.fecha_objetivo or hoy())
    if not estado["completa"]:
        return False, (
            f"Aún falta: {estado['encuestas']} encuestas y {estado['controles']} controles por enviar; "
            f"renovaciones + reactivaciones enviadas hoy: {estado['renovaciones_hoy'] + estado['reactivaciones_hoy']} "
            f"de {estado['minimo']}."
        )
    acreditar(tarea, tarea.tipo.puntos, "Lista de WhatsApp del día", datos={"verificacion": estado})
    return True, "Lista del día enviada."


def completar_wa_resp(tarea):
    from whatsapp.models import MensajeWhatsApp

    numero = tarea.conversacion.numero if tarea.conversacion else ""
    resp = (
        MensajeWhatsApp.objects.filter(tipo="SALIENTE", numero__in=_variantes(numero),
                                       creado__gt=tarea.referencia or tarea.creada,
                                       creado__gte=(tarea.inicio or tarea.creada) - timedelta(minutes=1))
        .order_by("creado").first()
    )
    if not resp:
        return False, "No se encuentra tu respuesta en el chat. Envíala desde la bandeja y vuelve a terminar."
    minutos = (resp.creado - (tarea.referencia or tarea.creada)).total_seconds() / 60
    limite = P("WA_RESP_MINUTOS")
    puntos = tarea.tipo.puntos if minutos <= limite else D0
    acreditar(tarea, puntos, f"Respuesta WhatsApp en {minutos:.0f} min",
              datos={"minutos_respuesta": round(minutos, 1), "mensaje_id": resp.pk})
    _alerta_wa_exceso(tarea.asignada_a)
    if puntos:
        return True, f"Respuesta registrada en {minutos:.0f} min."
    return True, f"Respuesta registrada, pero pasó de {limite} min: no suma puntos."


def _alerta_wa_exceso(usuario):
    hace_1h = ahora() - timedelta(hours=1)
    n = Tarea.objects.filter(asignada_a=usuario, tipo__codigo=TipoTarea.WA_RESP, fin__gte=hace_1h).count()
    if n > P("ALERTA_WA_POR_HORA"):
        clave = f"wa-exceso-{usuario.pk}-{ahora():%Y%m%d%H}"
        if not cache.get(clave):
            cache.set(clave, 1, 3600)
            Alerta.objects.create(fecha=hoy(), usuario=usuario, tipo=Alerta.WA_EXCESO,
                                  detalle=f"{n} respuestas de WhatsApp en la última hora")


def completar_inv(tarea, contadas, diferencias, nota=""):
    contadas = max(0, int(contadas))
    diferencias = max(0, min(contadas, int(diferencias)))
    puntos = tarea.tipo.puntos * (contadas - diferencias)
    acreditar(
        tarea, puntos, f"Conteo {tarea.exhibidor}: {contadas} {P('INV_UNIDAD')}(s), {diferencias} con diferencia",
        evidencia=nota, datos={"contadas": contadas, "diferencias": diferencias, "unidad": P("INV_UNIDAD")},
    )
    return True, "Conteo registrado. Queda pendiente de revisión."


def completar_tel(tarea, telefonos):
    """telefonos: {cliente_id: texto}. Guarda los válidos."""
    from core.models import Cliente

    ids = set(tarea.datos.get("clientes", []))
    corregidos = {}
    for cid, texto in telefonos.items():
        cid = int(cid)
        tel = telefono_normalizado(texto)
        if cid in ids and tel:
            Cliente.objects.filter(pk=cid).update(telefono=tel)  # update(): no dispara lógica de ventas
            corregidos[str(cid)] = tel
    puntos = tarea.tipo.puntos * Decimal(len(corregidos)) / 2
    acreditar(tarea, puntos, f"{len(corregidos)} teléfonos corregidos", datos={"corregidos": corregidos})
    return True, f"{len(corregidos)} teléfonos corregidos."


# ---------- Resultados (no van en la cola) ----------

def registrar_resultado(usuario, codigo, evidencia="", cita=None, registrado_por=None, ticket=None):
    t = tipo(codigo)
    momento = ahora()
    datos = {"registrado_por": registrado_por.pk if registrado_por else usuario.pk}
    if ticket:
        datos["ticket"] = ticket
    tarea = Tarea.objects.create(
        tipo=t, asignada_a=usuario, estado=Tarea.EN_CURSO, inicio=momento, cita=cita, evidencia=evidencia,
        datos=datos,
    )
    if cita is not None:
        from whatsapp.models import CitaWhatsApp

        CitaWhatsApp.objects.filter(pk=cita.pk).update(atendido=True)
    return acreditar(tarea, t.puntos, f"{t.nombre}: {evidencia[:120]}")


# =====================================================================
# Revisión de calidad
# =====================================================================

def aprobar(tarea, por):
    if tarea.estado != Tarea.TERMINADA:
        return False
    tarea.estado = Tarea.APROBADA
    tarea.aprobada_por = por
    tarea.aprobada_en = ahora()
    tarea.save(update_fields=["estado", "aprobada_por", "aprobada_en"])
    return True


def _borrar_fotos(producto):
    from core.models import Producto

    for campo in ("imagenF", "imagenD", "imagenL"):
        f = getattr(producto, campo)
        if f:
            try:
                f.storage.delete(f.name)
            except Exception:
                log.warning("No se pudo borrar %s de %s", campo, producto.pk)
    # update(): se borra sin pasar por save(), la reversión la hacemos aquí
    Producto.objects.filter(pk=producto.pk).update(imagenF="", imagenD="", imagenL="")


def eliminar(tarea, por, motivo, borrar_fotos=True):
    if tarea.estado == Tarea.ELIMINADA:
        return False
    with transaction.atomic():
        if borrar_fotos and tarea.tipo.codigo == TipoTarea.FOTO and tarea.producto_id:
            _borrar_fotos(tarea.producto)
        tarea.estado = Tarea.ELIMINADA
        tarea.eliminada_por = por
        tarea.eliminada_en = ahora()
        tarea.motivo_eliminacion = motivo[:255]
        tarea.save(update_fields=["estado", "eliminada_por", "eliminada_en", "motivo_eliminacion"])
        revertir_tarea(tarea, motivo, por)
    cache.delete("ic_generar_tareas")
    return True


def revertir_fotos_producto(producto_id, motivo):
    """Se llama cuando alguien borra las fotos de un producto desde otra pantalla."""
    n = 0
    for t in Tarea.objects.filter(producto_id=producto_id, tipo__codigo=TipoTarea.FOTO,
                                  estado__in=[Tarea.TERMINADA, Tarea.APROBADA]):
        if eliminar(t, None, motivo, borrar_fotos=False):
            n += 1
    return n


# =====================================================================
# Asistencia
# =====================================================================

def minutos_entre(a, b):
    return int((b - a).total_seconds() // 60)


def _puntos_tardanza(minutos):
    if minutos <= 0:
        return P("PTS_A_TIEMPO"), MovimientoPuntos.PUNTUALIDAD, "Entrada a tiempo"
    if minutos <= 5:
        return P("PTS_TARDE_1_5"), MovimientoPuntos.TARDANZA, f"Tardanza {minutos} min"
    if minutos <= 15:
        return P("PTS_TARDE_6_15"), MovimientoPuntos.TARDANZA, f"Tardanza {minutos} min"
    return P("PTS_TARDE_MAS_15"), MovimientoPuntos.TARDANZA, f"Tardanza {minutos} min (día no cumplido)"


ACCIONES = ("entrada", "inicio_refrigerio", "fin_refrigerio", "salida")


def marcar(usuario, accion, dispositivo="", ip=None):
    if accion not in ACCIONES:
        return False, "Acción no válida."
    momento = ahora()
    fecha = momento.date()
    turno = Turno.objects.filter(usuario=usuario, fecha=fecha).first()
    with transaction.atomic():
        asis, _ = Asistencia.objects.select_for_update().get_or_create(usuario=usuario, fecha=fecha)
        if getattr(asis, accion):
            return False, f"Ya marcaste {accion.replace('_', ' ')} hoy a las {a_lima(getattr(asis, accion)):%H:%M}."
        orden = {"inicio_refrigerio": "entrada", "fin_refrigerio": "inicio_refrigerio", "salida": "entrada"}
        previa = orden.get(accion)
        if previa and not getattr(asis, previa):
            return False, f"Primero marca {previa.replace('_', ' ')}."
        setattr(asis, accion, momento)
        asis.dispositivo = dispositivo[:80]
        asis.ip = ip
        msg = f"{accion.replace('_', ' ').capitalize()} registrada: {momento:%H:%M}."
        if accion == "entrada":
            asis.falta = False
            if turno:
                tarde = max(0, minutos_entre(combinar(fecha, turno.hora_entrada), momento) - P("TOLERANCIA_MIN"))
                asis.minutos_tarde = tarde
                pts, tipo_mov, det = _puntos_tardanza(tarde)
                # si había una falta registrada por error (marcó tarde después del proceso), se revierte
                falta = MovimientoPuntos.objects.filter(clave=f"falta-{usuario.pk}-{fecha}").first()
                if falta:
                    revertir_movimiento(falta, "marcó entrada")
                registrar_movimiento(usuario, fecha, pts, tipo_mov, detalle=det, clave=f"punt-{usuario.pk}-{fecha}")
                msg += f" {det} ({pts:+} pts)."
            else:
                msg += " No tienes turno programado hoy (avisa a la gerencia)."
                Alerta.objects.create(fecha=fecha, usuario=usuario, tipo=Alerta.OTRO,
                                      detalle="Marcó entrada sin turno programado")
        if accion == "fin_refrigerio":
            permitido = turno.minutos_refrigerio if turno else P("REFRIGERIO_LS")
            exceso = minutos_entre(asis.inicio_refrigerio, momento) - permitido
            if exceso > P("REFRIGERIO_TOLERANCIA_MIN"):
                asis.minutos_refrigerio_exceso = exceso
                pts = P("PTS_REFRIGERIO_TARDE")
                registrar_movimiento(usuario, fecha, pts, MovimientoPuntos.TARDANZA,
                                     detalle=f"Regreso tarde del refrigerio ({exceso} min)",
                                     clave=f"refri-{usuario.pk}-{fecha}")
                msg += f" Regreso tarde del refrigerio: {exceso} min ({pts:+} pts)."
        if accion in ("inicio_refrigerio", "salida"):
            t = tarea_en_curso(usuario)
            if t:
                pausar(t)
        asis.save()
    return True, msg


def justificar(asistencia, motivo, por):
    with transaction.atomic():
        asistencia.justificada = True
        asistencia.motivo_justificacion = motivo[:200]
        asistencia.cumplido = None
        asistencia.save(update_fields=["justificada", "motivo_justificacion", "cumplido"])
        u, f = asistencia.usuario_id, asistencia.fecha
        for clave in (f"falta-{u}-{f}", f"punt-{u}-{f}", f"refri-{u}-{f}"):
            mov = MovimientoPuntos.objects.filter(clave=clave).first()
            if mov and mov.puntos < 0:
                revertir_movimiento(mov, f"Justificado: {motivo}", por)


# =====================================================================
# Día y mes
# =====================================================================

def meta_del_dia(fecha, tickets, ordenes_biseladas=0):
    base = P("META_BASE_SABADO", fecha) if fecha.weekday() == 5 else P("META_BASE", fecha)
    descuento = P("META_POR_TICKET", fecha) * tickets + P("BISEL_META_POR_ORDEN", fecha) * ordenes_biseladas
    return max(P("META_MINIMA", fecha), base - descuento)


def ordenes_biseladas(fecha):
    """Órdenes que pasaron a biselado ese día (el biselador es el único que bisela)."""
    from core.models import OrdenTrabajo

    ini, fin = rango_dia(fecha)
    return OrdenTrabajo.objects.filter(ts_biselado__gte=ini, ts_biselado__lt=fin).count()


def resultado_dia(trab, fecha, asis=None):
    """Calcula (sin guardar) tickets, meta, puntos y si cumplió."""
    tickets = tickets_del_dia(trab.nombre_vendedor, fecha)
    biseladas = ordenes_biseladas(fecha) if trab.es_biselador else 0
    meta = meta_del_dia(fecha, tickets, biseladas)
    puntos = MovimientoPuntos.suma(usuario=trab.usuario, fecha=fecha)
    cumplido = puntos >= meta
    if asis is not None and (asis.falta or asis.minutos_tarde > 15):
        cumplido = False
    return {"tickets": tickets, "meta": meta, "puntos": puntos, "cumplido": cumplido, "biseladas": biseladas}


def procesar_dia(fecha, liberar=True):
    """Proceso nocturno. Es idempotente: se puede correr varias veces."""
    resumen = []
    for trab in trabajadores():
        u = trab.usuario
        turno = Turno.objects.filter(usuario=u, fecha=fecha).first()
        asis = Asistencia.objects.filter(usuario=u, fecha=fecha).first()
        if turno and (asis is None or asis.entrada is None) and not (asis and asis.justificada):
            asis = asis or Asistencia(usuario=u, fecha=fecha)
            asis.falta = True
            asis.save()
            registrar_movimiento(u, fecha, P("PTS_FALTA", fecha), MovimientoPuntos.TARDANZA,
                                 detalle="Falta injustificada", clave=f"falta-{u.pk}-{fecha}")
        if asis is None:
            continue
        if asis.justificada:
            asis.cumplido = None
            asis.procesado_en = ahora()
            asis.save(update_fields=["cumplido", "procesado_en"])
            continue
        r = resultado_dia(trab, fecha, asis)
        asis.tickets, asis.meta, asis.puntos_dia, asis.cumplido = r["tickets"], r["meta"], r["puntos"], r["cumplido"]
        asis.procesado_en = ahora()
        asis.save(update_fields=["tickets", "meta", "puntos_dia", "cumplido", "procesado_en"])
        _alerta_puntos_altos(trab, asis)
        resumen.append((trab.nombre_vendedor, r))
    if liberar:
        for t in Tarea.objects.filter(estado=Tarea.EN_CURSO, inicio__lt=rango_dia(fecha)[1]).select_related("tipo"):
            if t.tipo.codigo == TipoTarea.ASIGNADA:
                Tarea.objects.filter(pk=t.pk).update(estado=Tarea.PENDIENTE, inicio=None)
            else:
                _devolver_a_cola(t)
    try:
        vencer_tareas_asignadas(fecha)
    except Exception:
        log.exception("Puntos IC: error venciendo tareas asignadas")
    try:
        procesar_ventas_whatsapp(fecha)
    except Exception:
        log.exception("Puntos IC: error calculando ventas por WhatsApp")
    return resumen


# ---------- Tareas asignadas por la gerencia ----------

def asignar_tarea(usuario, descripcion, puntos, fecha_limite, por):
    return Tarea.objects.create(
        tipo=tipo(TipoTarea.ASIGNADA), asignada_a=usuario, descripcion=descripcion[:255],
        puntos=q2(puntos), fecha_limite=fecha_limite, prioridad=1,
        datos={"asignada_por": por.pk if por else None},
    )


def tareas_asignadas_pendientes(usuario):
    return Tarea.objects.filter(tipo__codigo=TipoTarea.ASIGNADA, asignada_a=usuario,
                                estado__in=Tarea.ABIERTAS).order_by("fecha_limite", "id")


def completar_asignada(tarea, evidencia):
    if not tarea.inicio:
        tarea.inicio = ahora()
    return acreditar(tarea, tarea.puntos, f"Tarea asignada: {tarea.descripcion}", evidencia=evidencia)


def vencer_tareas_asignadas(fecha):
    """Las tareas asignadas que pasan su fecha límite sin hacerse restan puntos."""
    n = 0
    for t in Tarea.objects.filter(tipo__codigo=TipoTarea.ASIGNADA, estado__in=Tarea.ABIERTAS,
                                  fecha_limite__lt=fecha + timedelta(days=1), fecha_limite__isnull=False):
        if t.fecha_limite >= fecha + timedelta(days=1):
            continue
        Tarea.objects.filter(pk=t.pk).update(estado=Tarea.ELIMINADA, motivo_eliminacion="Vencida sin hacerse",
                                             eliminada_en=ahora())
        registrar_movimiento(t.asignada_a, t.fecha_limite, P("PTS_TAREA_VENCIDA", fecha), MovimientoPuntos.TARDANZA,
                             tarea=t, detalle=f"Tarea asignada vencida: {t.descripcion}"[:255],
                             clave=f"vencida-{t.pk}")
        n += 1
    return n


# ---------- Venta cerrada por WhatsApp ----------

def procesar_ventas_whatsapp(fecha):
    """
    3 puntos por cada venta (> S/ 100) de un cliente que escribió por WhatsApp en los
    20 días anteriores y al que alguien del equipo le respondió a mano desde la bandeja.
    Los puntos van a la última persona que le respondió; si solo respondió el bot,
    al vendedor del ticket. No cuenta si el cliente tenía otro ticket en los 30 días
    previos al chat (estaba esperando un pedido). Una vez por ticket y por cliente
    dentro de la ventana.
    """
    from core.models import TicketVenta
    from whatsapp.models import CitaWhatsApp, MensajeWhatsApp

    t_tipo = tipo(TipoTarea.CITA)
    if not t_tipo.activo:
        return 0
    dias = P("VENTA_WA_DIAS", fecha)
    excluir = P("VENTA_WA_EXCLUIR_DIAS", fecha)
    monto = P("VENTA_WA_MONTO_MIN", fecha)
    por_vendedor = {t.nombre_vendedor.strip().lower(): t for t in trabajadores()}
    por_usuario = {t.usuario_id: t for t in trabajadores()}
    fin_dia = rango_dia(fecha)[1]
    creadas = 0
    tickets = (TicketVenta.objects.filter(_filtro_sistema(fecha.year), fecha_emision=fecha, total__gt=monto)
               .exclude(cliente__isnull=True).select_related("cliente"))
    for tk in tickets:
        tel = telefono_normalizado(tk.cliente.telefono or "")
        if not tel:
            continue
        clave = f"ventawa-{tk.pk}"
        if MovimientoPuntos.objects.filter(clave=clave).exists():
            continue
        variantes = _variantes(tel)
        desde = rango_dia(fecha - timedelta(days=dias))[0]
        entrantes = MensajeWhatsApp.objects.filter(numero__in=variantes, tipo="ENTRANTE",
                                                   creado__gte=desde, creado__lt=fin_dia)
        primero = entrantes.order_by("creado").values_list("creado", flat=True).first()
        if not primero:
            continue
        # ¿Esperaba un pedido? (tenía otro ticket en los 30 días previos al primer mensaje)
        f_primero = fecha_local(primero)
        if TicketVenta.objects.filter(cliente=tk.cliente, fecha_emision__gte=f_primero - timedelta(days=excluir),
                                      fecha_emision__lte=f_primero).exclude(pk=tk.pk).exists():
            continue
        # Una sola vez por cliente dentro de la ventana
        if Tarea.objects.filter(tipo=t_tipo, datos__cliente=tk.cliente_id,
                                fin__gte=ahora() - timedelta(days=dias)).exists():
            continue
        respuesta = (MensajeWhatsApp.objects.filter(numero__in=variantes, tipo="SALIENTE",
                                                    enviado_por__isnull=False, creado__gte=desde,
                                                    creado__lt=fin_dia)
                     .order_by("-creado").first())
        trab = por_usuario.get(respuesta.enviado_por_id) if respuesta else None
        if trab is None:
            trab = por_vendedor.get((tk.vendedor or "").strip().lower())
        if trab is None:
            continue
        momento = combinar(fecha, datetime.min.time()) + timedelta(hours=20)
        tarea = Tarea.objects.create(
            tipo=t_tipo, asignada_a=trab.usuario, estado=Tarea.APROBADA, inicio=momento, fin=momento,
            aprobada_en=momento, puntos=t_tipo.puntos,
            evidencia=f"Ticket {tk.numero} · S/ {tk.total}",
            datos={"ticket": tk.numero, "cliente": tk.cliente_id,
                   "respondio": "equipo" if respuesta else "bot (va al vendedor)"},
        )
        registrar_movimiento(trab.usuario, fecha, t_tipo.puntos, MovimientoPuntos.TAREA, tarea=tarea,
                             detalle=f"Venta cerrada por WhatsApp: ticket {tk.numero}", clave=clave)
        CitaWhatsApp.objects.filter(numero__in=variantes, atendido=False, creado__gte=desde).update(atendido=True)
        creadas += 1
    return creadas


# ---------- Clientes esperando respuesta (TV y tablero) ----------

def clientes_esperando():
    """Conversaciones cuyo último mensaje es del cliente y lleva más de N minutos sin respuesta."""
    from whatsapp.models import MensajeWhatsApp

    limite = ahora() - timedelta(minutes=P("WA_ESPERA_AVISO_MIN"))
    desde = ahora() - timedelta(hours=24)
    ultimos = {}
    for numero, tipo_m, creado in (MensajeWhatsApp.objects.filter(creado__gte=desde)
                                   .order_by("creado").values_list("numero", "tipo", "creado")):
        ultimos[_ultimos9(numero)] = (tipo_m, creado)
    esperando = sorted(c for t, c in ultimos.values() if t == "ENTRANTE" and c <= limite)
    if not esperando:
        return {"cantidad": 0, "minutos": 0}
    return {"cantidad": len(esperando), "minutos": int((ahora() - esperando[0]).total_seconds() // 60)}


def _alerta_puntos_altos(trab, asis):
    prev = list(
        Asistencia.objects.filter(usuario=trab.usuario, fecha__lt=asis.fecha, fecha__gte=asis.fecha - timedelta(days=60),
                                  entrada__isnull=False, justificada=False)
        .values_list("puntos_dia", flat=True)
    )
    if len(prev) < 5:
        return
    prom = sum(prev) / len(prev)
    if prom > 0 and asis.puntos_dia > prom * P("ALERTA_FACTOR_PUNTOS"):
        Alerta.objects.get_or_create(
            fecha=asis.fecha, usuario=trab.usuario, tipo=Alerta.PUNTOS_ALTOS,
            defaults={"detalle": f"{asis.puntos_dia} pts vs promedio {prom:.1f}"},
        )


# ---------- Órdenes (requisitos Listo y entregas a tiempo) ----------

_RE_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_RE_HORA = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])?", re.I)


def fecha_prometida(ticket):
    m = _RE_FECHA.search(ticket.fecha_entrega or "")
    if not m:
        return None
    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    hora = (ticket.hora_entrega or "").lower().replace(".", "").replace(" ", "")
    hm = _RE_HORA.search(hora)
    h, mi = 19, 0
    if hm:
        h, mi = int(hm.group(1)), int(hm.group(2) or 0)
        if hm.group(3) == "p" and h < 12:
            h += 12
        if hm.group(3) == "a" and h == 12:
            h = 0
    try:
        return datetime(d.year, d.month, d.day, min(h, 23), min(mi, 59)).replace(tzinfo=LIMA)
    except ValueError:
        return None


def ordenes_trabajador(trab, desde, hasta, evaluar_hasta=None):
    from core.models import OrdenTrabajo

    evaluar_hasta = evaluar_hasta or ahora()
    elegibles, con_listo, a_tiempo, con_fecha = 0, 0, 0, 0
    qs = OrdenTrabajo.objects.select_related("ticket").filter(
        ticket__vendedor__iexact=trab.nombre_vendedor.strip(),
        ticket__fecha_emision__gte=desde, ticket__fecha_emision__lte=hasta,
    )
    qs = qs.filter(ticket__numero__lt=TICKET_SISTEMA_ANTIGUO) if desde.year >= 2026 else qs
    for o in qs:
        prom = fecha_prometida(o.ticket)
        vence = prom or combinar(o.ticket.fecha_emision + timedelta(days=7), datetime.min.time())
        if vence > evaluar_hasta and not o.ts_listo:
            continue  # aún no vence: no se evalúa
        elegibles += 1
        if o.ts_listo:
            con_listo += 1
            if prom:
                con_fecha += 1
                if o.ts_listo <= prom:
                    a_tiempo += 1
    return {"elegibles": elegibles, "con_listo": con_listo, "con_fecha": con_fecha, "a_tiempo": a_tiempo}


def requisitos(trab, periodo, dias_trabajados, dias_cumplidos, hasta=None):
    from core.models import CajaDia

    fin = ultimo_dia(periodo)
    hasta = min(hasta or fin, fin)
    res = {}

    pct = (Decimal(dias_cumplidos) * 100 / dias_trabajados) if dias_trabajados else D0
    req = P("REQ_DIAS_CUMPLIDOS_PCT", periodo)
    res["dias"] = {"nombre": "Días cumplidos", "valor": f"{dias_cumplidos} de {dias_trabajados} ({pct:.0f}%)",
                   "meta": f"≥ {req:.0f}%", "ok": dias_trabajados > 0 and pct >= req}

    ini_dt, fin_dt = rango_dia(periodo)[0], rango_dia(fin)[1]
    fotos = Tarea.objects.filter(tipo__codigo=TipoTarea.FOTO, asignada_a=trab.usuario, fin__gte=ini_dt, fin__lt=fin_dt)
    aprobadas = fotos.filter(estado=Tarea.APROBADA).count()
    por_revisar = fotos.filter(estado=Tarea.TERMINADA).count()
    minimo = P("REQ_FOTOS_MIN", periodo)
    quedan = monturas_sin_fotos().count()
    res["fotos"] = {"nombre": "Fotos mínimas",
                    "valor": f"{aprobadas} aprobadas" + (f" + {por_revisar} por revisar" if por_revisar else ""),
                    "meta": f"≥ {minimo} (quedan {quedan} monturas sin fotos)",
                    "ok": aprobadas >= minimo or quedan == 0}

    if P("REQ_VENTA_VENDEDOR_ACTIVO", periodo):
        minimo_v = trab.venta_minima_mes if trab.venta_minima_mes is not None else P("REQ_VENTA_VENDEDOR_MIN", periodo)
        venta_v = venta_vendedor(trab.nombre_vendedor, periodo, hasta)
        res["venta_vendedor"] = {"nombre": "Tu venta del mes",
                                 "valor": f"S/ {venta_v:,.0f}", "meta": f"≥ S/ {minimo_v:,.0f}",
                                 "ok": venta_v >= minimo_v}

    if P("REQ_TICKETS_ACTIVO", periodo):
        minimo_t = P("REQ_TICKETS_MIN", periodo)
        monto_t = P("REQ_TICKETS_MONTO", periodo)
        n_t = tickets_mes(trab.nombre_vendedor, periodo, hasta, monto_t)
        res["tickets"] = {"nombre": f"Ventas de más de S/ {monto_t:.0f}",
                          "valor": f"{n_t} tickets", "meta": f"≥ {minimo_t}", "ok": n_t >= minimo_t}

    anterior_ini = mismo_mes_anio_anterior(periodo)
    anterior_total = venta_tienda(anterior_ini, ultimo_dia(anterior_ini))
    anterior_a_la_fecha = venta_tienda(anterior_ini, anterior_ini.replace(day=min(hasta.day, ultimo_dia(anterior_ini).day)))
    actual = venta_tienda(periodo, hasta)
    activo = P("REQ_VENTA_ACTIVO", periodo)
    if activo:
        res["venta"] = {"nombre": "Venta de la tienda",
                        "valor": f"S/ {actual:,.0f} (al {hasta:%d/%m}; año anterior a la misma fecha S/ {anterior_a_la_fecha:,.0f})",
                        "meta": f"> S/ {anterior_total:,.0f} ({anterior_ini:%m/%Y})", "ok": actual > anterior_total}

    if P("REQ_CAJA_ACTIVO", periodo):
        tol = P("REQ_CAJA_TOLERANCIA", periodo)
        malos = []
        for c in CajaDia.objects.filter(fecha__gte=periodo, fecha__lte=hasta):
            difs = [c.dif_efectivo, c.dif_yape, c.dif_tarjeta, c.dif_transferencia]
            if any(d is not None and abs(d) > tol for d in difs) and not (c.observacion or "").strip():
                malos.append(c.fecha.strftime("%d/%m"))
        res["caja"] = {"nombre": "Caja sin diferencias sin justificar",
                       "valor": "Ninguna" if not malos else "Días: " + ", ".join(malos),
                       "meta": "0 días", "ok": not malos}

    o = None
    if P("REQ_LISTO_ACTIVO", periodo) or P("REQ_ENTREGAS_ACTIVO", periodo):
        o = ordenes_trabajador(trab, periodo, hasta, evaluar_hasta=min(ahora(), rango_dia(hasta)[1]))
    if P("REQ_LISTO_ACTIVO", periodo):
        pct_l = Decimal(o["con_listo"] * 100) / o["elegibles"] if o["elegibles"] else Decimal(100)
        req_l = P("REQ_LISTO_PCT", periodo)
        res["listo"] = {"nombre": "Órdenes con etapa Listo",
                        "valor": f"{o['con_listo']} de {o['elegibles']} ({pct_l:.0f}%)",
                        "meta": f"≥ {req_l:.0f}%", "ok": pct_l >= req_l}

    if P("REQ_ENTREGAS_ACTIVO", periodo):
        pct_e = Decimal(o["a_tiempo"] * 100) / o["con_fecha"] if o["con_fecha"] else Decimal(100)
        req_e = P("REQ_ENTREGAS_PCT", periodo)
        res["entregas"] = {"nombre": "Entregas a tiempo",
                           "valor": f"{o['a_tiempo']} de {o['con_fecha']} ({pct_e:.0f}%)",
                           "meta": f"≥ {req_e:.0f}%", "ok": pct_e >= req_e}
    return res


def pago(puntos, meta, periodo):
    normal = P("PAGO_PUNTO_NORMAL", periodo) * min(puntos, meta)
    alto = P("PAGO_PUNTO_ALTO", periodo) * max(D0, puntos - meta)
    return q2(min(P("PAGO_TOPE", periodo), normal + alto))


# ---------- Bono del equipo por venta del mes ----------

_RE_LUNA = re.compile(r"resina|policarb|luna|cristal|mineral|alto [ií]ndice|trivex|monofocal|multifocal|bifocal|progresiv",
                      re.I)
_RE_MULTI = re.compile(r"multifocal|progresiv", re.I)
_RE_FOTO = re.compile(r"foto|photo|transition", re.I)
_RE_MONTURA = re.compile(r"montura|momtura|motura|armaz", re.I)


def puntos_venta_linea(det, periodo):
    """Puntos de venta de una línea del ticket (distintos de los Puntos IC de tareas)."""
    desc = det.descripcion or ""
    cant = det.cantidad or 1
    tipo_prod = getattr(det.producto, "tipo", None) if det.producto_id else None
    es_montura = (tipo_prod in MONTURAS) or (tipo_prod is None and bool(_RE_MONTURA.search(desc)))
    if es_montura:
        if tipo_prod == "Monturas de Marca" or (det.precio or 0) > P("PV_PRECIO_MARCA", periodo):
            return P("PV_MONTURA_MARCA", periodo) * cant, "montura de marca"
        return D0, ""
    if tipo_prod is None and _RE_LUNA.search(desc):
        # En los tickets la cantidad de una línea de lunas es el número de lunas
        # (una línea por ojo con cantidad 1, o una línea con cantidad 2). Un par = 2 lunas.
        lunas = Decimal(cant)
        pts, motivo = D0, []
        if _RE_MULTI.search(desc) and "digital" in desc.lower():
            pts += P("PV_MULTIFOCAL_DIGITAL", periodo) * lunas / 2
            motivo.append("multifocal digital")
        if _RE_FOTO.search(desc):
            por_luna = P("PV_FOTO_UNIDAD", periodo).strip().lower() != "par"
            pts += P("PV_FOTO", periodo) * (lunas if por_luna else lunas / 2)
            motivo.append("fotocromática")
        return pts, " + ".join(motivo)
    return D0, ""


def puntos_venta(trab, periodo, hasta=None):
    from core.models import DetalleTicketVenta

    hasta = min(hasta or ultimo_dia(periodo), ultimo_dia(periodo))
    total = D0
    detalle = []
    qs = DetalleTicketVenta.objects.select_related("producto", "ticket_numero").filter(
        ticket_numero__fecha_emision__gte=periodo, ticket_numero__fecha_emision__lte=hasta,
        ticket_numero__vendedor__iexact=trab.nombre_vendedor.strip(),
    )
    qs = qs.filter(ticket_numero__numero__lt=TICKET_SISTEMA_ANTIGUO) if periodo.year >= 2026 else qs.filter(
        ticket_numero__numero__gte=TICKET_SISTEMA_ANTIGUO)
    for det in qs:
        pts, motivo = puntos_venta_linea(det, periodo)
        if pts:
            total += pts
            detalle.append((det.ticket_numero.numero, det.descripcion[:60], motivo, pts))
    return total, detalle


def bono_ventas(periodo, hasta=None):
    """Bono del equipo: monto igual + adicional repartido según puntos de venta."""
    fin = ultimo_dia(periodo)
    hasta = min(hasta or fin, fin)
    venta = venta_tienda(periodo, hasta)
    trabs = trabajadores()
    igual_total, adicional = D0, D0
    if venta >= P("BONO_T1_VENTA", periodo):
        igual_total = P("BONO_T1_MONTO", periodo)
    if venta >= P("BONO_T3_VENTA", periodo):
        adicional = P("BONO_T3_ADICIONAL", periodo)
    elif venta >= P("BONO_T2_VENTA", periodo):
        adicional = P("BONO_T2_ADICIONAL", periodo)
    filas = []
    for t in trabs:
        pts, det = puntos_venta(t, periodo, hasta)
        filas.append({"trabajador": t, "puntos_venta": pts, "detalle": det, "igual": D0, "adicional": D0})
    n = len(filas)
    if n:
        for f in filas:
            f["igual"] = q2(igual_total / n)
        filas[0]["igual"] += q2(igual_total) - sum(f["igual"] for f in filas)
        total_pts = sum(f["puntos_venta"] for f in filas)
        if adicional:
            if total_pts == 0:
                for f in filas:  # nadie juntó puntos de venta: el adicional va en partes iguales
                    f["adicional"] = q2(adicional / n)
            else:
                tope = adicional * P("PV_TOPE_PCT", periodo) / 100
                restante, activos = adicional, [f for f in filas if f["puntos_venta"] > 0]
                # reparto proporcional con tope: lo que pasa del tope se redistribuye entre los demás
                while activos and restante > Decimal("0.01"):
                    pts_act = sum(f["puntos_venta"] for f in activos)
                    excedidos = []
                    repartido = D0
                    for f in activos:
                        parte = restante * f["puntos_venta"] / pts_act
                        if f["adicional"] + parte > tope:
                            parte = tope - f["adicional"]
                            excedidos.append(f)
                        f["adicional"] += parte
                        repartido += parte
                    restante -= repartido
                    if not excedidos:
                        break
                    activos = [f for f in activos if f not in excedidos]
                for f in filas:
                    f["adicional"] = q2(f["adicional"])
                # el centavo que se pierde al redondear va a quien tiene más puntos
                dif = q2(adicional) - sum(f["adicional"] for f in filas)
                if dif:
                    max(filas, key=lambda f: f["puntos_venta"])["adicional"] += dif
    for f in filas:
        f["total"] = f["igual"] + f["adicional"]
    proximo = None
    for clave_v in ("BONO_T1_VENTA", "BONO_T2_VENTA", "BONO_T3_VENTA"):
        meta_v = P(clave_v, periodo)
        if venta < meta_v:
            proximo = meta_v
            break
    return {"venta": venta, "igual_total": igual_total, "adicional": adicional, "filas": filas,
            "total": sum(f["total"] for f in filas), "proximo_tramo": proximo,
            "falta": (proximo - venta) if proximo else D0}


def calcular_mes(trab, periodo, hasta=None, con_requisitos=True):
    """Estado del mes de un trabajador (estimado si el mes no ha terminado)."""
    fin = ultimo_dia(periodo)
    hasta = min(hasta or hoy(), fin)
    asis = list(Asistencia.objects.filter(usuario=trab.usuario, fecha__gte=periodo, fecha__lte=hasta))
    trabajados = cumplidos = 0
    meta = D0
    a_tiempo = tardanzas = faltas = 0
    for a in asis:
        if not a.cuenta_como_trabajado:
            continue
        if a.procesado_en is None:
            r = resultado_dia(trab, a.fecha, a)
            meta += r["meta"]
            trabajados += 1
            cumplidos += 1 if r["cumplido"] else 0
        else:
            trabajados += 1
            meta += a.meta
            cumplidos += 1 if a.cumplido else 0
        if a.falta:
            faltas += 1
        elif a.minutos_tarde > 0:
            tardanzas += 1
        elif a.entrada:
            a_tiempo += 1
    puntos = max(D0, puntos_usuario(trab.usuario, periodo, fin))
    puntos_punt = MovimientoPuntos.suma(usuario=trab.usuario, fecha__gte=periodo, fecha__lte=fin,
                                        tipo__in=[MovimientoPuntos.PUNTUALIDAD, MovimientoPuntos.TARDANZA])
    datos = {
        "trabajador": trab, "periodo": periodo, "hasta": hasta, "puntos": puntos, "meta": meta,
        "dias_trabajados": trabajados, "dias_cumplidos": cumplidos,
        "a_tiempo": a_tiempo, "tardanzas": tardanzas, "faltas": faltas, "puntos_puntualidad": puntos_punt,
        "pago_calculado": pago(puntos, meta, periodo),
        "tramo_normal": q2(P("PAGO_PUNTO_NORMAL", periodo) * min(puntos, meta)),
        "tramo_alto": q2(P("PAGO_PUNTO_ALTO", periodo) * max(D0, puntos - meta)),
    }
    if con_requisitos:
        datos["requisitos"] = requisitos(trab, periodo, trabajados, cumplidos, hasta)
        datos["cumple"] = all(r["ok"] for r in datos["requisitos"].values())
        datos["pago"] = datos["pago_calculado"] if datos["cumple"] else D0
    return datos


def ranking(periodo):
    filas = []
    for trab in trabajadores():
        filas.append({
            "trabajador": trab,
            "puntos": max(D0, puntos_usuario(trab.usuario, periodo, ultimo_dia(periodo))),
            "dias_cumplidos": Asistencia.objects.filter(usuario=trab.usuario, fecha__gte=periodo,
                                                        fecha__lte=ultimo_dia(periodo), cumplido=True).count(),
        })
    filas.sort(key=lambda f: (-f["puntos"], -f["dias_cumplidos"], f["trabajador"].nombre_vendedor))
    for i, f in enumerate(filas, 1):
        f["posicion"] = i
    return filas


def pendientes_revision(periodo=None):
    qs = Tarea.objects.filter(estado=Tarea.TERMINADA, tipo__requiere_aprobacion=True)
    if periodo:
        qs = qs.filter(fin__lt=rango_dia(ultimo_dia(periodo))[1])
    return qs


def cerrar_mes(periodo, por, forzar=False):
    periodo = primer_dia(periodo)
    fin = ultimo_dia(periodo)
    if CierreMensual.objects.filter(periodo=periodo).exists():
        return False, "Ese mes ya está cerrado."
    if hoy() <= fin and not forzar:
        return False, f"El mes termina el {fin:%d/%m/%Y}. Ciérralo desde el día siguiente."
    pend = pendientes_revision(periodo).count()
    if pend and P("CIERRE_BLOQUEA_PENDIENTES", periodo) and not forzar:
        return False, f"Hay {pend} tareas pendientes de revisión. Revísalas antes de cerrar."
    # Recalcula cada día (toma en cuenta reversiones y justificaciones del mes)
    for d in dias_del_mes(periodo, hasta=min(fin, hoy())):
        procesar_dia(d, liberar=False)
    filas = []
    with transaction.atomic():
        for trab in trabajadores():
            u = trab.usuario
            asis = Asistencia.objects.filter(usuario=u, fecha__gte=periodo, fecha__lte=fin, justificada=False)
            trabajados = asis.filter(Q(entrada__isnull=False) | Q(falta=True))
            if trabajados.exists() and not trabajados.filter(Q(falta=True) | Q(minutos_tarde__gt=0)).exists():
                registrar_movimiento(u, fin, P("PTS_MES_SIN_TARDANZAS", periodo), MovimientoPuntos.PUNTUALIDAD,
                                     detalle="Mes completo sin tardanzas", clave=f"bonus-punt-{u.pk}-{periodo:%Y%m}")
            filas.append(calcular_mes(trab, periodo, hasta=fin))
        filas.sort(key=lambda f: (-f["puntos"], -f["dias_cumplidos"], f["trabajador"].nombre_vendedor))
        bono = {f["trabajador"].pk: f for f in bono_ventas(periodo, fin)["filas"]}
        for i, f in enumerate(filas, 1):
            b = bono.get(f["trabajador"].pk, {})
            CierreMensual.objects.create(
                puntos_venta=b.get("puntos_venta", D0), bono_ventas=b.get("total", D0),
                periodo=periodo, usuario=f["trabajador"].usuario, puntos=f["puntos"], meta_mes=f["meta"],
                dias_trabajados=f["dias_trabajados"], dias_cumplidos=f["dias_cumplidos"],
                requisitos={k: {**v, "ok": bool(v["ok"])} for k, v in f["requisitos"].items()},
                cumple_requisitos=f["cumple"], pago_calculado=f["pago_calculado"], pago=f["pago"],
                posicion_ranking=i, domingo_extra=(i == 1 and f["puntos"] > 0), cerrado_por=por,
            )
    total = sum(f["pago"] for f in filas)
    total_bono = sum(b.get("total", D0) for b in bono.values())
    return True, (f"Mes {periodo:%m/%Y} cerrado. Puntos IC: S/ {total:,.2f}. "
                  f"Bono de ventas: S/ {total_bono:,.2f}.")


# =====================================================================
# Turnos
# =====================================================================

def generar_turnos(periodo, config, reemplazar=False):
    """
    Horario desde el 26/11/2026: lunes a sábado 9:00–19:45 (todo el equipo) y
    domingos y feriados 10:30–18:00 (quienes se marquen).
    config: {usuario_id: {"lunes_a_sabado": bool,
                          "domingos": [date, ...],      # domingos y feriados que trabaja
                          "descanso": 0..5 | None}}     # día libre en la semana del domingo trabajado
    """
    from .horario import es_domingo_o_feriado, horario_del_dia

    creados = 0
    for uid, cfg in config.items():
        especiales = set(cfg.get("domingos", []))
        libres = set()
        if cfg.get("descanso") not in (None, ""):
            for d in especiales:
                if d.weekday() == 6:
                    libres.add(d - timedelta(days=6) + timedelta(days=int(cfg["descanso"])))
        for d in dias_del_mes(periodo):
            datos = None
            if es_domingo_o_feriado(d):
                if d in especiales:
                    ini, fin = horario_del_dia(d)
                    datos = (ini, fin, P("REFRIGERIO_DF", d), False)
            elif cfg.get("lunes_a_sabado", True) and d not in libres:
                ini, fin = horario_del_dia(d)
                datos = (ini, fin, P("REFRIGERIO_LS", d), d.weekday() == 5)
            existe = Turno.objects.filter(usuario_id=uid, fecha=d)
            if datos is None:
                if reemplazar:
                    existe.delete()
                continue
            if existe.exists() and not reemplazar:
                continue
            Turno.objects.update_or_create(
                usuario_id=uid, fecha=d,
                defaults=dict(hora_entrada=datos[0], hora_salida=datos[1], minutos_refrigerio=datos[2],
                              es_sabado=datos[3]),
            )
            creados += 1
    return creados


# =====================================================================
# Productividad (gerencia)
# =====================================================================

def productividad(periodo):
    ini_dt, fin_dt = rango_dia(periodo)[0], rango_dia(ultimo_dia(periodo))[1]
    filas = []
    for trab in trabajadores():
        tareas = list(Tarea.objects.filter(asignada_a=trab.usuario, fin__gte=ini_dt, fin__lt=fin_dt,
                                           tipo__codigo__in=TipoTarea.EN_COLA)
                      .exclude(estado=Tarea.ELIMINADA).select_related("tipo"))
        minutos = sum(t.minutos_trabajados for t in tareas)
        pts = sum(t.puntos for t in tareas)
        por_tipo = {}
        for t in tareas:
            d = por_tipo.setdefault(t.tipo.codigo, [0, 0])
            d[0] += 1
            d[1] += t.minutos_trabajados
        filas.append({
            "trabajador": trab, "tareas": len(tareas), "horas": round(minutos / 60, 1),
            "puntos_hora": round(float(pts) / (minutos / 60), 1) if minutos else 0,
            "por_tipo": {k: {"n": v[0], "prom": round(v[1] / v[0], 1)} for k, v in sorted(por_tipo.items())},
            "eliminadas": Tarea.objects.filter(asignada_a=trab.usuario, estado=Tarea.ELIMINADA,
                                               eliminada_en__gte=ini_dt, eliminada_en__lt=fin_dt).count(),
            "abandonos": Alerta.objects.filter(usuario=trab.usuario, tipo=Alerta.ABANDONO,
                                               fecha__gte=periodo, fecha__lte=ultimo_dia(periodo)).count(),
        })
    return filas


def tiempos_por_tipo(periodo):
    """Tiempo real (mediana, sin pausas) frente al estándar, por tipo de tarea."""
    from statistics import median

    ini_dt, fin_dt = rango_dia(periodo)[0], rango_dia(ultimo_dia(periodo))[1]
    filas = []
    for t in TipoTarea.objects.filter(codigo__in=TipoTarea.EN_COLA + (TipoTarea.ASIGNADA,)):
        mins = [x.minutos_trabajados for x in Tarea.objects.filter(
            tipo=t, fin__gte=ini_dt, fin__lt=fin_dt, inicio__isnull=False).exclude(estado=Tarea.ELIMINADA)]
        if not mins:
            continue
        real = median(mins)
        std = t.minutos_estandar or 0
        desvio = round((real - std) * 100 / std) if std else None
        filas.append({"tipo": t, "n": len(mins), "real": round(real, 1), "estandar": std, "desvio": desvio,
                      "alerta": desvio is not None and abs(desvio) > 30,
                      "puntos_sugeridos": round(real / 6, 1)})
    return filas


def resumen_cola():
    return list(
        Tarea.objects.filter(estado__in=Tarea.ABIERTAS).values("tipo__codigo", "tipo__nombre")
        .annotate(pendientes=Count("id", filter=Q(estado=Tarea.PENDIENTE)),
                  en_curso=Count("id", filter=Q(estado=Tarea.EN_CURSO)))
        .order_by("tipo__prioridad")
    )
