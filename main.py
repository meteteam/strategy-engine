# main.py

import json
from fastapi import FastAPI
from pydantic import BaseModel
from bybit import place_limit_order
import uvicorn

app = FastAPI()

# === Webhook verisi için model ===
class WebhookMessage(BaseModel):
    message: str

# === Bant yapılarını yükle ===
with open("bands_config.json", "r") as f:
    bands = json.load(f)

print("✅ Yüklenen bantlar:", bands)

# === Symbol -> geçilen bantları tutmak için durum hafızası ===
symbol_state = {}

# === Pozisyonu seviyelere böl ===
def split_position(levels: list[float], position_size: float, close_price: float, direction: str):
    sorted_levels = sorted(levels) if direction == "long" else sorted(levels, reverse=True)
    tp_levels = [lvl for lvl in sorted_levels if (lvl > close_price if direction == "long" else lvl < close_price)]
    retrace_levels = [lvl for lvl in sorted_levels if (lvl <= close_price if direction == "long" else lvl >= close_price)]

    total_levels = len(tp_levels) + len(retrace_levels)
    if total_levels == 0:
        return []

    tp_ratio = len(tp_levels) / total_levels
    retrace_ratio = 1 - tp_ratio

    tp_amount = position_size * tp_ratio
    retrace_amount = position_size * retrace_ratio

    tp_share = tp_amount / len(tp_levels) if tp_levels else 0
    retrace_share = retrace_amount / len(retrace_levels) if retrace_levels else 0

    tp_orders = [{"price": lvl, "size": tp_share, "side": "sell" if direction == "long" else "buy"} for lvl in tp_levels]
    retrace_orders = [{"price": lvl, "size": retrace_share, "side": "buy" if direction == "long" else "sell"} for lvl in retrace_levels]

    return tp_orders + retrace_orders

# === Webhook dinleyici ===
@app.post("/webhook")
async def webhook_listener(data: WebhookMessage):
    message = data.message
    print("📩 Gelen mesaj:", message)

    direction = "long" if "LONG" in message else "short"

    try:
        level_part = message.split("Fiyat")[1].split("seviyesini")[0].strip()
        close_price = float(level_part)
        symbol = message.split("(")[1].split(":")[1].split(" ")[0]  # Örn: BYBIT:AAVEUSDT.P
    except Exception as e:
        return {"error": "Mesaj formatı çözümlemedi", "detail": str(e)}

    print(f"🎯 Symbol: {symbol} | Yön: {direction} | Kapanış: {close_price}")

    # İlgili bant aralığını bul
    band = next((
        b for b in bands if
        b["direction"] == direction and (
            (b["from"] <= close_price <= b["to"]) if b["from"] < b["to"]
            else (b["to"] <= close_price <= b["from"])
        )
    ), None)

    if not band:
        return {"status": "Bant aralığı bulunamadı"}

    levels = band["levels"]
    position_size = 100  # Sabit örnek

    orders = split_position(levels, position_size, close_price, direction)

    for o in orders:
        print(f"📦 Emir → {o}")
        place_limit_order(symbol=symbol, side=o["side"], price=o["price"], qty=o["size"])

    return {
        "status": "İşlem tamamlandı",
        "adet": len(orders),
        "detay": orders
    }

# === Uvicorn local çalıştırıcı ===
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
