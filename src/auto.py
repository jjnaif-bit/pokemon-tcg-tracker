"""Siembra sola los sets nuevos o incompletos. Corre los martes."""
import logging, os, sys, time
import requests
from src.sets import connect, guardar_carta, BASE

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("auto")

UMBRAL = 0.80          # siembra si tiene menos del 80% de lo esperado
TOPE_CARTAS = 2000     # tope por corrida (~4000 creditos)
MINIMO = 20            # ignora sets diminutos

def sets_api(session):
    """Todos los sets con su cardCount, paginando."""
    todos, offset = [], 0
    while True:
        r = session.get(f"{BASE}/sets", params={"limit": 100, "offset": offset}, timeout=40)
        if r.status_code != 200:
            log.warning("HTTP %s pidiendo sets", r.status_code); break
        data = r.json().get("data") or []
        if not data: break
        todos.extend(data)
        offset += 100
        time.sleep(1.0)
        if len(data) < 100: break
    return todos

def conteo_local(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT set_name, COUNT(*) FROM graded_cards GROUP BY set_name")
        return {r[0]: r[1] for r in cur.fetchall()}

def bajar(session, set_name, jp=False):
    """Baja un set. jp=True usa el catalogo japones."""
    todas, offset = [], 0
    while True:
        intentos = 0
        while True:
            p = {"setName": set_name, "limit": 50, "offset": offset, "includeEbay": "true"}
            if jp: p["language"] = "japanese"
            r = session.get(f"{BASE}/cards", params=p, timeout=40)
            if r.status_code == 429:
                intentos += 1
                if intentos > 5: return todas
                time.sleep(30 * intentos); continue
            break
        if r.status_code != 200: break
        data = r.json().get("data") or []
        if not data: break
        todas.extend(data)
        offset += 50
        time.sleep(2.0)
        if len(data) < 50: break
    return todas

def main():
    key = os.environ.get("PPT_API_KEY")
    if not key:
        log.error("Falta PPT_API_KEY"); return 1
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {key}"

    remotos = sets_api(session)
    log.info("Sets en la API: %s", len(remotos))

    with connect() as conn:
        local = conteo_local(conn)
        faltantes = []
        for st in remotos:
            nombre = st.get("name")
            esperado = st.get("cardCount") or 0
            if not nombre or esperado < MINIMO:
                continue
            tengo = local.get(nombre, 0)
            if tengo < esperado * UMBRAL:
                faltantes.append((nombre, tengo, esperado))

        faltantes.sort(key=lambda x: x[2] - x[1], reverse=True)
        log.info("Sets incompletos: %s", len(faltantes))
        if not faltantes:
            log.info("Nada que sembrar. Todo al dia."); return 0

        gastado, total = 0, 0
        for nombre, tengo, esperado in faltantes:
            if gastado >= TOPE_CARTAS:
                log.info("Tope alcanzado. Faltan %s sets para la proxima.", len(faltantes) - faltantes.index((nombre, tengo, esperado)))
                break
            log.info("=== %s (tengo %s de %s) ===", nombre, tengo, esperado)
            time.sleep(5)
            cartas = bajar(session, nombre)
            if not cartas:
                log.info("   vacio en ingles, probando japones...")
                time.sleep(5)
                cartas = bajar(session, nombre, jp=True)
            if not cartas:
                log.warning("   sin resultado en ningun idioma"); continue
            n = 0
            for d in cartas:
                try: n += guardar_carta(conn, d)
                except Exception as exc: log.warning("   fallo carta: %s", str(exc)[:80])
            conn.commit()
            gastado += len(cartas); total += n
            log.info("   %s guardadas", n)
    log.info("LISTO. %s cartas guardadas, %s consultadas.", total, gastado)
    return 0

if __name__ == "__main__":
    sys.exit(main())
