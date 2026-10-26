from django.db import migrations, models
from django.db.models import Max
from django.utils import timezone


def copiar_renovaciones_a_cliente(apps, schema_editor):
    """
    La renovación pasa a controlarse por cliente. Se copian los datos
    que ya existían en las órdenes de trabajo:

      - fecha_ultima_renovacion: la más reciente de sus órdenes.
      - renovacion_descartada: si alguna orden fue retirada de la lista
        (renovacion_enviada=True sin fecha de envío), se marca hoy, para
        que no vuelva a aparecer hasta que el cliente compre de nuevo.
    """

    Cliente = apps.get_model("core", "Cliente")
    OrdenTrabajo = apps.get_model("core", "OrdenTrabajo")

    fechas = (
        OrdenTrabajo.objects
        .filter(
            ticket__cliente__isnull=False,
            fecha_ultima_renovacion__isnull=False,
        )
        .values("ticket__cliente_id")
        .annotate(ultima=Max("fecha_ultima_renovacion"))
    )

    for fila in fechas:
        Cliente.objects.filter(pk=fila["ticket__cliente_id"]).update(
            fecha_ultima_renovacion=fila["ultima"]
        )

    descartados = (
        OrdenTrabajo.objects
        .filter(
            ticket__cliente__isnull=False,
            renovacion_enviada=True,
            fecha_ultima_renovacion__isnull=True,
        )
        .values_list("ticket__cliente_id", flat=True)
        .distinct()
    )

    Cliente.objects.filter(pk__in=list(descartados)).update(
        renovacion_descartada=timezone.localdate()
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_cliente_excluir_reactivacion_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="fecha_ultima_renovacion",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cliente",
            name="renovacion_descartada",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(
            copiar_renovaciones_a_cliente,
            migrations.RunPython.noop,
        ),
    ]
