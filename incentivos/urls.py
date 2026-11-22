from django.urls import path

from . import views

app_name = "incentivos"

urlpatterns = [
    # Trabajador
    path("", views.panel, name="panel"),
    path("siguiente/", views.siguiente, name="siguiente"),
    path("tarea/<int:pk>/", views.tarea_detalle, name="tarea"),
    path("resultado/", views.resultado, name="resultado"),
    # Marcación (equipo de la tienda)
    path("marcar/", views.marcar, name="marcar"),
    # Gerencia
    path("gerencia/", views.gerencia, name="gerencia"),
    path("gerencia/alertas-vistas/", views.alertas_vistas, name="alertas_vistas"),
    path("gerencia/trabajador/<int:trabajador_id>/", views.panel_de, name="panel_de"),
    path("revision/", views.revision, name="revision"),
    path("examen/", views.examen, name="examen"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("turnos/", views.turnos, name="turnos"),
    path("asistencia/", views.asistencia, name="asistencia"),
    path("dispositivo/", views.dispositivo, name="dispositivo"),
    path("cerrar/", views.cerrar, name="cerrar"),
    path("cierre.xlsx", views.cierre_excel, name="cierre_excel"),
]
