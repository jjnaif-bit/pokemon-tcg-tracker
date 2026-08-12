import logging, sys
from . import db
from .ptcg_client import PTCGClient
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scrape")
def _num(v):
    try: return round(float(v), 2)
    except (TypeError, ValueError): return None
def procesar_set(cliente, conn, set_id, label):
    log.info("-> %s (%s)", label, set_id)
    cartas = cliente.cards_in_set(set_id)
    if not cartas:
        log.warning("   sin cartas"); return 0
    filas_cartas, filas_precios = [], []
    for c in cartas:
        card_id = c.get("id")
        if not card_id: continue
        set_info = c.get("set", {}); images = c.get("images", {}); tcg = c.get("tcgplayer", {})
        rel = (set_info.get("releaseDate") or "").replace("/", "-") or None
        filas_cartas.append({"card_id": card_id, "name": c.get("name"), "set_name": set_info.get("name"), "set_id": set_info.get("id"), "number": c.get("number"), "rarity": c.get("rarity"), "image_small": images.get("small"), "tcgplayer_url": tcg.get("url"), "release_date": rel})
        precios = tcg.get("prices") or {}
        for variante, vals in precios.items():
            if not isinstance(vals, dict): continue
            filas_precios.append({"card_id": card_id, "variant": variante, "market_usd": _num(vals.get("market")), "low_usd": _num(vals.get("low")), "mid_usd": _num(vals.get("mid")), "high_usd": _num(vals.get("high"))})
    db.upsert_cards(conn, filas_cartas)
    db.insert_price_snapshots(conn, filas_precios)
    conn.commit()
    log.info("   %s cartas . %s precios guardados", len(filas_cartas), len(filas_precios))
    return len(filas_cartas)
def main():
    with db.connect() as conn:
        cliente = PTCGClient()
        sets = db.active_sets(conn)
        if not sets:
            log.error("No hay sets activos."); return 1
        log.info("Rastreando %s sets", len(sets))
        total, fallos = 0, 0
        for set_id, label in sets:
            try:
                total += procesar_set(cliente, conn, set_id, label)
            except Exception as exc:
                fallos += 1; log.exception("Fallo el set '%s': %s", label, exc)
        log.info("Listo. %s cartas en total, %s sets con error.", total, fallos)
    return 1 if fallos == len(sets) else 0
if __name__ == "__main__":
    sys.exit(main())
