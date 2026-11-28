from django.contrib import admin

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


@admin.register(Trabajador)
class TrabajadorAdmin(admin.ModelAdmin):
    list_display = ("nombre_vendedor", "usuario", "participa", "es_biselador", "venta_minima_mes", "orden_rotacion")
    list_editable = ("participa", "es_biselador", "venta_minima_mes", "orden_rotacion")


@admin.register(TipoTarea)
class TipoTareaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "puntos", "minutos_estandar", "prioridad", "requiere_aprobacion", "activo")
    list_editable = ("puntos", "minutos_estandar", "prioridad", "requiere_aprobacion", "activo")


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "estado", "asignada_a", "producto", "exhibidor", "inicio", "fin", "puntos")
    list_filter = ("tipo", "estado", "asignada_a")
    search_fields = ("producto__cod", "exhibidor", "evidencia")
    raw_id_fields = ("producto", "conversacion", "cita")
    date_hierarchy = "creada"


class SoloLecturaMixin:
    """El libro de puntos no se edita: se corrige con un movimiento de AJUSTE o REVERSION."""

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MovimientoPuntos)
class MovimientoPuntosAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ("fecha", "usuario", "puntos", "tipo", "detalle", "tarea")
    list_filter = ("tipo", "usuario")
    date_hierarchy = "fecha"
    raw_id_fields = ("tarea", "reversa_de")

    def has_add_permission(self, request):
        return request.user.is_superuser  # para ajustes manuales excepcionales


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "hora_entrada", "hora_salida", "minutos_refrigerio", "es_sabado")
    list_filter = ("usuario",)
    date_hierarchy = "fecha"


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "entrada", "salida", "minutos_tarde", "falta", "justificada",
                    "tickets", "meta", "puntos_dia", "cumplido")
    list_filter = ("usuario", "falta", "justificada", "cumplido")
    date_hierarchy = "fecha"
    readonly_fields = ("entrada", "inicio_refrigerio", "fin_refrigerio", "salida", "dispositivo", "ip")


@admin.register(CierreMensual)
class CierreMensualAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ("periodo", "posicion_ranking", "usuario", "puntos", "meta_mes", "cumple_requisitos", "pago",
                    "domingo_extra")
    list_filter = ("periodo",)


@admin.register(ParametroIncentivo)
class ParametroIncentivoAdmin(admin.ModelAdmin):
    list_display = ("clave", "valor", "vigente_desde", "creado_por", "creado")
    list_filter = ("clave",)


@admin.register(DispositivoTienda)
class DispositivoTiendaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "creado")
    readonly_fields = ("token",)


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "tipo", "usuario", "detalle", "vista")
    list_filter = ("tipo", "vista", "usuario")
