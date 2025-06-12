import json
from fastapi import FastAPI, Request
from pydantic import BaseModel
from bybit import place_limit_order, get_balance
import uvicorn

app = FastAPI()

class WebhookMessage(BaseModel):
    message: str

# === Bant yapılarını yükle ===
with open("bands_config.json", "r") as f:
    bands = json.load(f)

print("✅ Yüklenen bantlar:", bands)

symbol_state = {}  # Symbol bazlı geçilen bantları takip için

def split_position(levels: list[float], close_price: float, position_size: float, direction: str):
    """
    Kapanış fiyatına göre seviyeleri ayır:
    - Geçilmiş seviyelere pozisyon aç
    - Kalan seviyelere kar al (take-profit)
    """
    sorted_levels = sorted(levels) if direction == "long" else sorted(levels, reverse=True)

    if direction == "long":
        entry_levels = [lvl for lvl in sorted_levels if lvl <= close_price]
        tp_levels = [lvl for lvl in sorted_levels if lvl > close_price]
    else:
        entry_levels = [lvl for lvl in sorted_levels if lvl >= close_price]
        tp_levels = [lvl for lvl in sorted_levels if lvl < close_price]

    if not entry_levels:
        entry_levels = [sorted_levels[0]]  # fallback en yakın seviye

    entry_share = position_size / len(entry_levels) if entry_levels else 0
    tp_share = position_size / len(tp_levels) if tp_levels else 0

    entry_orders = [{
        "price": lvl,
        "size": round(entry_share, 2),
        "side": "buy" if direction == "long" else "sell"
    } for lvl in entry_levels]

    tp_orders = [{
        "price": lvl,
        "size": round(tp_share, 2),
        "side": "sell" if direction == "long" else "buy"
    } for lvl in tp_levels]

    return entry_orders + tp_orders

@app.post("/webhook")
async def webhook_listener(data: WebhookMessage):
    message = data.message
    print("📩 Gelen mesaj:", message)

    direction = "long" if "LONG" in message else "short"

    try:
        level_part = message.split("Fiyat")[1].split("seviyesini")[0].strip()
        close_price = float(level_part)

        symbol = message.split("(")[1].split(":")[1].split(" ")[0]
    except Exception as e:
        return {"error": "Mesaj formatı hatalı", "detail": str(e)}

    print(f"🎯 Symbol: {symbol} | Yön: {direction} | Kapanış: {close_price}")

    # === Bant aralığını bul ===
    band = next(
        (
            b for b in bands
            if b["direction"] == direction and (
                (b["from"] <= close_price <= b["to"]) if b["from"] < b["to"]
                else (b["to"] <= close_price <= b["from"])
            )
        ),
        None
    )

    if not band:
        return {"status": "Bant aralığı bulunamadı"}



    levels = band["levels"]
    usdt_balance = get_balance()
    position_size = round(usdt_balance * 0.98, 2)  # %98 güvenli margin

    orders = split_position(levels, close_price, position_size, direction)

    for o in orders:
        print(f"📦 Emir: {o}")
        place_limit_order(symbol=symbol, side=o["side"], price=o["price"], qty=o["size"])

    return {
        "status": "İşlem tamamlandı",
        "adet": len(orders),
        "detay": orders
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
