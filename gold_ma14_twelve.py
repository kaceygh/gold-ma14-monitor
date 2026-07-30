#!/usr/bin/env python3
"""
Gold MA14 Cross Monitor - Optimized State-Based Version
"""
import urllib.request
import json
import os
import tempfile
import re
import csv
from datetime import datetime, timezone

# ==================== CONFIG ====================
TWELVE_DATA_API_KEY = "832cf3c990594c9ca5f142b40ee3761c"
SYMBOL = "XAU/USD"
INTERVAL = "30min"
OUTPUTSIZE = 60

MEMORY_FILE = "/root/gold_ma14_signal_memory.json"
STATUS_FILE = "/root/gold_ma14_status.json"
OUTPUT_HTML = "/root/gold_ma14_twelve_report.html"
HISTORY_FILE = "/root/gold_ma14_history.csv"

TELEGRAM_BOT_TOKEN = "8495697171:AAF9NTvA2gLnHITGA0QWtPD9-Myd8ckGeuU"
TELEGRAM_USER_ID = "5278674012"

CROSS_THRESHOLD = 0.05  # USD
# =================================================

def load_last_state():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                content = f.read().strip()
            if not content: return {}
            matches = re.findall(r'\{.*\}', content)
            if matches:
                return json.loads(matches[-1])
    except Exception as e:
        print(f"[WARN] load_last_state failed: {e}")
    return {}

def save_atomic(filepath, data, is_html=False):
    try:
        dir_name = os.path.dirname(filepath) or "."
        with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False) as tf:
            if is_html:
                tf.write(data)
            else:
                json.dump(data, tf, separators=(',', ':'))
            temp_name = tf.name
        os.replace(temp_name, filepath)
    except Exception as e:
        print(f"[ERROR] Atomic save failed for {filepath}: {e}")

def fetch_twelve_data():
    url = (f"https://api.twelvedata.com/time_series"
           f"?symbol={SYMBOL}&interval={INTERVAL}&outputsize={OUTPUTSIZE}&apikey={TWELVE_DATA_API_KEY}")
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if "values" not in data:
            raise ValueError(f"API Error: {data}")
        return sorted(data["values"], key=lambda x: x["datetime"], reverse=True)
    except Exception as e:
        print(f"[ERROR] Twelve Data fetch failed: {e}")
        return None

def fetch_xaus_spot():
    try:
        with urllib.request.urlopen("https://xaus.com/api/v1/spot", timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return float(data.get("spot_usd_oz", 0))
    except Exception as e:
        print(f"[ERROR] XAUS spot fetch failed: {e}")
        return None

def compute_ma14(closes, start_idx):
    if start_idx + 14 > len(closes):
        return None
    return sum(closes[start_idx:start_idx+14]) / 14.0

def get_position(price, ma):
    if price > ma + CROSS_THRESHOLD: return "ABOVE"
    if price < ma - CROSS_THRESHOLD: return "BELOW"
    return "ON"

def send_telegram(signal, price, ma14):
    label = "🚀 黄金金叉 (UP)" if signal == "GOLD_CROSS_UP" else "📉 黄金死叉 (DOWN)"
    dev = ((price - ma14) / ma14 * 100) if ma14 else 0
    msg = (f"{label}\n"
           f"现价: ${price:.2f}\n"
           f"MA14: ${ma14:.2f}\n"
           f"偏离: {dev:+.2f}%\n"
           f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TELEGRAM_USER_ID, "text": msg}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        if result.get("ok"):
            print("[INFO] Telegram alert sent")
    except Exception as e:
        print(f"[ERROR] Telegram failed: {e}")

def append_history(signal, price, ma14, timestamp=None):
    if not signal: return
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    dev = ((price - ma14) / ma14 * 100) if ma14 else 0
    file_exists = os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "signal", "price", "ma14", "deviation_pct"])
        writer.writerow([ts, signal, f"{price:.2f}", f"{ma14:.2f}", f"{dev:.2f}"])

def generate_html(signal, price, ma14):
    label_map = {"GOLD_CROSS_UP": "📈 金叉 (UP)", "GOLD_CROSS_DOWN": "📉 死叉 (DOWN)", None: "➡️ 无交叉 (Neutral)"}
    label = label_map.get(signal, "❓ 未知")
    cls = "cross-up" if signal == "GOLD_CROSS_UP" else "cross-down" if signal == "GOLD_CROSS_DOWN" else "neutral"
    dev = ((price - ma14) / ma14 * 100) if ma14 else 0
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>Gold MA14 Cross</title>
<style>
body{{font-family:system-ui,sans-serif;line-height:1.6;padding:40px;background:#f4f7f6;color:#333}}
.card{{background:#fff;padding:30px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,.1);max-width:600px;margin:auto}}
.signal{{font-size:28px;font-weight:bold;text-align:center;margin-bottom:20px}}
.cross-up{{color:#d32f2f}}.cross-down{{color:#1976d2}}.neutral{{color:#757575}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}}
.item{{background:#f9f9f9;padding:15px;border-radius:8px;text-align:center;border:1px solid #eee}}
.lbl{{font-size:14px;color:#666;margin-bottom:5px}}.val{{font-size:20px;font-weight:bold}}
.dev{{text-align:center;margin-top:20px}}.foot{{text-align:center;font-size:12px;color:#999;margin-top:30px}}
</style></head><body><div class="card">
<div class="signal {cls}">{label}</div>
<div class="grid">
<div class="item"><div class="lbl">现货价格</div><div class="val">${price:.2f}</div></div>
<div class="item"><div class="lbl">MA14 均线</div><div class="val">${ma14:.2f}</div></div>
</div>
<div class="dev"><span class="lbl">价格偏离度: </span><span class="val" style="color:{'#d32f2f' if dev>0 else '#1976d2'}">{dev:+.2f}%</span></div>
<div class="foot">更新: {ts} | 数据源: Twelve Data & XAUS</div>
</div></body></html>"""
    save_atomic(OUTPUT_HTML, html, is_html=True)

def main():
    data = fetch_twelve_data()
    if not data:
        spot = fetch_xaus_spot()
        if spot:
            save_atomic(STATUS_FILE, {"status": "fallback", "price": spot, "signal": None, "timestamp": datetime.now(timezone.utc).isoformat()})
            generate_html("ERROR", spot, 0)
        else:
            save_atomic(STATUS_FILE, {"status": "error", "timestamp": datetime.now(timezone.utc).isoformat()})
            generate_html("ERROR", 0, 0)
        return 1

    closes = [float(e["close"]) for e in data]
    price_now = closes[0]
    ma14_now = compute_ma14(closes, 0)
    
    if ma14_now is None:
        print("[ERROR] Not enough data for MA14")
        return 1

    pos_now = get_position(price_now, ma14_now)
    last_state = load_last_state()
    last_pos = last_state.get("last_pos")

    print(f"[INFO] Price={price_now:.2f}, MA14={ma14_now:.2f}, Pos={pos_now}, LastPos={last_pos}")

    signal = None
    if last_pos:
        if last_pos == "BELOW" and pos_now == "ABOVE":
            signal = "GOLD_CROSS_UP"
        elif last_pos == "ABOVE" and pos_now == "BELOW":
            signal = "GOLD_CROSS_DOWN"
    else:
        print("[INFO] No last_pos found, initializing state.")

    if signal:
        print(f"[INFO] Signal detected: {signal}. Sending alert...")
        send_telegram(signal, price_now, ma14_now)
        append_history(signal, price_now, ma14_now)
        save_atomic(MEMORY_FILE, {
            "last_signal": signal,
            "last_pos": pos_now,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    elif pos_now != "ON" and pos_now != last_pos:
        save_atomic(MEMORY_FILE, {
            "last_signal": None,
            "last_pos": pos_now,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    save_atomic(STATUS_FILE, {
        "status": "ok",
        "price": price_now,
        "ma14": ma14_now,
        "signal": signal,
        "position": pos_now,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    generate_html(signal, price_now, ma14_now)
    return 0

if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        print(f"[FATAL] {e}")
        generate_html("ERROR", 0, 0)
        save_atomic(STATUS_FILE, {"status": "error", "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()})
        exit(1)
