"""Fusiona clientes importados de Access SIN DNI que están duplicados por nombre.

Instalar en: core/management/commands/fusionar_duplicados_access.py

  python manage.py fusionar_duplicados_access                                   (solo muestra)
  python manage.py fusionar_duplicados_access --ejecutar --confirmar FUSIONAR
  python manage.py fusionar_duplicados_access --par 21892:4294 --ejecutar --confirmar FUSIONAR

Solo mueve clientes creados por la importación Access (sin DNI y sin actividad en tienda).
Nunca borra ni modifica clientes reales.

Fusión automática cuando el nombre tiene 3 o más palabras útiles (sin contar de, la, del...) y coincide exactamente
(sin importar mayúsculas, tildes ni el orden de las palabras) con:
  * un único cliente con DNI de 8 dígitos  -> se pasa a ese cliente
  * o, si no hay ninguno con DNI, con otros clientes sin DNI -> se juntan en uno
Fusión automática también cuando el nombre corto está contenido en UN solo nombre más
largo y además tienen el MISMO teléfono (ej. "LINDA EFFIO" -> "EFFIO BECERRA LINDA LADY").
Nombres de 1 o 2 palabras ("CARLOS RODRIGUEZ"), con varios candidatos con DNI o con
coincidencia parcial sin teléfono igual solo se listan para revisión manual.
Pares confirmados por usted:  --par ORIGEN:DESTINO  (se puede repetir).
El ORIGEN siempre debe ser un cliente importado de Access; nunca se borra un cliente real.
Recetas idénticas (misma fecha y graduación) no se duplican al fusionar.
"""
import re
import unicodedata
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q

from core.models import Cliente, MedidaVista, ReactivacionWhatsApp, TicketVenta, TipoLunas, Venta

MIG_RECETA = 'MIGRACION ACCESS '
RECETA_CAMPOS = [f.name for f in MedidaVista._meta.fields
                 if f.name not in ('id', 'cliente', 'descripcion', 'Optometra')]


def clave(nombre):
    v = unicodedata.normalize('NFKD', (nombre or '').casefold())
    v = ''.join(c for c in v if not unicodedata.combining(c))
    return tuple(sorted(re.sub(r'[^a-z0-9ñ ]', ' ', v).split()))


CONECTORES = {'del', 'las', 'los', 'vda', 'viuda'}


def palabras_utiles(k):
    return sum(1 for t in k if len(t) >= 3 and t not in CONECTORES)


def dni_ok(v):
    return bool(v and re.fullmatch(r'\d{8}', v.strip()))


def firma(m):
    return tuple(str(getattr(m, f)) for f in RECETA_CAMPOS)


class Command(BaseCommand):
    help = 'Fusiona clientes Access sin DNI duplicados por nombre.'

    def add_arguments(self, parser):
        parser.add_argument('--ejecutar', action='store_true')
        parser.add_argument('--confirmar', default='')
        parser.add_argument('--par', action='append', default=[],
                            help='ORIGEN:DESTINO confirmado manualmente (repetible)')
        parser.add_argument('--solo-pares', action='store_true',
                            help='Fusiona solo los --par indicados, sin las automáticas')

    def handle(self, *args, **opt):
        if opt['ejecutar'] and opt['confirmar'] != 'FUSIONAR':
            raise CommandError('Para ejecutar: --ejecutar --confirmar FUSIONAR')
        if connection.vendor != 'postgresql':
            raise CommandError('Solo PostgreSQL.')

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute('LOCK TABLE core_cliente, core_ticketventa, core_medidavista IN SHARE ROW EXCLUSIVE MODE')

            mig_tk = Q(numero__gte=1100000000, numero__lte=1299999999)
            con_tk_real = set(TicketVenta.objects.exclude(mig_tk).exclude(cliente__isnull=True)
                              .values_list('cliente_id', flat=True))
            con_rec_real = set(MedidaVista.objects.exclude(descripcion__startswith=MIG_RECETA)
                               .values_list('cliente_id', flat=True))
            con_mig = set(TicketVenta.objects.filter(mig_tk).values_list('cliente_id', flat=True)) | \
                set(MedidaVista.objects.filter(descripcion__startswith=MIG_RECETA).values_list('cliente_id', flat=True))
            otros = set(TipoLunas.objects.values_list('cliente_id', flat=True)) | \
                set(Venta.objects.values_list('cliente_id', flat=True)) | \
                set(ReactivacionWhatsApp.objects.values_list('cliente_id', flat=True))

            clientes = list(Cliente.objects.values('id', 'DNI', 'nombre', 'telefono', 'fecha_registro',
                                                   'excluir_reactivacion'))
            info = {c['id']: c for c in clientes}

            def importado(c):
                return (c['excluir_reactivacion'] and c['id'] in con_mig and c['id'] not in con_tk_real
                        and c['id'] not in con_rec_real and c['id'] not in otros)

            grupos = defaultdict(list)
            for c in clientes:
                k = clave(c['nombre'])
                if k:
                    grupos[k].append(c)

            fusiones, manual = [], []        # fusiones: (origen_id, destino_id)
            for k, miembros in grupos.items():
                fuentes = [c for c in miembros if not c['DNI'] and importado(c)]
                if not fuentes or len(miembros) < 2:
                    continue
                con_dni = [c for c in miembros if dni_ok(c['DNI'])]
                if palabras_utiles(k) < 3 or len(con_dni) > 1:
                    manual.append((k, miembros))
                    continue
                if con_dni:
                    destino = con_dni[0]
                else:
                    reales = [c for c in miembros if not importado(c)]
                    if len(reales) > 1:
                        manual.append((k, miembros))
                        continue
                    destino = reales[0] if reales else min(
                        fuentes, key=lambda c: (c['fecha_registro'] or c['id'], c['id']))
                for f in fuentes:
                    if f['id'] != destino['id']:
                        fusiones.append((f['id'], destino['id']))

            def utiles(nombre):
                return frozenset(t for t in clave(nombre) if len(t) >= 3 and t not in CONECTORES)

            origenes_a = {o for o, _ in fusiones}
            en_manual = {c['id'] for _, ms in manual for c in ms}
            tokens = {c['id']: utiles(c['nombre']) for c in clientes}
            indice = defaultdict(set)
            for cid, ts in tokens.items():
                for t in ts:
                    indice[t].add(cid)
            parciales, sugerencias = [], []
            for c in clientes:
                ts = tokens[c['id']]
                if c['DNI'] or not importado(c) or c['id'] in origenes_a or len(ts) < 2:
                    continue
                cands = [x for x in set.intersection(*(indice[t] for t in ts))
                         if x != c['id'] and x not in origenes_a and len(tokens[x]) > len(ts)]
                if not cands:
                    continue
                tel = (c['telefono'] or '').strip()
                if len(cands) == 1 and tel and (info[cands[0]]['telefono'] or '').strip() == tel:
                    parciales.append((c['id'], cands[0]))
                elif c['id'] not in en_manual:
                    sugerencias.append((c['id'], sorted(cands)[:4]))

            pares = []
            for p in opt['par']:
                try:
                    o, d = (int(x) for x in p.split(':'))
                except ValueError:
                    raise CommandError(f'--par inválido: {p} (use ORIGEN:DESTINO)')
                if o not in info or d not in info or o == d:
                    raise CommandError(f'--par {p}: cliente inexistente o repetido')
                if not importado(info[o]):
                    raise CommandError(f"--par {p}: el origen {o} '{info[o]['nombre']}' no es un cliente "
                                       f"importado de Access (tiene actividad real). No se fusiona.")
                pares.append((o, d))

            todas = pares if opt['solo_pares'] else fusiones + parciales + pares
            destino_de = {}
            for o, d in todas:
                if o in destino_de and destino_de[o] != d:
                    raise CommandError(f'El cliente {o} tiene dos destinos distintos. Revise los --par.')
                destino_de[o] = d

            def final(d):
                vistos = set()
                while d in destino_de:
                    if d in vistos:
                        raise CommandError('Fusión circular detectada. Revise los --par.')
                    vistos.add(d)
                    d = destino_de[d]
                return d
            fusiones = [(o, final(d)) for o, d in destino_de.items()]
            # en la lista manual solo quedan nombres con algún importado sin resolver
            manual = [(k, ms) for k, ms in manual
                      if any(not c['DNI'] and importado(c) and c['id'] not in destino_de for c in ms)]
            sugerencias = [(o, cs) for o, cs in sugerencias if o not in destino_de]

            # ---------------------------------------------------------------- reporte
            def linea(o, d):
                return (f"  {o} '{info[o]['nombre']}' tel {info[o]['telefono'] or '-'}  ->  "
                        f"{d} '{info[d]['nombre']}' DNI {info[d]['DNI'] or '-'} tel {info[d]['telefono'] or '-'}")
            origen_tipo = {}
            if not opt['solo_pares']:
                for o in origenes_a:
                    origen_tipo[o] = 'A'
                for o, _ in parciales:
                    origen_tipo.setdefault(o, 'B')
            for o, _ in pares:
                origen_tipo[o] = 'C'
            for tipo, titulo in (('A', 'NOMBRE IGUAL'), ('B', 'NOMBRE PARCIAL + MISMO TELÉFONO'),
                                 ('C', 'PARES INDICADOS CON --par')):
                sel = [(o, d) for o, d in fusiones if origen_tipo.get(o) == tipo]
                self.stdout.write(f'FUSIONES {titulo}: {len(sel)}')
                for o, d in sorted(sel, key=lambda x: info[x[1]]['nombre'].upper()):
                    self.stdout.write(linea(o, d))
            self.stdout.write(f'TOTAL A FUSIONAR: {len(fusiones)}')
            self.stdout.write(f'\nPOSIBLES DUPLICADOS POR NOMBRE PARCIAL (no se tocan; confirme con --par): {len(sugerencias)}')
            for o, cands in sorted(sugerencias, key=lambda x: info[x[0]]['nombre'].upper()):
                self.stdout.write(f"  {o} '{info[o]['nombre']}' tel {info[o]['telefono'] or '-'}  ?  " + ' | '.join(
                    f"{x} {info[x]['nombre']} DNI {info[x]['DNI'] or '-'} tel {info[x]['telefono'] or '-'}" for x in cands))
            self.stdout.write(f'\nREVISIÓN MANUAL (posibles homónimos, no se tocan; confirme con --par): {len(manual)} nombres')
            for k, miembros in sorted(manual, key=lambda x: x[0]):
                self.stdout.write('  ' + ' | '.join(
                    f"{c['id']} {c['nombre']} DNI {c['DNI'] or '-'}" for c in sorted(miembros, key=lambda c: c['id'])))

            if not opt['ejecutar']:
                transaction.set_rollback(True)
                self.stdout.write(self.style.SUCCESS('\nREVISIÓN: no se modificó nada.'))
                return

            # ---------------------------------------------------------------- fusión
            n_rec = n_dup = n_tk = 0
            for o, d in fusiones:
                firmas_destino = {firma(m) for m in MedidaVista.objects.filter(cliente_id=d)}
                for m in MedidaVista.objects.filter(cliente_id=o):
                    if firma(m) in firmas_destino:
                        m.delete()
                        n_dup += 1
                    else:
                        MedidaVista.objects.filter(pk=m.pk).update(cliente_id=d)
                        firmas_destino.add(firma(m))
                        n_rec += 1
                n_tk += TicketVenta.objects.filter(cliente_id=o).update(cliente_id=d)
                if importado(info[d]):     # solo se completa un cliente importado, nunca uno real
                    cambios = {}
                    if not info[d]['telefono'] and info[o]['telefono']:
                        cambios['telefono'] = info[d]['telefono'] = info[o]['telefono']
                    fo, fd = info[o]['fecha_registro'], info[d]['fecha_registro']
                    if fo and (not fd or fo < fd):
                        cambios['fecha_registro'] = info[d]['fecha_registro'] = fo
                    if cambios:
                        Cliente.objects.filter(pk=d).update(**cambios)
                Cliente.objects.filter(pk=o).delete()

            if Cliente.objects.filter(pk__in=[o for o, _ in fusiones]).exists():
                raise CommandError('Quedaron clientes sin fusionar. Se revirtió todo.')
            self.stdout.write(self.style.SUCCESS(
                f'\nFUSIÓN CONFIRMADA: {len(fusiones)} clientes fusionados; recetas movidas {n_rec}, '
                f'recetas repetidas descartadas {n_dup}, tickets movidos {n_tk}.'))
