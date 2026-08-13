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
log = logging.getLogger("movers")

BASE = "https://www.pokemonpricetracker.com/api/v2"
CATEGORIAS = ["mostActive", "volumeMovers"]
CUANTAS = 40
PAUSA = 2

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

def traer_movers(session):
    vistos, orden = {}, []
    for cat in CATEGORIAS:
        r = session.get(f"{BASE}/market-movers", params={"category": cat, "limit": CUANTAS}, timeout=30)
        if r.status_code != 200:
            log.warning("   cat %s HTTP %s", cat, r.status_code); continue
        lista = (r.json().get("data") or {}).get(cat) or []
        log.info("   %s: %s cartas", cat, len(lista))
        for c in lista:
            tid = str(c.get("tcgPlayerId") or "")
            if tid and tid not in vistos:
                vistos[tid] = c; orden.append(tid)
        time.sleep(PAUSA)
    return [vistos[t] for t in orden]

def carta_gradeada(session, tcg_id):
    r = session.get(f"{BASE}/cards", params={"tcgPlayerId": tcg_id, "includeEbay": "true"}, timeout=30)
    if r.status_code != 200:
        return None
    j = r.json()
    d = j.get("data")
    if isinstance(d, list): return d[0] if d else None
    return d

def guardar_carta(conn, d):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO graded_cards (tcgplayer_id, name, set_name, number, rarity, image_url, market_usd)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tcgplayer_id) DO UPDATE SET
                name=EXCLUDED.name, set_name=EXCLUDED.set_name, rarity=EXCLUDED.rarity,
                image_url=EXCLUDED.image_url, market_usd=EXCLUDED.market_usd, last_seen=now()
        """, (d["tcgplayer_id"], d["name"], d["set_name"], d["number"], d["rarity"], d["image_url"], d["market_usd"]))

def guardar_grados(conn, tcg_id, filas):
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
        log.error("Falta PPT_API_KEY"); return 1
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    with connect() as conn:
        log.info("Bajando cartas mas activas del mercado...")
        movers = traer_movers(session)
        log.info("Total unicas a procesar: %s", len(movers))
        ok, fallos, con_grado = 0, 0, 0
        for c in movers:
            tid = str(c.get("tcgPlayerId") or "")
            nombre = c.get("name")
            try:
                log.info("-> %s", nombre)
                d = carta_gradeada(session, tid)
                if not d:
                    fallos += 1; time.sleep(PAUSA); continue
                img = d.get("imageCdnUrl400") or d.get("imageCdnUrl200") or c.get("imageUrl")
                prices = d.get("prices") or {}
                guardar_carta(conn, {
                    "tcgplayer_id": tid, "name": d.get("name") or nombre,
                    "set_name": d.get("setName") or c.get("setName"),
                    "number": d.get("cardNumber") or c.get("cardNumber"),
                    "rarity": d.get("rarity") or c.get("rarity"),
                    "image_url": img, "market_usd": _num(prices.get("market") or c.get("currentPrice")),
                })
                sbg = (d.get("ebay") or {}).get("salesByGrade") or {}
                filas = []
                for grado, vals in sbg.items():
                    if not isinstance(vals, dict): continue
                    filas.append((grado.lower().replace(".","").replace("_",""),
                                  _num(vals.get("medianPrice")), _num(vals.get("averagePrice")), vals.get("count")))
                guardar_grados(conn, tid, filas)
                conn.commit()
                if filas: con_grado += 1
                log.info("   %s grados", len(filas))
                ok += 1
            except Exception as exc:
                fallos += 1; log.warning("   fallo: %s", str(exc)[:120])
            time.sleep(PAUSA)
        log.info("Listo. %s procesadas, %s con datos gradeados, %s fallos.", ok, con_grado, fallos)
    return 1 if ok == 0 else 0

if __name__ == "__main__":
    sys.exit(main())
