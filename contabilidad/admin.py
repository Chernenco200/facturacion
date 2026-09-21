from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .services import contabilizar_asiento

from .models import (
    CuentaContable,
    CategoriaGerencial,
    CentroCosto,
    ConceptoOperacion,
    PeriodoContable,
    AsientoContable,
    DetalleAsiento,
)


# ============================================================
# CUENTAS CONTABLES
# ============================================================

@admin.register(CuentaContable)
class CuentaContableAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "tipo",
        "naturaleza",
        "codigo_pcge",
        "cuenta_padre",
        "acepta_movimientos",
        "activo",
    )

    list_filter = (
        "tipo",
        "naturaleza",
        "estado_financiero",
        "acepta_movimientos",
        "activo",
    )

    search_fields = (
        "codigo",
        "nombre",
        "codigo_pcge",
    )

    ordering = ("codigo",)

    list_per_page = 50


# ============================================================
# CATEGORÍAS GERENCIALES
# ============================================================

@admin.register(CategoriaGerencial)
class CategoriaGerencialAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "categoria_padre",
        "activo",
    )

    list_filter = (
        "activo",
    )

    search_fields = (
        "codigo",
        "nombre",
    )

    ordering = ("codigo",)

    list_per_page = 50


# ============================================================
# CENTROS DE COSTO
# ============================================================

@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "centro_padre",
        "activo",
    )

    list_filter = (
        "activo",
    )

    search_fields = (
        "codigo",
        "nombre",
    )

    ordering = ("codigo",)


# ============================================================
# CONCEPTOS DE OPERACIÓN
# ============================================================

@admin.register(ConceptoOperacion)
class ConceptoOperacionAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "nombre",
        "concepto_padre",
        "tipo_operacion",
        "cuenta_contable",
        "categoria_gerencial",
        "centro_costo",
        "es_grupo",
        "activo",
    )

    list_filter = (
        "tipo_operacion",
        "es_grupo",
        "activo",
        "centro_costo",
        "categoria_gerencial",
    )

    search_fields = (
        "codigo",
        "nombre",
        "palabras_clave",
        "sinonimos",
    )

    autocomplete_fields = (
        "concepto_padre",
        "cuenta_contable",
        "categoria_gerencial",
        "centro_costo",
    )

    ordering = (
        "orden",
        "nombre",
    )

    list_per_page = 50


# ============================================================
# PERIODOS CONTABLES
# ============================================================

@admin.register(PeriodoContable)
class PeriodoContableAdmin(admin.ModelAdmin):

    list_display = (
        "anio",
        "mes",
        "fecha_inicio",
        "fecha_fin",
        "estado",
    )

    list_filter = (
        "anio",
        "estado",
    )

    ordering = (
        "-anio",
        "-mes",
    )


# ============================================================
# DETALLE DEL ASIENTO COMO INLINE
# ============================================================

class DetalleAsientoInline(admin.TabularInline):

    model = DetalleAsiento

    extra = 2

    autocomplete_fields = (
        "cuenta",
        "categoria_gerencial",
        "centro_costo",
    )

    fields = (
        "secuencia",
        "cuenta",
        "descripcion",
        "debe",
        "haber",
        "categoria_gerencial",
        "centro_costo",
        "referencia",
    )


# ============================================================
# ASIENTOS CONTABLES
# ============================================================

@admin.register(AsientoContable)
class AsientoContableAdmin(admin.ModelAdmin):

    list_display = (
        "numero",
        "fecha",
        "periodo",
        "tipo",
        "glosa",
        "estado",
        "mostrar_total_debe",
        "mostrar_total_haber",
        "mostrar_cuadrado",
    )

    list_filter = (
        "estado",
        "tipo",
        "periodo",
        "fecha",
    )

    search_fields = (
        "numero",
        "glosa",
        "origen",
    )

    ordering = (
        "-fecha",
        "-numero",
    )

    inlines = [
        DetalleAsientoInline,
    ]

    readonly_fields = (
        "creado_en",
        "actualizado_en",
    )

    actions = [
        "contabilizar_asientos_seleccionados",
    ]

    def mostrar_total_debe(self, obj):
        return f"S/ {obj.total_debe:.2f}"

    mostrar_total_debe.short_description = "Debe"

    def mostrar_total_haber(self, obj):
        return f"S/ {obj.total_haber:.2f}"

    mostrar_total_haber.short_description = "Haber"

    def mostrar_cuadrado(self, obj):
        return obj.esta_cuadrado

    mostrar_cuadrado.boolean = True
    mostrar_cuadrado.short_description = "Cuadrado"

    @admin.action(
        description="Contabilizar asientos seleccionados"
    )
    def contabilizar_asientos_seleccionados(
        self,
        request,
        queryset,
    ):
        contabilizados = 0
        errores = 0

        for asiento in queryset:

            try:
                contabilizar_asiento(asiento)
                contabilizados += 1

            except ValidationError as error:
                errores += 1

                self.message_user(
                    request,
                    (
                        f"Asiento {asiento.numero}: "
                        f"{' '.join(error.messages)}"
                    ),
                    level=messages.ERROR,
                )

        if contabilizados:
            self.message_user(
                request,
                (
                    f"{contabilizados} asiento(s) "
                    "contabilizado(s) correctamente."
                ),
                level=messages.SUCCESS,
            )

        if errores:
            self.message_user(
                request,
                (
                    f"{errores} asiento(s) no pudieron "
                    "ser contabilizados."
                ),
                level=messages.WARNING,
            )


# ============================================================
# DETALLES DE ASIENTO
# ============================================================

@admin.register(DetalleAsiento)
class DetalleAsientoAdmin(admin.ModelAdmin):

    list_display = (
        "asiento",
        "secuencia",
        "cuenta",
        "debe",
        "haber",
        "categoria_gerencial",
        "centro_costo",
    )

    list_filter = (
        "cuenta",
        "categoria_gerencial",
        "centro_costo",
    )

    search_fields = (
        "descripcion",
        "referencia",
        "cuenta__codigo",
        "cuenta__nombre",
    )

    autocomplete_fields = (
        "asiento",
        "cuenta",
        "categoria_gerencial",
        "centro_costo",
    )