"""
Corrige las ventas que no descontaron inventario ni generaron movimiento en el kardex
entre el 21/10/2026 (ticket 2419) y el 07/11/2026 (ticket 2552).
Se conecta directo a la base de Heroku con el URI (variable DATABASE_URL).

Por cada línea de venta ligada a un producto en ese rango que NO tenga salida (OUT)
en el kardex para su ticket y producto:
  1. crea la salida en el kardex, ligada al ticket, con la fecha y hora del ticket, y
  2. descuenta la cantidad del stock del producto.
Se puede correr varias veces: lo que ya tiene salida se omite.
Si el stock es menor que la cantidad vendida, no se toca y aparece en "REVISAR".

USO EN POWERSHELL (desde la carpeta donde está este archivo)
  0) Respaldo: Heroku > Resources > Heroku Postgres > Durability > Create Manual Backup
  1) Una sola vez:            pip install psycopg2-binary
  2) Configurar el URI:       $env:DATABASE_URL = Read-Host "Pega el URI de PostgreSQL de Heroku"
  3) Simulación:              python corregir_kardex_uri.py
  4) Prueba con un ticket:    $env:SOLO_TICKET = "2499"; $env:APLICAR = "1"; python corregir_kardex_uri.py
  5) Todos:                   Remove-Item Env:SOLO_TICKET; $env:APLICAR = "1"; python corregir_kardex_uri.py
  Al terminar:                Remove-Item Env:APLICAR; Remove-Item Env:DATABASE_URL
"""
import os
import sys
import psycopg2

URI = os.environ.get("DATABASE_URL")
if not URI:
    sys.exit("Falta DATABASE_URL. Ejecuta primero: $env:DATABASE_URL = Read-Host \"Pega el URI\"")
APLICAR = os.environ.get("APLICAR") == "1"
SOLO_TICKET = os.environ.get("SOLO_TICKET")

kw = {}
if "sslmode" not in URI and "localhost" not in URI and "host=/" not in URI:
    kw["sslmode"] = "require"
conn = psycopg2.connect(URI, **kw)
conn.autocommit = False
cur = conn.cursor()

sql = """
select d.id, t.id, t.numero, d.producto_id, coalesce(d.cantidad, 1), d.descripcion,
       (t.fecha_emision + coalesce(t.hora_emision, time '00:00')) at time zone 'America/Lima'
from core_detalleticketventa d
join core_ticketventa t on t.id = d.ticket_numero_id
where d.producto_id is not null
  and t.numero between 2419 and 2552
  and t.fecha_emision between date '2026-10-21' and date '2026-11-07'
  and not exists (select 1 from core_kardexmovimiento k
                  where k.ticket_id = t.id and k.producto_id = d.producto_id and k.tipo = 'OUT')
"""
params = []
if SOLO_TICKET:
    sql += " and t.numero = %s"
    params.append(int(SOLO_TICKET))
sql += " order by t.fecha_emision, t.hora_emision, d.id"
cur.execute(sql, params)
lineas = cur.fetchall()

corregidas, revisar = [], []
try:
    for det_id, ticket_id, numero, prod_id, cant, desc, fecha in lineas:
        cur.execute("select cod, stock, coalesce(costo_promedio, 0) from core_producto where id = %s for update", (prod_id,))
        cod, stock, costo = cur.fetchone()
        if stock < cant:
            revisar.append((numero, cod, desc, stock))
            continue
        corregidas.append((numero, cod, desc, stock, stock - cant))
        cur.execute(
            """insert into core_kardexmovimiento
               (fecha, tipo, cantidad, costo_unitario, costo_total, stock_anterior, stock_actual,
                costo_promedio, producto_id, ticket_id, compra_id, ajuste_id)
               values (%s, 'OUT', %s, %s, %s, %s, %s, %s, %s, %s, null, null)""",
            (fecha, cant, costo, costo * cant, stock, stock - cant, costo, prod_id, ticket_id))
        cur.execute("update core_producto set stock = stock - %s where id = %s", (cant, prod_id))
    if APLICAR:
        conn.commit()
    else:
        conn.rollback()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()

print("\n=== " + ("APLICADO" if APLICAR else "SIMULACIÓN (no se cambió nada)") + " ===")
print(f"Líneas corregidas: {len(corregidas)}")
for n, cod, desc, a, b in corregidas:
    print(f"  ticket {n:>5} | {cod:<10} | stock {a} -> {b} | {desc}")
print(f"REVISAR a mano (stock menor que la cantidad vendida): {len(revisar)}")
for n, cod, desc, a in revisar:
    print(f"  ticket {n:>5} | {cod:<10} | stock actual {a} | {desc}")
