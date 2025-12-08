# -*- coding: utf-8 -*-
"""
Debug script para probar la conexion con IOL API
Ejecutar: python debug_iol.py
"""

import os
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

print("=" * 50)
print("DEBUG IOL API CONNECTION")
print("=" * 50)

# 1. Verificar que las variables de entorno estan configuradas
username = os.environ.get('IOL_USERNAME')
password = os.environ.get('IOL_PASSWORD')

print("\nVariables de entorno:")
print(f"   IOL_USERNAME: {username if username else 'NO CONFIGURADO'}")
print(f"   IOL_PASSWORD: {'*' * len(password) if password else 'NO CONFIGURADO'}")

if not username or not password:
    print("\nERROR: Falta configurar IOL_USERNAME y/o IOL_PASSWORD en el archivo .env")
    print("\nAsegurate de que tu .env tenga estas lineas:")
    print("   IOL_USERNAME=tu_email@ejemplo.com")
    print("   IOL_PASSWORD=tu_contrasena")
    exit(1)

# 2. Intentar autenticar
import requests

print("\nIntentando autenticar con IOL...")

url = "https://api.invertironline.com/token"
data = {
    "username": username,
    "password": password,
    "grant_type": "password"
}

try:
    print(f"   URL: {url}")
    print(f"   Datos enviados: username={username}, grant_type=password")
    
    response = requests.post(url, data=data, timeout=30)
    
    print(f"\nRespuesta HTTP: {response.status_code}")
    
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get('access_token')
        print(f"OK - Token obtenido exitosamente!")
        print(f"   Token (primeros 50 chars): {access_token[:50]}...")
        
        # 3. Probar obtener precio de AL30
        print("\nProbando obtener precio de AL30...")
        
        precio_url = "https://api.invertironline.com/api/v2/bCBA/Titulos/AL30/Cotizacion"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        precio_response = requests.get(precio_url, headers=headers, timeout=30)
        
        if precio_response.status_code == 200:
            precio_data = precio_response.json()
            ultimo_precio = precio_data.get('ultimoPrecio')
            variacion = precio_data.get('variacion')
            print(f"OK - AL30: ${ultimo_precio} (Variacion: {variacion}%)")
            print("\nTODO FUNCIONA CORRECTAMENTE!")
        else:
            print(f"ERROR al obtener precio: {precio_response.status_code}")
            print(f"   Respuesta: {precio_response.text}")
    else:
        print(f"ERROR de autenticacion: {response.status_code}")
        print(f"   Respuesta: {response.text}")
        
        if response.status_code == 401:
            print("\nPosibles causas:")
            print("   - Usuario o contrasena incorrectos")
            print("   - La API no esta activada en tu cuenta de IOL")
            print("   - Necesitas solicitar acceso a la API desde IOL")
            
except requests.exceptions.ConnectionError as e:
    print(f"\nERROR de conexion: {e}")
    print("\nVerifica tu conexion a internet")
    
except requests.exceptions.Timeout:
    print("\nERROR Timeout: La conexion tardo demasiado")
    
except Exception as e:
    print(f"\nERROR inesperado: {type(e).__name__}: {e}")

print("\n" + "=" * 50)
