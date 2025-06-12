import json
from fastapi import FastAPI
from pydantic import BaseModel
from bybit import place_limit_order
import uvicorn

app = FastAPI()

# === Bant yapılarını yükle ===
with open("bands_config.json", "r") as f:
    bands = json.load(f)

# === Symbol'e özel işlem geçmişi ===
symbol_state = {}

# === Webhook mesaj yapısı ===
class WebhookMessage(BaseModel):
    message: str

# === Ara seviyelere göre pozisyonu 2'ye böl: TP ve geri çekilme emirleri ===
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

# === Webhook listener: TradingView alarmını dinle ===
@app.post("/webhook")
async def webhook_listener(data: WebhookMessage):
    message = data.message
    print("📩 Gelen mesaj:", message)

    # Sinyal içeriğini çöz (örnek: "🔼 LONG: Fiyat 306.0 seviyesini yukarı geçti (BINANCE:ETHUSDT.P - HA 4H)")
    direction = "long" if "LONG" in message else "short"
    try:
        level_part = message.split("Fiyat")[1].split("seviyesini")[0].strip()
        close_price = float(level_part)
        symbol = message.split("(")[1].split(":")[1].split()[0]
    except Exception as e:
        return {"error": "Mesaj formatı çözülemedi", "detail": str(e)}

    # Sembol özel geçmişini kontrol et
    state = symbol_state.get(symbol, {"last_band": None})
    already_triggered = state["last_band"] == close_price
    if already_triggered:
        return {"info": f"{symbol} için {close_price} seviyesi zaten işlenmiş."}

    symbol_state[symbol] = {"last_band": close_price}

    # Uygun ana bant aralığını bul
    band = next((b for b in bands if b["direction"] == direction and b["from"] <= close_price <= b["to"]), None)
    if not band:
        return {"error": "Uygun band aralığı bulunamadı."}

    position_size = 100  # ← Buraya gerçek pozisyon büyüklüğünü yaz
    orders = split_position(band["levels"], position_size, close_price, direction)

    # Emirleri gönder
    for order in orders:
        place_limit_order(
            symbol=symbol,
            side=order["side"],
            size=order["size"],
            price=order["price"]
        )

    return {
        "status": "success",
        "symbol": symbol,
        "direction": direction,
        "entry_price": close_price,
        "band": band,
        "orders_sent": len(orders)
    }

# === Lokal test için ===
if name == "main":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
