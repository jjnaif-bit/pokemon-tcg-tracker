import os, sys, json, logging, requests, psycopg2
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("set_years")
BASE = "https://www.pokemonpricetracker.com/api/v2"

def main():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {os.environ['PPT_API_KEY']}"
    sets, offset = [], 0
    while True:
        r = s.get(f"{BASE}/sets", params={"limit": 100, "offset": offset, "sortBy": "releaseDate", "sortOrder": "desc"}, timeout=40)
        if r.status_code != 200:
            log.error("HTTP %s: %s", r.status_code, r.text[:200]); break
        data = r.json().get("data") or []
        if not data: break
        sets.extend(data); offset += 100
        if len(data) < 100: break
    log.info("Sets recibidos de la API: %s", len(sets))
    if not sets: return 1
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    cur.execute("INSERT INTO prueba_json (contenido) VALUES (%s)", (json.dumps(sets[0], indent=2)[:4000],))
    actualizados, sin_fecha = 0, 0
    for st in sets:
        nombre = st.get("name") or st.get("setName")
        fecha = st.get("releaseDate") or st.get("release_date") or st.get("released")
        if not nombre: continue
        if not fecha:
            sin_fecha += 1; continue
        try: year = int(str(fecha)[:4])
        except ValueError: sin_fecha += 1; continue
        cur.execute("""INSERT INTO set_years (set_name, year) VALUES (%s, %s)
                       ON CONFLICT (set_name) DO UPDATE SET year = EXCLUDED.year""", (nombre, year))
        actualizados += 1
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM graded_cards gc LEFT JOIN set_years sy ON sy.set_name = gc.set_name WHERE sy.year IS NULL OR sy.year = 0")
    log.info("Sets actualizados: %s | sin fecha: %s | cartas aun sin año: %s", actualizados, sin_fecha, cur.fetchone()[0])
    conn.close(); return 0

if __name__ == "__main__":
    sys.exit(main())
