# -*- coding: utf-8 -*-
"""
Script para migrar la base de datos - Agregar columna category a broker_ratings
Ejecutar: python migrate_db.py
"""

import os
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from config import Config
import psycopg2

def migrate():
    print("=" * 50)
    print("MIGRACION DE BASE DE DATOS")
    print("=" * 50)
    
    # Connect to database
    try:
        conn = psycopg2.connect(Config.DATABASE_URL)
        cursor = conn.cursor()
        print("[OK] Conectado a la base de datos")
        
        # Check if column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'broker_ratings' AND column_name = 'category'
        """)
        
        if cursor.fetchone():
            print("[OK] La columna 'category' ya existe")
        else:
            print("[...] Agregando columna 'category' a broker_ratings...")
            
            # Add column
            cursor.execute("""
                ALTER TABLE broker_ratings 
                ADD COLUMN category VARCHAR(50) DEFAULT 'general'
            """)
            
            print("[OK] Columna 'category' agregada")
            
            # Drop old unique constraint if exists
            try:
                cursor.execute("""
                    ALTER TABLE broker_ratings 
                    DROP CONSTRAINT IF EXISTS unique_broker_user_rating
                """)
                print("[OK] Constraint antiguo eliminado")
            except:
                pass
            
            # Add new unique constraint
            try:
                cursor.execute("""
                    ALTER TABLE broker_ratings 
                    ADD CONSTRAINT unique_broker_user_category_rating 
                    UNIQUE (broker_id, user_id, category)
                """)
                print("[OK] Nuevo constraint agregado")
            except Exception as e:
                print(f"[WARN] No se pudo agregar constraint: {e}")
        
        conn.commit()
        print("\n[OK] Migracion completada exitosamente!")
        
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    
    return True

if __name__ == '__main__':
    migrate()
    print("\nAhora reinicia el servidor Flask: python app.py")
