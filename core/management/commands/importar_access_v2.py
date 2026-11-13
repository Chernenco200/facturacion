"""Importación Access -> Django V2: clientes, tickets históricos y recetas en UNA transacción.

Instalar en: core/management/commands/importar_access_v2.py
Requiere en --carpeta: BDIC_Clientes.xlsx, BDICMIGUEL_Clientes.xlsx, FacturaIC.xlsx, FacturaMIGUEL.xlsx,
DetalleFacturaIC.xlsx, DetalleFacturaMIGUEL.xlsx, HistorialClientesIC.xlsx, HistorialClientesMIGUEL.xlsx

Modos:
  python manage.py importar_access_v2 --carpeta X --simular            (solo reportes)
  python manage.py importar_access_v2 --carpeta X --ensayar            (inserta y revierte)
  python manage.py importar_access_v2 --carpeta X --importar --confirmar IMPORTAR_ACCESS_V2

Reglas principales:
  * Identidad del cliente: DNI de 8 dígitos (común a IC y MIGUEL). Si no hay DNI válido, el campo RUC
    de Access es la clave del cliente dentro de su origen (es único en la tabla de clientes).
    RUC basura (vacío, nd, 000, 1234...) => no identificable, solo reporte.
  * Clientes que ya existen en Heroku por DNI: se usan tal cual, NO se modifican.
  * Clientes nuevos: DNI válido o NULL (nunca ''), excluir_reactivacion=True,
    fecha_registro = primera fecha conocida en Access (no la fecha de hoy).
  * Fila cuyo nombre no corresponde al cliente de ese DNI/clave => REVISAR (no se importa).
  * Tickets: numero = 1100000000 + Id (IC) / 1200000000 + Id (MIGUEL); hora 00:00; sin caja, pagos,
    kardex ni contabilidad. Se omiten ventas ya existentes en Heroku (cliente/nombre + fecha + total).
  * Recetas: obligatorio tener fecha (las sin fecha van al reporte). Mismas reglas ópticas que V8.
"""
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from openpyxl import load_workbook

from core.models import Cliente, DetalleTicketVenta, MedidaVista, TicketVenta

SOURCES = {
    'IC': {'clientes': 'BDIC_Clientes.xlsx', 'facturas': 'FacturaIC.xlsx',
           'detalles': 'DetalleFacturaIC.xlsx', 'historial': 'HistorialClientesIC.xlsx'},
    'MIGUEL': {'clientes': 'BDICMIGUEL_Clientes.xlsx', 'facturas': 'FacturaMIGUEL.xlsx',
               'detalles': 'DetalleFacturaMIGUEL.xlsx', 'historial': 'HistorialClientesMIGUEL.xlsx'},
}
PREFIX = {'IC': 1100000000, 'MIGUEL': 1200000000}
CENT = Decimal('0.01')
JUNK_RUC = re.compile(r'^(0*|nd|n/d|s/n|sn|sin dni|-+|\.+|\d{1,5})$', re.I)

# Correcciones de eje aprobadas previamente (V8)
AXIS_FIXES = {
    ('IC', '291', 'OD_Eje'): (Decimal('1.75'), Decimal('175')),
    ('MIGUEL', '1895', 'OI_Eje'): (Decimal('1.72'), Decimal('172')),
    ('MIGUEL', '1903', 'OI_Eje'): (Decimal('1.55'), Decimal('155')),
    ('MIGUEL', '1907', 'OD_Eje'): (Decimal('1.76'), Decimal('176')),
    ('MIGUEL', '2003', 'OD_Eje'): (Decimal('1.76'), Decimal('176')),
}
NUMERIC = ('OD_Esf', 'OD_Cil', 'OD_Eje', 'OI_Esf', 'OI_Cil', 'OI_Eje',
           'OD_Dip', 'OI_DIP', 'Add', 'OD_Dip_Cerca', 'OI_Dip_Cerca')
RECETA_FIELDS = ['esf_lejos_OD', 'cil_lejos_OD', 'eje_lejos_OD', 'DIP_lejos_OD',
                 'esf_lejos_OI', 'cil_lejos_OI', 'eje_lejos_OI', 'DIP_lejos_OI',
                 'Add_lejos_OD', 'Add_lejos_OI',
                 'esf_cerca_OD', 'cil_cerca_OD', 'eje_cerca_OD', 'DIP_cerca_OD',
                 'esf_cerca_OI', 'cil_cerca_OI', 'eje_cerca_OI', 'DIP_cerca_OI']


# ----------------------------------------------------------------------------- utilidades
def clean(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return ' '.join(str(v).split())


def valid_dni(v):
    s = clean(v)
    return s if re.fullmatch(r'\d{8}', s) else ''


def norm_name(v):
    v = unicodedata.normalize('NFKD', clean(v).casefold())
    v = ''.join(c for c in v if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9ñ ]', ' ', v).split())


def same_person(a, b):
    """True si dos nombres pueden ser la misma persona.
    Compara palabras (>=3 letras) con tolerancia a errores de tipeo (similitud >= 0.7).
    Exige 2 palabras coincidentes cuando ambos nombres tienen 2 o más palabras,
    para no mezclar familiares que comparten apellido o DNI."""
    ta = [t for t in norm_name(a).split() if len(t) >= 3]
    tb = [t for t in norm_name(b).split() if len(t) >= 3]
    if not ta or not tb:
        return True
    hits = sum(1 for x in ta if any(SequenceMatcher(None, x, y).ratio() >= 0.7 for y in tb))
    return hits >= min(2, len(ta), len(tb))


def first_phone(v):
    raw = clean(v).upper()
    if raw in ('', 'SN', 'S/N', 'SIN NUMERO', 'SIN NÚMERO', 'NO TIENE', '0', '-', 'NINGUNO'):
        return None
    for chunk in re.split(r'[/,;\-]| Y ', raw):
        digits = re.sub(r'\D', '', chunk)
        if 7 <= len(digits) <= 15 and set(digits) != {'0'}:
            return digits
    return None


def amount(v):
    try:
        n = Decimal(clean(v)).quantize(CENT)
        return n if n.is_finite() and Decimal('0') <= n < Decimal('100000000') else None
    except (InvalidOperation, ValueError):
        return None


def number(v):
    s = clean(v)
    if not s:
        return None
    try:
        n = Decimal(s.replace(',', '.'))
        return n if n.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def parse_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = clean(v)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def sheet(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        it = iter(wb.active.values)
        header = [clean(x) for x in next(it)]
        for line, values in enumerate(it, 2):
            if any(clean(x) for x in values):
                yield line, dict(zip(header, values))
    finally:
        wb.close()


def write_csv(path, rows, cols):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def client_key(src, raw_ruc):
    doc = valid_dni(raw_ruc)
    if doc:
        return ('DNI', doc)
    raw = clean(raw_ruc)
    if JUNK_RUC.match(raw):
        return None
    return ('ACC', src, raw)


def key_label(k):
    return '' if k is None else (k[1] if k[0] == 'DNI' else f'{k[1]}:{k[2]}')


# ----------------------------------------------------------------------------- recetas
def parse_receta(src, record):
    """Devuelve (valores_modelo | None, problemas, marcadores, correcciones). Reglas de V8."""
    problems, markers, corrections = [], [], []
    nums = {c: number(record.get(c)) for c in NUMERIC}
    for col in ('OD_Eje', 'OI_Eje'):
        fix = AXIS_FIXES.get((src, clean(record.get('Id')), col))
        if fix and nums[col] == fix[0]:
            nums[col] = fix[1]
            corrections.append(f'{col}: {fix[0]} -> {fix[1]}')
    for col in ('OD_Dip', 'OI_DIP', 'OD_Dip_Cerca', 'OI_Dip_Cerca', 'Add'):
        if nums[col] is None and not clean(record.get(col)):
            nums[col] = Decimal('0')
            markers.append(col)
    if any(clean(record.get(c)) and nums[c] is None for c in NUMERIC):
        problems.append('VALOR_NUMERICO_INVALIDO')
    for eye in ('OD', 'OI'):
        esf, cil, eje = f'{eye}_Esf', f'{eye}_Cil', f'{eye}_Eje'
        if nums[esf] is not None and not clean(record.get(cil)) and not clean(record.get(eje)):
            nums[cil] = nums[eje] = Decimal('0')
            markers += [cil, eje]
        elif nums[cil] == 0 and not clean(record.get(eje)):
            nums[eje] = Decimal('0')
            markers.append(eje)
        for c in (esf, cil, eje):
            if nums[c] is None:
                problems.append('GRADUACION_INCOMPLETA')
        for c in (('OD_Dip', 'OD_Dip_Cerca') if eye == 'OD' else ('OI_DIP', 'OI_Dip_Cerca')):
            if nums[c] not in (None, 0) and not (Decimal('15') <= nums[c] <= Decimal('80')):
                problems.append('DIP_FUERA_RANGO')
        if nums[cil] is not None and nums[cil] > 0:
            problems.append('CILINDRO_POSITIVO_REVISAR')
        if nums[eje] is not None and not (0 <= nums[eje] <= 180):
            problems.append('EJE_FUERA_RANGO')
    add = nums['Add']
    if add is None:
        problems.append('ADD_INVALIDA')
    elif not (0 <= add <= 4):
        problems.append('ADD_FUERA_RANGO')
    elif all(nums[f'{e}_Esf'] is not None for e in ('OD', 'OI')):
        if any(not (-30 <= nums[f'{e}_Esf'] + add <= 30) for e in ('OD', 'OI')):
            problems.append('ESFERA_CERCA_FUERA_RANGO')
    if all(nums[k] in (None, Decimal(0)) for k in ('OD_Esf', 'OD_Cil', 'OI_Esf', 'OI_Cil', 'Add')):
        problems.append('SIN_GRADUACION_IDENTIFICABLE')
    if problems:
        return None, problems, markers, corrections
    values = dict(zip(RECETA_FIELDS, (
        nums['OD_Esf'], nums['OD_Cil'], nums['OD_Eje'], float(nums['OD_Dip']),
        nums['OI_Esf'], nums['OI_Cil'], nums['OI_Eje'], float(nums['OI_DIP']),
        add, add,
        nums['OD_Esf'] + add, nums['OD_Cil'], nums['OD_Eje'], float(nums['OD_Dip_Cerca']),
        nums['OI_Esf'] + add, nums['OI_Cil'], nums['OI_Eje'], float(nums['OI_Dip_Cerca']))))
    # precisión según el modelo
    for fname, val in values.items():
        field = MedidaVista._meta.get_field(fname)
        if getattr(field, 'max_digits', None):
            q = Decimal(val).quantize(Decimal(1).scaleb(-field.decimal_places))
            if q != val or len(str(abs(int(q)))) > field.max_digits - field.decimal_places:
                return None, [f'PRECISION_INVALIDA:{fname}'], markers, corrections
    return values, [], markers, corrections


def receta_signature(client_ref, dt, values):
    return (client_ref, dt, tuple('' if values[f] is None else str(Decimal(str(values[f])).normalize())
                                  for f in RECETA_FIELDS))


# ----------------------------------------------------------------------------- comando
class Command(BaseCommand):
    help = 'Importa clientes, tickets históricos y recetas de Access (V2, una sola transacción).'

    def add_arguments(self, parser):
        parser.add_argument('--carpeta', required=True)
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument('--simular', action='store_true')
        modes.add_argument('--ensayar', action='store_true')
        modes.add_argument('--importar', action='store_true')
        parser.add_argument('--confirmar', default='')

    def handle(self, *args, **opt):
        if opt['importar'] and opt['confirmar'] != 'IMPORTAR_ACCESS_V2':
            raise CommandError('Para importar: --importar --confirmar IMPORTAR_ACCESS_V2')
        if connection.vendor != 'postgresql':
            raise CommandError('Solo PostgreSQL. Conexión actual: ' + connection.vendor)
        base = Path(opt['carpeta']).expanduser().resolve()
        faltan = [f for s in SOURCES.values() for f in s.values() if not (base / f).is_file()]
        if faltan:
            raise CommandError('Faltan archivos: ' + ', '.join(faltan))

        # La base debe estar limpia de importaciones Access anteriores (paso 01).
        if TicketVenta.objects.filter(numero__gte=1100000000, numero__lte=1299999999).exists():
            raise CommandError('Ya existen tickets Access (11/12xxxxxxxx). Ejecute primero 01_base_sin_migracion.sql')
        if MedidaVista.objects.filter(descripcion__startswith='MIGRACION ACCESS ').exists():
            raise CommandError('Ya existen recetas MIGRACION ACCESS. Ejecute primero 01_base_sin_migracion.sql')

        # ------------------------------------------------------------- lectura
        data = {src: {k: list(sheet(base / f)) for k, f in files.items()} for src, files in SOURCES.items()}

        heroku_dni = defaultdict(list)
        heroku_name = {}
        for pk, doc, name in Cliente.objects.values_list('pk', 'DNI', 'nombre').iterator(chunk_size=2000):
            heroku_name[pk] = name
            if valid_dni(doc):
                heroku_dni[valid_dni(doc)].append(pk)
        heroku_dni_snapshot = {d: tuple(v) for d, v in heroku_dni.items()}

        existing_sales = set()
        for cid, cname, dt, total in TicketVenta.objects.values_list(
                'cliente_id', 'cliente__nombre', 'fecha_emision', 'total').iterator(chunk_size=2000):
            existing_sales.add(('ID', cid, dt, Decimal(total)))
            existing_sales.add(('NOMBRE', norm_name(cname), dt, Decimal(total)))
        existing_nums = set(TicketVenta.objects.values_list('numero', flat=True))
        existing_recetas = set()
        for vals in MedidaVista.objects.values_list('cliente_id', 'fecha_registro', *RECETA_FIELDS).iterator(chunk_size=2000):
            existing_recetas.add(receta_signature(('ID', vals[0]), vals[1], dict(zip(RECETA_FIELDS, vals[2:]))))

        # ------------------------------------------------------------- ficha de cada cliente Access
        ficha = {}             # key -> dict(nombre, telefono)
        names_by_key = defaultdict(Counter)
        for src in SOURCES:
            for kind in ('clientes', 'historial', 'facturas'):
                for _, r in data[src][kind]:
                    k = client_key(src, r.get('RUC'))
                    if not k:
                        continue
                    name = clean(r.get('Cliente'))
                    if name:
                        names_by_key[k][name] += 1
                    if kind == 'clientes' and k not in ficha and name:
                        ficha[k] = {'nombre': name, 'telefono': first_phone(r.get('Telefono'))}
        for src in SOURCES:
            for _, r in data[src]['historial']:      # teléfono de respaldo
                k = client_key(src, r.get('RUC'))
                if k and k in ficha and not ficha[k]['telefono']:
                    ficha[k]['telefono'] = first_phone(r.get('Telefono'))
                elif k and k not in ficha and names_by_key[k]:
                    ficha[k] = {'nombre': names_by_key[k].most_common(1)[0][0],
                                'telefono': first_phone(r.get('Telefono'))}
        for k, cnt in names_by_key.items():
            ficha.setdefault(k, {'nombre': cnt.most_common(1)[0][0], 'telefono': None})

        def resolve(k):
            """(estado, cliente_id_heroku|None, nombre_referencia)"""
            if k is None:
                return 'NO_IDENTIFICABLE', None, ''
            if k[0] == 'DNI':
                ids = heroku_dni.get(k[1], [])
                if len(ids) > 1:
                    return 'DNI_DUPLICADO_HEROKU', None, ''
                if ids:
                    return 'EXISTE', ids[0], heroku_name[ids[0]]
            return 'NUEVO', None, ficha.get(k, {}).get('nombre', '')

        # ------------------------------------------------------------- facturas
        accepted_tickets, rep_fact = [], []
        seen_sale = set()
        for src in SOURCES:
            facturas = data[src]['facturas']
            nums = Counter(clean(r.get('Numero_Factura')) for _, r in facturas)
            ids = Counter(clean(r.get('Id')) for _, r in facturas)
            det_by = defaultdict(list)
            for line, d in data[src]['detalles']:
                det_by[clean(d.get('Factura'))].append((line, d))
            for line, r in facturas:
                p = []
                k = client_key(src, r.get('RUC'))
                estado, hid, ref = resolve(k)
                if estado in ('NO_IDENTIFICABLE', 'DNI_DUPLICADO_HEROKU'):
                    p.append(estado)
                elif not same_person(r.get('Cliente'), ref):
                    p.append('NOMBRE_NO_COINCIDE')
                orig, aid = clean(r.get('Numero_Factura')), clean(r.get('Id'))
                dt, total = parse_date(r.get('Fecha')), amount(r.get('Total'))
                if not dt: p.append('FECHA_INVALIDA')
                if total is None: p.append('TOTAL_INVALIDO')
                elif total == 0: p.append('TOTAL_CERO_REVISAR')
                if not orig or nums[orig] != 1: p.append('NUMERO_FACTURA_AMBIGUO')
                if not aid.isdigit() or ids[aid] != 1: p.append('ID_ACCESS_INVALIDO')
                numero = PREFIX[src] + int(aid) if aid.isdigit() else None
                if numero is not None and (int(aid) >= 100000000 or numero in existing_nums):
                    p.append('NUMERO_DESTINO_OCUPADO')
                lines = []
                for dline, d in det_by.get(orig, []) if orig else []:
                    if valid_dni(d.get('RUC')) and valid_dni(d.get('RUC')) != valid_dni(r.get('RUC')):
                        p.append('DNI_DETALLE_DIFERENTE')
                    price = amount(d.get('Precio'))
                    try:
                        qty = Decimal(clean(d.get('Cantidad')))
                        if qty <= 0 or qty != int(qty) or qty > 2147483647:
                            raise ValueError
                        qty = int(qty)
                    except (InvalidOperation, ValueError):
                        qty = None
                        p.append('CANTIDAD_INVALIDA')
                    if price is None: p.append('PRECIO_DETALLE_INVALIDO')
                    desc = ' - '.join(x for x in (clean(d.get('Producto')), clean(d.get('Descripcion'))) if x) \
                        or clean(d.get('Codigo_Producto'))
                    if not desc: p.append('DESCRIPCION_DETALLE_VACIA')
                    lines.append((desc, qty, price))
                if not lines: p.append('SIN_DETALLES')
                elif total is not None and all(q is not None and pr is not None for _, q, pr in lines):
                    if abs(sum(pr * q for _, q, pr in lines) - total) > Decimal('0.02'):
                        p.append('TOTAL_DIFIERE_DETALLES')
                if dt and total is not None and estado in ('EXISTE', 'NUEVO'):
                    if (hid and ('ID', hid, dt, total) in existing_sales) or \
                            ('NOMBRE', norm_name(r.get('Cliente')), dt, total) in existing_sales:
                        p.append('VENTA_YA_EXISTE_EN_HEROKU')
                    elif (k, dt, total) in seen_sale:
                        p.append('VENTA_DUPLICADA_EN_ACCESS')
                    seen_sale.add((k, dt, total))
                ok = not p
                if ok:
                    accepted_tickets.append(dict(src=src, key=k, fecha=dt, total=total, numero=numero,
                                                 vendedor=(clean(r.get('Vendedor')) or 'HISTORICO')[:100], lines=lines))
                rep_fact.append(dict(origen=src, fila=line, id_access=aid, factura=orig, numero_destino=numero or '',
                                     ruc=clean(r.get('RUC')), cliente_access=clean(r.get('Cliente')),
                                     cliente_referencia=ref, clave=key_label(k), fecha=dt or '', total=total if total is not None else '',
                                     detalles=len(lines), estado='IMPORTAR' if ok else 'REVISAR',
                                     motivos=';'.join(sorted(set(p)))))

        # ------------------------------------------------------------- recetas
        accepted_recetas, rep_rec = [], []
        seen_rec = set()
        for src in SOURCES:
            hist = data[src]['historial']
            ids = Counter(clean(r.get('Id')) for _, r in hist)
            for line, r in hist:
                p = []
                k = client_key(src, r.get('RUC'))
                estado, hid, ref = resolve(k)
                if estado in ('NO_IDENTIFICABLE', 'DNI_DUPLICADO_HEROKU'):
                    p.append(estado)
                elif not same_person(r.get('Cliente'), ref):
                    p.append('NOMBRE_NO_COINCIDE')
                aid = clean(r.get('Id'))
                if not aid or ids[aid] != 1:
                    p.append('ID_ACCESS_INVALIDO')
                raw_dt = clean(r.get('Fecha'))
                dt = parse_date(r.get('Fecha'))
                if not raw_dt:
                    p.append('SIN_FECHA')
                elif not dt:
                    p.append('FECHA_INVALIDA')
                values, rp, markers, corr = parse_receta(src, r)
                p += rp
                desc = ('MIGRACION ACCESS ' + src + ' ID ' + aid +
                        (' | SIN DATO ORIGINAL: ' + ', '.join(markers) if markers else '') +
                        (' | CERCA NO CONFIRMADA: ADD AUSENTE' if 'Add' in markers else '') +
                        (' | EJE CORREGIDO: ' + ', '.join(corr) if corr else ''))[:255]
                if values and not p:
                    ref_id = ('ID', hid) if hid else ('KEY', k)
                    sig = receta_signature(ref_id, dt, values)
                    if hid and sig in existing_recetas:
                        p.append('RECETA_YA_EXISTE_EN_HEROKU')
                    elif sig in seen_rec:
                        p.append('RECETA_DUPLICADA_EN_ACCESS')
                    seen_rec.add(sig)
                ok = not p
                if ok:
                    accepted_recetas.append(dict(key=k, fecha=dt, values=values, descripcion=desc))
                rep_rec.append(dict(origen=src, fila=line, id_access=aid, ruc=clean(r.get('RUC')),
                                    cliente_access=clean(r.get('Cliente')), cliente_referencia=ref, clave=key_label(k),
                                    fecha=dt or '', estado='IMPORTAR' if ok else 'REVISAR',
                                    motivos=';'.join(sorted(set(p))), descripcion=desc,
                                    **{c: clean(r.get(c)) for c in NUMERIC}))

        # ------------------------------------------------------------- clientes a crear
        used = defaultdict(list)
        for t in accepted_tickets:
            used[t['key']].append(t['fecha'])
        for rc in accepted_recetas:
            used[rc['key']].append(rc['fecha'])
        to_create, rep_cli = {}, []
        for k, fechas in sorted(used.items(), key=lambda x: key_label(x[0])):
            estado, hid, ref = resolve(k)
            if estado == 'NUEVO':
                f = ficha[k]
                to_create[k] = dict(DNI=k[1] if k[0] == 'DNI' else None, nombre=f['nombre'][:255],
                                    telefono=f['telefono'], fecha_registro=min(fechas))
                if not f['nombre'].strip():
                    raise CommandError(f'Cliente sin nombre: {key_label(k)}')
            rep_cli.append(dict(clave=key_label(k), estado=estado, cliente_id_heroku=hid or '',
                                dni=k[1] if k[0] == 'DNI' else '', nombre=ref if hid else to_create[k]['nombre'],
                                telefono='' if hid else (to_create[k]['telefono'] or ''),
                                fecha_registro='' if hid else to_create[k]['fecha_registro'],
                                tickets=sum(1 for t in accepted_tickets if t['key'] == k),
                                recetas=sum(1 for r in accepted_recetas if r['key'] == k)))

        # ------------------------------------------------------------- reportes
        out = base / 'auditoria_v2'
        out.mkdir(parents=True, exist_ok=True)
        write_csv(out / 'facturas.csv', rep_fact, list(rep_fact[0].keys()))
        write_csv(out / 'recetas.csv', rep_rec, list(rep_rec[0].keys()))
        write_csv(out / 'clientes.csv', rep_cli, list(rep_cli[0].keys()))
        resumen = [
            f'Facturas: {dict(Counter(r["estado"] for r in rep_fact))}',
            f'  motivos: {dict(Counter(m for r in rep_fact for m in r["motivos"].split(";") if m))}',
            f'Recetas: {dict(Counter(r["estado"] for r in rep_rec))}',
            f'  motivos: {dict(Counter(m for r in rep_rec for m in r["motivos"].split(";") if m))}',
            f'Clientes usados: {dict(Counter(r["estado"] for r in rep_cli))}',
            f'  nuevos con DNI: {sum(1 for v in to_create.values() if v["DNI"])}; nuevos sin DNI: {sum(1 for v in to_create.values() if not v["DNI"])}',
            f'Tickets a importar: {len(accepted_tickets)}; detalles: {sum(len(t["lines"]) for t in accepted_tickets)}',
            f'Recetas a importar: {len(accepted_recetas)}',
        ]
        (out / 'resumen.txt').write_text('\n'.join(resumen), encoding='utf-8')
        for line in resumen:
            self.stdout.write(line)
        self.stdout.write(f'Reportes: {out}')
        if not (opt['importar'] or opt['ensayar']):
            self.stdout.write(self.style.SUCCESS('SIMULACIÓN: no se modificó la base de datos.'))
            return

        # ------------------------------------------------------------- escritura
        with transaction.atomic():
            with connection.cursor() as cur:
                for model in (Cliente, TicketVenta, MedidaVista):
                    cur.execute('LOCK TABLE %s IN SHARE ROW EXCLUSIVE MODE' % connection.ops.quote_name(model._meta.db_table))
            live = defaultdict(list)
            for pk, doc in Cliente.objects.values_list('pk', 'DNI'):
                if valid_dni(doc):
                    live[valid_dni(doc)].append(pk)
            for k in used:
                if k[0] == 'DNI' and tuple(live.get(k[1], [])) != heroku_dni_snapshot.get(k[1], ()):
                    raise CommandError(f'Cambió el DNI {k[1]} en Heroku durante la importación. Cancelado.')
            dest = [t['numero'] for t in accepted_tickets]
            if len(dest) != len(set(dest)) or TicketVenta.objects.filter(numero__in=dest).exists():
                raise CommandError('Números de ticket destino ocupados o repetidos. Cancelado.')

            keys = list(to_create)
            objs = Cliente.objects.bulk_create(
                [Cliente(excluir_reactivacion=True, **to_create[k]) for k in keys], batch_size=500)
            cid = {k: o.pk for k, o in zip(keys, objs)}
            for k in used:
                if k not in cid:
                    cid[k] = resolve(k)[1]
            if any(v is None for v in cid.values()):
                raise CommandError('Cliente sin resolver. Cancelado.')

            TicketVenta.objects.bulk_create([
                TicketVenta(numero=t['numero'], cliente_id=cid[t['key']], vendedor=t['vendedor'],
                            fecha_emision=t['fecha'], total=t['total'], a_cuenta=t['total'],
                            saldo=Decimal('0.00'), puntos_ic=0) for t in accepted_tickets], batch_size=500)
            TicketVenta.objects.filter(numero__in=dest).update(hora_emision=time(0, 0))
            tid = dict(TicketVenta.objects.filter(numero__in=dest).values_list('numero', 'pk'))
            DetalleTicketVenta.objects.bulk_create([
                DetalleTicketVenta(ticket_numero_id=tid[t['numero']], producto_id=None,
                                   descripcion=d, cantidad=q, precio=pr)
                for t in accepted_tickets for d, q, pr in t['lines']], batch_size=1000)
            MedidaVista.objects.bulk_create([
                MedidaVista(cliente_id=cid[r['key']], fecha_registro=r['fecha'], Optometra=None,
                            descripcion=r['descripcion'], **r['values']) for r in accepted_recetas], batch_size=500)

            n_det = DetalleTicketVenta.objects.filter(ticket_numero_id__in=tid.values()).count()
            n_rec = MedidaVista.objects.filter(descripcion__startswith='MIGRACION ACCESS ').count()
            if len(tid) != len(accepted_tickets) or n_det != sum(len(t['lines']) for t in accepted_tickets) \
                    or n_rec != len(accepted_recetas):
                raise CommandError('Conteos inconsistentes después de insertar. Revirtiendo.')
            msg = f'clientes nuevos={len(objs)}, tickets={len(tid)}, detalles={n_det}, recetas={n_rec}'
            if opt['ensayar']:
                transaction.set_rollback(True)
                self.stdout.write(self.style.SUCCESS('ENSAYO CORRECTO (revertido): ' + msg))
            else:
                self.stdout.write(self.style.SUCCESS('IMPORTACIÓN CONFIRMADA: ' + msg))
