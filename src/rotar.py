import datetime
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
log = logging.getLogger("rotar")

BASE = "https://www.pokemonpricetracker.com/api/v2"
PAUSA = 1.5
GRUPOS = 6

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

def cartas_del_grupo(conn, grupo):
    """Trae las cartas cuyo id, ordenado, cae en el grupo de hoy."""
    with conn.cursor() as cur:
        cur.execute("SELECT tcgplayer_id FROM graded_cards ORDER BY tcgplayer_id")
        todas = [r[0] for r in cur.fetchall()]
    return [t for i, t in enumerate(todas) if i % GRUPOS == grupo]

def actualizar_carta(session, conn, tid):
    r = session.get(f"{BASE}/cards", params={"tcgPlayerId": tid, "includeEbay": "true"}, timeout=30)
    if r.status_code != 200:
        return 0
    d = r.json().get("data")
    if isinstance(d, list): d = d[0] if d else None
    if not d: return 0
    img = d.get("imageCdnUrl400") or d.get("imageCdnUrl200")
    prices = d.get("prices") or {}
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE graded_cards SET market_usd=%s, image_url=COALESCE(%s,image_url), last_seen=now()
            WHERE tcgplayer_id=%s
        """, (_num(prices.get("market")), img, tid))
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

    # Grupo de hoy segun el dia del anio (0, 1 o 2)
    dia = datetime.date.today().timetuple().tm_yday
    grupo = dia % GRUPOS
    log.info("Hoy toca el grupo %s de %s", grupo, GRUPOS)

    with connect() as conn:
        ids = cartas_del_grupo(conn, grupo)
        log.info("Cartas en este grupo: %s", len(ids))
        ok, fallos = 0, 0
        for i, tid in enumerate(ids):
            try:
                ok += actualizar_carta(session, conn, tid)
                if (i + 1) % 100 == 0:
                    conn.commit()
                    log.info("   progreso: %s/%s", i + 1, len(ids))
            except Exception as exc:
                fallos += 1
                if fallos <= 5:
                    log.warning("   fallo %s: %s", tid, str(exc)[:80])
            time.sleep(PAUSA)
        conn.commit()
        log.info("LISTO. %s actualizadas, %s fallos.", ok, fallos)
    return 0 if ok > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
