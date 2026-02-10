from django.urls import path
from core import views, views_dashboard  
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('', views.index, name='index'),
    path('ventas/registro/', views.registrar_venta, name='registrar_venta'),
    path('clientes/registro/', views.registrar_cliente, name='registrar_cliente'),
    path('crear-producto/', views.crear_producto, name='crear_producto'),
    path('compras/', views.lista_compras, name='lista_compras'),

    path('editar-producto/<int:pk>/', views.editar_producto, name='editar_producto'),
    path('eliminar-producto/<int:pk>/', views.eliminar_producto, name='eliminar_producto'),
    

    #path('buscar-producto/', views.buscar_producto, name='buscar_producto'),

    path('buscar-codigos/', views.buscar_codigos, name='buscar_codigos'),

    path('producto-por-codigo/', views.detalle_producto_por_codigo, name='producto_por_codigo'),

    path('ticket-pdf/', views.generar_ticket_pdf, name='ticket_pdf'),
    #path('ticket-pdf/', views.ticket_pdf, name='ticket_pdf'),

    path('guardar-ticket/', views.guardar_ticket, name='guardar_ticket'),  # NUEVO

    #path('api/consulta-dni/', views.consulta_dni, name='consulta_dni'),


    path('compras/nueva/', views.registrar_compra, name='registrar_compra'),
    path('proveedores/nuevo/', views.crear_proveedor, name='crear_proveedor'),
    

    path('compras/', views.lista_compras, name='lista_compras'),
    path('compras/<int:compra_id>/editar/', views.editar_compra, name='editar_compra'),
    path('compras/<int:compra_id>/eliminar/', views.eliminar_compra, name='eliminar_compra'),

    # DetalleCompra
    path('compras/detalles/', views.lista_detalles_compra, name='lista_detalles_compra'),
    path('compras/detalles/<int:detalle_id>/editar/', views.editar_detalle_compra, name='editar_detalle_compra'),
    path('compras/detalles/<int:detalle_id>/eliminar/', views.eliminar_detalle_compra, name='eliminar_detalle_compra'),

    
    path('clientes/buscar_por_dni/', views.buscar_cliente_por_dni, name='buscar_cliente_por_dni'),
# Lista / editar / eliminar / historial (lo de antes)
    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('clientes/nuevo/', views.crear_cliente, name='crear_cliente'),
    path('clientes/<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
    path('clientes/<int:cliente_id>/eliminar/', views.eliminar_cliente, name='eliminar_cliente'),
    path('clientes/<int:cliente_id>/historial/', views.cliente_historial, name='cliente_historial'),

    path('clientes/consulta_dni/', views.consulta_dni, name='consulta_dni'),

    path('buscar-clientes/', views.buscar_clientes, name='buscar_clientes'),

    path('clientes/ultima_medida/', views.ultima_medida_cliente, name='ultima_medida_cliente'),

    path("buscar-medidas/", views.buscar_medidas, name="buscar_medidas"),
    path("api/medidas/<int:medida_id>/", views.medida_detalle, name="medida_detalle"),
    path("ultimas-medidas/", views.ultimas_medidas, name="ultimas_medidas"),

    path("ticket/<int:numero>/detalle/", views.ticket_detalle, name="ticket_detalle"),

    path("ticket/imprimir/", views.imprimir_ticket_pdf, name="imprimir_ticket_pdf"),

    path("kardex/", views.kardex_resumen, name="kardex_resumen"),
    path("kardex/<int:producto_id>/", views.kardex_detalle, name="kardex_detalle"),

    path("caja/<str:fecha>/cobrar-saldo/<int:ticket_id>/", views.caja_cobrar_saldo, name="caja_cobrar_saldo"),

# Caja
    path("caja/", views.caja_hoy, name="caja_hoy"),
    path("caja/<str:fecha>/", views.caja_detalle, name="caja_detalle"),
    path("caja/<str:fecha>/importar-ventas/", views.caja_importar_ventas, name="caja_importar_ventas"),
    path("caja/<str:fecha>/agregar/", views.caja_agregar_movimiento, name="caja_agregar_movimiento"),

# Saldos
    path("saldos/", views.saldos_pendientes, name="saldos_pendientes"),
    path("tickets/<int:ticket_id>/registrar-pago/", views.registrar_pago_ticket, name="registrar_pago_ticket"),


    path("caja/<str:fecha>/cerrar/", views.caja_cerrar, name="caja_cerrar"),
# Reabrir caja    
    path("caja/<str:fecha>/reabrir/", views.caja_reabrir, name="caja_reabrir"),

# Imprimir caja  

    path("caja/<str:fecha>/reporte-pdf/", views.caja_reporte_pdf, name="caja_reporte_pdf"),

# TV en tiempo real
    path("tv/ordenes/", views.tv_ordenes, name="tv_ordenes"),
    path("api/tv/ordenes/", views.tv_ordenes_data, name="tv_ordenes_data"),
    path("orden/<int:ticket_id>/estado/", views.actualizar_estado_orden, name="actualizar_estado_orden"),

    path("operador/ordenes/", views.operador_ordenes, name="operador_ordenes"),
    path("operador/orden/<int:ticket_id>/cambiar/", views.operador_cambiar_estado, name="operador_cambiar_estado"),


    # ... tus otras urls

    path("dashboard/", views_dashboard.dashboard, name="dashboard"),
    path("dashboard/data/", views_dashboard.dashboard_data, name="dashboard_data"),

    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("receta/<int:medida_id>/pdf/", views.receta_pdf, name="receta_pdf"),
    

    





]