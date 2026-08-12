# Tracker de cartas Pokémon · México

Bot que mide qué cartas de Pokémon se están moviendo más en México, usando
la API oficial de Mercado Libre. Corre solo en la nube, sin servidor y sin costo.

**Señal que mide:** unidades vendidas, precio mediano y número de publicaciones —
no likes ni comentarios. Es demanda real, no ruido.

```
GitHub Actions (cron diario)  →  API Mercado Libre  →  Supabase  →  Streamlit
```

---

## Puesta en marcha (unos 30 minutos)

### 1. Base de datos — Supabase

1. Crea un proyecto gratis en [supabase.com](https://supabase.com).
2. Abre **SQL Editor**, pega todo el contenido de `schema.sql` y ejecútalo.
3. Ve a **Project Settings → Database → Connection string → URI**.
   Copia la que usa el puerto **6543** (el pooler) y reemplaza `[YOUR-PASSWORD]`.
   Esa cadena es tu `DATABASE_URL`.

### 2. Aplicación de Mercado Libre

1. Entra a [developers.mercadolibre.com.mx](https://developers.mercadolibre.com.mx)
   con tu cuenta de ML y crea una aplicación.
2. En **Redirect URI** pon cualquier URL con HTTPS que controles.
   Si no tienes una, sirve `https://httpbin.org/get`.
3. Anota el **App ID** (`ML_CLIENT_ID`) y el **Secret Key** (`ML_CLIENT_SECRET`).

### 3. Primer token (una sola vez, desde tu compu)

```bash
git clone <tu-repo> && cd pokemon-ml-tracker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # llena DATABASE_URL, ML_CLIENT_ID, ML_CLIENT_SECRET, ML_REDIRECT_URI
python -m src.bootstrap_token
```

Te da una liga, la abres, autorizas, y pegas el `code` que aparece en la URL.
El script guarda los tokens en la base y te imprime el `refresh_token`.

Pruébalo de inmediato:

```bash
python -m src.scrape
```

### 4. Automatizarlo — GitHub Actions

Sube el repo a GitHub (**privado**) y en
**Settings → Secrets and variables → Actions → New repository secret** agrega:

| Secret | Valor |
|---|---|
| `DATABASE_URL` | la cadena de Supabase |
| `ML_CLIENT_ID` | App ID |
| `ML_CLIENT_SECRET` | Secret Key |
| `ML_REFRESH_TOKEN` | el que imprimió el bootstrap (respaldo) |

El workflow ya está en `.github/workflows/scrape.yml` y corre a las 7:00 AM
hora del centro. Puedes dispararlo a mano desde la pestaña **Actions**.

### 5. Dashboard — Streamlit Cloud

1. [share.streamlit.io](https://share.streamlit.io) → **New app** → tu repo.
2. Main file path: `dashboard/app.py`.
3. En **Advanced settings → Secrets** pega:
   ```toml
   DATABASE_URL = "postgresql://..."
   ```

En local: `streamlit run dashboard/app.py`.

---

## Qué guarda

| Tabla | Para qué sirve |
|---|---|
| `listings` | catálogo de cada publicación vista |
| `listing_snapshots` | foto diaria: precio, vendidos, stock, visitas |
| `term_snapshots` | agregados por término de búsqueda |
| `keyword_snapshots` | agregados por Pokémon / set — **el ranking sale de aquí** |
| `oauth_tokens` | tokens de ML, que rotan solos |

La popularidad real se calcula como la **diferencia** de `sold_quantity` entre
dos fechas. Por eso el primer día no vas a ver tendencias: necesitas mínimo dos
corridas, e idealmente una o dos semanas para que el ranking tenga sentido.

## Personalizarlo

- **Más búsquedas:** inserta filas en `search_terms` desde el SQL Editor.
- **Más cartas o sets:** agrega a las listas `POKEMON` y `SETS` en `src/keywords.py`.
- **Más profundidad:** sube `MAX_ITEMS_POR_TERMINO` en `src/scrape.py` (tope de 1000, límite de la API).
- **Otro horario:** cambia el `cron` en el workflow (está en UTC).

## Cosas que conviene saber

- El `offset` de la búsqueda de ML topa en 1000 resultados por término. Para
  cubrir más, usa términos más específicos en lugar de subir el límite.
- `sold_quantity` a veces viene redondeado por ML en categorías con mucho volumen.
  Sirve para rankear tendencias, no como cifra contable exacta.
- El endpoint de visitas es inestable; si falla, el job sigue y solo deja ese
  campo en nulo.
- Los refresh tokens de ML rotan en cada renovación. Por eso viven en la base:
  si los dejaras solo en un Secret, el bot moriría a las 6 horas.
- Si el repo no tiene actividad por 60 días, GitHub pausa los cron. Un commit
  ocasional o correrlo a mano lo reactiva.
