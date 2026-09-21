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


    
]