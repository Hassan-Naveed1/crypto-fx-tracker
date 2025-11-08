import sqlite3, os

DB_PATH = os.path.join("db", "app.db")
SCHEMA = os.path.join("db", "schema.sql")

def init_db():
    os.makedirs("db", exist_ok=True)
    with sqlite3.connect(DB_PATH) as c, open(SCHEMA, "r", encoding="utf-8") as f:
        c.executescript(f.read())
    print("✅ DB ready:", DB_PATH)

def seed():
    rows = [
        ("bitcoin","btc","Bitcoin",None,0),
        ("ethereum","eth","Ethereum",None,0),
        ("solana","sol","Solana",None,0),
    ]
    with sqlite3.connect(DB_PATH) as c:
        cur = c.cursor()
        for r in rows:
            try:
                cur.execute("""INSERT INTO watchlist(coin_id,symbol,name,target_price,alert_enabled)
                               VALUES(?,?,?,?,?)""", r)
            except sqlite3.IntegrityError:
                pass
        c.commit()
    print("🌱 Seeded watchlist.")

if __name__=="__main__":
    import sys
    if len(sys.argv)<2:
        print("Use: python manage.py [init|seed]"); exit(1)
    {"init":init_db, "seed":seed}.get(sys.argv[1], lambda:print("Unknown command"))()
