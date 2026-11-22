from decimal import Decimal

from django.db import migrations

TIPOS = [
    # codigo, nombre, puntos, minutos, prioridad, requiere_aprobacion
    ("WA_RESP", "Responder a un cliente que contestó (dentro de 30 min)", "0.5", 3, 5, False),
    ("WA_LISTA", "Enviar la lista de WhatsApp del día", "1.0", 30, 10, False),
    ("FOTO", "Montura publicada en la web (3 fotos + ficha)", "3.0", 7, 20, True),
    ("COD", "Montura codificada (ficha completa)", "0.5", 3, 30, False),
    ("INV", "Conteo de exhibidor (por unidad sin diferencia)", "0.5", 30, 40, True),
    ("TEL", "Teléfonos corregidos (puntos por cada 2)", "0.5", 10, 50, False),
    ("REEL", "Publicación o reel", "5.0", 30, 90, False),
    ("CITA", "Cliente con cita que llega a la tienda", "3.0", 0, 90, False),
    ("RESENA", "Reseña nueva en Google", "1.0", 0, 90, True),
    ("EXAMEN", "Examen de capacitación aprobado", "5.0", 0, 90, False),
]


def cargar(apps, schema_editor):
    TipoTarea = apps.get_model("incentivos", "TipoTarea")
    for codigo, nombre, pts, minutos, prio, aprob in TIPOS:
        TipoTarea.objects.update_or_create(
            codigo=codigo,
            defaults=dict(nombre=nombre, puntos=Decimal(pts), minutos_estandar=minutos, prioridad=prio,
                          requiere_aprobacion=aprob, activo=True),
        )
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Gerencia IC")


def quitar(apps, schema_editor):
    apps.get_model("incentivos", "TipoTarea").objects.filter(codigo__in=[t[0] for t in TIPOS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("incentivos", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(cargar, quitar)]
