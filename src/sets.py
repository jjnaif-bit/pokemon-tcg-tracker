import logging, os, sys, time
from contextlib import contextmanager
import requests
import psycopg2, psycopg2.extras
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("sets")

BASE = "https://www.pokemonpricetracker.com/api/v2"
PAUSA = 1.2
PAGINA = 50

SETS = [
    "Prismatic Evolutions",
    "151",
    "Surging Sparks",
    "Crown Zenith",
    "Evolving Skies",
    "Obsidian Flames",
    "Paldean Fates",
    "Lost Origin",
    "Brilliant Stars",
    "Paradox Rift",
]

def _dsn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn: raise RuntimeError("Falta DATABASE_URL")
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

def _num(v):
    try: return round(float(v), 2)
    except (TypeError, ValueError): return None

def cartas_de_set(session, set_name):
    """Baja todas las cartas de un set, paginando."""
    todas, offset = [], 0
    while True:
        r = session.get(f"{BASE}/cards", params={"setName": set_name, "limit": PAGINA, "offset": offset, "includeEbay": "true"}, timeout=40)
        if r.status_code != 200:
            log.warning("   HTTP %s en %s offset %s", r.status_code, set_name, offset)
            break
        data = r.json().get("data") or []
        if not data:
            break
        todas.extend(data)
        offset += PAGINA
        time.sleep(PAUSA)
        if len(data) < PAGINA:
            break
    return todas

def guardar_carta(conn, d):
    tid = str(d.get("tcgPlayerId") or d.get("id") or "")
    if not tid:
        return 0
    img = d.get("imageCdnUrl400") or d.get("imageCdnUrl200")
    prices = d.get("prices") or {}
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO graded_cards (tcgplayer_id, name, set_name, number, rarity, image_url, market_usd)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tcgplayer_id) DO UPDATE SET
                name=EXCLUDED.name, set_name=EXCLUDED.set_name, rarity=EXCLUDED.rarity,
                image_url=EXCLUDED.image_url, market_usd=EXCLUDED.market_usd, last_seen=now()
        """, (tid, d.get("name"), d.get("setName"), d.get("cardNumber"), d.get("rarity"), img, _num(prices.get("market"))))
        sbg = (d.get("ebay") or {}).get("salesByGrade") or {}
        filas = []
        for g, v in sbg.items():
            if not isinstance(v, dict): continue
            gr = g.lower().replace(".", "").replace("_", "")
            filas.append((tid, gr, _num(v.get("medianPrice")), _num(v.get("averagePrice")), v.get("count")))
        if filas:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO graded_price_snapshots (tcgplayer_id, grade, median_usd, average_usd, sales_count)
                VALUES %s ON CONFLICT (tcgplayer_id, captured_on, grade) DO UPDATE SET
                    median_usd=EXCLUDED.median_usd, average_usd=EXCLUDED.average_usd, sales_count=EXCLUDED.sales_count
            """, filas)
    return 1

def main():
    api_key = os.environ.get("PPT_API_KEY")
    if not api_key:
        log.error("Falta PPT_API_KEY"); return 1
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    total_guardadas = 0
    with connect() as conn:
        for set_name in SETS:
            log.info("=== Set: %s ===", set_name)
            try:
                cartas = cartas_de_set(session, set_name)
                log.info("   %s cartas encontradas", len(cartas))
                n = 0
                for d in cartas:
                    try:
                        n += guardar_carta(conn, d)
                    except Exception as exc:
                        log.warning("   fallo carta: %s", str(exc)[:100])
                conn.commit()
                total_guardadas += n
                log.info("   %s guardadas de %s", n, set_name)
            except Exception as exc:
                log.warning("   fallo set %s: %s", set_name, str(exc)[:120])
    log.info("LISTO. Total cartas guardadas: %s", total_guardadas)
    return 0 if total_guardadas > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
