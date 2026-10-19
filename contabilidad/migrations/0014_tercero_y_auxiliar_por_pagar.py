# Escrita a mano: agrega el auxiliar de terceros
# (proveedores / trabajadores) para cuentas por pagar.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0013_notacredito_detallenotacredito'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tercero',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('PROVEEDOR', 'Proveedor'), ('TRABAJADOR', 'Trabajador'), ('OTRO', 'Otro')], db_index=True, default='PROVEEDOR', max_length=15)),
                ('nombre', models.CharField(max_length=200)),
                ('nombre_normalizado', models.CharField(db_index=True, editable=False, max_length=200)),
                ('numero_documento', models.CharField(blank=True, help_text='RUC o DNI (opcional).', max_length=20)),
                ('activo', models.BooleanField(default=True)),
                ('observacion', models.TextField(blank=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Tercero (proveedor / trabajador)',
                'verbose_name_plural': 'Terceros (proveedores / trabajadores)',
                'ordering': ['tipo', 'nombre'],
                'constraints': [
                    models.UniqueConstraint(fields=('tipo', 'nombre_normalizado'), name='unique_tercero_tipo_nombre'),
                ],
            },
        ),
        migrations.AddField(
            model_name='detalleasiento',
            name='tercero',
            field=models.ForeignKey(blank=True, help_text='Proveedor o trabajador al que corresponde la línea. Obligatorio en la práctica para cuentas 41 y 42.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movimientos', to='contabilidad.tercero'),
        ),
        migrations.AddField(
            model_name='compradirectaventa',
            name='tercero',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='compras_directas', to='contabilidad.tercero'),
        ),
        migrations.AddField(
            model_name='servicioterceroventa',
            name='tercero',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='servicios_venta', to='contabilidad.tercero'),
        ),
        migrations.AddField(
            model_name='operacioncontable',
            name='tercero',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='operaciones_contables', to='contabilidad.tercero'),
        ),
        migrations.AlterField(
            model_name='compradirectaventa',
            name='proveedor_nombre',
            field=models.CharField(blank=True, help_text='Nombre del proveedor. Al contabilizar se vincula automáticamente con un Tercero.', max_length=200),
        ),
        migrations.AlterField(
            model_name='operacioncontable',
            name='proveedor_nombre',
            field=models.CharField(blank=True, help_text='Proveedor o trabajador. Obligatorio cuando queda un saldo por pagar.', max_length=200),
        ),
    ]
