import logging, os, sys, time
from contextlib import contextmanager
import psycopg2, psycopg2.extras
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from trendspy import Trends

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("trends")

GEO = "MX"
TIMEFRAME = "today 3-m"
PAUSA = 8

def _dsn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL en el .env")
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

def active_terms(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT term, label FROM trends_watch_terms WHERE active IS TRUE ORDER BY id")
        return cur.fetchall()

def guardar(conn, term, serie):
    if not serie: return 0
    payload = [(term, f, i) for f, i in serie]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, "INSERT INTO trends_snapshots (term, trend_date, interest) VALUES %s ON CONFLICT (term, trend_date) DO UPDATE SET interest = EXCLUDED.interest", payload)
    return len(payload)

def extraer_serie(df, term):
    if df is None or not hasattr(df, "columns"): return []
    col = term if term in df.columns else None
    if col is None:
        for c in df.columns:
            if c not in ("isPartial", "date"): col = c; break
    if col is None: return []
    serie = []
    for idx, val in df[col].items():
        try:
            fecha = idx.date() if hasattr(idx, "date") else idx
            serie.append((fecha, int(val)))
        except (TypeError, ValueError):
            continue
    return serie

def main():
    tr = Trends()
    with connect() as conn:
        terminos = active_terms(conn)
        if not terminos:
            log.error("No hay terminos activos en trends_watch_terms.")
            return 1
        log.info("Consultando %s terminos en Google Trends (%s)", len(terminos), GEO)
        ok, fallos = 0, 0
        for term, label in terminos:
            try:
                log.info("-> %s", label)
                df = tr.interest_over_time([term], geo=GEO, timeframe=TIMEFRAME)
                serie = extraer_serie(df, term)
                n = guardar(conn, term, serie)
                conn.commit()
                log.info("   %s puntos guardados", n)
                ok += 1
            except Exception as exc:
                fallos += 1
                log.warning("   fallo '%s': %s", label, str(exc)[:150])
            time.sleep(PAUSA)
        log.info("Listo. %s ok, %s con error.", ok, fallos)
    return 1 if ok == 0 else 0

if __name__ == "__main__":
    sys.exit(main())
