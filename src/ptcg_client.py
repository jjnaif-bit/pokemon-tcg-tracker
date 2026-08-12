import logging, os, time
import requests
log = logging.getLogger(__name__)
BASE = "https://api.pokemontcg.io/v2"
TIMEOUT = 30
class PTCGClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "toshi-ptcg-tracker/1.0"
        key = os.environ.get("PTCG_API_KEY")
        if key:
            self.session.headers["X-Api-Key"] = key
            log.info("Usando PTCG_API_KEY.")
        else:
            log.info("Sin API key (limite mas bajo, pero funciona).")
    def _get(self, path, params=None, reintentos=4):
        url = f"{BASE}{path}"
        for intento in range(reintentos):
            try:
                resp = self.session.get(url, params=params, timeout=TIMEOUT)
            except requests.RequestException as exc:
                log.warning("Error de red (%s), reintento %s", exc, intento + 1)
                time.sleep(2 ** intento); continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                espera = 2 ** intento * 3
                log.warning("HTTP %s, esperando %ss", resp.status_code, espera)
                time.sleep(espera); continue
            log.error("HTTP %s en %s: %s", resp.status_code, url, resp.text[:200])
            return None
        return None
    def cards_in_set(self, set_id, page_size=250):
        cartas, page = [], 1
        while True:
            data = self._get("/cards", params={"q": f"set.id:{set_id}", "page": page, "pageSize": page_size, "select": "id,name,number,rarity,set,images,tcgplayer"})
            if not data: break
            lote = data.get("data", [])
            if not lote: break
            cartas.extend(lote)
            total = data.get("totalCount", 0)
            if page * page_size >= total: break
            page += 1; time.sleep(0.5)
        return cartas
