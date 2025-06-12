from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import os

# --- .env dosyasını yükle ---
load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

# --- Bybit oturumu oluştur ---
session = HTTP(
    api_key=API_KEY,
    api_secret=API_SECRET,
    testnet=TESTNET
)

def place_limit_order(symbol: str, side: str, qty: float, price: float):
    """
    Bybit'te limit emir gönderir.
    """
    try:
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side.capitalize(),
            order_type="Limit",
            qty=round(qty, 2),
            price=round(price, 2),
            time_in_force="GTC"
        )
        print(f"✅ EMİR GÖNDERİLDİ: {side.upper()} {qty:.2f} @ {price:.2f} → {symbol}")
        return response
    except Exception as e:
        print(f"❌ Emir gönderilirken hata oluştu: {e}")
        return None

def get_balance() -> float:
    """
    Gerçek cüzdan bakiyesini çeker (USDT olarak).
    Unified account kullanımı varsayılmıştır.
    """
    try:
        response = session.get_wallet_balance(accountType="UNIFIED")
        balance = float(response["result"]["list"][0]["totalEquity"])
        print(f"💰 Güncel USDT bakiyesi: {balance:.2f}")
        return balance
    except Exception as e:
        print(f"❌ Bakiye alınamadı: {e}")
        return 0.0
