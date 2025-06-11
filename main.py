from fastapi import FastAPI, Request
import json
from typing import Optional
import uvicorn

app = FastAPI()

# Her coin için bağımsız pozisyon yönetimi
symbol_state = {}  # örnek: BTCUSDT: {position_size, realized_profit, current_band}

# Bantları yükle
with open("bands_config.json", "r") as f:
    band_list = json.load(f)

def find_band(price: float, direction: str) -> Optional[dict]:
    """
    Belirli bir fiyat ve yön için geçerli bandı bulur.
    """
    for band in band_list:
        if band["direction"] == direction and min(band["from"], band["to"]) <= price <= max(band["from"], band["to"]):
            return band
    return None

def split_position(levels: list[float], position_size: float) -> list[dict]:
    """
    Pozisyonu ara seviyelere eşit şekilde böler.
    """
    per_level = round(position_size / len(levels), 8)
    return [{"price": lvl, "amount": per_level} for lvl in levels]

@app.post("/webhook")
async def webhook_listener(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol")
        direction = data.get("direction")  # "long" or "short"
        price = float(data.get("triggerPrice"))

        matched_band = find_band(price, direction)
        if not matched_band:
            print(f"[{symbol}] Uygun bant bulunamadı: {price} - {direction}")
            return {"status": "no_band_match"}

        # Her sembol için state oluştur
        if symbol not in symbol_state:
            symbol_state[symbol] = {
                "position_size": 1.0,
                "realized_profit": 0.0,
                "current_band": None
            }

        state = symbol_state[symbol]
        is_new_band = matched_band != state["current_band"]

       if is_new_band:
    # Gerçek kar/zararı al
    profit = state.get("realized_profit", 0)
    state["position_size"] += profit
    state["realized_profit"] = 0
    state["current_band"] = matched_band

            orders = split_position(matched_band["levels"], state["position_size"])

            print(f"--- [{symbol}] Yeni Banda Geçiş ---")
            print(f"Fiyat: {price} → Bant: {matched_band['from']} - {matched_band['to']} ({direction})")
            print(f"Yeni pozisyon: {state['position_size']:.4f} ({profit:.4f} kar eklendi)")
            for o in orders:
                print(f"  → TP: {o['price']} | Miktar: {o['amount']}")

            return {
                "status": "new_band",
                "symbol": symbol,
                "position_size": state["position_size"],
                "used_profit": profit,
                "orders": orders
            }

        else:
            orders = split_position(matched_band["levels"], state["position_size"])

            print(f"[{symbol}] Aynı bantta kalındı → {matched_band['from']} - {matched_band['to']}")
            return {
                "status": "same_band",
                "symbol": symbol,
                "position_size": state["position_size"],
                "orders": orders
            }

    except Exception as e:
        return {"error": str(e)}
