# -*- coding: utf-8 -*-
"""
Script para agregar threading a mensajes (respuestas)
Ejecutar: python migrate_message_threading.py
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
    print("MIGRACION DE MENSAJES (THREADING)")
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
            WHERE table_name = 'messages' AND column_name = 'parent_id'
        """)
        
        if cursor.fetchone():
            print("[OK] La columna 'parent_id' ya existe")
        else:
            print("[...] Agregando columna 'parent_id' a messages...")
            
            # Add column
            cursor.execute("""
                ALTER TABLE messages 
                ADD COLUMN parent_id INTEGER REFERENCES messages(id) ON DELETE CASCADE
            """)
            
            print("[OK] Columna 'parent_id' agregada")
        
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
