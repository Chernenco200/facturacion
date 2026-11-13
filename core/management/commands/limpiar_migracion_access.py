"""Paso 1 de la reimportación: quita la migración Access anterior conservando la actividad real.

Instalar en: core/management/commands/limpiar_migracion_access.py

  python manage.py limpiar_migracion_access                                   (solo revisa, no cambia nada)
  python manage.py limpiar_migracion_access --ejecutar --confirmar LIMPIAR_ACCESS

Elimina SOLO:
  * tickets con numeración Access (1100000000–1299999999) y sus detalles
  * recetas con descripcion 'MIGRACION ACCESS ...'
  * clientes creados por la migración (id > 5512 y excluir_reactivacion = true)
    que ya no tienen ninguna actividad real
Conserva ventas, pagos, caja, órdenes, contabilidad y clientes reales.
También sirve para deshacer importar_access_v2.
Todo en una transacción: si una verificación falla, no se borra nada.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

MAX_ID_09NOV = 5512   # id de cliente más alto en el respaldo del 09/11/2026

SQL_TEMP = """
CREATE TEMP TABLE mig_tickets ON COMMIT DROP AS
SELECT id FROM core_ticketventa WHERE numero BETWEEN 1100000000 AND 1299999999;
"""

SQL_CHECKS = {
    'tickets Access con fecha reciente (>= 09/11/2026)':
        "SELECT count(*) FROM core_ticketventa WHERE id IN (SELECT id FROM mig_tickets) AND fecha_emision >= DATE '2026-11-09'",
    'tickets Access con pagos':
        "SELECT count(*) FROM core_pagoticket WHERE ticket_id IN (SELECT id FROM mig_tickets)",
    'tickets Access con órdenes de trabajo':
        "SELECT count(*) FROM core_ordentrabajo WHERE ticket_id IN (SELECT id FROM mig_tickets)",
    'tickets Access con movimientos de caja':
        "SELECT count(*) FROM core_movimientocaja WHERE ticket_id IN (SELECT id FROM mig_tickets)",
    'tickets Access con kardex':
        "SELECT count(*) FROM core_kardexmovimiento WHERE ticket_id IN (SELECT id FROM mig_tickets)",
    'tickets Access con costo de venta':
        "SELECT count(*) FROM contabilidad_propuestacostoventa WHERE ticket_id IN (SELECT id FROM mig_tickets)",
    'tickets Access con nota de crédito':
        "SELECT count(*) FROM contabilidad_notacredito WHERE ticket_id IN (SELECT id FROM mig_tickets)",
    'detalles Access usados en notas de crédito':
        """SELECT count(*) FROM contabilidad_detallenotacredito d JOIN core_detalleticketventa t ON t.id = d.detalle_ticket_id
           WHERE t.ticket_numero_id IN (SELECT id FROM mig_tickets)""",
    'detalles Access usados en costo de venta':
        """SELECT count(*) FROM contabilidad_detallepropuestacostoventa d JOIN core_detalleticketventa t ON t.id = d.detalle_ticket_id
           WHERE t.ticket_numero_id IN (SELECT id FROM mig_tickets)""",
}

SQL_CLIENTES = f"""
CREATE TEMP TABLE mig_clientes ON COMMIT DROP AS
SELECT c.id FROM core_cliente c
WHERE c.id > {MAX_ID_09NOV} AND c.excluir_reactivacion
  AND NOT EXISTS (SELECT 1 FROM core_ticketventa t WHERE t.cliente_id = c.id
                  AND t.id NOT IN (SELECT id FROM mig_tickets))
  AND NOT EXISTS (SELECT 1 FROM core_medidavista m WHERE m.cliente_id = c.id
                  AND coalesce(m.descripcion, '') NOT LIKE 'MIGRACION ACCESS %%')
  AND NOT EXISTS (SELECT 1 FROM core_tipolunas l WHERE l.cliente_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM core_venta v WHERE v.cliente_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM core_reactivacionwhatsapp r WHERE r.cliente_id = c.id);
"""


def one(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


class Command(BaseCommand):
    help = 'Quita la migración Access anterior (tickets 11/12xxxxxxxx, recetas MIGRACION ACCESS y sus clientes).'

    def add_arguments(self, parser):
        parser.add_argument('--ejecutar', action='store_true')
        parser.add_argument('--confirmar', default='')

    def handle(self, *args, **opt):
        if opt['ejecutar'] and opt['confirmar'] != 'LIMPIAR_ACCESS':
            raise CommandError('Para ejecutar: --ejecutar --confirmar LIMPIAR_ACCESS')
        if connection.vendor != 'postgresql':
            raise CommandError('Solo PostgreSQL. Conexión actual: ' + connection.vendor)

        with transaction.atomic(), connection.cursor() as cur:
            cur.execute('LOCK TABLE core_cliente, core_ticketventa, core_medidavista IN SHARE ROW EXCLUSIVE MODE')
            antes = {
                'clientes': one(cur, 'SELECT count(*) FROM core_cliente'),
                'recetas': one(cur, 'SELECT count(*) FROM core_medidavista'),
                'tickets': one(cur, 'SELECT count(*) FROM core_ticketventa'),
            }
            self.stdout.write(f"Estado actual: {antes['clientes']} clientes, {antes['recetas']} recetas, "
                              f"{antes['tickets']} tickets; correlativo "
                              f"{one(cur, 'SELECT max(numero_actual) FROM core_recibocorrelativo')}; "
                              f"última venta {one(cur, 'SELECT max(fecha_emision) FROM core_ticketventa')}")

            cur.execute(SQL_TEMP)
            problemas = []
            for nombre, sql in SQL_CHECKS.items():
                n = one(cur, sql)
                if n:
                    problemas.append(f'  {nombre}: {n}')
            cur.execute(SQL_CLIENTES)
            n_tk = one(cur, 'SELECT count(*) FROM mig_tickets')
            n_det = one(cur, 'SELECT count(*) FROM core_detalleticketventa WHERE ticket_numero_id IN (SELECT id FROM mig_tickets)')
            n_rec = one(cur, "SELECT count(*) FROM core_medidavista WHERE descripcion LIKE 'MIGRACION ACCESS %%'")
            n_cli = one(cur, 'SELECT count(*) FROM mig_clientes')
            self.stdout.write(f'Se eliminarían: {n_tk} tickets Access, {n_det} detalles, {n_rec} recetas, {n_cli} clientes migrados')

            cur.execute(f"""SELECT id, coalesce("DNI", ''), nombre FROM core_cliente
                            WHERE id > {MAX_ID_09NOV} AND excluir_reactivacion
                              AND id NOT IN (SELECT id FROM mig_clientes) ORDER BY id""")
            conservados = cur.fetchall()
            if conservados:
                self.stdout.write(f'Clientes migrados que se CONSERVAN por tener actividad real ({len(conservados)}):')
                for row in conservados[:50]:
                    self.stdout.write(f'  id {row[0]}  {row[1]}  {row[2]}')

            if problemas:
                raise CommandError('Verificación fallida, no se borró nada:\n' + '\n'.join(problemas))

            if not opt['ejecutar']:
                self.stdout.write(self.style.SUCCESS('REVISIÓN: no se modificó nada.'))
                transaction.set_rollback(True)
                return

            cur.execute('DELETE FROM core_detalleticketventa WHERE ticket_numero_id IN (SELECT id FROM mig_tickets)')
            cur.execute('DELETE FROM core_ticketventa WHERE id IN (SELECT id FROM mig_tickets)')
            cur.execute("DELETE FROM core_medidavista WHERE descripcion LIKE 'MIGRACION ACCESS %%'")
            cur.execute('DELETE FROM core_cliente WHERE id IN (SELECT id FROM mig_clientes)')

            despues = {
                'clientes': one(cur, 'SELECT count(*) FROM core_cliente'),
                'recetas': one(cur, 'SELECT count(*) FROM core_medidavista'),
                'tickets': one(cur, 'SELECT count(*) FROM core_ticketventa'),
            }
            if (antes['clientes'] - despues['clientes'] != n_cli or antes['recetas'] - despues['recetas'] != n_rec
                    or antes['tickets'] - despues['tickets'] != n_tk):
                raise CommandError('Conteos inconsistentes. Se revirtió todo.')
            self.stdout.write(self.style.SUCCESS(
                f"LIMPIEZA CONFIRMADA. Ahora: {despues['clientes']} clientes, {despues['recetas']} recetas, "
                f"{despues['tickets']} tickets."))
