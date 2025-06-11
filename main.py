import json
from fastapi import FastAPI, Request
from bybit import place_limit_order
import uvicorn

app = FastAPI()

# === Bant yapılarını yükle ===
with open("bands_config.json", "r") as f:
    bands = json.load(f)

# === Symbol'e özel işlem geçmişi tut ===
symbol_state = {}

def split_position(levels: list[float], position_size: float, close_price: float, direction: str):
    """
    Ara seviyelere göre pozisyonu 2'ye böl: TP ve geri çekilme emirleri
    """
    sorted_levels = sorted(levels) if direction == "long" else sorted(levels, reverse=True)

    tp_levels = [lvl for lvl in sorted_levels if (lvl > close_price if direction == "long" else lvl < close_price)]
    retrace_levels = [lvl for lvl in sorted_levels if (lvl <= close_price if direction == "long" else lvl >= close_price)]

    total_levels = len(tp_levels) + len(retrace_levels)
    if total_levels == 0:
        return []

    tp_ratio = len(tp_levels) / total_levels
    retrace_ratio = len(retrace_levels) / total_levels

    tp_amount = position_size * tp_ratio
    retrace_amount = position_size * retrace_ratio

    orders = []

    for lvl in tp_levels:
        orders.append({
            "side": "Sell" if direction == "long" else "Buy",
            "price": lvl,
            "amount": round(tp_amount / len(tp_levels), 4)
        })

    for lvl in retrace_levels:
        orders.append({
            "side": "Buy" if direction == "long" else "Sell",
            "price": lvl,
            "amount": round(retrace_amount / len(retrace_levels), 4)
        })

    return orders


@app.post("/webhook")
async def webhook_listener(request: Request):
    data = await request.json()

    symbol = data.get("symbol")
    close_price = float(data.get("close"))
    direction = data.get("direction")

    matched_band = next(
        (b for b in bands if b["direction"] == direction and b["from"] < close_price < b["to"]),
        None
    )

    if not matched_band:
        return {"status": "no_band_match"}

    state = symbol_state.get(symbol, {
        "current_band": None,
        "position_size": 1.0,  # İlk işlem 1 BTC gibi düşünebilirsin
        "profit": 0.0
    })

    is_new_band = matched_band != state["current_band"]

    # Eğer yeni banda geçildiyse karı dahil et
    if is_new_band:
        state["profit"] += 0  # Kar hesabı dinamik değilse sabit bırak
        state["position_size"] += state["profit"]
        state["current_band"] = matched_band

    # Emirleri ara seviyelere göre böl
    orders = split_position(matched_band["levels"], state["position_size"], close_price, direction)

    for o in orders:
        print(f"Emir: {o['side']} | Fiyat: {o['price']} | Miktar: {o['amount']}")
        place_limit_order(
            symbol=symbol,
            side=o["side"],
            price=o["price"],
            qty=o["amount"]
        )

    symbol_state[symbol] = state

    return {
        "status": "executed",
        "symbol": symbol,
        "position_size": state["position_size"],
        "orders": orders
    }


# === Uvicorn sunucusunu başlat (Render için) ===
if name == "main":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
