"""Siembra sets viejos completos. Disparo MANUAL, no corre solo."""
import logging, os, sys, time
import requests
from src.sets import connect, cartas_de_set, guardar_carta

log = logging.getLogger("sembrar")

GRUPOS = {
    "A": [
        "Base Set", "Base Set (Shadowless)", "Jungle", "Fossil",
        "Team Rocket", "Gym Heroes", "Gym Challenge",
        "Neo Genesis", "Neo Discovery", "Neo Revelation", "Neo Destiny",
        "Base Set 2", "Legendary Collection", "Southern Islands",
        "Expedition", "Aquapolis", "Skyridge", "Pokemon Web",
        "Best of Promos", "WoTC Promo",
    ],
    "B": [
        "EX Ruby and Sapphire", "EX Sandstorm", "EX Dragon",
        "EX Team Magma vs Team Aqua", "EX Hidden Legends",
        "EX FireRed & LeafGreen", "EX Team Rocket Returns", "EX Deoxys",
        "EX Emerald", "EX Unseen Forces", "EX Delta Species",
        "EX Legend Maker", "EX Holon Phantoms", "EX Crystal Guardians",
        "EX Dragon Frontiers", "EX Power Keepers", "EX Battle Stadium",
    ],
    "C": [
        "XY - Evolutions", "Generations", "Generations: Radiant Collection",
        "Shining Legends", "SM Base Set", "SM - Guardians Rising",
        "SM - Burning Shadows", "SM - Crimson Invasion", "SM - Ultra Prism",
        "SM - Forbidden Light", "SM - Celestial Storm", "SM - Lost Thunder",
        "Dragon Majesty", "XY - Steam Siege", "XY - Fates Collide",
        "XY - BREAKpoint", "SM Promos",
    ],
    "D": [
        "Majestic Dawn", "Legends Awakened", "Stormfront", "Platinum",
        "Rising Rivals", "Supreme Victors", "Arceus", "HeartGold SoulSilver",
        "Unleashed", "Undaunted", "Triumphant", "Call of Legends",
        "Black and White", "Emerging Powers", "Noble Victories",
        "Next Destinies", "Dark Explorers", "Dragons Exalted", "Dragon Vault",
        "Boundaries Crossed", "Plasma Storm", "Plasma Freeze", "Plasma Blast",
        "Legendary Treasures", "XY Base Set", "XY - Flashfire",
        "XY - Furious Fists", "XY - Phantom Forces", "XY - Primal Clash",
        "XY - Roaring Skies", "XY - Ancient Origins", "XY - BREAKthrough",
    ],
    "E": [
        "SV09: Journey Together", "SV10: Destined Rivals",
        "SV: Black Bolt", "SV: White Flare", "SV9: Battle Partners",
        "SV9a: Heat Wave Arena", "ME01: Mega Evolution",
        "ME02: Phantasmal Flames", "ME03: Perfect Order",
        "ME04: Chaos Rising", "ME05: Pitch Black", "ME: Ascended Heroes",
        "ME: Mega Evolution Promo", "ME: 30th Celebration",
        "ME: 30th Celebration Classic Collection",
        "MEE: Mega Evolution Energies", "M2: Inferno X",
        "M2a: High Class Pack: MEGA Dream ex", "M4: Ninja Spinner",
        "m1S: Mega Symphonia", "First Partner Collection 2026",
        "Player Placement Trainer Promos",
    ],
}

def main():
    if not os.environ.get("PPT_API_KEY"):
        log.error("Falta PPT_API_KEY"); return 1
    grupo = (os.environ.get("GRUPO") or "C").upper()
    if grupo not in GRUPOS:
        log.error("Grupo invalido: %s. Usa A, B, C, D o E", grupo); return 1
    lista = GRUPOS[grupo]
    log.info("### GRUPO %s — %s sets ###", grupo, len(lista))

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {os.environ['PPT_API_KEY']}"

    total, vacios = 0, []
    with connect() as conn:
        for set_name in lista:
            log.info("=== Set: %s ===", set_name)
            time.sleep(10)
            try:
                cartas = cartas_de_set(session, set_name)
                log.info("   %s cartas encontradas", len(cartas))
                if not cartas:
                    vacios.append(set_name); continue
                n = 0
                for d in cartas:
                    try:
                        n += guardar_carta(conn, d)
                    except Exception as exc:
                        log.warning("   fallo carta: %s", str(exc)[:100])
                conn.commit()
                total += n
                log.info("   %s guardadas", n)
            except Exception as exc:
                log.warning("   fallo set %s: %s", set_name, str(exc)[:120])
    log.info("LISTO. Grupo %s: %s cartas guardadas", grupo, total)
    if vacios:
        log.warning("SETS SIN RESULTADO (revisar nombre): %s", ", ".join(vacios))
    return 0

if __name__ == "__main__":
    sys.exit(main())
