from django.urls import path

from . import views


app_name = "contabilidad"


urlpatterns = [

    path(
        "libro-diario/",
        views.libro_diario,
        name="libro_diario",
    ),

    path(
        "libro-mayor/",
        views.libro_mayor,
        name="libro_mayor",
    ),

    path(
        "balance-comprobacion/",
        views.balance_comprobacion,
        name="balance_comprobacion",
    ),

    path(
        "estado-resultados/",
        views.estado_resultados,
        name="estado_resultados",
    ),

    # ========================================================
    # COSTOS DE VENTA
    # ========================================================

    path(
        "costos-venta/<int:propuesta_id>/validar/",
        views.validar_costo_venta,
        name="validar_costo_venta",
    ),

    path(
        "costos-venta/detalle/<int:detalle_costo_id>/compra-directa/",
        views.registrar_compra_directa,
        name="registrar_compra_directa",
    ),

    path(
        "compras-directas/<int:compra_id>/editar/",
        views.editar_compra_directa,
        name="editar_compra_directa",
    ),

    path(
        "compras-directas/<int:compra_id>/pagar/",
        views.registrar_pago_proveedor,
        name="registrar_pago_proveedor",
    ),

    path(
        "servicios-terceros/<int:servicio_id>/registrar/",
        views.registrar_servicio_tercero,
        name="registrar_servicio_tercero",
    ),

    path(
        "servicios-terceros/<int:servicio_id>/eliminar/",
        views.eliminar_servicio_tercero,
        name="eliminar_servicio_tercero",
    ),

    path(
        "costos-venta/<int:propuesta_id>/contabilizar/",
        views.contabilizar_propuesta_costo,
        name="contabilizar_propuesta_costo",
    ),

    # ========================================================
    # ESTADOS FINANCIEROS
    # ========================================================

    path(
        "balance-general/",
        views.balance_general,
        name="balance_general",
    ),

    path(
        "estado-cambios-patrimonio/",
        views.estado_cambios_patrimonio,
        name="estado_cambios_patrimonio",
    ),

    path(
        "estado-flujo-efectivo/",
        views.estado_flujo_efectivo,
        name="estado_flujo_efectivo",
    ),

    path(
        "estados-financieros/",
        views.estados_financieros,
        name="estados_financieros",
    ),

    # ========================================================
    # PERÍODOS
    # ========================================================

    path(
        "periodos/<int:periodo_id>/cerrar/",
        views.cerrar_periodo_contable,
        name="cerrar_periodo_contable",
    ),

    path(
        "periodos/<int:periodo_id>/reabrir/",
        views.reabrir_periodo_contable,
        name="reabrir_periodo_contable",
    ),

    path(
        "cierre-anual/<int:anio>/",
        views.cierre_anual,
        name="cierre_anual",
    ),

    # ========================================================
    # PENDIENTES
    # ========================================================

    path(
        "pendientes/",
        views.pendientes_contables,
        name="pendientes_contables",
    ),
    
    path(
        "operaciones/registrar/",
        views.registrar_gasto_operacion,
        name="registrar_gasto_operacion",
    ),

    path(
        "operaciones/<int:operacion_id>/pagar/",
        views.registrar_pago_operacion,
        name="registrar_pago_operacion",
    ),

    path(
        "notas-credito/registrar/",
        views.registrar_nota_credito,
        name="registrar_nota_credito",
    ),

    path(
        "notas-credito/",
        views.lista_notas_credito,
        name="lista_notas_credito",
    ),

    path(
        "notas-credito/<int:nota_id>/contabilizar/",
        views.contabilizar_nota_credito_view,
        name="contabilizar_nota_credito",
    ),

    path(
        "notas-credito/<int:nota_id>/anular/",
        views.anular_nota_credito,
        name="anular_nota_credito",
    ),

    path(
        "conceptos/",
        views.lista_conceptos_contables,
        name="lista_conceptos_contables",
    ),

    path(
        "conceptos/nuevo/",
        views.crear_concepto_contable,
        name="crear_concepto_contable",
    ),

    path(
        "conceptos/<int:concepto_id>/editar/",
        views.editar_concepto_contable,
        name="editar_concepto_contable",
    ),

    path(
        "conceptos/<int:concepto_id>/estado/",
        views.cambiar_estado_concepto_contable,
        name="cambiar_estado_concepto_contable",
    ),

    # ========================================================
    # SALDOS POR PAGAR (PROVEEDORES Y TRABAJADORES)
    # ========================================================

    path(
        "saldos-por-pagar/",
        views.saldos_por_pagar,
        name="saldos_por_pagar",
    ),

    path(
        "saldos-por-pagar/sin-identificar/",
        views.estado_cuenta_tercero_view,
        name="estado_cuenta_sin_identificar",
    ),

    path(
        "saldos-por-pagar/<int:tercero_id>/",
        views.estado_cuenta_tercero_view,
        name="estado_cuenta_tercero",
    ),

    # ========================================================
    # IMPUESTOS DEL MES (IGV - RENTA RER)
    # ========================================================

    path(
        "impuestos-mensuales/",
        views.impuestos_mensuales,
        name="impuestos_mensuales",
    ),

    # ========================================================
    # COMPRAS DE MERCADERÍA Y PAGOS A TERCEROS
    # ========================================================

    path(
        "compras-mercaderia/",
        views.compras_por_contabilizar,
        name="compras_por_contabilizar",
    ),

    path(
        "compras-mercaderia/<int:compra_id>/contabilizar/",
        views.contabilizar_compra_mercaderia_view,
        name="contabilizar_compra_mercaderia",
    ),

    path(
        "saldos-por-pagar/<int:tercero_id>/pagar/",
        views.registrar_pago_tercero_view,
        name="registrar_pago_tercero",
    ),
]


# ============================================================
# CONTROL DE ACCESO
#
# Toda la contabilidad queda restringida al superusuario, igual
# que el menú. Antes las vistas no tenían ningún control: se podía
# entrar escribiendo la dirección, incluso sin iniciar sesión.
# ============================================================

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden


def _solo_administrador_contable(vista):

    @wraps(vista)
    def envoltura(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not request.user.is_superuser:
            return HttpResponseForbidden(
                "No tienes permisos para acceder a la contabilidad."
            )

        return vista(request, *args, **kwargs)

    return envoltura


for _patron in urlpatterns:
    _patron.callback = _solo_administrador_contable(_patron.callback)
