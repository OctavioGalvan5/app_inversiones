# -*- coding: utf-8 -*-
"""
IOL (Invertir Online) API Service
Handles authentication and price fetching for Argentine stocks and bonds
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class IOLService:
    BASE_URL = "https://api.invertironline.com"
    
    def __init__(self):
        self.username = os.environ.get('IOL_USERNAME')
        self.password = os.environ.get('IOL_PASSWORD')
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
    
    def authenticate(self):
        """Authenticate with IOL API and get bearer token"""
        url = f"{self.BASE_URL}/token"
        
        data = {
            'username': self.username,
            'password': self.password,
            'grant_type': 'password'
        }
        
        try:
            print(f"[IOL] Obteniendo Token de seguridad para {self.username}...")
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                self.refresh_token = token_data.get('refresh_token')
                # Token expires in 15 minutes
                self.token_expiry = datetime.now() + timedelta(minutes=14)
                print("[IOL] Token obtenido exitosamente")
                return True
            else:
                print(f"[IOL] Auth Error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"[IOL] Auth Exception: {str(e)}")
            return False
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        url = f"{self.BASE_URL}/token"
        
        data = {
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        try:
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                self.refresh_token = token_data.get('refresh_token')
                self.token_expiry = datetime.now() + timedelta(minutes=14)
                return True
            else:
                # If refresh fails, re-authenticate
                return self.authenticate()
        except Exception as e:
            print(f"[IOL] Refresh Exception: {str(e)}")
            return self.authenticate()
    
    def ensure_authenticated(self):
        """Ensure we have a valid access token"""
        if not self.access_token or not self.token_expiry:
            return self.authenticate()
        
        if datetime.now() >= self.token_expiry:
            return self.refresh_access_token()
        
        return True
    
    def get_headers(self):
        """Get headers with authorization"""
        return {
            'Authorization': f'Bearer {self.access_token}'
        }
    
    def get_bond_price(self, symbol):
        """
        Get current price for a bond/stock from BCBA
        
        Args:
            symbol: Bond/Stock ticker (e.g., 'AL30', 'GD35', 'GGAL')
        
        Returns:
            dict with price info or None if failed
        """
        if not self.ensure_authenticated():
            return {'symbol': symbol, 'price': None, 'error': 'Auth failed'}
        
        # Endpoint para Cotizacion - bCBA = Bolsa de Comercio de Buenos Aires
        url = f"{self.BASE_URL}/api/v2/bCBA/Titulos/{symbol}/Cotizacion"
        
        try:
            response = requests.get(url, headers=self.get_headers(), timeout=30)
            
            if response.status_code == 200:
                datos = response.json()
                ultimo_precio = datos.get('ultimoPrecio')
                variacion = datos.get('variacion')
                
                print(f"[IOL] {symbol}: ${ultimo_precio} (Var: {variacion}%)")
                
                return {
                    'symbol': symbol,
                    'price': ultimo_precio,
                    'variation': variacion,
                    'volume': datos.get('volumen'),
                    'date': datos.get('fechaHora') or datetime.now().isoformat(),
                    'raw_data': datos
                }
            else:
                print(f"[IOL] Error al buscar {symbol}: {response.status_code}")
                return {'symbol': symbol, 'price': None, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            print(f"[IOL] Price Error for {symbol}: {str(e)}")
            return {'symbol': symbol, 'price': None, 'error': str(e)}
    
    def get_multiple_prices(self, symbols):
        """
        Get prices for multiple symbols
        
        Args:
            symbols: List of ticker symbols
            
        Returns:
            dict mapping symbol to price info
        """
        results = {}
        
        for symbol in symbols:
            price_data = self.get_bond_price(symbol.upper())
            results[symbol] = price_data
        
        return results


# Pre-configured bonds to track
DEFAULT_BONDS = [
    'SA24D',
    'AL29',
    'GD35',
    'BA37D',
    'GD29',
    'CO24D',
    'GD38',
    'AL30',
    'GD30',
    'PMM29'
]

# Singleton instance
iol_service = IOLService()
