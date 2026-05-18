#!/usr/bin/env python3
"""
Script de migración: Copia todos los datos de DATABASE_URL a database_url_definitiva
  Paso 1: Crea todas las tablas en la base de datos definitiva
  Paso 2: Copia los datos en lotes con progreso visible
  Paso 3: Actualiza las secuencias de ID (autoincrement)
Uso: python migrate_to_final.py
"""
import os
import sys
from dotenv import dotenv_values

BATCH_SIZE = 500  # filas por lote de inserción

# --- Leer URLs del .env ---
env_values = dotenv_values('.env')

SOURCE_URL = env_values.get('DATABASE_URL')
raw_dest = env_values.get('database_url_definitiva', '')

# El .env tiene el prefijo "DATABASE_URL=" extra en la url definitiva
if raw_dest.startswith('DATABASE_URL='):
    DEST_URL = raw_dest[len('DATABASE_URL='):]
else:
    DEST_URL = raw_dest

if not SOURCE_URL:
    print("ERROR: No se encontró DATABASE_URL en .env")
    sys.exit(1)
if not DEST_URL:
    print("ERROR: No se encontró database_url_definitiva en .env")
    sys.exit(1)

print("=" * 65)
print("          MIGRACIÓN DE BASE DE DATOS")
print("=" * 65)
print(f"Origen:  {SOURCE_URL[:70]}")
print(f"Destino: {DEST_URL[:70]}")
print()

if 'your-tenant-id' in DEST_URL:
    print("ADVERTENCIA: La URL destino contiene 'your-tenant-id'.")
    print("  Reemplazá ese valor con el tenant ID real en tu .env")
    resp = input("\n¿Continuar de todas formas? (s/n): ").strip().lower()
    if resp != 's':
        print("Migración cancelada.")
        sys.exit(0)
    print()

# ---------------------------------------------------------------------------
# PASO 1: Crear tablas en base de datos destino
# ---------------------------------------------------------------------------
print("Paso 1: Creando tablas en base de datos definitiva...")

try:
    from sqlalchemy import create_engine
    from models import (
        db, User, Broker, BrokerRating, Investment, Portfolio,
        Stock, PortfolioStock, PriceHistory, Message, ActivityLog
    )
    engine_dest = create_engine(DEST_URL, connect_args={'connect_timeout': 10})
    db.metadata.create_all(engine_dest)
    engine_dest.dispose()
    print("  OK  Tablas creadas exitosamente")
except Exception as e:
    print(f"  ERROR creando tablas: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# PASO 2: Copiar datos en lotes
# ---------------------------------------------------------------------------
print("\nPaso 2: Copiando datos...")

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Orden que respeta dependencias de foreign keys
TABLES = [
    'users',
    'brokers',
    'stocks',
    'portfolios',
    'investments',
    'broker_ratings',
    'portfolio_stocks',
    'price_history',    # probablemente la tabla más grande
    'messages',         # self-reference en parent_id, manejo especial
    'activity_logs',
]

try:
    src_conn = psycopg2.connect(SOURCE_URL, connect_timeout=10)
    dest_conn = psycopg2.connect(DEST_URL, connect_timeout=10)
    print("  OK  Conexiones establecidas\n")
except Exception as e:
    print(f"  ERROR conectando: {e}")
    sys.exit(1)

dest_cur = dest_conn.cursor()
total_rows = 0


def contar_filas(conn, table):
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    n = cur.fetchone()[0]
    cur.close()
    return n


def copiar_tabla(table, columns, rows_iter, total):
    """Inserta filas en lotes de BATCH_SIZE con progreso en pantalla."""
    col_str = ', '.join(f'"{c}"' for c in columns)
    sql = f'INSERT INTO "{table}" ({col_str}) VALUES %s ON CONFLICT DO NOTHING'

    count = 0
    batch = []

    def flush(batch):
        if batch:
            execute_values(dest_cur, sql, batch, page_size=BATCH_SIZE)
            dest_conn.commit()

    for row in rows_iter:
        batch.append(tuple(row[c] for c in columns))
        count += 1
        if len(batch) >= BATCH_SIZE:
            flush(batch)
            batch = []
            # Progreso en la misma línea
            pct = int(count / total * 100) if total else 0
            print(f"\r    {count}/{total} filas ({pct}%)...", end='', flush=True)

    flush(batch)
    return count


try:
    for table in TABLES:
        # Contar filas en origen para mostrar progreso real
        try:
            total = contar_filas(src_conn, table)
        except Exception:
            total = 0

        if total == 0:
            print(f"  -    {table}: vacía, omitiendo")
            continue

        print(f"  -->  {table}: {total} filas", end='', flush=True)

        # Obtener nombres de columnas con query liviana (LIMIT 0)
        try:
            col_cur = src_conn.cursor()
            col_cur.execute(f'SELECT * FROM "{table}" LIMIT 0')
            columns = [desc[0] for desc in col_cur.description]
            col_cur.close()
        except Exception as e:
            print(f"\n  WARN {table}: no se pudo leer columnas ({e}), omitiendo")
            src_conn.rollback()
            continue

        # Usar cursor del lado del servidor para no cargar todo en memoria
        src_cur = src_conn.cursor(name=f'cur_{table}', cursor_factory=RealDictCursor)
        src_cur.itersize = BATCH_SIZE

        try:
            src_cur.execute(f'SELECT * FROM "{table}" ORDER BY id')
        except Exception as e:
            print(f"\n  WARN {table}: no se pudo leer ({e}), omitiendo")
            src_cur.close()
            src_conn.rollback()
            continue

        if table == 'messages':
            # messages tiene self-reference: parent_id → messages.id
            # Insertamos sin parent_id, luego lo actualizamos
            cols_no_parent = [c for c in columns if c != 'parent_id']
            col_str = ', '.join(f'"{c}"' for c in cols_no_parent)
            sql_msg = f'INSERT INTO "{table}" ({col_str}) VALUES %s ON CONFLICT DO NOTHING'

            rows_data = []
            parent_map = {}
            for row in src_cur:
                rows_data.append(row)
                if row.get('parent_id') is not None:
                    parent_map[row['id']] = row['parent_id']

            # Insertar en lotes sin parent_id
            batches = [rows_data[i:i+BATCH_SIZE] for i in range(0, len(rows_data), BATCH_SIZE)]
            inserted = 0
            for i, batch in enumerate(batches):
                execute_values(
                    dest_cur, sql_msg,
                    [tuple(r[c] for c in cols_no_parent) for r in batch],
                    page_size=BATCH_SIZE
                )
                dest_conn.commit()
                inserted += len(batch)
                pct = int(inserted / total * 100)
                print(f"\r  -->  {table}: {total} filas  ({pct}%)...", end='', flush=True)

            # Actualizar parent_id
            updated = 0
            for msg_id, parent_id in parent_map.items():
                dest_cur.execute('UPDATE messages SET parent_id = %s WHERE id = %s', (parent_id, msg_id))
                updated += 1
            dest_conn.commit()

            count = inserted
            parent_info = f", {updated} con respuestas anidadas" if updated else ""
            print(f"\r  OK   {table}: {count} filas copiadas{parent_info}          ")

        else:
            count = copiar_tabla(table, columns, src_cur, total)
            print(f"\r  OK   {table}: {count} filas copiadas          ")

        src_cur.close()
        total_rows += count

    # -------------------------------------------------------------------------
    # PASO 3: Resetear secuencias de autoincrement
    # -------------------------------------------------------------------------
    print("\nPaso 3: Actualizando secuencias de ID (autoincrement)...")
    for table in TABLES:
        try:
            dest_cur.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{table}"), 1)
                )
            """)
        except Exception as e:
            print(f"  WARN {table}: no se pudo actualizar secuencia ({e})")

    dest_conn.commit()
    print("  OK  Secuencias actualizadas")

    print()
    print("=" * 65)
    print(f"  MIGRACIÓN COMPLETADA: {total_rows} filas copiadas en total")
    print("=" * 65)

except Exception as e:
    dest_conn.rollback()
    print(f"\nERROR durante la migración: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

finally:
    dest_cur.close()
    dest_conn.close()
    src_conn.close()
