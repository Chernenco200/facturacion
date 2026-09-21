from django.core.exceptions import ValidationError
from django.db import models

from decimal import Decimal
from django.db.models import Q
from django.conf import settings



# ============================================================
# 1. CUENTA CONTABLE
# ============================================================

class CuentaContable(models.Model):

    class ClasificacionBalance(models.TextChoices):
        ACTIVO_CORRIENTE = "ACTIVO_CORRIENTE", "Activo corriente"
        ACTIVO_NO_CORRIENTE = "ACTIVO_NO_CORRIENTE", "Activo no corriente"
        PASIVO_CORRIENTE = "PASIVO_CORRIENTE", "Pasivo corriente"
        PASIVO_NO_CORRIENTE = "PASIVO_NO_CORRIENTE", "Pasivo no corriente"
        PATRIMONIO = "PATRIMONIO", "Patrimonio"
        NO_APLICA = "NO_APLICA", "No aplica"

    class TipoCuenta(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        PASIVO = "PASIVO", "Pasivo"
        PATRIMONIO = "PATRIMONIO", "Patrimonio"
        INGRESO = "INGRESO", "Ingreso"
        COSTO = "COSTO", "Costo"
        GASTO = "GASTO", "Gasto"

    class Naturaleza(models.TextChoices):
        DEUDORA = "DEUDORA", "Deudora"
        ACREEDORA = "ACREEDORA", "Acreedora"

    class EstadoFinanciero(models.TextChoices):
        ESF = "ESF", "Estado de Situación Financiera"
        ER = "ER", "Estado de Resultados"
        ECP = "ECP", "Estado de Cambios en el Patrimonio"
        EFE = "EFE", "Estado de Flujos de Efectivo"
        NINGUNO = "NINGUNO", "No aplica"

    codigo = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )

    nombre = models.CharField(
        max_length=200,
    )

    codigo_pcge = models.CharField(
        max_length=20,
        blank=True,
        help_text="Código PCGE de referencia.",
    )

    cuenta_padre = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subcuentas",
    )

    tipo = models.CharField(
        max_length=20,
        choices=TipoCuenta.choices,
    )

    naturaleza = models.CharField(
        max_length=15,
        choices=Naturaleza.choices,
    )

    estado_financiero = models.CharField(
        max_length=10,
        choices=EstadoFinanciero.choices,
        default=EstadoFinanciero.NINGUNO,
    )
    
    clasificacion_balance = models.CharField(
        max_length=30,
        choices=ClasificacionBalance.choices,
        default=ClasificacionBalance.NO_APLICA,
    )


    nivel = models.PositiveSmallIntegerField(
        default=1,
    )

    acepta_movimientos = models.BooleanField(
        default=True,
        help_text=(
            "Si está desactivado, la cuenta solo sirve "
            "para agrupar otras cuentas."
        ),
    )

    activo = models.BooleanField(
        default=True,
    )

    descripcion = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["codigo"]
        verbose_name = "Cuenta contable"
        verbose_name_plural = "Cuentas contables"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if self.cuenta_padre and self.cuenta_padre_id == self.id:
            raise ValidationError(
                "Una cuenta no puede ser su propia cuenta padre."
            )


# ============================================================
# 2. CATEGORÍA GERENCIAL
# ============================================================

class CategoriaGerencial(models.Model):

    codigo = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )

    nombre = models.CharField(
        max_length=200,
    )

    categoria_padre = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subcategorias",
    )

    descripcion = models.TextField(
        blank=True,
    )

    activo = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["codigo"]
        verbose_name = "Categoría gerencial"
        verbose_name_plural = "Categorías gerenciales"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if self.categoria_padre and self.categoria_padre_id == self.id:
            raise ValidationError(
                "Una categoría no puede ser su propia categoría padre."
            )


# ============================================================
# 3. CENTRO DE COSTO
# ============================================================

class CentroCosto(models.Model):

    codigo = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )

    nombre = models.CharField(
        max_length=150,
    )

    centro_padre = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subcentros",
    )

    descripcion = models.TextField(
        blank=True,
    )

    activo = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["codigo"]
        verbose_name = "Centro de costo"
        verbose_name_plural = "Centros de costo"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if self.centro_padre and self.centro_padre_id == self.id:
            raise ValidationError(
                "Un centro de costo no puede ser su propio centro padre."
            )

# ============================================================
# 4. CONCEPTO DE OPERACIÓN
# ============================================================

class ConceptoOperacion(models.Model):

    class TipoOperacion(models.TextChoices):
        GASTO = "GASTO", "Gasto"
        COMPRA = "COMPRA", "Compra"
        VENTA = "VENTA", "Venta"
        INGRESO = "INGRESO", "Ingreso"
        PAGO = "PAGO", "Pago"
        COBRO = "COBRO", "Cobro"
        ACTIVO = "ACTIVO", "Compra de activo"
        FINANCIAMIENTO = "FINANCIAMIENTO", "Financiamiento"
        OTRO = "OTRO", "Otro"

    codigo = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
    )

    nombre = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Nombre que verá y buscará el usuario.",
    )

    # --------------------------------------------------------
    # Navegación jerárquica
    # --------------------------------------------------------

    concepto_padre = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subconceptos",
    )

    es_grupo = models.BooleanField(
        default=False,
        help_text=(
            "Si está activo, el concepto sirve para agrupar "
            "otros conceptos y no debería usarse como operación final."
        ),
    )

    # --------------------------------------------------------
    # Clasificación operativa
    # --------------------------------------------------------

    tipo_operacion = models.CharField(
        max_length=20,
        choices=TipoOperacion.choices,
        default=TipoOperacion.GASTO,
    )

    categoria_gerencial = models.ForeignKey(
        CategoriaGerencial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conceptos_operacion",
    )

    centro_costo = models.ForeignKey(
        CentroCosto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conceptos_operacion",
    )

    # --------------------------------------------------------
    # Clasificación contable automática
    # --------------------------------------------------------

    cuenta_contable = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conceptos_operacion",
        help_text=(
            "Cuenta contable principal sugerida para este concepto."
        ),
    )

    # --------------------------------------------------------
    # Búsqueda amigable
    # --------------------------------------------------------

    palabras_clave = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "Palabras relacionadas separadas por comas. "
            "Ej.: papel, hojas, bond, resma, oficina."
        ),
    )

    sinonimos = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "Sinónimos o formas alternativas usadas por el personal."
        ),
    )

    # --------------------------------------------------------
    # Comportamiento del formulario
    # --------------------------------------------------------

    requiere_proveedor = models.BooleanField(
        default=False,
    )

    requiere_cliente = models.BooleanField(
        default=False,
    )

    requiere_comprobante = models.BooleanField(
        default=False,
    )

    requiere_centro_costo = models.BooleanField(
        default=False,
    )

    permite_cambiar_cuenta = models.BooleanField(
        default=False,
        help_text=(
            "Permite que un usuario autorizado cambie "
            "la cuenta sugerida antes de contabilizar."
        ),
    )

    # --------------------------------------------------------
    # Datos gerenciales
    # --------------------------------------------------------

    es_fijo = models.BooleanField(
        default=False,
        help_text="Indica si normalmente se considera costo/gasto fijo.",
    )

    es_variable = models.BooleanField(
        default=True,
        help_text="Indica si normalmente se considera costo/gasto variable.",
    )

    descripcion = models.TextField(
        blank=True,
    )

    activo = models.BooleanField(
        default=True,
    )

    orden = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        ordering = [
            "orden",
            "nombre",
        ]

        verbose_name = "Concepto de operación"
        verbose_name_plural = "Conceptos de operación"

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()

        if (
            self.concepto_padre
            and self.concepto_padre_id == self.id
        ):
            raise ValidationError(
                "Un concepto no puede ser su propio concepto padre."
            )

        if self.es_grupo and self.cuenta_contable:
            raise ValidationError(
                "Un concepto agrupador no debería tener "
                "una cuenta contable final asignada."
            )

        if (
            not self.es_grupo
            and self.cuenta_contable
            and not self.cuenta_contable.acepta_movimientos
        ):
            raise ValidationError(
                "La cuenta asignada es una cuenta agrupadora "
                "y no acepta movimientos."
            )



# ============================================================
# 5. PERIODO CONTABLE
# ============================================================

class PeriodoContable(models.Model):

    class Estado(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        CERRADO = "CERRADO", "Cerrado"

    anio = models.PositiveIntegerField()

    mes = models.PositiveSmallIntegerField()

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField()

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.ABIERTO,
    )

    fecha_reapertura = models.DateTimeField(
        null=True,
        blank=True,
    )

    reabierto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodos_contables_reabiertos",
    )

    motivo_reapertura = models.TextField(
        blank=True,
        default="",
    )



    class Meta:
        ordering = ["-anio", "-mes"]

        constraints = [
            models.UniqueConstraint(
                fields=["anio", "mes"],
                name="unique_periodo_contable",
            ),

            models.CheckConstraint(
                condition=Q(mes__gte=1) & Q(mes__lte=12),
                name="mes_contable_valido",
            ),
        ]

        verbose_name = "Periodo contable"
        verbose_name_plural = "Periodos contables"

    def __str__(self):
        return f"{self.mes:02d}/{self.anio}"

    def clean(self):
        super().clean()

        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_inicio > self.fecha_fin:
                raise ValidationError(
                    "La fecha inicial no puede ser posterior "
                    "a la fecha final."
                )


# ============================================================
# 6. ASIENTO CONTABLE
# ============================================================

class AsientoContable(models.Model):

    class TipoAsiento(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        AUTOMATICO = "AUTOMATICO", "Automático"
        AJUSTE = "AJUSTE", "Ajuste"
        APERTURA = "APERTURA", "Apertura"
        CIERRE = "CIERRE", "Cierre"

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        CONTABILIZADO = "CONTABILIZADO", "Contabilizado"
        ANULADO = "ANULADO", "Anulado"

    numero = models.PositiveBigIntegerField(
        db_index=True,
    )

    fecha = models.DateField(
        db_index=True,
    )

    periodo = models.ForeignKey(
        PeriodoContable,
        on_delete=models.PROTECT,
        related_name="asientos",
    )

    tipo = models.CharField(
        max_length=15,
        choices=TipoAsiento.choices,
        default=TipoAsiento.MANUAL,
    )

    glosa = models.CharField(
        max_length=500,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )

    origen = models.CharField(
        max_length=50,
        blank=True,
        help_text=(
            "Ej.: VENTA, COMPRA, PAGO, PLANILLA, "
            "DEPRECIACION, MANUAL."
        ),
    )

    origen_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text=(
            "ID del objeto que originó automáticamente el asiento."
        ),
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["fecha", "numero"]

        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "numero"],
                name="unique_numero_asiento_por_periodo",
            ),
        ]

        verbose_name = "Asiento contable"
        verbose_name_plural = "Asientos contables"

    def __str__(self):
        return f"Asiento {self.numero} - {self.fecha}"

    @property
    def total_debe(self):
        return self.detalles.aggregate(
            total=models.Sum("debe")
        )["total"] or Decimal("0.00")

    @property
    def total_haber(self):
        return self.detalles.aggregate(
            total=models.Sum("haber")
        )["total"] or Decimal("0.00")

    @property
    def esta_cuadrado(self):
        return self.total_debe == self.total_haber

    def clean(self):
        super().clean()

        if self.periodo_id:

            if self.periodo.estado == PeriodoContable.Estado.CERRADO:
                raise ValidationError(
                    "No se pueden registrar asientos "
                    "en un periodo cerrado."
                )

            if not (
                self.periodo.fecha_inicio
                <= self.fecha
                <= self.periodo.fecha_fin
            ):
                raise ValidationError(
                    "La fecha del asiento no pertenece "
                    "al periodo seleccionado."
                )


# ============================================================
# 7. DETALLE DE ASIENTO
# ============================================================

class DetalleAsiento(models.Model):

    asiento = models.ForeignKey(
        AsientoContable,
        on_delete=models.CASCADE,
        related_name="detalles",
    )

    secuencia = models.PositiveSmallIntegerField()

    cuenta = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        related_name="movimientos",
    )

    descripcion = models.CharField(
        max_length=300,
        blank=True,
    )

    debe = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    haber = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    categoria_gerencial = models.ForeignKey(
        CategoriaGerencial,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos",
    )

    centro_costo = models.ForeignKey(
        CentroCosto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos",
    )

    referencia = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "Factura, boleta, ticket, orden de trabajo, etc."
        ),
    )

    class Meta:
        ordering = ["asiento", "secuencia"]

        constraints = [
            models.UniqueConstraint(
                fields=["asiento", "secuencia"],
                name="unique_secuencia_detalle_asiento",
            ),

            models.CheckConstraint(
                condition=Q(debe__gte=0),
                name="detalle_debe_no_negativo",
            ),

            models.CheckConstraint(
                condition=Q(haber__gte=0),
                name="detalle_haber_no_negativo",
            ),

            models.CheckConstraint(
                condition=(
                    Q(debe__gt=0, haber=0)
                    |
                    Q(debe=0, haber__gt=0)
                ),
                name="detalle_solo_debe_o_haber",
            ),
        ]

        verbose_name = "Detalle de asiento"
        verbose_name_plural = "Detalles de asiento"

    def __str__(self):
        return (
            f"{self.asiento.numero} - "
            f"{self.cuenta.codigo}"
        )

    def clean(self):
        super().clean()

        if self.cuenta_id:

            if not self.cuenta.activo:
                raise ValidationError({
                    "cuenta":
                    "La cuenta contable se encuentra inactiva."
                })

            if not self.cuenta.acepta_movimientos:
                raise ValidationError({
                    "cuenta":
                    "Esta cuenta es agrupadora y no "
                    "acepta movimientos."
                })

        if self.debe < 0:
            raise ValidationError({
                "debe":
                "El importe del Debe no puede ser negativo."
            })

        if self.haber < 0:
            raise ValidationError({
                "haber":
                "El importe del Haber no puede ser negativo."
            })

        if self.debe > 0 and self.haber > 0:
            raise ValidationError(
                "Una línea no puede tener simultáneamente "
                "importe en Debe y Haber."
            )

        if self.debe == 0 and self.haber == 0:
            raise ValidationError(
                "La línea debe tener importe en Debe o Haber."
            )

# ============================================================
# 8. PROPUESTA DE COSTO DE VENTA
# ============================================================

class PropuestaCostoVenta(models.Model):

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        VALIDADA = "VALIDADA", "Validada"
        CONTABILIZADA = "CONTABILIZADA", "Contabilizada"

    ticket = models.OneToOneField(
        "core.TicketVenta",
        on_delete=models.PROTECT,
        related_name="propuesta_costo_contable",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    validado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    observacion = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["-ticket__fecha_emision", "-ticket__numero"]
        verbose_name = "Propuesta de costo de venta"
        verbose_name_plural = "Propuestas de costo de venta"

    def __str__(self):
        return (
            f"Costo venta Ticket "
            f"{self.ticket.numero:06d}"
        )

    @property
    def costo_total(self):
        return sum(
            (
                detalle.costo_total
                for detalle in self.detalles.all()
            ),
            Decimal("0.00"),
        )

    @property
    def esta_completa(self):
        """
        True si todas las líneas que requieren costo
        tienen un costo unitario informado.
        """
        return not self.detalles.filter(
            costo_unitario__isnull=True
        ).exists()


# ============================================================
# 9. DETALLE DE PROPUESTA DE COSTO DE VENTA
# ============================================================

class DetallePropuestaCostoVenta(models.Model):

    class OrigenCosto(models.TextChoices):
        KARDEX = (
            "KARDEX",
            "Kardex de la venta",
        )
        PROMEDIO = (
            "PROMEDIO",
            "Costo promedio ponderado",
        )
        MANUAL = (
            "MANUAL",
            "Ingresado manualmente",
        )
        SIN_COSTO = (
            "SIN_COSTO",
            "Sin costo registrado",
        )

    propuesta = models.ForeignKey(
        PropuestaCostoVenta,
        on_delete=models.CASCADE,
        related_name="detalles",
    )

    detalle_ticket = models.OneToOneField(
        "core.DetalleTicketVenta",
        on_delete=models.PROTECT,
        related_name="costo_contable",
    )

    producto = models.ForeignKey(
        "core.Producto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )

    origen_costo = models.CharField(
        max_length=15,
        choices=OrigenCosto.choices,
        default=OrigenCosto.SIN_COSTO,
    )

    validado = models.BooleanField(
        default=False,
    )

    observacion = models.CharField(
        max_length=300,
        blank=True,
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Detalle de costo de venta"
        verbose_name_plural = "Detalles de costo de venta"

    def __str__(self):
        return self.detalle_ticket.descripcion

    @property
    def costo_total(self):

        if self.costo_unitario is None:
            return Decimal("0.00")

        return (
            self.cantidad
            * self.costo_unitario
        )

# ============================================================
# 10. COMPRA DIRECTA PARA UNA VENTA
# ============================================================
class CompraDirectaVenta(models.Model):

    class FormaPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        BANCO = "BANCO", "Banco / transferencia"
        CREDITO = "CREDITO", "Crédito proveedor"
        PARCIAL = "PARCIAL", "Pago parcial"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CONTABILIZADA = "CONTABILIZADA", "Contabilizada"

    detalle_costo = models.OneToOneField(
        DetallePropuestaCostoVenta,
        on_delete=models.PROTECT,
        related_name="compra_directa",
    )

    proveedor_nombre = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Nombre del proveedor. Más adelante podremos "
            "reemplazarlo por un modelo Proveedor."
        ),
    )

    fecha_compra = models.DateField()

    tipo_documento = models.CharField(
        max_length=30,
        blank=True,
        help_text=(
            "Factura, boleta, recibo, "
            "sin comprobante, etc."
        ),
    )

    numero_documento = models.CharField(
        max_length=50,
        blank=True,
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
    )

    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )

    # ========================================================
    # CONDICIÓN INICIAL DE PAGO
    # ========================================================

    forma_pago = models.CharField(
        max_length=15,
        choices=FormaPago.choices,
        default=FormaPago.EFECTIVO,
    )

    monto_pagado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Monto pagado al proveedor al momento "
            "de registrar inicialmente la compra."
        ),
    )

    fecha_pago = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Fecha del pago inicial realizado."
        ),
    )

    fecha_vencimiento = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Fecha de vencimiento de la deuda "
            "con el proveedor."
        ),
    )

    cuenta_pago = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compras_directas_pagadas",
        help_text=(
            "Cuenta utilizada para el pago inicial. "
            "Ej.: 10101 Caja o 10401 Banco."
        ),
    )

    cuenta_proveedor = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compras_directas_credito",
        help_text=(
            "Cuenta por pagar al proveedor cuando "
            "existe saldo pendiente."
        ),
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    observacion = models.TextField(
        blank=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    confirmado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "-fecha_compra",
            "-id",
        ]

        verbose_name = (
            "Compra directa para venta"
        )

        verbose_name_plural = (
            "Compras directas para venta"
        )

    def __str__(self):

        return (
            f"Compra directa - "
            f"{self.detalle_costo.detalle_ticket.descripcion}"
        )

    # ========================================================
    # IMPORTES
    # ========================================================

    @property
    def costo_total(self):

        return (
            self.cantidad
            * self.costo_unitario
        )

    @property
    def pagos_posteriores_total(self):

        return sum(
            (
                pago.monto
                for pago in self.pagos_proveedor.exclude(
                    estado=PagoProveedor.Estado.ANULADO
                )
            ),
            Decimal("0.00"),
        )

    @property
    def total_pagado(self):

        pago_inicial = (
            self.monto_pagado
            or Decimal("0.00")
        )

        return (
            pago_inicial
            + self.pagos_posteriores_total
        )

    @property
    def saldo_pendiente(self):

        saldo = (
            self.costo_total
            - self.total_pagado
        )

        if saldo < Decimal("0.00"):
            return Decimal("0.00")

        return saldo

    @property
    def esta_pagada(self):

        return (
            self.saldo_pendiente
            == Decimal("0.00")
        )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    def clean(self):

        super().clean()

        if self.cantidad is None:

            raise ValidationError({
                "cantidad":
                "Debe ingresar la cantidad."
            })

        if self.cantidad <= 0:

            raise ValidationError({
                "cantidad":
                "La cantidad debe ser mayor que cero."
            })

        if self.costo_unitario is None:

            raise ValidationError({
                "costo_unitario":
                "Debe ingresar el costo unitario."
            })

        if self.costo_unitario <= 0:

            raise ValidationError({
                "costo_unitario":
                "El costo unitario debe ser mayor que cero."
            })

        total = self.costo_total

        monto_pagado = (
            self.monto_pagado
            or Decimal("0.00")
        )

        if monto_pagado < Decimal("0.00"):

            raise ValidationError({
                "monto_pagado":
                "El monto pagado no puede ser negativo."
            })

        if monto_pagado > total:

            raise ValidationError({
                "monto_pagado":
                "El monto pagado no puede superar "
                "el importe total de la compra."
            })

        # ====================================================
        # CRÉDITO TOTAL
        # ====================================================

        if (
            self.forma_pago
            == self.FormaPago.CREDITO
        ):

            if monto_pagado != Decimal("0.00"):

                raise ValidationError({
                    "monto_pagado":
                    "Una compra totalmente al crédito "
                    "debe iniciar con monto pagado cero."
                })

            if not self.cuenta_proveedor:

                raise ValidationError({
                    "cuenta_proveedor":
                    "Debe seleccionar una cuenta "
                    "por pagar al proveedor."
                })

            if self.cuenta_pago:

                raise ValidationError({
                    "cuenta_pago":
                    "La compra totalmente al crédito "
                    "no debe registrar una cuenta "
                    "de pago inicial."
                })

            if self.fecha_pago:

                raise ValidationError({
                    "fecha_pago":
                    "La compra totalmente al crédito "
                    "no debe registrar fecha de "
                    "pago inicial."
                })

        # ====================================================
        # PAGO PARCIAL
        # ====================================================

        elif (
            self.forma_pago
            == self.FormaPago.PARCIAL
        ):

            if monto_pagado <= Decimal("0.00"):

                raise ValidationError({
                    "monto_pagado":
                    "El pago parcial debe ser "
                    "mayor que cero."
                })

            if monto_pagado >= total:

                raise ValidationError({
                    "monto_pagado":
                    "El pago parcial debe ser menor "
                    "que el total de la compra."
                })

            if not self.cuenta_pago:

                raise ValidationError({
                    "cuenta_pago":
                    "Debe seleccionar la cuenta desde "
                    "la que se realizó el pago parcial."
                })

            if not self.cuenta_proveedor:

                raise ValidationError({
                    "cuenta_proveedor":
                    "Debe seleccionar la cuenta "
                    "por pagar donde quedará el saldo."
                })

            if not self.fecha_pago:

                raise ValidationError({
                    "fecha_pago":
                    "Debe ingresar la fecha "
                    "del pago parcial."
                })

        # ====================================================
        # CONTADO
        # ====================================================

        else:

            if monto_pagado != total:

                raise ValidationError({
                    "monto_pagado":
                    "Cuando la compra está pagada "
                    "al contado, el monto pagado "
                    "debe ser igual al importe total."
                })

            if not self.cuenta_pago:

                raise ValidationError({
                    "cuenta_pago":
                    "Debe seleccionar la cuenta "
                    "desde la que se realizó el pago."
                })

            if not self.fecha_pago:

                raise ValidationError({
                    "fecha_pago":
                    "Debe registrar la fecha del pago."
                })

            if self.cuenta_proveedor:

                raise ValidationError({
                    "cuenta_proveedor":
                    "Una compra totalmente pagada "
                    "no debe generar cuenta por pagar."
                })

        # ====================================================
        # FECHAS
        # ====================================================

        if (
            self.fecha_vencimiento
            and self.fecha_vencimiento
            < self.fecha_compra
        ):

            raise ValidationError({
                "fecha_vencimiento":
                "La fecha de vencimiento no puede "
                "ser anterior a la fecha de compra."
            })


# ============================================================
# PAGOS POSTERIORES A PROVEEDORES
# ============================================================

class PagoProveedor(models.Model):

    class Estado(models.TextChoices):
        REGISTRADO = (
            "REGISTRADO",
            "Registrado",
        )

        CONTABILIZADO = (
            "CONTABILIZADO",
            "Contabilizado",
        )

        ANULADO = (
            "ANULADO",
            "Anulado",
        )

    compra = models.ForeignKey(
        CompraDirectaVenta,
        on_delete=models.PROTECT,
        related_name="pagos_proveedor",
    )

    fecha_pago = models.DateField()

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    cuenta_pago = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        related_name="pagos_a_proveedores",
        help_text=(
            "Cuenta desde la que se realizó el pago. "
            "Ej.: 10101 Caja o 10401 Banco."
        ),
    )

    observacion = models.TextField(
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.REGISTRADO,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:

        ordering = [
            "-fecha_pago",
            "-id",
        ]

        verbose_name = (
            "Pago a proveedor"
        )

        verbose_name_plural = (
            "Pagos a proveedores"
        )

    def __str__(self):

        return (
            f"Pago proveedor - "
            f"{self.compra.proveedor_nombre or 'Sin proveedor'} "
            f"- S/ {self.monto}"
        )

    def clean(self):

        super().clean()

        # ====================================================
        # COMPRA
        # ====================================================

        if not self.compra_id:
            return

        # ====================================================
        # MONTO
        # ====================================================

        if self.monto is None:

            raise ValidationError({
                "monto":
                "Debe ingresar el monto del pago."
            })

        if self.monto <= Decimal("0.00"):

            raise ValidationError({
                "monto":
                "El monto del pago debe ser "
                "mayor que cero."
            })

        # ====================================================
        # FECHA
        # ====================================================

        if (
            self.fecha_pago
            and self.compra.fecha_compra
            and self.fecha_pago
            < self.compra.fecha_compra
        ):

            raise ValidationError({
                "fecha_pago":
                "La fecha del pago no puede ser "
                "anterior a la fecha de compra."
            })

        # ====================================================
        # SALDO DISPONIBLE ANTES DE ESTE PAGO
        # ====================================================

        pagos_previos = (
            self.compra.pagos_proveedor
            .exclude(
                estado=self.Estado.ANULADO
            )
        )

        if self.pk:

            pagos_previos = (
                pagos_previos.exclude(
                    pk=self.pk
                )
            )

        total_pagos_previos = sum(
            (
                pago.monto
                for pago in pagos_previos
            ),
            Decimal("0.00"),
        )

        pago_inicial = (
            self.compra.monto_pagado
            or Decimal("0.00")
        )

        saldo_antes_pago = (
            self.compra.costo_total
            - pago_inicial
            - total_pagos_previos
        )

        if self.monto > saldo_antes_pago:

            raise ValidationError({
                "monto":
                (
                    "El pago no puede superar el saldo "
                    f"pendiente de S/ "
                    f"{saldo_antes_pago:.2f}."
                )
            })

        # ====================================================
        # CUENTA DE PAGO
        # ====================================================

        if not self.cuenta_pago_id:

            raise ValidationError({
                "cuenta_pago":
                "Debe seleccionar la cuenta desde "
                "la que se realizó el pago."
            })
# ============================================================
# 11. SERVICIO DE TERCERO VINCULADO A UNA VENTA
# ============================================================

class ServicioTerceroVenta(models.Model):

    class TipoServicio(models.TextChoices):
        MEDIDA_VISTA = "MEDIDA_VISTA", "Medida de vista"
        BISELADO = "BISELADO", "Biselado"
        COLOREADO = "COLOREADO", "Coloreado"
        FLEX = "FLEX", "Cambio de Flex"
        OTRO = "OTRO", "Otro"

    class FormaPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        BANCO = "BANCO", "Banco / transferencia"
        CREDITO = "CREDITO", "Crédito proveedor"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PROPUESTO = "PROPUESTO", "Propuesto"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        CONTABILIZADO = "CONTABILIZADO", "Contabilizado"

    propuesta = models.ForeignKey(
        PropuestaCostoVenta,
        on_delete=models.CASCADE,
        related_name="servicios_terceros",
    )

    tipo_servicio = models.CharField(
        max_length=20,
        choices=TipoServicio.choices,
    )

    descripcion = models.CharField(
        max_length=200,
        blank=True,
    )

    proveedor_nombre = models.CharField(
        max_length=200,
        blank=True,
    )

    fecha_servicio = models.DateField(
        null=True,
        blank=True,
    )

    costo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    forma_pago = models.CharField(
        max_length=15,
        choices=FormaPago.choices,
        blank=True,
    )

    cuenta_pago = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="servicios_terceros_pagados",
    )

    cuenta_proveedor = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="servicios_terceros_credito",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PROPUESTO,
    )

    creado_automaticamente = models.BooleanField(
        default=True,
    )

    observacion = models.TextField(
        blank=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["tipo_servicio", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["propuesta", "tipo_servicio"],
                name="unique_servicio_tercero_por_propuesta",
            ),
        ]

        verbose_name = "Servicio de tercero para venta"
        verbose_name_plural = "Servicios de tercero para venta"

    def __str__(self):
        return (
            f"{self.get_tipo_servicio_display()} - "
            f"Ticket {self.propuesta.ticket.numero:06d}"
        )

    def clean(self):
        super().clean()

        if self.costo < 0:
            raise ValidationError({
                "costo":
                "El costo del servicio no puede ser negativo."
            })

        # Si queda en cero, sigue siendo solo una propuesta.
        if self.costo == 0:
            return

        if self.forma_pago == self.FormaPago.CREDITO:

            if not self.cuenta_proveedor:
                raise ValidationError({
                    "cuenta_proveedor":
                    "Debe seleccionar la cuenta por pagar."
                })

        else:

            if not self.cuenta_pago:
                raise ValidationError({
                    "cuenta_pago":
                    "Debe seleccionar la cuenta de pago."
                })

# ============================================================
# OPERACIÓN CONTABLE MANUAL / NO GENERADA POR FACTURACIÓN
# ============================================================

class OperacionContable(models.Model):

    class FormaPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        BANCO = "BANCO", "Banco / transferencia"
        CREDITO = "CREDITO", "Crédito"
        PARCIAL = "PARCIAL", "Pago parcial"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        CONTABILIZADA = "CONTABILIZADA", "Contabilizada"
        ANULADA = "ANULADA", "Anulada"

    # --------------------------------------------------------
    # DATOS GENERALES
    # --------------------------------------------------------

    fecha = models.DateField(
        db_index=True,
    )

    concepto = models.ForeignKey(
        ConceptoOperacion,
        on_delete=models.PROTECT,
        related_name="operaciones_contables",
    )

    descripcion = models.CharField(
        max_length=300,
        blank=True,
        help_text=(
            "Detalle adicional de la operación. "
            "Ej.: Alquiler correspondiente a agosto 2026."
        ),
    )

    # --------------------------------------------------------
    # TERCERO / COMPROBANTE
    # --------------------------------------------------------

    proveedor_nombre = models.CharField(
        max_length=200,
        blank=True,
    )

    cliente_nombre = models.CharField(
        max_length=200,
        blank=True,
    )

    tipo_documento = models.CharField(
        max_length=50,
        blank=True,
        help_text=(
            "Factura, boleta, recibo, voucher, etc."
        ),
    )

    numero_documento = models.CharField(
        max_length=100,
        blank=True,
    )

    # --------------------------------------------------------
    # IMPORTE
    # --------------------------------------------------------

    importe_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    # --------------------------------------------------------
    # FORMA DE PAGO
    # --------------------------------------------------------

    forma_pago = models.CharField(
        max_length=20,
        choices=FormaPago.choices,
    )

    monto_pagado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    fecha_pago = models.DateField(
        null=True,
        blank=True,
    )

    cuenta_pago = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones_contables_pagadas",
        help_text=(
            "Cuenta de Caja o Banco utilizada para pagar."
        ),
    )

    cuenta_por_pagar = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operaciones_contables_por_pagar",
        help_text=(
            "Cuenta por pagar utilizada cuando la operación "
            "es al crédito o parcialmente pagada."
        ),
    )

    fecha_vencimiento = models.DateField(
        null=True,
        blank=True,
    )

    # --------------------------------------------------------
    # ASIENTO GENERADO
    # --------------------------------------------------------

    asiento = models.OneToOneField(
        AsientoContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operacion_contable",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
        db_index=True,
    )

    observacion = models.TextField(
        blank=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "-fecha",
            "-id",
        ]

        verbose_name = "Operación contable"
        verbose_name_plural = "Operaciones contables"

    def __str__(self):
        return (
            f"{self.fecha} - "
            f"{self.concepto.nombre} - "
            f"S/ {self.importe_total}"
        )

    # --------------------------------------------------------
    # PROPIEDADES
    # --------------------------------------------------------

    @property
    def pagos_posteriores_total(self):

        if not self.pk:
            return Decimal("0.00")

        return sum(
            (
                pago.monto
                for pago in self.pagos_posteriores.exclude(
                    estado=PagoOperacionContable.Estado.ANULADO
                )
            ),
            Decimal("0.00"),
        )

    @property
    def total_pagado(self):

        return (
            (self.monto_pagado or Decimal("0.00"))
            + self.pagos_posteriores_total
        )

    @property
    def saldo_pendiente(self):

        saldo = (
            self.importe_total
            - self.total_pagado
        )

        if saldo < Decimal("0.00"):
            return Decimal("0.00")

        return saldo

    @property
    def esta_pagada(self):

        return (
            self.saldo_pendiente
            == Decimal("0.00")
        )

    @property
    def cuenta_principal(self):
        return self.concepto.cuenta_contable

    @property
    def categoria_gerencial(self):
        return self.concepto.categoria_gerencial

    @property
    def centro_costo(self):
        return self.concepto.centro_costo

    # --------------------------------------------------------
    # VALIDACIONES
    # --------------------------------------------------------

    def clean(self):

        super().clean()

        errores = {}

        # ====================================================
        # CONCEPTO
        # ====================================================

        if self.concepto_id:

            if not self.concepto.activo:
                errores["concepto"] = (
                    "El concepto seleccionado está inactivo."
                )

            elif self.concepto.es_grupo:
                errores["concepto"] = (
                    "Debe seleccionar un concepto final "
                    "y no un grupo."
                )

            elif not self.concepto.cuenta_contable_id:
                errores["concepto"] = (
                    "El concepto seleccionado no tiene "
                    "una cuenta contable configurada."
                )

            elif (
                not self.concepto.cuenta_contable.activo
            ):
                errores["concepto"] = (
                    "La cuenta contable del concepto "
                    "se encuentra inactiva."
                )

            elif (
                not self.concepto
                .cuenta_contable
                .acepta_movimientos
            ):
                errores["concepto"] = (
                    "La cuenta contable asignada al concepto "
                    "no acepta movimientos."
                )

        # ====================================================
        # REQUISITOS DEL CONCEPTO
        # ====================================================

        if self.concepto_id:

            if (
                self.concepto.requiere_proveedor
                and not self.proveedor_nombre.strip()
            ):
                errores["proveedor_nombre"] = (
                    "Este concepto requiere identificar "
                    "al proveedor."
                )

            if (
                self.concepto.requiere_cliente
                and not self.cliente_nombre.strip()
            ):
                errores["cliente_nombre"] = (
                    "Este concepto requiere identificar "
                    "al cliente."
                )

            if (
                self.concepto.requiere_comprobante
                and (
                    not self.tipo_documento.strip()
                    or not self.numero_documento.strip()
                )
            ):
                errores["numero_documento"] = (
                    "Este concepto requiere registrar "
                    "el comprobante."
                )

        # ====================================================
        # IMPORTE
        # ====================================================

        if (
            self.importe_total is None
            or self.importe_total
            <= Decimal("0.00")
        ):
            errores["importe_total"] = (
                "El importe total debe ser mayor que cero."
            )

        if (
            self.monto_pagado is not None
            and self.monto_pagado
            < Decimal("0.00")
        ):
            errores["monto_pagado"] = (
                "El monto pagado no puede ser negativo."
            )

        if (
            self.importe_total is not None
            and self.monto_pagado is not None
            and self.monto_pagado > self.importe_total
        ):
            errores["monto_pagado"] = (
                "El monto pagado no puede superar "
                "el importe total."
            )

        # ====================================================
        # PAGO AL CONTADO
        # ====================================================

        if self.forma_pago in [
            self.FormaPago.EFECTIVO,
            self.FormaPago.BANCO,
            self.FormaPago.OTRO,
        ]:

            if (
                self.importe_total is not None
                and self.monto_pagado
                != self.importe_total
            ):
                errores["monto_pagado"] = (
                    "Cuando la operación está pagada "
                    "totalmente, el monto pagado debe ser "
                    "igual al importe total."
                )

            if not self.fecha_pago:
                errores["fecha_pago"] = (
                    "Debe indicar la fecha de pago."
                )

            if not self.cuenta_pago_id:
                errores["cuenta_pago"] = (
                    "Debe seleccionar la cuenta utilizada "
                    "para realizar el pago."
                )

            if self.cuenta_por_pagar_id:
                errores["cuenta_por_pagar"] = (
                    "Una operación totalmente pagada "
                    "no debe tener cuenta por pagar."
                )

        # ====================================================
        # CRÉDITO
        # ====================================================

        elif (
            self.forma_pago
            == self.FormaPago.CREDITO
        ):

            if (
                self.monto_pagado
                != Decimal("0.00")
            ):
                errores["monto_pagado"] = (
                    "Una operación totalmente al crédito "
                    "debe tener monto pagado igual a cero."
                )

            if self.fecha_pago:
                errores["fecha_pago"] = (
                    "Una operación totalmente al crédito "
                    "no debe registrar una fecha de pago inicial."
                )

            if self.cuenta_pago_id:
                errores["cuenta_pago"] = (
                    "Una operación totalmente al crédito "
                    "no debe registrar una cuenta de pago inicial."
                )

            if not self.cuenta_por_pagar_id:
                errores["cuenta_por_pagar"] = (
                    "Debe seleccionar la cuenta por pagar."
                )

        # ====================================================
        # PAGO PARCIAL
        # ====================================================

        elif (
            self.forma_pago
            == self.FormaPago.PARCIAL
        ):

            if (
                self.importe_total is not None
                and (
                    self.monto_pagado
                    <= Decimal("0.00")
                    or self.monto_pagado
                    >= self.importe_total
                )
            ):
                errores["monto_pagado"] = (
                    "En una operación parcialmente pagada, "
                    "el monto pagado debe ser mayor que cero "
                    "y menor que el importe total."
                )

            if not self.fecha_pago:
                errores["fecha_pago"] = (
                    "Debe indicar la fecha del pago inicial."
                )

            if not self.cuenta_pago_id:
                errores["cuenta_pago"] = (
                    "Debe seleccionar la cuenta utilizada "
                    "para el pago inicial."
                )

            if not self.cuenta_por_pagar_id:
                errores["cuenta_por_pagar"] = (
                    "Debe seleccionar la cuenta por pagar "
                    "del saldo pendiente."
                )

        # ====================================================
        # VALIDAR CUENTA DE PAGO
        # ====================================================

        if self.cuenta_pago_id:

            if not self.cuenta_pago.activo:
                errores["cuenta_pago"] = (
                    "La cuenta de pago está inactiva."
                )

            elif not self.cuenta_pago.acepta_movimientos:
                errores["cuenta_pago"] = (
                    "La cuenta de pago no acepta movimientos."
                )

        # ====================================================
        # VALIDAR CUENTA POR PAGAR
        # ====================================================

        if self.cuenta_por_pagar_id:

            if not self.cuenta_por_pagar.activo:
                errores["cuenta_por_pagar"] = (
                    "La cuenta por pagar está inactiva."
                )

            elif (
                not self.cuenta_por_pagar
                .acepta_movimientos
            ):
                errores["cuenta_por_pagar"] = (
                    "La cuenta por pagar no acepta movimientos."
                )

        # ====================================================
        # FECHAS
        # ====================================================

        if (
            self.fecha_pago
            and self.fecha
            and self.fecha_pago < self.fecha
        ):
            errores["fecha_pago"] = (
                "La fecha de pago no puede ser anterior "
                "a la fecha de la operación."
            )

        if (
            self.fecha_vencimiento
            and self.fecha
            and self.fecha_vencimiento < self.fecha
        ):
            errores["fecha_vencimiento"] = (
                "La fecha de vencimiento no puede ser anterior "
                "a la fecha de la operación."
            )

        # ====================================================
        # NO MODIFICAR OPERACIONES CONTABILIZADAS
        # ====================================================

        if (
            self.pk
            and self.estado
            == self.Estado.CONTABILIZADA
        ):

            original = (
                OperacionContable.objects
                .filter(pk=self.pk)
                .first()
            )

            if original:

                campos_protegidos = [
                    "fecha",
                    "concepto_id",
                    "importe_total",
                    "forma_pago",
                    "monto_pagado",
                    "fecha_pago",
                    "cuenta_pago_id",
                    "cuenta_por_pagar_id",
                ]

                for campo in campos_protegidos:

                    if (
                        getattr(original, campo)
                        != getattr(self, campo)
                    ):
                        raise ValidationError(
                            "Una operación contabilizada "
                            "no puede ser modificada."
                        )

        if errores:
            raise ValidationError(errores)


class PagoOperacionContable(models.Model):

    class Estado(models.TextChoices):
        REGISTRADO = (
            "REGISTRADO",
            "Registrado",
        )

        CONTABILIZADO = (
            "CONTABILIZADO",
            "Contabilizado",
        )

        ANULADO = (
            "ANULADO",
            "Anulado",
        )

    # --------------------------------------------------------
    # OPERACIÓN
    # --------------------------------------------------------

    operacion = models.ForeignKey(
        OperacionContable,
        on_delete=models.PROTECT,
        related_name="pagos_posteriores",
    )

    # --------------------------------------------------------
    # PAGO
    # --------------------------------------------------------

    fecha_pago = models.DateField(
        db_index=True,
    )

    monto = models.DecimalField(
        max_digits=15,
        decimal_places=2,
    )

    cuenta_pago = models.ForeignKey(
        CuentaContable,
        on_delete=models.PROTECT,
        related_name="pagos_operaciones_contables",
    )

    observacion = models.TextField(
        blank=True,
    )

    # --------------------------------------------------------
    # ASIENTO
    # --------------------------------------------------------

    asiento = models.OneToOneField(
        AsientoContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pago_operacion_contable",
    )

    # --------------------------------------------------------
    # ESTADO
    # --------------------------------------------------------

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.REGISTRADO,
        db_index=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:

        ordering = [
            "-fecha_pago",
            "-id",
        ]

        verbose_name = (
            "Pago de operación contable"
        )

        verbose_name_plural = (
            "Pagos de operaciones contables"
        )

    def __str__(self):

        return (
            f"{self.fecha_pago} - "
            f"{self.operacion.concepto.nombre} - "
            f"S/ {self.monto}"
        )

    # --------------------------------------------------------
    # VALIDACIONES
    # --------------------------------------------------------

    def clean(self):

        super().clean()

        errores = {}

        # ====================================================
        # OPERACIÓN
        # ====================================================

        if self.operacion_id:

            if (
                self.operacion.estado
                != OperacionContable.Estado.CONTABILIZADA
            ):
                errores["operacion"] = (
                    "Solo se pueden registrar pagos de "
                    "operaciones contabilizadas."
                )

            if not self.operacion.cuenta_por_pagar_id:
                errores["operacion"] = (
                    "La operación no tiene una cuenta "
                    "por pagar asociada."
                )

        # ====================================================
        # MONTO
        # ====================================================

        if (
            self.monto is None
            or self.monto <= Decimal("0.00")
        ):
            errores["monto"] = (
                "El monto del pago debe ser mayor que cero."
            )

        # ====================================================
        # SALDO DISPONIBLE
        # ====================================================

        if (
            self.operacion_id
            and self.monto is not None
            and self.monto > Decimal("0.00")
        ):

            pagos_anteriores = (
                PagoOperacionContable.objects
                .filter(
                    operacion=self.operacion,
                )
                .exclude(
                    estado=self.Estado.ANULADO,
                )
            )

            if self.pk:
                pagos_anteriores = (
                    pagos_anteriores.exclude(
                        pk=self.pk,
                    )
                )

            total_pagos_anteriores = sum(
                (
                    pago.monto
                    for pago in pagos_anteriores
                ),
                Decimal("0.00"),
            )

            saldo_disponible = (
                self.operacion.importe_total
                - (
                    self.operacion.monto_pagado
                    or Decimal("0.00")
                )
                - total_pagos_anteriores
            )

            if self.monto > saldo_disponible:

                errores["monto"] = (
                    "El monto del pago no puede superar "
                    f"el saldo pendiente de S/ "
                    f"{saldo_disponible:.2f}."
                )

        # ====================================================
        # CUENTA DE PAGO
        # ====================================================

        if self.cuenta_pago_id:

            if not self.cuenta_pago.activo:

                errores["cuenta_pago"] = (
                    "La cuenta de pago está inactiva."
                )

            elif not self.cuenta_pago.acepta_movimientos:

                errores["cuenta_pago"] = (
                    "La cuenta de pago no acepta movimientos."
                )

            elif (
                self.cuenta_pago.tipo
                != CuentaContable.TipoCuenta.ACTIVO
            ):

                errores["cuenta_pago"] = (
                    "La cuenta de pago debe ser una "
                    "cuenta de activo, como Caja o Banco."
                )

        # ====================================================
        # FECHA
        # ====================================================

        if (
            self.operacion_id
            and self.fecha_pago
            and self.fecha_pago < self.operacion.fecha
        ):

            errores["fecha_pago"] = (
                "La fecha de pago no puede ser anterior "
                "a la fecha de la operación."
            )

        # ====================================================
        # NO MODIFICAR UN PAGO CONTABILIZADO
        # ====================================================

        if (
            self.pk
            and self.estado
            == self.Estado.CONTABILIZADO
        ):

            original = (
                PagoOperacionContable.objects
                .filter(
                    pk=self.pk,
                )
                .first()
            )

            if original:

                campos_protegidos = [
                    "operacion_id",
                    "fecha_pago",
                    "monto",
                    "cuenta_pago_id",
                ]

                for campo in campos_protegidos:

                    if (
                        getattr(original, campo)
                        != getattr(self, campo)
                    ):

                        raise ValidationError(
                            "Un pago contabilizado "
                            "no puede ser modificado."
                        )

        if errores:

            raise ValidationError(
                errores
            )
# ============================================================
# NOTAS DE CRÉDITO
# ============================================================




class NotaCredito(models.Model):

    class Motivo(models.TextChoices):

        ERROR_PRECIO = (
            "ERROR_PRECIO",
            "Error de precio",
        )

        ANULACION_TOTAL = (
            "ANULACION_TOTAL",
            "Anulación total de la venta",
        )

        DEVOLUCION_PRODUCTO = (
            "DEVOLUCION_PRODUCTO",
            "Devolución de producto",
        )

        DESCUENTO_POSTERIOR = (
            "DESCUENTO_POSTERIOR",
            "Descuento posterior",
        )

        OTRO = (
            "OTRO",
            "Otro",
        )


    class Estado(models.TextChoices):

        BORRADOR = (
            "BORRADOR",
            "Borrador",
        )

        CONTABILIZADA = (
            "CONTABILIZADA",
            "Contabilizada",
        )

        ANULADA = (
            "ANULADA",
            "Anulada",
        )


    numero = models.PositiveBigIntegerField(
        unique=True,
        db_index=True,
    )

    ticket = models.ForeignKey(
        "core.TicketVenta",
        on_delete=models.PROTECT,
        related_name="notas_credito",
    )

    fecha_emision = models.DateField(
        db_index=True,
    )

    motivo = models.CharField(
        max_length=30,
        choices=Motivo.choices,
    )

    descripcion = models.CharField(
        max_length=300,
        blank=True,
    )

    # --------------------------------------------------------
    # IMPORTE TOTAL DE LA NOTA DE CRÉDITO
    # --------------------------------------------------------

    monto_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    # --------------------------------------------------------
    # DESTINO DEL IMPORTE
    #
    # Ejemplo:
    #
    # Nota de crédito S/ 100
    #
    # Cliente todavía debía S/ 60:
    #
    # monto_aplicado_saldo = 60
    # monto_devuelto       = 40
    #
    # --------------------------------------------------------

    monto_aplicado_saldo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    monto_devuelto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # --------------------------------------------------------
    # CUENTA UTILIZADA SI EXISTE DEVOLUCIÓN DE DINERO
    #
    # Ejemplos:
    # 10101 Caja
    # 10401 Banco
    #
    # --------------------------------------------------------

    cuenta_devolucion = models.ForeignKey(
        "CuentaContable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notas_credito_devueltas",
    )

    observacion = models.TextField(
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
        db_index=True,
    )

    asiento = models.OneToOneField(
        "AsientoContable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="nota_credito",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    contabilizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    class Meta:

        ordering = [
            "-fecha_emision",
            "-numero",
        ]

        verbose_name = (
            "Nota de crédito"
        )

        verbose_name_plural = (
            "Notas de crédito"
        )


    def __str__(self):

        return (
            f"NC {self.numero:06d} - "
            f"Ticket {self.ticket.numero:06d}"
        )


    @property
    def monto_distribuido(self):

        return (
            (self.monto_aplicado_saldo or Decimal("0.00"))
            +
            (self.monto_devuelto or Decimal("0.00"))
        )


    def clean(self):

        super().clean()

        monto_total = (
            self.monto_total
            or Decimal("0.00")
        )

        aplicado = (
            self.monto_aplicado_saldo
            or Decimal("0.00")
        )

        devuelto = (
            self.monto_devuelto
            or Decimal("0.00")
        )


        # ====================================================
        # 1. MONTO TOTAL
        # ====================================================

        if monto_total <= Decimal("0.00"):

            raise ValidationError({
                "monto_total":
                    "El monto de la nota de crédito "
                    "debe ser mayor que cero."
            })


        # ====================================================
        # 2. IMPORTES NO NEGATIVOS
        # ====================================================

        if aplicado < Decimal("0.00"):

            raise ValidationError({
                "monto_aplicado_saldo":
                    "El monto aplicado al saldo "
                    "no puede ser negativo."
            })


        if devuelto < Decimal("0.00"):

            raise ValidationError({
                "monto_devuelto":
                    "El monto devuelto "
                    "no puede ser negativo."
            })


        # ====================================================
        # 3. DISTRIBUCIÓN DEL MONTO
        # ====================================================

        if aplicado + devuelto != monto_total:

            raise ValidationError(
                "La suma del monto aplicado al saldo "
                "y el monto devuelto debe ser igual "
                "al total de la nota de crédito."
            )


        # ====================================================
        # 4. DEVOLUCIÓN DE DINERO
        # ====================================================

        if (
            devuelto > Decimal("0.00")
            and not self.cuenta_devolucion
        ):

            raise ValidationError({
                "cuenta_devolucion":
                    "Debe indicar la cuenta desde "
                    "la cual se devolverá el dinero."
            })


        if (
            devuelto == Decimal("0.00")
            and self.cuenta_devolucion
        ):

            raise ValidationError({
                "cuenta_devolucion":
                    "No debe indicar una cuenta de "
                    "devolución cuando no existe "
                    "devolución de dinero."
            })


        # ====================================================
        # 5. NO SUPERAR EL TOTAL DEL TICKET
        # ====================================================

        if self.ticket_id:

            total_ticket = (
                self.ticket.total
                or Decimal("0.00")
            )

            otras_notas = (
                NotaCredito.objects
                .filter(
                    ticket_id=self.ticket_id,
                    estado__in=[
                        NotaCredito.Estado.BORRADOR,
                        NotaCredito.Estado.CONTABILIZADA,
                    ],
                )
                .exclude(pk=self.pk)
            )

            total_otras_notas = sum(
                (
                    nc.monto_total
                    for nc in otras_notas
                ),
                Decimal("0.00"),
            )

            if (
                total_otras_notas
                + monto_total
                > total_ticket
            ):

                raise ValidationError({
                    "monto_total":
                        "Las notas de crédito no pueden "
                        "superar el total del ticket original."
                })


        # ====================================================
        # 6. MONTO APLICADO AL SALDO DEL CLIENTE
        # ====================================================

        if self.ticket_id:

            saldo_ticket = (
                self.ticket.saldo
                or Decimal("0.00")
            )

            if aplicado > saldo_ticket:

                raise ValidationError({
                    "monto_aplicado_saldo":
                        "El importe aplicado al saldo "
                        "no puede superar el saldo "
                        "actual del ticket."
                })


        # ====================================================
        # 7. DESCRIPCIÓN OBLIGATORIA PARA OTROS
        # ====================================================

        if (
            self.motivo
            == NotaCredito.Motivo.OTRO
            and not self.descripcion.strip()
        ):

            raise ValidationError({
                "descripcion":
                    "Debe explicar el motivo "
                    "de la nota de crédito."
            })


class DetalleNotaCredito(models.Model):

    nota_credito = models.ForeignKey(
        NotaCredito,
        on_delete=models.CASCADE,
        related_name="detalles",
    )

    detalle_ticket = models.ForeignKey(
        "core.DetalleTicketVenta",
        on_delete=models.PROTECT,
        related_name="detalles_notas_credito",
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    importe = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    # --------------------------------------------------------
    # SOLO SE MARCA SI EL PRODUCTO REGRESA FÍSICAMENTE
    # AL INVENTARIO Y PUEDE VOLVER A VENDERSE.
    #
    # Ejemplo:
    # Montura en buen estado -> Sí
    # Luna fabricada para cliente -> normalmente No
    # --------------------------------------------------------

    devuelve_stock = models.BooleanField(
        default=False,
    )

    # --------------------------------------------------------
    # COSTO UTILIZADO PARA REVERTIR EL COSTO DE VENTA.
    #
    # Se completará automáticamente al contabilizar
    # cuando corresponda.
    # --------------------------------------------------------

    costo_unitario_reversion = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )

    kardex_generado = models.BooleanField(
        default=False,
    )

    observacion = models.CharField(
        max_length=300,
        blank=True,
    )


    class Meta:

        ordering = [
            "id",
        ]

        verbose_name = (
            "Detalle de nota de crédito"
        )

        verbose_name_plural = (
            "Detalles de nota de crédito"
        )


    def __str__(self):

        return (
            f"NC {self.nota_credito.numero:06d} - "
            f"{self.detalle_ticket.descripcion}"
        )


    def clean(self):

        super().clean()


        # ====================================================
        # 1. CANTIDAD
        # ====================================================

        if (
            self.cantidad is None
            or self.cantidad <= Decimal("0.00")
        ):

            raise ValidationError({
                "cantidad":
                    "La cantidad debe ser mayor que cero."
            })


        # ====================================================
        # 2. IMPORTE
        # ====================================================

        if (
            self.importe is None
            or self.importe <= Decimal("0.00")
        ):

            raise ValidationError({
                "importe":
                    "El importe debe ser mayor que cero."
            })


        # ====================================================
        # 3. EL DETALLE DEBE PERTENECER AL TICKET ORIGINAL
        # ====================================================

        if (
            self.nota_credito_id
            and self.detalle_ticket_id
            and
            self.detalle_ticket.ticket_numero_id
            != self.nota_credito.ticket_id
        ):

            raise ValidationError({
                "detalle_ticket":
                    "El producto seleccionado no pertenece "
                    "al ticket de esta nota de crédito."
            })


        # ====================================================
        # 4. NO DEVOLVER MÁS UNIDADES QUE LAS VENDIDAS
        # ====================================================

        if self.detalle_ticket_id:

            cantidad_vendida = Decimal(
                str(
                    self.detalle_ticket.cantidad
                )
            )

            if self.cantidad > cantidad_vendida:

                raise ValidationError({
                    "cantidad":
                        "No puede devolver una cantidad "
                        "mayor que la vendida."
                })


        # ====================================================
        # 5. STOCK
        # ====================================================

        if (
            self.devuelve_stock
            and not self.detalle_ticket.producto_id
        ):

            raise ValidationError({
                "devuelve_stock":
                    "Este detalle no está asociado a un "
                    "producto de inventario y no puede "
                    "regresar automáticamente al stock."
            })