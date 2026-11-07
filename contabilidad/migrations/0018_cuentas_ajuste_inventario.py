"""
Cuentas para el asiento automático del ajuste de inventario:
    65901 Faltantes de inventario   (gasto)
    75    Otros ingresos de gestión (agrupadora)
    75901 Sobrantes de inventario   (ingreso)

Si el plan contable aún no se cargó (no existe la cuenta 65),
no hace nada: cargar_plan_contable las crea igualmente.
"""

from django.db import migrations


def crear_cuentas(apps, schema_editor):
    Cuenta = apps.get_model("contabilidad", "CuentaContable")

    padre_65 = Cuenta.objects.filter(codigo="65").first()
    if not padre_65:
        return

    Cuenta.objects.get_or_create(
        codigo="65901",
        defaults=dict(
            nombre="Faltantes de inventario", codigo_pcge="659",
            cuenta_padre=padre_65, tipo="GASTO", naturaleza="DEUDORA",
            estado_financiero="ER", clasificacion_balance="NO_APLICA",
            nivel=padre_65.nivel + 1, acepta_movimientos=True, activo=True,
        ),
    )
    padre_75, _ = Cuenta.objects.get_or_create(
        codigo="75",
        defaults=dict(
            nombre="Otros ingresos de gestión", codigo_pcge="75",
            cuenta_padre=None, tipo="INGRESO", naturaleza="ACREEDORA",
            estado_financiero="ER", clasificacion_balance="NO_APLICA",
            nivel=1, acepta_movimientos=False, activo=True,
        ),
    )
    Cuenta.objects.get_or_create(
        codigo="75901",
        defaults=dict(
            nombre="Sobrantes de inventario", codigo_pcge="759",
            cuenta_padre=padre_75, tipo="INGRESO", naturaleza="ACREEDORA",
            estado_financiero="ER", clasificacion_balance="NO_APLICA",
            nivel=padre_75.nivel + 1, acepta_movimientos=True, activo=True,
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidad", "0017_ventaanulada"),
    ]

    operations = [
        migrations.RunPython(crear_cuentas, migrations.RunPython.noop),
    ]
