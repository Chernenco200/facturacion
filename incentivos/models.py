"""
Puntos IC: tareas, libro de puntos, turnos, asistencia y cierre mensual.

Regla de oro: los puntos se guardan como movimientos (MovimientoPuntos).
El total de un trabajador es siempre la SUMA de sus movimientos; nunca
se sobrescribe un total.

Este módulo solo LEE las tablas de ventas, productos, caja, órdenes y
WhatsApp. Las únicas escrituras fuera de esta app son:
  - las fotos y la ficha de la montura (tareas FOTO y COD),
  - el teléfono del cliente (tarea TEL),
  - el campo "atendido" de la cita (resultado CITA).
No toca tickets, detalles de venta ni kardex.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum


class Trabajador(models.Model):
    """Relaciona el usuario del sistema con su nombre de vendedor en el ticket."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trabajador_ic"
    )
    nombre_vendedor = models.CharField(
        max_length=100,
        help_text="Exactamente como aparece en el ticket (campo vendedor). Ej.: Ana",
    )
    participa = models.BooleanField(default=True, help_text="Participa en Puntos IC")
    orden_rotacion = models.PositiveSmallIntegerField(
        default=0, help_text="Orden para rotar la lista de WhatsApp del día"
    )
    es_biselador = models.BooleanField(
        default=False, help_text="Su meta baja por cada orden que pasa a biselado ese día"
    )
    venta_minima_mes = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Requisito para cobrar: venta mínima del mes con IGV (vacío = valor general de Configuración)",
    )

    class Meta:
        verbose_name = "Trabajador"
        verbose_name_plural = "Trabajadores"
        ordering = ["orden_rotacion", "id"]

    def __str__(self):
        return f"{self.nombre_vendedor} ({self.usuario.username})"


class TipoTarea(models.Model):
    FOTO = "FOTO"
    COD = "COD"
    WA_LISTA = "WA_LISTA"
    WA_RESP = "WA_RESP"
    INV = "INV"
    REEL = "REEL"
    CITA = "CITA"
    RESENA = "RESENA"
    TEL = "TEL"
    EXAMEN = "EXAMEN"
    ASIGNADA = "ASIGNADA"

    EN_COLA = (FOTO, COD, WA_LISTA, WA_RESP, INV, TEL)
    RESULTADOS = (REEL, CITA, RESENA, EXAMEN)
    # CITA = "Venta cerrada por WhatsApp" (la calcula el sistema cada noche)

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120)
    puntos = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Puntos por tarea (INV: por unidad contada sin diferencia; TEL: por cada 2 teléfonos)",
    )
    minutos_estandar = models.PositiveSmallIntegerField(default=0)
    prioridad = models.PositiveSmallIntegerField(default=50, help_text="Menor = sale primero en la cola")
    requiere_aprobacion = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipo de tarea"
        verbose_name_plural = "Tipos de tarea"
        ordering = ["prioridad", "codigo"]

    def __str__(self):
        return f"{self.codigo} · {self.nombre} ({self.puntos} pts)"


class Tarea(models.Model):
    PENDIENTE = "PENDIENTE"
    EN_CURSO = "EN_CURSO"
    TERMINADA = "TERMINADA"
    APROBADA = "APROBADA"
    ELIMINADA = "ELIMINADA"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (EN_CURSO, "En curso"),
        (TERMINADA, "Terminada"),
        (APROBADA, "Aprobada"),
        (ELIMINADA, "Eliminada"),
    ]
    ABIERTAS = (PENDIENTE, EN_CURSO)

    tipo = models.ForeignKey(TipoTarea, on_delete=models.PROTECT, related_name="tareas")
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PENDIENTE)
    prioridad = models.PositiveSmallIntegerField(default=50, help_text="Dentro del mismo tipo")

    producto = models.ForeignKey(
        "core.Producto", on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_ic"
    )
    conversacion = models.ForeignKey(
        "whatsapp.ConversacionWhatsApp", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tareas_ic",
    )
    cita = models.ForeignKey(
        "whatsapp.CitaWhatsApp", on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_ic"
    )
    exhibidor = models.CharField(max_length=60, blank=True, default="")
    fecha_objetivo = models.DateField(null=True, blank=True, help_text="Para tareas del día (WA_LISTA)")
    referencia = models.DateTimeField(
        null=True, blank=True, help_text="WA_RESP: hora del mensaje del cliente"
    )
    descripcion = models.CharField(max_length=255, blank=True, default="",
                                   help_text="Tarea asignada por la gerencia: qué hay que hacer")
    fecha_limite = models.DateField(null=True, blank=True, help_text="Tarea asignada: fecha límite")

    asignada_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tareas_ic",
    )
    creada = models.DateTimeField(auto_now_add=True)
    inicio = models.DateTimeField(null=True, blank=True)
    fin = models.DateTimeField(null=True, blank=True)
    pausada_en = models.DateTimeField(null=True, blank=True)
    segundos_pausa = models.PositiveIntegerField(default=0)
    veces_abandonada = models.PositiveSmallIntegerField(default=0)

    puntos = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    evidencia = models.TextField(blank=True, default="", help_text="Link, nota o detalle del trabajo")
    datos = models.JSONField(default=dict, blank=True)

    aprobada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    aprobada_en = models.DateTimeField(null=True, blank=True)
    eliminada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    eliminada_en = models.DateTimeField(null=True, blank=True)
    motivo_eliminacion = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"
        indexes = [
            models.Index(fields=["estado", "tipo", "prioridad"]),
            models.Index(fields=["asignada_a", "estado"]),
        ]

    def __str__(self):
        obj = self.producto or self.conversacion or self.exhibidor or self.fecha_objetivo or ""
        return f"{self.tipo.codigo} #{self.pk} {obj} [{self.estado}]"

    @property
    def minutos_trabajados(self):
        if not self.inicio:
            return 0
        fin = self.fin or self.pausada_en
        if fin is None:
            from django.utils import timezone
            fin = timezone.now()
        seg = (fin - self.inicio).total_seconds() - self.segundos_pausa
        return max(0, round(seg / 60, 1))


class MovimientoPuntos(models.Model):
    TAREA = "TAREA"
    PUNTUALIDAD = "PUNTUALIDAD"
    TARDANZA = "TARDANZA"
    REVERSION = "REVERSION"
    AJUSTE = "AJUSTE"
    TIPOS = [
        (TAREA, "Tarea"),
        (PUNTUALIDAD, "Puntualidad"),
        (TARDANZA, "Tardanza / falta"),
        (REVERSION, "Reversión"),
        (AJUSTE, "Ajuste"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_ic"
    )
    fecha = models.DateField()
    puntos = models.DecimalField(max_digits=7, decimal_places=2)
    tipo = models.CharField(max_length=12, choices=TIPOS)
    tarea = models.ForeignKey(
        Tarea, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos"
    )
    reversa_de = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversion"
    )
    detalle = models.CharField(max_length=255, blank=True, default="")
    clave = models.CharField(
        max_length=80, null=True, blank=True, unique=True,
        help_text="Evita duplicar movimientos automáticos (ej. tardanza del día)",
    )
    creado = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Movimiento de puntos"
        verbose_name_plural = "Movimientos de puntos"
        indexes = [models.Index(fields=["usuario", "fecha"])]
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.usuario} {self.fecha} {self.puntos:+} {self.tipo}"

    @classmethod
    def suma(cls, **filtros):
        return cls.objects.filter(**filtros).aggregate(s=Sum("puntos"))["s"] or Decimal("0")


class Turno(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="turnos_ic")
    fecha = models.DateField()
    hora_entrada = models.TimeField()
    hora_salida = models.TimeField()
    minutos_refrigerio = models.PositiveSmallIntegerField(default=60)
    es_sabado = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        unique_together = [("usuario", "fecha")]
        ordering = ["fecha", "hora_entrada"]

    def __str__(self):
        return f"{self.usuario} {self.fecha} {self.hora_entrada:%H:%M}-{self.hora_salida:%H:%M}"


class Asistencia(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="asistencias_ic"
    )
    fecha = models.DateField()
    entrada = models.DateTimeField(null=True, blank=True)
    inicio_refrigerio = models.DateTimeField(null=True, blank=True)
    fin_refrigerio = models.DateTimeField(null=True, blank=True)
    salida = models.DateTimeField(null=True, blank=True)
    minutos_tarde = models.PositiveSmallIntegerField(default=0)
    minutos_refrigerio_exceso = models.PositiveSmallIntegerField(default=0)
    falta = models.BooleanField(default=False)
    justificada = models.BooleanField(default=False, help_text="Descanso médico o permiso: no resta ni cuenta")
    motivo_justificacion = models.CharField(max_length=200, blank=True, default="")
    dispositivo = models.CharField(max_length=80, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)

    # Resultado del día (lo llena el proceso diario y se recalcula en el cierre)
    tickets = models.PositiveSmallIntegerField(default=0)
    meta = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    puntos_dia = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    cumplido = models.BooleanField(null=True, blank=True)
    procesado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"
        unique_together = [("usuario", "fecha")]
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.usuario} {self.fecha}"

    @property
    def cuenta_como_trabajado(self):
        return not self.justificada and (self.entrada is not None or self.falta)


class CierreMensual(models.Model):
    periodo = models.DateField(help_text="Primer día del mes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cierres_ic")
    puntos = models.DecimalField(max_digits=8, decimal_places=2)
    meta_mes = models.DecimalField(max_digits=8, decimal_places=2)
    dias_trabajados = models.PositiveSmallIntegerField()
    dias_cumplidos = models.PositiveSmallIntegerField()
    requisitos = models.JSONField(default=dict)
    cumple_requisitos = models.BooleanField(default=False)
    pago_calculado = models.DecimalField(max_digits=8, decimal_places=2, help_text="Antes de requisitos")
    pago = models.DecimalField(max_digits=8, decimal_places=2)
    posicion_ranking = models.PositiveSmallIntegerField()
    domingo_extra = models.BooleanField(default=False)
    puntos_venta = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    bono_ventas = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                      help_text="Bono del equipo por venta (parte igual + adicional)")
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    cerrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cierre mensual"
        verbose_name_plural = "Cierres mensuales"
        unique_together = [("periodo", "usuario")]
        ordering = ["-periodo", "posicion_ranking"]

    def __str__(self):
        return f"{self.periodo:%m/%Y} {self.usuario} S/ {self.pago}"


class ParametroIncentivo(models.Model):
    """Valor configurable. Se usa el de vigente_desde más reciente <= fecha."""

    clave = models.CharField(max_length=60)
    valor = models.CharField(max_length=255)
    vigente_desde = models.DateField()
    descripcion = models.CharField(max_length=255, blank=True, default="")
    creado = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Parámetro"
        verbose_name_plural = "Parámetros"
        ordering = ["clave", "-vigente_desde", "-id"]
        indexes = [models.Index(fields=["clave", "vigente_desde"])]

    def __str__(self):
        return f"{self.clave} = {self.valor} (desde {self.vigente_desde})"


class DispositivoTienda(models.Model):
    """Equipo autorizado para marcar asistencia (tablet o PC de la tienda)."""

    nombre = models.CharField(max_length=60)
    token = models.CharField(max_length=64, unique=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dispositivo de la tienda"
        verbose_name_plural = "Dispositivos de la tienda"

    def __str__(self):
        return f"{self.nombre} ({'activo' if self.activo else 'inactivo'})"


class Alerta(models.Model):
    TAREA_RAPIDA = "TAREA_RAPIDA"
    WA_EXCESO = "WA_EXCESO"
    MARCACION = "MARCACION"
    PUNTOS_ALTOS = "PUNTOS_ALTOS"
    FOTO_REPETIDA = "FOTO_REPETIDA"
    ABANDONO = "ABANDONO"
    DEVOLUCION = "DEVOLUCION"
    OTRO = "OTRO"
    TIPOS = [
        (TAREA_RAPIDA, "Tarea demasiado rápida"),
        (WA_EXCESO, "Demasiadas respuestas de WhatsApp en una hora"),
        (MARCACION, "Marcación desde equipo no autorizado"),
        (PUNTOS_ALTOS, "Puntos del día muy altos"),
        (FOTO_REPETIDA, "Foto repetida en otro producto"),
        (ABANDONO, "Tarea abandonada"),
        (DEVOLUCION, "Tarea devuelta a la cola"),
        (OTRO, "Otro"),
    ]

    fecha = models.DateField()
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    detalle = models.CharField(max_length=255)
    tarea = models.ForeignKey(Tarea, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    vista = models.BooleanField(default=False)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        ordering = ["vista", "-creada"]

    def __str__(self):
        return f"{self.fecha} {self.get_tipo_display()}: {self.detalle}"
