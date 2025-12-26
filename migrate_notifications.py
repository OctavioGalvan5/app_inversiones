# -*- coding: utf-8 -*-
"""
Script para agregar notificaciones a usuarios
Ejecutar: python migrate_notifications.py
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
    print("MIGRACION DE NOTIFICACIONES")
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
            WHERE table_name = 'users' AND column_name = 'last_notification_read_at'
        """)
        
        if cursor.fetchone():
            print("[OK] La columna 'last_notification_read_at' ya existe")
        else:
            print("[...] Agregando columna 'last_notification_read_at' a users...")
            
            # Add column
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN last_notification_read_at TIMESTAMP
            """)
            
            print("[OK] Columna 'last_notification_read_at' agregada")
            
            # Set default value to now for existing users
            cursor.execute("UPDATE users SET last_notification_read_at = CURRENT_TIMESTAMP")
            print("[OK] Valores iniciales establecidos")
        
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
