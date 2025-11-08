import os, sqlite3, time, requests
from urllib.parse import urlencode
from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")

BASE_FIAT = os.getenv("BASE_FIAT","GBP").upper()
DEFAULT_COINS = [c.strip() for c in os.getenv("DEFAULT_COINS","bitcoin,ethereum,solana").split(",") if c.strip()]
DEFAULT_VS = os.getenv("DEFAULT_VS","gbp").lower()
HOST = os.getenv("HOST","127.0.0.1")
PORT = int(os.getenv("PORT","5000"))

DB_PATH = os.path.join("db","app.db")

# APIs
CG = "https://api.coingecko.com/api/v3"            # live cards
FRANKFURTER = "https://api.frankfurter.dev/v1"     # FX (no key)
BINANCE = "https://api.binance.com"                # history (no key, USDT)

def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

# ---------- Live prices (CoinGecko) ----------
def cg_simple(ids, vs):
    p = {
        "ids": ",".join(ids),
        "vs_currencies": ",".join(vs),
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }
    r = requests.get(f"{CG}/simple/price?{urlencode(p)}", timeout=15)
    r.raise_for_status()
    return r.json()

# ---------- FX (Frankfurter) ----------
def fx_rate(from_code: str, to_code: str):
    url = f"{FRANKFURTER}/latest"
    params = {"base": from_code.upper(), "symbols": to_code.upper()}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    rate = data.get("rates", {}).get(to_code.upper())
    if rate is None:
        raise ValueError(f"Unsupported pair {from_code}->{to_code}")
    return {"rate": rate, "date": data.get("date"), "base": data.get("base")}

# ---------- History (Binance klines 1h, USDT≈USD) ----------
# Minimal mapping from CoinGecko id -> Binance symbol
BINANCE_SYMBOLS = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
    # add more if you like, default logic below handles simple ids
}

def to_binance_symbol(coin_id: str) -> str:
    if coin_id in BINANCE_SYMBOLS:
        return BINANCE_SYMBOLS[coin_id]
    # heuristic: take letters only and append USDT, e.g. "cardano" -> "CARDANOUSDT"
    sym = "".join([c for c in coin_id if c.isalnum()]).upper()
    return f"{sym}USDT"

def binance_history_usdt(coin_id: str, hours: int = 24*7):
    """
    GET /api/v3/klines?symbol=BTCUSDT&interval=1h&limit=168
    returns [[openTime, open, high, low, close, volume, closeTime, ...], ...]
    We use close as price.
    """
    symbol = to_binance_symbol(coin_id)
    limit = max(1, min(hours, 1000))  # Binance cap per call
    url = f"{BINANCE}/api/v3/klines"
    params = {"symbol": symbol, "interval": "1h", "limit": limit}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    arr = r.json()
    if not isinstance(arr, list) or not arr:
        raise ValueError(f"No klines for {symbol}")
    series = []
    for k in arr:
        try:
            ms = int(k[0])
            close_price = float(k[4])
            series.append((ms, close_price))  # price in USDT ~ USD
        except Exception:
            continue
    if not series:
        raise ValueError(f"No usable klines for {symbol}")
    return series

def history_prices_vs(coin_id: str, vs: str, days: int = 7):
    vs = vs.lower()
    hours = days * 24
    series_usd = binance_history_usdt(coin_id, hours)
    if vs == "usd":
        rate = 1.0
    else:
        rate = fx_rate("USD", vs.upper())["rate"]
    prices = [[ms, p_usd * rate] for (ms, p_usd) in series_usd]
    return {"prices": prices}

# ---------- Routes ----------
@app.get("/")
def home():
    return render_template("index.html",
        base_fiat=BASE_FIAT,
        default_vs=DEFAULT_VS,
        default_coins=",".join(DEFAULT_COINS))

@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": int(time.time())})

@app.get("/api/crypto/price")
def price():
    ids = [s.strip() for s in request.args.get("ids", ",".join(DEFAULT_COINS)).split(",") if s.strip()]
    vs = [s.strip().lower() for s in request.args.get("vs", DEFAULT_VS).split(",") if s.strip()]
    try:
        return jsonify({"ok": True, "data": cg_simple(ids, vs)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

@app.get("/api/crypto/history")
def history():
    coin = request.args.get("coin_id", "bitcoin")
    vs = request.args.get("vs", DEFAULT_VS)
    days = int(request.args.get("days", "7"))
    try:
        data = history_prices_vs(coin, vs, days)
        return jsonify({"ok": True, "data": data})
    except requests.HTTPError as he:
        resp = he.response
        txt = ""
        try: txt = resp.text
        except Exception: pass
        return jsonify({"ok": False, "error": f"HTTP {resp.status_code} from history source", "body": txt[:300]}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

@app.get("/api/fx/convert")
def convert():
    amount = float(request.args.get("amount", "1"))
    f = request.args.get("from", "USD")
    t = request.args.get("to", BASE_FIAT)
    try:
        info = fx_rate(f, t)
        result = amount * info["rate"]
        return jsonify({"ok": True, "data": {
            "success": True,
            "query": {"from": f.upper(), "to": t.upper(), "amount": amount},
            "info": {"rate": info["rate"], "date": info["date"], "base": info["base"]},
            "result": result
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

@app.get("/api/watchlist")
def wl_list():
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM watchlist ORDER BY name ASC").fetchall()]
    return jsonify({"ok": True, "data": rows})

@app.post("/api/watchlist")
def wl_add():
    b = request.get_json(force=True, silent=True) or {}
    need = all(b.get(k) for k in ("coin_id","symbol","name"))
    if not need:
        return jsonify({"ok": False, "error": "coin_id, symbol, name required"}), 400
    with db() as c:
        try:
            c.execute("""INSERT INTO watchlist(coin_id,symbol,name,target_price,alert_enabled)
                         VALUES(?,?,?,?,?)""",
                      (b["coin_id"].strip(), b["symbol"].strip(), b["name"].strip(),
                       b.get("target_price"), 1 if b.get("alert_enabled") else 0))
            c.commit()
        except sqlite3.IntegrityError:
            return jsonify({"ok": False, "error": "coin already in watchlist"}), 409
    return jsonify({"ok": True})

@app.delete("/api/watchlist/<coin_id>")
def wl_del(coin_id):
    with db() as c:
        c.execute("DELETE FROM watchlist WHERE coin_id=?", (coin_id,))
        c.commit()
    return jsonify({"ok": True})

if __name__ == "__main__":
    os.makedirs("db", exist_ok=True)
    if not os.path.exists(DB_PATH):
        print("ℹ️  First run? Do:  python manage.py init && python manage.py seed")
    app.run(host=HOST, port=PORT)
