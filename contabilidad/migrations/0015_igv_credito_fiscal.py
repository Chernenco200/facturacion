# Escrita a mano: IGV crédito fiscal en compras, servicios
# y operaciones (Régimen Especial de Renta con IGV).

from decimal import Decimal

from django.db import migrations, models


AYUDA = (
    "IGV incluido en el importe que da derecho a crédito "
    "fiscal (solo comprobantes con factura). Cero si no hay "
    "crédito fiscal."
)


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0014_tercero_y_auxiliar_por_pagar'),
    ]

    operations = [
        migrations.AddField(
            model_name='compradirectaventa',
            name='igv_credito_fiscal',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text=AYUDA, max_digits=12),
        ),
        migrations.AddField(
            model_name='servicioterceroventa',
            name='igv_credito_fiscal',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text=AYUDA, max_digits=12),
        ),
        migrations.AddField(
            model_name='operacioncontable',
            name='igv_credito_fiscal',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text=AYUDA, max_digits=12),
        ),
    ]
