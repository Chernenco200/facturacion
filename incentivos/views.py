import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import BytesIO

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Producto

from . import services as S
from .models import (
    Alerta,
    Asistencia,
    CierreMensual,
    DispositivoTienda,
    MovimientoPuntos,
    ParametroIncentivo,
    Tarea,
    TipoTarea,
    Trabajador,
    Turno,
)
from .params import DEFAULTS, P, _convertir, valor_crudo
from .tiempo import ahora, dias_del_mes, hoy, parse_periodo, primer_dia, rango_dia, ultimo_dia

COOKIE_DISPOSITIVO = "ic_dispositivo"


# =====================================================================
# Permisos
# =====================================================================

def gerencia_required(view):
    @login_required
    @wraps(view)
    def _w(request, *a, **kw):
        if not S.es_gerencia(request.user):
            return HttpResponseForbidden("Solo la gerencia puede entrar aquí.")
        return view(request, *a, **kw)
    return _w


def trabajador_required(view):
    @login_required
    @wraps(view)
    def _w(request, *a, **kw):
        trab = S.trabajador_de(request.user)
        if trab is None:
            if S.es_gerencia(request.user):
                return redirect("incentivos:gerencia")
            return HttpResponseForbidden("Tu usuario no está registrado como trabajador en Puntos IC.")
        request.trabajador = trab
        return view(request, *a, **kw)
    return _w


def ip_cliente(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def dispositivo_autorizado(request):
    """(ok, nombre). Vale el token del equipo de la tienda o una IP del local."""
    token = request.get_signed_cookie(COOKIE_DISPOSITIVO, default=None, salt="ic")
    if token:
        d = DispositivoTienda.objects.filter(token=token, activo=True).first()
        if d:
            return True, d.nombre
    ip = ip_cliente(request)
    if ip and ip in P("IPS_TIENDA"):
        return True, f"IP {ip}"
    return False, ""


# =====================================================================
# Trabajador
# =====================================================================

def _bono_de(trab, periodo):
    b = S.bono_ventas(periodo, hoy())
    fila = next((f for f in b["filas"] if f["trabajador"].pk == trab.pk), None)
    return {**b, "mia": fila}


@trabajador_required
def panel(request):
    trab = request.trabajador
    hoy_ = hoy()
    periodo = primer_dia(hoy_)
    res_hoy = S.resultado_dia(trab, hoy_, Asistencia.objects.filter(usuario=trab.usuario, fecha=hoy_).first())
    avance = int(min(100, (res_hoy["puntos"] / res_hoy["meta"] * 100))) if res_hoy["meta"] else 0
    mes = S.calcular_mes(trab, periodo)
    ctx = {
        "bono": _bono_de(trab, periodo),
        "trab": trab,
        "hoy": hoy_,
        "res_hoy": res_hoy,
        "avance": avance,
        "tarea": S.tarea_en_curso(trab.usuario),
        "asistencia": Asistencia.objects.filter(usuario=trab.usuario, fecha=hoy_).first(),
        "turno": Turno.objects.filter(usuario=trab.usuario, fecha=hoy_).first(),
        "mes": mes,
        "ranking": S.ranking(periodo),
        "movimientos": MovimientoPuntos.objects.filter(usuario=trab.usuario, fecha__gte=periodo)
        .select_related("tarea__tipo")[:200],
    }
    return render(request, "incentivos/panel.html", ctx)


@trabajador_required
@require_POST
def siguiente(request):
    tarea, nueva = S.siguiente_tarea(request.user)
    if tarea is None:
        messages.info(request, "No hay tareas disponibles en este momento.")
        return redirect("incentivos:panel")
    return redirect("incentivos:tarea", pk=tarea.pk)


class CodForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["marca", "material", "forma", "color", "talla_luna", "puente", "largo", "ancho", "altura",
                  "precio_venta"]


@trabajador_required
def tarea_detalle(request, pk):
    tarea = get_object_or_404(Tarea.objects.select_related("tipo", "producto", "conversacion"), pk=pk)
    if tarea.asignada_a_id != request.user.id or tarea.estado != Tarea.EN_CURSO:
        messages.warning(request, "Esa tarea ya no está en curso para ti.")
        return redirect("incentivos:panel")
    codigo = tarea.tipo.codigo
    ctx = {"tarea": tarea, "codigo": codigo}

    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "pausar":
            S.pausar(tarea)
            messages.info(request, "Tarea en pausa. Atiende al cliente y luego presiona Reanudar.")
            return redirect("incentivos:tarea", pk=pk)
        if accion == "reanudar":
            S.reanudar(tarea)
            return redirect("incentivos:tarea", pk=pk)
        if accion == "soltar":
            S.soltar(tarea)
            messages.info(request, "La tarea volvió a la cola.")
            return redirect("incentivos:panel")
        if tarea.pausada_en:
            S.reanudar(tarea)
        ok, msg = False, "Acción no reconocida."
        if codigo == TipoTarea.FOTO:
            ok, msg = S.completar_foto(tarea, request.FILES)
        elif codigo == TipoTarea.COD:
            form = CodForm(request.POST, instance=tarea.producto)
            if form.is_valid():
                form.save()
                ok, msg = S.completar_cod(tarea)
            else:
                ctx["form"] = form
                msg = "Revisa los campos marcados."
        elif codigo == TipoTarea.WA_LISTA:
            ok, msg = S.completar_wa_lista(tarea)
        elif codigo == TipoTarea.WA_RESP:
            ok, msg = S.completar_wa_resp(tarea)
        elif codigo == TipoTarea.INV:
            try:
                ok, msg = S.completar_inv(tarea, int(request.POST.get("contadas", "0")),
                                          int(request.POST.get("diferencias", "0")), request.POST.get("nota", ""))
            except ValueError:
                msg = "Escribe números enteros."
        elif codigo == TipoTarea.TEL:
            tels = {k[4:]: v for k, v in request.POST.items() if k.startswith("tel_") and v.strip()}
            ok, msg = S.completar_tel(tarea, tels)
        (messages.success if ok else messages.error)(request, msg)
        if ok:
            if request.POST.get("seguir"):
                t2, _ = S.siguiente_tarea(request.user)
                if t2:
                    return redirect("incentivos:tarea", pk=t2.pk)
            return redirect("incentivos:panel")
        tarea.refresh_from_db()

    if codigo == TipoTarea.COD and "form" not in ctx:
        ctx["form"] = CodForm(instance=tarea.producto)
    if codigo == TipoTarea.WA_LISTA:
        try:
            ctx["lista"] = S.pendientes_lista_wa(tarea.fecha_objetivo or hoy())
        except Exception as e:  # la pantalla de seguimiento sigue funcionando aunque falle el conteo
            ctx["lista_error"] = str(e)
    if codigo == TipoTarea.TEL:
        from core.models import Cliente

        ctx["clientes"] = Cliente.objects.filter(pk__in=tarea.datos.get("clientes", []))
    if codigo == TipoTarea.INV:
        ctx["unidad"] = P("INV_UNIDAD")
    ctx["minutos"] = tarea.minutos_trabajados
    return render(request, "incentivos/tarea.html", ctx)


class ResultadoForm(forms.Form):
    tipo = forms.ChoiceField(choices=[
        (TipoTarea.REEL, "Publicación o reel publicado"),
        (TipoTarea.RESENA, "Reseña nueva en Google"),
        (TipoTarea.CITA, "Cliente con cita llegó a la tienda"),
    ])
    evidencia = forms.CharField(label="Link o detalle", max_length=500, required=False,
                                widget=forms.TextInput(attrs={"placeholder": "Link del reel o nombre del cliente"}))
    cita = forms.ModelChoiceField(queryset=None, required=False, label="Cita (solo para 'cliente con cita')")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        from whatsapp.models import CitaWhatsApp

        usadas = Tarea.objects.filter(cita__isnull=False).values_list("cita_id", flat=True)
        self.fields["cita"].queryset = CitaWhatsApp.objects.filter(
            atendido=False, creado__gte=ahora() - timedelta(days=45)).exclude(id__in=usadas).order_by("-creado")

    def clean(self):
        c = super().clean()
        if c.get("tipo") == TipoTarea.CITA and not c.get("cita"):
            self.add_error("cita", "Elige la cita del cliente que llegó.")
        if c.get("tipo") in (TipoTarea.REEL, TipoTarea.RESENA) and not c.get("evidencia"):
            self.add_error("evidencia", "Pon el link o el detalle.")
        return c


@trabajador_required
def resultado(request):
    form = ResultadoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = S.registrar_resultado(request.user, form.cleaned_data["tipo"], form.cleaned_data["evidencia"] or "",
                                  cita=form.cleaned_data.get("cita"))
        messages.success(request, f"Registrado: {t.tipo.nombre} ({t.puntos} pts"
                         + (", pendiente de revisión)" if t.estado == Tarea.TERMINADA else ")"))
        return redirect("incentivos:panel")
    return render(request, "incentivos/resultado.html", {"form": form})


# =====================================================================
# Marcación (solo desde el equipo de la tienda)
# =====================================================================

def marcar(request):
    ok_disp, nombre_disp = dispositivo_autorizado(request)
    ip = ip_cliente(request)
    if request.method == "POST":
        if not ok_disp:
            u = authenticate(request, username=request.POST.get("usuario", ""), password=request.POST.get("clave", ""))
            Alerta.objects.create(fecha=hoy(), usuario=u, tipo=Alerta.MARCACION,
                                  detalle=f"Intento de marcación desde equipo no autorizado (IP {ip})")
            messages.error(request, "Este equipo no está autorizado para marcar asistencia.")
            return redirect("incentivos:marcar")
        u = authenticate(request, username=request.POST.get("usuario", ""), password=request.POST.get("clave", ""))
        if u is None or S.trabajador_de(u) is None:
            messages.error(request, "Usuario o contraseña incorrectos (o no participa en Puntos IC).")
            return redirect("incentivos:marcar")
        ok, msg = S.marcar(u, request.POST.get("accion", ""), dispositivo=nombre_disp, ip=ip)
        (messages.success if ok else messages.error)(request, f"{S.trabajador_de(u).nombre_vendedor}: {msg}")
        return redirect("incentivos:marcar")
    hoy_ = hoy()
    marc = Asistencia.objects.filter(fecha=hoy_).select_related("usuario")
    return render(request, "incentivos/marcar.html", {
        "autorizado": ok_disp, "dispositivo": nombre_disp, "ip": ip, "ahora": ahora(), "marcaciones": marc,
    })


@gerencia_required
def dispositivo(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "registrar":
            d = DispositivoTienda.objects.create(nombre=request.POST.get("nombre", "Equipo tienda")[:60],
                                                 token=secrets.token_hex(24))
            resp = redirect("incentivos:dispositivo")
            resp.set_signed_cookie(COOKIE_DISPOSITIVO, d.token, salt="ic", max_age=5 * 365 * 24 * 3600,
                                   httponly=True, secure=request.is_secure(), samesite="Lax")
            messages.success(request, f"Este equipo quedó autorizado como '{d.nombre}'.")
            return resp
        if accion == "desactivar":
            DispositivoTienda.objects.filter(pk=request.POST.get("id")).update(activo=False)
            messages.info(request, "Equipo desactivado.")
            return redirect("incentivos:dispositivo")
    ok, nombre = dispositivo_autorizado(request)
    return render(request, "incentivos/dispositivo.html", {
        "dispositivos": DispositivoTienda.objects.all(), "este_ok": ok, "este": nombre, "ip": ip_cliente(request),
    })


# =====================================================================
# Gerencia
# =====================================================================

@gerencia_required
def gerencia(request):
    periodo = parse_periodo(request.GET.get("mes"), primer_dia(hoy()))
    filas = [S.calcular_mes(t, periodo) for t in S.trabajadores()]
    rk = {r["trabajador"].pk: r["posicion"] for r in S.ranking(periodo)}
    for f in filas:
        f["posicion"] = rk.get(f["trabajador"].pk)
    filas.sort(key=lambda f: f["posicion"] or 99)
    ini, fin = rango_dia(periodo)[0], rango_dia(ultimo_dia(periodo))[1]
    asistencia = []
    for t in S.trabajadores():
        qs = Asistencia.objects.filter(usuario=t.usuario, fecha__gte=periodo, fecha__lte=ultimo_dia(periodo))
        asistencia.append({
            "trabajador": t,
            "tardanzas": qs.filter(minutos_tarde__gt=0, justificada=False).count(),
            "minutos": sum(qs.filter(justificada=False).values_list("minutos_tarde", flat=True)),
            "faltas": qs.filter(falta=True, justificada=False).count(),
            "justificadas": qs.filter(justificada=True).count(),
            "refrigerio": qs.filter(minutos_refrigerio_exceso__gt=0).count(),
        })
    ctx = {
        "periodo": periodo,
        "mes_anterior": primer_dia(periodo - timedelta(days=1)),
        "mes_siguiente": primer_dia(ultimo_dia(periodo) + timedelta(days=1)),
        "filas": filas,
        "bono": S.bono_ventas(periodo, hoy()),
        "costo_total": sum(f["pago"] for f in filas),
        "costo_sin_requisitos": sum(f["pago_calculado"] for f in filas),
        "productividad": S.productividad(periodo),
        "pend_revision": S.pendientes_revision().count(),
        "sin_fotos": S.monturas_sin_fotos().count(),
        "fotos_mes": Tarea.objects.filter(tipo__codigo=TipoTarea.FOTO, estado__in=[Tarea.TERMINADA, Tarea.APROBADA],
                                          fin__gte=ini, fin__lt=fin).count(),
        "cola": S.resumen_cola(),
        "asistencia": asistencia,
        "alertas": Alerta.objects.filter(vista=False).select_related("usuario")[:50],
        "cerrado": CierreMensual.objects.filter(periodo=periodo).exists(),
        "cierres": CierreMensual.objects.filter(periodo=periodo).select_related("usuario"),
        "puede_cerrar": hoy() > ultimo_dia(periodo),
    }
    return render(request, "incentivos/gerencia.html", ctx)


@gerencia_required
@require_POST
def alertas_vistas(request):
    Alerta.objects.filter(vista=False).update(vista=True)
    return redirect("incentivos:gerencia")


@gerencia_required
def revision(request):
    if request.method == "POST":
        tarea = get_object_or_404(Tarea, pk=request.POST.get("id"))
        if request.POST.get("accion") == "aprobar":
            S.aprobar(tarea, request.user)
            messages.success(request, f"Aprobada: {tarea}")
        elif request.POST.get("accion") == "eliminar":
            motivo = request.POST.get("motivo", "").strip() or "Rechazada por la gerencia"
            S.eliminar(tarea, request.user, motivo)
            messages.warning(request, f"Eliminada y puntos revertidos: {tarea}")
        return redirect(request.get_full_path())
    pendientes = S.pendientes_revision().select_related("tipo", "producto", "asignada_a").order_by("fin")
    recientes = (Tarea.objects.filter(estado=Tarea.APROBADA, fin__gte=ahora() - timedelta(days=7))
                 .select_related("tipo", "producto", "asignada_a", "aprobada_por").order_by("-fin")[:150])
    return render(request, "incentivos/revision.html", {"pendientes": pendientes, "recientes": recientes})


class ExamenForm(forms.Form):
    trabajador = forms.ModelChoiceField(queryset=Trabajador.objects.filter(participa=True))
    detalle = forms.CharField(max_length=200, label="Examen y nota")


@gerencia_required
def examen(request):
    form = ExamenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = S.registrar_resultado(form.cleaned_data["trabajador"].usuario, TipoTarea.EXAMEN,
                                  form.cleaned_data["detalle"], registrado_por=request.user)
        messages.success(request, f"Examen registrado ({t.puntos} pts).")
        return redirect("incentivos:gerencia")
    return render(request, "incentivos/form_simple.html", {"form": form, "titulo": "Registrar examen aprobado"})


@gerencia_required
def configuracion(request):
    if request.method == "POST":
        if request.POST.get("accion") == "param":
            clave = request.POST.get("clave")
            valor = request.POST.get("valor", "").strip()
            if clave in DEFAULTS:
                try:
                    _convertir(valor, DEFAULTS[clave][1])
                    desde = request.POST.get("vigente_desde") or hoy().isoformat()
                    ParametroIncentivo.objects.create(clave=clave, valor=valor, vigente_desde=desde,
                                                      descripcion=DEFAULTS[clave][2], creado_por=request.user)
                    messages.success(request, f"{clave} = {valor} desde {desde}")
                except (InvalidOperation, ValueError):
                    messages.error(request, f"Valor no válido para {clave}.")
        elif request.POST.get("accion") == "tipo":
            t = get_object_or_404(TipoTarea, pk=request.POST.get("id"))
            try:
                t.puntos = Decimal(request.POST.get("puntos", t.puntos))
                t.minutos_estandar = int(request.POST.get("minutos_estandar", t.minutos_estandar))
                t.prioridad = int(request.POST.get("prioridad", t.prioridad))
                t.requiere_aprobacion = bool(request.POST.get("requiere_aprobacion"))
                t.activo = bool(request.POST.get("activo"))
                t.save()
                messages.success(request, f"Actualizado {t.codigo}.")
            except (InvalidOperation, ValueError):
                messages.error(request, "Revisa los números.")
        return redirect("incentivos:configuracion")
    params = [{"clave": k, "valor": valor_crudo(k), "defecto": v[0], "tipo": v[1], "descripcion": v[2]}
              for k, v in DEFAULTS.items()]
    return render(request, "incentivos/configuracion.html", {
        "params": params, "tipos": TipoTarea.objects.all(), "hoy": hoy(),
        "historial": ParametroIncentivo.objects.select_related("creado_por")[:60],
    })


@gerencia_required
def turnos(request):
    periodo = parse_periodo(request.GET.get("mes") or request.POST.get("mes"), primer_dia(hoy() + timedelta(days=10)))
    trabs = S.trabajadores()
    domingos = [d for d in dias_del_mes(periodo) if d.weekday() == 6]
    if request.method == "POST":
        config = {}
        for t in trabs:
            config[t.usuario_id] = {
                "lv": request.POST.get(f"lv_{t.pk}", ""),
                "rotar": bool(request.POST.get(f"rot_{t.pk}")),
                "descanso": request.POST.get(f"desc_{t.pk}", ""),
                "sabado": bool(request.POST.get(f"sab_{t.pk}")),
                "domingos": [d for d in domingos if request.POST.get(f"dom_{t.pk}_{d.isoformat()}")],
            }
        n = S.generar_turnos(periodo, config, reemplazar=bool(request.POST.get("reemplazar")))
        messages.success(request, f"{n} turnos creados o actualizados para {periodo:%m/%Y}.")
        return redirect(f"{request.path}?mes={periodo:%Y-%m}")
    tabla = []
    turnos_mes = {(x.usuario_id, x.fecha): x for x in Turno.objects.filter(fecha__gte=periodo,
                                                                            fecha__lte=ultimo_dia(periodo))}
    dias = list(dias_del_mes(periodo))
    for t in trabs:
        tabla.append({"trabajador": t, "celdas": [turnos_mes.get((t.usuario_id, d)) for d in dias]})
    return render(request, "incentivos/turnos.html", {
        "periodo": periodo, "trabajadores": trabs, "domingos": domingos, "dias": dias, "tabla": tabla,
        "opciones_lv": ["09:00-18:00", "10:00-19:00"],
        "dias_semana": [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes")],
        "domingo_horario": f"{P('DOMINGO_ENTRADA'):%H:%M}–{P('DOMINGO_SALIDA'):%H:%M}",
    })


@gerencia_required
def asistencia(request):
    periodo = parse_periodo(request.GET.get("mes"), primer_dia(hoy()))
    if request.method == "POST":
        motivo = request.POST.get("motivo", "").strip() or "Justificado por la gerencia"
        if request.POST.get("id"):
            a = get_object_or_404(Asistencia, pk=request.POST["id"])
        else:
            t = get_object_or_404(Trabajador, pk=request.POST.get("trabajador"))
            a, _ = Asistencia.objects.get_or_create(usuario=t.usuario, fecha=request.POST.get("fecha"))
        S.justificar(a, motivo, request.user)
        messages.success(request, f"Justificado {a.usuario} {a.fecha}.")
        return redirect(f"{request.path}?mes={periodo:%Y-%m}")
    regs = (Asistencia.objects.filter(fecha__gte=periodo, fecha__lte=ultimo_dia(periodo))
            .select_related("usuario").order_by("-fecha", "usuario__username"))
    return render(request, "incentivos/asistencia.html", {
        "periodo": periodo, "registros": regs, "trabajadores": S.trabajadores(), "hoy": hoy(),
    })


@gerencia_required
@require_POST
def cerrar(request):
    periodo = parse_periodo(request.POST.get("mes"))
    ok, msg = S.cerrar_mes(periodo, request.user, forzar=bool(request.POST.get("forzar")))
    (messages.success if ok else messages.error)(request, msg)
    return redirect(f"/incentivos/gerencia/?mes={periodo:%Y-%m}")


@gerencia_required
def cierre_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    periodo = parse_periodo(request.GET.get("mes"))
    wb = Workbook()
    ws = wb.active
    ws.title = "Cierre"
    cierres = list(CierreMensual.objects.filter(periodo=periodo).select_related("usuario"))
    req_cols = []
    for c in cierres:
        for k in c.requisitos:
            if k not in req_cols:
                req_cols.append(k)
    head = ["Posición", "Trabajador", "Puntos", "Suma de metas", "Días trabajados", "Días cumplidos",
            "Pago calculado (S/)", "Cumple requisitos", "Pago Puntos IC (S/)", "Domingo extra",
            "Puntos de venta", "Bono de ventas (S/)", "Total a pagar (S/)"] + \
           [f"Req: {k}" for k in req_cols]
    ws.append(head)
    for c in cierres:
        trab = Trabajador.objects.filter(usuario=c.usuario).first()
        ws.append([c.posicion_ranking, trab.nombre_vendedor if trab else c.usuario.username, float(c.puntos),
                   float(c.meta_mes), c.dias_trabajados, c.dias_cumplidos, float(c.pago_calculado),
                   "Sí" if c.cumple_requisitos else "No", float(c.pago), "Sí" if c.domingo_extra else "No",
                   float(c.puntos_venta), float(c.bono_ventas), float(c.pago + c.bono_ventas)] +
                  [("OK " if c.requisitos.get(k, {}).get("ok") else "NO ") + str(c.requisitos.get(k, {}).get("valor", ""))
                   for k in req_cols])
    if cierres:
        n = len(cierres) + 1
        ws.append([None, "Total", f"=SUM(C2:C{n})", None, None, None, f"=SUM(G2:G{n})", None, f"=SUM(I2:I{n})",
                   None, f"=SUM(K2:K{n})", f"=SUM(L2:L{n})", f"=SUM(M2:M{n})"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws2 = wb.create_sheet("Movimientos")
    ws2.append(["Fecha", "Trabajador", "Tipo", "Puntos", "Detalle", "Tarea"])
    for m in MovimientoPuntos.objects.filter(fecha__gte=periodo, fecha__lte=ultimo_dia(periodo)).select_related(
            "usuario", "tarea__tipo").order_by("usuario__username", "fecha", "id"):
        ws2.append([m.fecha, m.usuario.username, m.get_tipo_display(), float(m.puntos), m.detalle,
                    m.tarea.tipo.codigo if m.tarea else ""])
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    buf = BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="Cierre_PuntosIC_{periodo:%Y_%m}.xlsx"'
    return resp


@gerencia_required
def panel_de(request, trabajador_id):
    """La gerencia ve el panel de un trabajador tal como lo ve él."""
    trab = get_object_or_404(Trabajador, pk=trabajador_id)
    request.trabajador = trab
    hoy_ = hoy()
    periodo = primer_dia(hoy_)
    res_hoy = S.resultado_dia(trab, hoy_, Asistencia.objects.filter(usuario=trab.usuario, fecha=hoy_).first())
    return render(request, "incentivos/panel.html", {
        "trab": trab, "hoy": hoy_, "res_hoy": res_hoy, "solo_lectura": True,
        "avance": int(min(100, res_hoy["puntos"] / res_hoy["meta"] * 100)) if res_hoy["meta"] else 0,
        "tarea": S.tarea_en_curso(trab.usuario),
        "asistencia": Asistencia.objects.filter(usuario=trab.usuario, fecha=hoy_).first(),
        "turno": Turno.objects.filter(usuario=trab.usuario, fecha=hoy_).first(),
        "mes": S.calcular_mes(trab, periodo), "ranking": S.ranking(periodo), "bono": _bono_de(trab, periodo),
        "movimientos": MovimientoPuntos.objects.filter(usuario=trab.usuario, fecha__gte=periodo)
        .select_related("tarea__tipo")[:200],
    })
