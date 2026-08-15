import logging, os, re, sys, time
from contextlib import contextmanager
import psycopg2, psycopg2.extras
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from trendspy import Trends

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("mtrends")

GEO = "MX"
TIMEFRAME = "today 3-m"
PAUSA_GRUPO = 10
MAX_CARTAS = 40

def _dsn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL")
    return dsn

@contextmanager
def connect():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def simplificar(nombre):
    n = (nombre or "").lower()
    n = re.sub(r"\d+/\d+", " ", n)
    n = re.sub(r"[-/]", " ", n)
    n = re.sub(r"\b[a-z]{1,3}\d+\b", " ", n)
    conservar = ["vmax","vstar","ex","gx","v","alt","art","secret","full","alternate","shining","mega"]
    m = re.findall(r"\(([^)]*)\)", n)
    extra = []
    for grupo in m:
        for w in grupo.split():
            if w in conservar:
                extra.append(w)
    n = re.sub(r"\([^)]*\)", " ", n)
    n = n.replace("'s", "")
    n = re.sub(r"\b\d+\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    palabras = n.split() + [e for e in extra if e not in n.split()]
    return " ".join(palabras[:4])

def cartas_top(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.tcgplayer_id, c.name, MAX(s.sales_count) AS ventas
            FROM graded_cards c
            JOIN graded_price_snapshots s ON s.tcgplayer_id = c.tcgplayer_id
            WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots)
            GROUP BY c.tcgplayer_id, c.name
            ORDER BY ventas DESC NULLS LAST
            LIMIT %s
        """, (MAX_CARTAS,))
        return cur.fetchall()

def guardar(conn, tid, nombre, termino, serie):
    if not serie:
        return 0
    payload = [(tid, nombre, termino, f, i) for f, i in serie]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO market_trends (tcgplayer_id, card_name, search_term, trend_date, interest_mx)
            VALUES %s ON CONFLICT (search_term, trend_date, captured_on) DO UPDATE SET interest_mx = EXCLUDED.interest_mx
        """, payload)
    return len(payload)

def extraer(df, term):
    if df is None or not hasattr(df, "columns"):
        return []
    col = term if term in df.columns else None
    if col is None:
        for c in df.columns:
            if c not in ("isPartial", "date"):
                col = c
                break
    if col is None:
        return []
    out = []
    for idx, val in df[col].items():
        try:
            f = idx.date() if hasattr(idx, "date") else idx
            out.append((f, int(val)))
        except (TypeError, ValueError):
            continue
    return out

def main():
    tr = Trends()
    with connect() as conn:
        cartas = cartas_top(conn)
        if not cartas:
            log.error("No hay cartas en la base.")
            return 1
        mapa = {}
        for tid, nombre, ventas in cartas:
            t = simplificar(nombre)
            if t and t not in mapa:
                mapa[t] = (tid, nombre)
        terminos = list(mapa.keys())
        log.info("Consultando %s cartas en Google Mexico (grupos de 5)", len(terminos))
        ok, fallos = 0, 0
        for i in range(0, len(terminos), 5):
            grupo = terminos[i:i+5]
            try:
                log.info("-> grupo: %s", ", ".join(grupo))
                df = tr.interest_over_time(grupo, geo=GEO, timeframe=TIMEFRAME)
                for t in grupo:
                    tid, nombre = mapa[t]
                    serie = extraer(df, t)
                    n = guardar(conn, tid, nombre, t, serie)
                    if n > 0:
                        ok += 1
                conn.commit()
            except Exception as exc:
                fallos += 1
                log.warning("   fallo grupo: %s", str(exc)[:120])
            time.sleep(PAUSA_GRUPO)
        log.info("Listo. %s cartas con datos, %s grupos con error.", ok, fallos)
    return 1 if ok == 0 else 0

if __name__ == "__main__":
    sys.exit(main())
