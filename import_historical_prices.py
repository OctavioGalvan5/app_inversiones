# -*- coding: utf-8 -*-
"""
Script para importar historial de precios desde IOL
Obtiene datos de los ultimos 6 meses para todos los bonos
Ejecutar: python import_historical_prices.py
"""

import os
import sys
import time
from datetime import datetime, timedelta, date

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

import requests
from config import Config
import psycopg2

# IOL API Configuration
IOL_BASE_URL = "https://api.invertironline.com"
IOL_USERNAME = os.environ.get('IOL_USERNAME')
IOL_PASSWORD = os.environ.get('IOL_PASSWORD')

# Global token
access_token = None
token_expiry = None


def authenticate():
    """Get access token from IOL"""
    global access_token, token_expiry
    
    url = f"{IOL_BASE_URL}/token"
    data = {
        'username': IOL_USERNAME,
        'password': IOL_PASSWORD,
        'grant_type': 'password'
    }
    
    try:
        print("[AUTH] Obteniendo token...")
        response = requests.post(url, data=data, timeout=30)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            token_expiry = datetime.now() + timedelta(minutes=14)
            print("[AUTH] Token obtenido OK")
            return True
        else:
            print(f"[AUTH] Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[AUTH] Exception: {e}")
        return False


def ensure_authenticated():
    """Ensure we have a valid token"""
    global access_token, token_expiry
    
    if not access_token or not token_expiry or datetime.now() >= token_expiry:
        return authenticate()
    return True


def get_historical_prices(symbol, desde, hasta):
    """
    Get historical prices for a symbol
    
    Args:
        symbol: Stock/bond ticker
        desde: Start date (datetime)
        hasta: End date (datetime)
    
    Returns:
        List of price records or empty list
    """
    if not ensure_authenticated():
        return []
    
    # Format dates for API
    desde_str = desde.strftime('%Y-%m-%d')
    hasta_str = hasta.strftime('%Y-%m-%d')
    
    # Endpoint for historical data
    url = f"{IOL_BASE_URL}/api/v2/bCBA/Titulos/{symbol}/Cotizacion/seriehistorica/{desde_str}/{hasta_str}/ajustada"
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, list) else []
        else:
            print(f"  [WARN] {symbol}: HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")
        return []


def import_historical_data():
    """Main function to import historical data for all stocks"""
    
    print("=" * 60)
    print("IMPORTACION DE HISTORIAL DE PRECIOS DESDE IOL")
    print("=" * 60)
    
    # Connect to database
    try:
        conn = psycopg2.connect(Config.DATABASE_URL)
        cursor = conn.cursor()
        print("[DB] Conectado a la base de datos")
    except Exception as e:
        print(f"[DB] Error de conexion: {e}")
        return
    
    # Get all stocks
    cursor.execute("SELECT id, symbol FROM stocks ORDER BY symbol")
    stocks = cursor.fetchall()
    
    if not stocks:
        print("[INFO] No hay activos registrados. Agrega algunos primero.")
        return
    
    print(f"[INFO] Se encontraron {len(stocks)} activos")
    
    # Date range: last 6 months
    hasta = date.today()
    desde = hasta - timedelta(days=180)
    
    print(f"[INFO] Rango: {desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')}")
    print("-" * 60)
    
    total_imported = 0
    
    for stock_id, symbol in stocks:
        print(f"\n[{symbol}] Obteniendo historial...")
        
        # Get historical prices from IOL
        prices = get_historical_prices(symbol, desde, hasta)
        
        if not prices:
            print(f"  [SKIP] Sin datos historicos")
            continue
        
        print(f"  [DATA] {len(prices)} registros encontrados")
        
        imported = 0
        for record in prices:
            try:
                # Parse date
                fecha_str = record.get('fechaHora', record.get('fecha'))
                if not fecha_str:
                    continue
                
                # Parse date format
                fecha = None
                for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                    try:
                        fecha = datetime.strptime(fecha_str[:10], fmt[:len(fecha_str[:10])]).date()
                        break
                    except:
                        continue
                
                if not fecha:
                    continue
                
                # Get price
                precio = record.get('ultimoPrecio') or record.get('apertura') or record.get('cierre')
                if not precio:
                    continue
                
                volumen = record.get('volumen')
                
                # Check if already exists
                cursor.execute("""
                    SELECT id FROM price_history 
                    WHERE stock_id = %s AND date = %s
                """, (stock_id, fecha))
                
                if cursor.fetchone():
                    # Update existing
                    cursor.execute("""
                        UPDATE price_history 
                        SET price = %s, volume = %s 
                        WHERE stock_id = %s AND date = %s
                    """, (precio, volumen, stock_id, fecha))
                else:
                    # Insert new
                    cursor.execute("""
                        INSERT INTO price_history (stock_id, price, volume, date)
                        VALUES (%s, %s, %s, %s)
                    """, (stock_id, precio, volumen, fecha))
                
                imported += 1
                
            except Exception as e:
                print(f"  [ERROR] {e}")
                continue
        
        conn.commit()
        print(f"  [OK] {imported} registros importados")
        total_imported += imported
        
        # Rate limiting - wait a bit between requests
        time.sleep(0.5)
    
    print("\n" + "=" * 60)
    print(f"[DONE] Total importado: {total_imported} registros")
    print("=" * 60)
    
    cursor.close()
    conn.close()


if __name__ == '__main__':
    import_historical_data()
