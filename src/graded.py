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
log = logging.getLogger("graded")

BASE = "https://www.pokemonpricetracker.com/api/v2"
GRADOS = ["psa10","psa9","psa8","cgc10","cgc9.5","bgs10","bgs9.5","sgc10"]
PAUSA = 2

def _dsn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn: raise RuntimeError("Falta DATABASE_URL en el .env")
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

def buscar_carta(session, nombre):
    r = session.get(f"{BASE}/cards", params={"search": nombre, "limit": 1, "includeEbay": "true"}, timeout=30)
    if r.status_code != 200:
        log.warning("   HTTP %s buscando '%s': %s", r.status_code, nombre, r.text[:150])
        return None
    j = r.json()
    data = j.get("data")
    if isinstance(data, list):
        return data[0] if data else None
    return data

def watch_list(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, tcgplayer_id, search_name, label FROM graded_watch WHERE active IS TRUE ORDER BY id")
        return cur.fetchall()

def upsert_card(conn, d):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO graded_cards (tcgplayer_id, name, set_name, number, rarity, image_url, market_usd)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tcgplayer_id) DO UPDATE SET
                name=EXCLUDED.name, set_name=EXCLUDED.set_name, rarity=EXCLUDED.rarity,
                image_url=EXCLUDED.image_url, market_usd=EXCLUDED.market_usd, last_seen=now()
        """, (d["tcgplayer_id"], d["name"], d["set_name"], d["number"], d["rarity"], d["image_url"], d["market_usd"]))

def insert_grades(conn, tcg_id, filas):
    if not filas: return
    payload = [(tcg_id, g, m, a, c) for g, m, a, c in filas]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO graded_price_snapshots (tcgplayer_id, grade, median_usd, average_usd, sales_count)
            VALUES %s ON CONFLICT (tcgplayer_id, captured_on, grade) DO UPDATE SET
                median_usd=EXCLUDED.median_usd, average_usd=EXCLUDED.average_usd, sales_count=EXCLUDED.sales_count
        """, payload)

def main():
    api_key = os.environ.get("PPT_API_KEY")
    if not api_key:
        log.error("Falta PPT_API_KEY en el .env"); return 1
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"
    session.headers["Content-Type"] = "application/json"

    with connect() as conn:
        cartas = watch_list(conn)
        if not cartas:
            log.error("No hay cartas en graded_watch."); return 1
        log.info("Consultando %s cartas gradeadas", len(cartas))
        ok, fallos = 0, 0
        for wid, tcg_id, nombre, label in cartas:
            try:
                log.info("-> %s", label)
                termino = tcg_id if tcg_id else nombre
                d = buscar_carta(session, termino)
                if not d:
                    log.warning("   sin resultado"); fallos += 1; time.sleep(PAUSA); continue
                card_id = str(d.get("tcgPlayerId") or d.get("id") or "")
                if not card_id:
                    log.warning("   sin id"); fallos += 1; time.sleep(PAUSA); continue
                img = d.get("imageCdnUrl400") or d.get("imageCdnUrl200") or (d.get("images") or {}).get("small")
                prices = d.get("prices") or {}
                upsert_card(conn, {
                    "tcgplayer_id": card_id, "name": d.get("name"),
                    "set_name": d.get("setName") or (d.get("set") or {}).get("name"),
                    "number": d.get("cardNumber") or d.get("number"),
                    "rarity": d.get("rarity"), "image_url": img,
                    "market_usd": _num(prices.get("market")),
                })
                sbg = (d.get("ebay") or {}).get("salesByGrade") or {}
                filas = []
                for grado, vals in sbg.items():
                    if not isinstance(vals, dict): continue
                    filas.append((grado.lower().replace(".", "").replace("_",""),
                                  _num(vals.get("medianPrice")), _num(vals.get("averagePrice")),
                                  vals.get("count")))
                insert_grades(conn, card_id, filas)
                conn.commit()
                log.info("   %s: %s grados guardados", d.get("name"), len(filas))
                ok += 1
            except Exception as exc:
                fallos += 1; log.warning("   fallo '%s': %s", label, str(exc)[:150])
            time.sleep(PAUSA)
        log.info("Listo. %s ok, %s con error.", ok, fallos)
    return 1 if ok == 0 else 0

if __name__ == "__main__":
    sys.exit(main())
