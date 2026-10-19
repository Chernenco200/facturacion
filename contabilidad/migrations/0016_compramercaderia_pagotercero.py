# Escrita a mano: condición contable de las compras de
# mercadería de core y pagos a cuenta de terceros.

import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0015_igv_credito_fiscal'),
        ('core', '0012_cliente_excluir_reactivacion_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CompraMercaderia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('usa_credito_fiscal', models.BooleanField(default=True, help_text='Solo facturas: el IGV se recupera como crédito fiscal y no forma parte del costo del inventario.')),
                ('precios_incluyen_igv', models.BooleanField(default=True, help_text='Indica si los precios de compra ingresados en el detalle ya incluyen el IGV.')),
                ('base_imponible', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Valor del inventario (sin IGV recuperable).', max_digits=12)),
                ('igv_credito_fiscal', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('total_comprobante', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Lo que se paga o se debe al proveedor.', max_digits=12)),
                ('forma_pago', models.CharField(choices=[('EFECTIVO', 'Efectivo'), ('BANCO', 'Banco / transferencia'), ('CREDITO', 'Crédito proveedor'), ('PARCIAL', 'Pago parcial')], max_length=15)),
                ('monto_pagado', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('fecha_pago', models.DateField(blank=True, null=True)),
                ('fecha_vencimiento', models.DateField(blank=True, null=True)),
                ('estado', models.CharField(choices=[('BORRADOR', 'Borrador'), ('CONTABILIZADA', 'Contabilizada')], db_index=True, default='BORRADOR', max_length=20)),
                ('observacion', models.TextField(blank=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('contabilizado_en', models.DateTimeField(blank=True, null=True)),
                ('compra', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='condicion_contable', to='core.compra')),
                ('cuenta_pago', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='compras_mercaderia_pagadas', to='contabilidad.cuentacontable')),
                ('cuenta_proveedor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='compras_mercaderia_credito', to='contabilidad.cuentacontable')),
                ('tercero', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='compras_mercaderia', to='contabilidad.tercero')),
                ('asiento', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='compra_mercaderia', to='contabilidad.asientocontable')),
            ],
            options={
                'verbose_name': 'Compra de mercadería (contable)',
                'verbose_name_plural': 'Compras de mercadería (contable)',
                'ordering': ['-compra__fecha', '-id'],
            },
        ),
        migrations.CreateModel(
            name='PagoTercero',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_pago', models.DateField(db_index=True)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=12)),
                ('referencia', models.CharField(blank=True, help_text='Factura o documento que se cancela (opcional).', max_length=100)),
                ('observacion', models.TextField(blank=True)),
                ('estado', models.CharField(choices=[('CONTABILIZADO', 'Contabilizado'), ('ANULADO', 'Anulado')], default='CONTABILIZADO', max_length=20)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('tercero', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagos', to='contabilidad.tercero')),
                ('cuenta_por_pagar', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagos_terceros_cancelados', to='contabilidad.cuentacontable')),
                ('cuenta_pago', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagos_terceros_realizados', to='contabilidad.cuentacontable')),
                ('asiento', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='pago_tercero', to='contabilidad.asientocontable')),
            ],
            options={
                'verbose_name': 'Pago a proveedor / trabajador',
                'verbose_name_plural': 'Pagos a proveedores / trabajadores',
                'ordering': ['-fecha_pago', '-id'],
            },
        ),
    ]
