# Escrita a mano: registro de ventas anuladas.

import django.db.models.deletion
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0016_compramercaderia_pagotercero'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VentaAnulada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_recibo', models.PositiveIntegerField(db_index=True)),
                ('fecha_venta', models.DateField(blank=True, null=True)),
                ('cliente', models.CharField(blank=True, max_length=200)),
                ('total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('motivo', models.TextField()),
                ('compras_anuladas', models.BooleanField(default=False, help_text='Si también se anularon compras a proveedores o servicios de terceros asociados a la venta.')),
                ('detalle', models.JSONField(blank=True, default=dict, help_text='Copia de productos, pagos y asientos anulados.')),
                ('anulado_en', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ventas_anuladas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Venta anulada',
                'verbose_name_plural': 'Ventas anuladas',
                'ordering': ['-anulado_en'],
            },
        ),
    ]
