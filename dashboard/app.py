import os
from datetime import date, timedelta
import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="Toshi · Precios Pokemon", page_icon="🔥", layout="wide")

def dsn():
    return st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL"))

@st.cache_data(ttl=1800)
def q(sql, params=None):
    with psycopg2.connect(dsn()) as conn:
        return pd.read_sql(sql, conn, params=params)

st.markdown("""
<style>
    .card-box { background:#1a1d24; border-radius:14px; padding:12px; border:1px solid #2a2e37; margin-bottom:10px; }
    .card-name { font-weight:700; font-size:15px; color:#fff; margin:6px 0 2px; }
    .card-set { font-size:12px; color:#9aa0aa; }
    .price-up { color:#22c55e; font-weight:700; }
    .price-down { color:#ef4444; font-weight:700; }
    .price-big { font-size:20px; font-weight:800; color:#fff; }
</style>
""", unsafe_allow_html=True)

st.title("🔥 Toshi Collectibles — Radar de precios Pokemon")
st.caption("Precio de mercado de TCGplayer (USD) · datos de pokemontcg.io")

dias = st.sidebar.slider("Ventana de analisis (dias)", 2, 180, 30)
desde = date.today() - timedelta(days=dias)
variante_pref = st.sidebar.selectbox("Variante", ["holofoil", "normal", "reverseHolofoil"], index=0)
precio_min = st.sidebar.number_input("Precio minimo USD (filtro)", value=1.0, step=1.0)

fechas = q("SELECT DISTINCT captured_on FROM ptcg_price_snapshots ORDER BY captured_on")
n_fechas = len(fechas)

col_a, col_b, col_c = st.columns(3)
total_cartas = q("SELECT COUNT(*) AS n FROM ptcg_cards")["n"].iloc[0]
col_a.metric("Cartas en catalogo", f"{total_cartas:,}")
col_b.metric("Dias de datos", n_fechas)
col_c.metric("Ultima captura", str(fechas["captured_on"].max()) if n_fechas else "-")

if n_fechas < 2:
    st.info("📸 Ya tienes la primera foto de precios. Para ver que sube y que baja necesito al menos dos dias distintos. Corre el bot otra vez manana y aqui apareceran las tendencias.")

def tarjetas(df):
    cols = st.columns(4)
    for i, (_, r) in enumerate(df.iterrows()):
        with cols[i % 4]:
            signo = "▲" if (r["cambio_pct"] or 0) >= 0 else "▼"
            clase = "price-up" if (r["cambio_pct"] or 0) >= 0 else "price-down"
            img = r["image_small"] or ""
            st.markdown(f'<div class="card-box"><img src="{img}" style="width:100%; border-radius:8px;" /><div class="card-name">{r["name"]}</div><div class="card-set">{r["set_name"]} · #{r["number"]}</div><div class="price-big">${r["precio_fin"]:.2f}</div><div class="{clase}">{signo} {abs(r["cambio_pct"]):.1f}% · antes ${r["precio_ini"]:.2f}</div></div>', unsafe_allow_html=True)

if n_fechas >= 2:
    st.header("📈 Las que mas subieron")
    movimiento = q("""
        WITH ventana AS (
            SELECT card_id, variant, MIN(captured_on) AS ini, MAX(captured_on) AS fin
            FROM ptcg_price_snapshots
            WHERE captured_on >= %(desde)s AND variant = %(variant)s
            GROUP BY card_id, variant
            HAVING MIN(captured_on) <> MAX(captured_on)
        )
        SELECT c.name, c.set_name, c.number, c.rarity, c.image_small, c.tcgplayer_url,
               pi.market_usd AS precio_ini, pf.market_usd AS precio_fin,
               CASE WHEN pi.market_usd > 0 THEN ROUND(100.0*(pf.market_usd-pi.market_usd)/pi.market_usd,1) END AS cambio_pct
        FROM ventana v
        JOIN ptcg_cards c ON c.card_id = v.card_id
        JOIN ptcg_price_snapshots pi ON pi.card_id=v.card_id AND pi.variant=v.variant AND pi.captured_on=v.ini
        JOIN ptcg_price_snapshots pf ON pf.card_id=v.card_id AND pf.variant=v.variant AND pf.captured_on=v.fin
        WHERE pi.market_usd >= %(pmin)s
        ORDER BY cambio_pct DESC NULLS LAST LIMIT 12
    """, {"desde": desde, "variant": variante_pref, "pmin": precio_min})
    subieron = movimiento[movimiento["cambio_pct"] > 0].head(12)
    if not subieron.empty: tarjetas(subieron)
    else: st.write("Ninguna subio en este periodo con los filtros actuales.")
    st.header("📉 Las que mas bajaron")
    bajaron = movimiento[movimiento["cambio_pct"] < 0].sort_values("cambio_pct").head(8)
    if not bajaron.empty: tarjetas(bajaron)
    else: st.write("Ninguna bajo en este periodo con los filtros actuales.")

st.header("💎 Las mas valiosas ahora")
caras = q("""
    SELECT DISTINCT ON (c.card_id) c.name, c.set_name, c.number, c.rarity, c.image_small, c.tcgplayer_url, s.market_usd, s.variant
    FROM ptcg_price_snapshots s JOIN ptcg_cards c ON c.card_id = s.card_id
    WHERE s.captured_on = (SELECT MAX(captured_on) FROM ptcg_price_snapshots) AND s.market_usd IS NOT NULL
    ORDER BY c.card_id, s.market_usd DESC
""")
if not caras.empty:
    caras = caras.sort_values("market_usd", ascending=False).head(12)
    cols = st.columns(4)
    for i, (_, r) in enumerate(caras.iterrows()):
        with cols[i % 4]:
            img = r["image_small"] or ""
            st.markdown(f'<div class="card-box"><img src="{img}" style="width:100%; border-radius:8px;" /><div class="card-name">{r["name"]}</div><div class="card-set">{r["set_name"]} · #{r["number"]} · {r["rarity"] or ""}</div><div class="price-big">${r["market_usd"]:.2f}</div><div class="card-set">{r["variant"]}</div></div>', unsafe_allow_html=True)

st.header("🔍 Ver una carta en el tiempo")
nombres = q("SELECT DISTINCT name FROM ptcg_cards ORDER BY name")
if not nombres.empty:
    elegida = st.selectbox("Carta", nombres["name"].tolist())
    if elegida:
        serie = q("""
            SELECT s.captured_on, s.variant, s.market_usd
            FROM ptcg_price_snapshots s JOIN ptcg_cards c ON c.card_id = s.card_id
            WHERE c.name = %(name)s AND s.captured_on >= %(desde)s ORDER BY s.captured_on
        """, {"name": elegida, "desde": desde})
        if len(serie) > 1:
            st.line_chart(serie.pivot_table(index="captured_on", columns="variant", values="market_usd"))
        else:
            st.caption("Esta carta necesita mas de un dia de datos para mostrar la grafica.")
