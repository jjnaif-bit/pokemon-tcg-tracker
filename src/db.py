import os
from contextlib import contextmanager
import psycopg2, psycopg2.extras
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
def _dsn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL. Revisa tu archivo .env")
    return dsn
@contextmanager
def connect():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
def active_sets(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT set_id, label FROM ptcg_watch_sets WHERE active IS TRUE ORDER BY id")
        return cur.fetchall()
def upsert_cards(conn, rows):
    if not rows: return
    payload = [(r["card_id"], r["name"], r.get("set_name"), r.get("set_id"), r.get("number"), r.get("rarity"), r.get("image_small"), r.get("tcgplayer_url"), r.get("release_date")) for r in rows]
    sql = "INSERT INTO ptcg_cards (card_id, name, set_name, set_id, number, rarity, image_small, tcgplayer_url, release_date) VALUES %s ON CONFLICT (card_id) DO UPDATE SET name = EXCLUDED.name, rarity = EXCLUDED.rarity, tcgplayer_url = EXCLUDED.tcgplayer_url, last_seen = now()"
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, payload)
def insert_price_snapshots(conn, rows):
    if not rows: return
    payload = [(r["card_id"], r["variant"], r.get("market_usd"), r.get("low_usd"), r.get("mid_usd"), r.get("high_usd")) for r in rows]
    sql = "INSERT INTO ptcg_price_snapshots (card_id, variant, market_usd, low_usd, mid_usd, high_usd) VALUES %s ON CONFLICT (card_id, captured_on, variant) DO UPDATE SET market_usd = EXCLUDED.market_usd, low_usd = EXCLUDED.low_usd, mid_usd = EXCLUDED.mid_usd, high_usd = EXCLUDED.high_usd"
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, payload)
