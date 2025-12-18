# -*- coding: utf-8 -*-
"""
Script para migrar la base de datos - Agregar tabla activity_logs
Ejecutar: python migrate_activity_log.py
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
    print("MIGRACION DE BASE DE DATOS - ActivityLog")
    print("=" * 50)
    
    # Connect to database
    try:
        conn = psycopg2.connect(Config.DATABASE_URL)
        cursor = conn.cursor()
        print("[OK] Conectado a la base de datos")
        
        # Check if table exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'activity_logs'
        """)
        
        if cursor.fetchone():
            print("[OK] La tabla 'activity_logs' ya existe")
        else:
            print("[...] Creando tabla 'activity_logs'...")
            
            # Create table
            cursor.execute("""
                CREATE TABLE activity_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    action_type VARCHAR(50) NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    entity_id INTEGER,
                    entity_name VARCHAR(200),
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            print("[OK] Tabla 'activity_logs' creada")
            
            # Create index for faster queries
            cursor.execute("""
                CREATE INDEX idx_activity_logs_created_at 
                ON activity_logs(created_at)
            """)
            print("[OK] Indice creado para columna created_at")
            
            cursor.execute("""
                CREATE INDEX idx_activity_logs_user_id 
                ON activity_logs(user_id)
            """)
            print("[OK] Indice creado para columna user_id")
        
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
