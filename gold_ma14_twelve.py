#!/usr/bin/env python3
"""
Gold MA14 Cross Monitor - Fixed Version with History Logging
Karpathy guidelines: simple, correct, no over-engineering.
Secrets are injected via environment variables.
"""
import urllib.request
import json
import os
import tempfile
import re
import csv
from datetime import datetime, timezone

# ==================== CONFIG ====================
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")
SYMBOL = "XAU/USD"
INTERVAL = "30min"
OUTPUTSIZE = 60

MEMORY_FILE = os.environ.get("MEMORY_FILE", "gold_ma14_signal_memory.json")
STATUS_FILE = os.environ.get("STATUS_FILE", "gold_ma14_status.json")
OUTPUT_HTML = os.environ.get("OUTPUT_HTML", "gold_ma14_twelve_report.html")
HISTORY_FILE = os.environ.get("HISTORY_FILE", "gold_ma14_history.csv")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = os.environ.get("TELEGRAM_USER_ID", "")

CROSS_THRESHOLD = 0.05  # USD
# =================================================


def load_last_signal():
    """Load last signal from memory file (robust to concatenated JSON)."""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                content = f.read().strip()
            if not content:
                return None
            matches = re.findall(r'\{.*\}', content)
            if matches:
                return json.loads(matches[-1]).get("last_signal")
    except Exception as e:
        print(f"[WARN] load_last_signal failed: {e}")
    return None


def save_atomic(filepath, data, is_html=False):
    """Atomic write via temp file + os.replace."""
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
    """Fetch 30min candles from Twelve Data, newest first."""
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
    """Fallback spot price from XAUS."""
    try:
        with urllib.request.urlopen("https://xaus.com/api/v1/spot", timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return float(data.get("spot_usd_oz", 0))
    except Exception as e:
        print(f"[ERROR] XAUS spot fetch failed: {e}")
        return None


def compute_ma14(closes, start_idx):
    """MA14 for candle at start_idx (newest first). Uses closes[start_idx : start_idx+14]."""
    if start_idx + 14 > len(closes):
        return None
    return sum(closes[start_idx:start_idx+14]) / 14.0


def detect_cross(data):
    """Detect MA14 cross using newest 14 candles (index 0) vs previous 14 (index 1)."""
    if len(data) < 15:
        return None, None, None

    closes = [float(e["close"]) for e in data]
    datetimes = [e["datetime"] for e in data]

    ma14_now = compute_ma14(closes, 0)
    ma14_prev = compute_ma14(closes, 1)

    if ma14_now is None or ma14_prev is None:
        return None, None, None

    price_now = closes[0]
    price_prev = closes[1]

    pos_now = "ABOVE" if price_now > ma14_now + CROSS_THRESHOLD else \
              "BELOW" if price_now < ma14_now - CROSS_THRESHOLD else "ON"
    pos_prev = "ABOVE" if price_prev > ma14_prev + CROSS_THRESHOLD else \
               "BELOW" if price_prev < ma14_prev - CROSS_THRESHOLD else "ON"

    signal = None
    if pos_prev == "BELOW" and pos_now == "ABOVE":
        signal = "GOLD_CROSS_UP"
    elif pos_prev == "ABOVE" and pos_now == "BELOW":
        signal = "GOLD_CROSS_DOWN"

    print(f"[DEBUG] {datetimes[0]}  price={price_now:.2f} ma14={ma14_now:.2f} pos={pos_now}")
    print(f"[DEBUG] {datetimes[1]}  price={price_prev:.2f} ma14={ma14_prev:.2f} pos={pos_prev}")
    if signal:
        print(f"[SIGNAL] {signal} detected at {datetimes[0]}")

    return signal, price_now, ma14_now


def send_telegram(signal, price, ma14):
    """Send Telegram alert."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        print("[WARN] Telegram credentials not configured, skipping notification")
        return
    label = "📈 金叉 (UP)" if signal == "GOLD_CROSS_UP" else "📉 死叉 (DOWN)"
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
    """Append crossover event to CSV history file."""
    if not signal:
        return
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    dev = ((price - ma14) / ma14 * 100) if ma14 else 0
    file_exists = os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "signal", "price", "ma14", "deviation_pct"])
        writer.writerow([ts, signal, f"{price:.2f}", f"{ma14:.2f}", f"{dev:.2f}"])


def generate_html(signal, price, ma14):
    label_map = {
        "GOLD_CROSS_UP": "📈 金叉 (UP)",
        "GOLD_CROSS_DOWN": "📉 死叉 (DOWN)",
        None: "➡️ 无交叉 (Neutral)"
    }
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
            save_atomic(STATUS_FILE, {"status": "fallback", "price": spot, "signal": None,
                         "timestamp": datetime.now(timezone.utc).isoformat()})
            generate_html("ERROR", spot, 0)
        else:
            save_atomic(STATUS_FILE, {"status": "error", "timestamp": datetime.now(timezone.utc).isoformat()})
            generate_html("ERROR", 0, 0)
        return 1

    signal, price, ma14 = detect_cross(data)
    last_signal = load_last_signal()

    print(f"[INFO] Current={signal}, Last={last_signal}, Price={price:.2f}, MA14={ma14:.2f}")

    # Alert only on NEW signal change
    if signal and signal != last_signal:
        print(f"[INFO] New signal: {signal}. Sending alert...")
        send_telegram(signal, price, ma14)
        save_atomic(MEMORY_FILE, {"last_signal": signal, "timestamp": datetime.now(timezone.utc).isoformat()})
        # Record to history CSV
        append_history(signal, price, ma14)
    else:
        print("[INFO] No new signal change.")

    save_atomic(STATUS_FILE, {
        "status": "ok",
        "price": price,
        "ma14": ma14,
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    generate_html(signal, price, ma14)
    print(f"[INFO] Report: {OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        print(f"[FATAL] {e}")
        generate_html("ERROR", 0, 0)
        save_atomic(STATUS_FILE, {"status": "error", "error": str(e),
                     "timestamp": datetime.now(timezone.utc).isoformat()})
        exit(1)
