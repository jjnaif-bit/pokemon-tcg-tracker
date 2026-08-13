import os
from datetime import date, timedelta
import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="Toshi Precios Pokemon", page_icon="🔥", layout="wide")

def dsn():
    return st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL"))

@st.cache_data(ttl=1800)
def q(sql, params=None):
    with psycopg2.connect(dsn()) as conn:
        return pd.read_sql(sql, conn, params=params)

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
    st.info("📸 Ya tienes la primera foto de precios. Corre el bot otra vez manana y aqui apareceran las tendencias.")

def tarjetas(df, modo="cambio"):
    for i in range(0, len(df), 4):
        cols = st.columns(4)
        for j, (_, r) in enumerate(df.iloc[i:i+4].iterrows()):
            with cols[j]:
                if r.get("image_small"):
                    st.image(r["image_small"], use_container_width=True)
                st.markdown(f"**{r['name']}**")
                st.caption(f"{r['set_name']} #{r['number']} {r.get('rarity') or ''}")
                if modo == "cambio":
                    signo = "🟢" if (r["cambio_pct"] or 0) >= 0 else "🔴"
                    st.markdown(f"### ${r['precio_fin']:.2f}")
                    st.markdown(f"{signo} {abs(r['cambio_pct']):.1f}% antes ${r['precio_ini']:.2f}")
                else:
                    st.markdown(f"### ${r['market_usd']:.2f}")
                    st.caption(r["variant"])

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
    else: st.write("Ninguna subio en este periodo.")
    st.header("📉 Las que mas bajaron")
    bajaron = movimiento[movimiento["cambio_pct"] < 0].sort_values("cambio_pct").head(8)
    if not bajaron.empty: tarjetas(bajaron)
    else: st.write("Ninguna bajo en este periodo.")

st.header("💎 Las mas valiosas ahora")
caras = q("""
    SELECT DISTINCT ON (c.card_id) c.name, c.set_name, c.number, c.rarity, c.image_small, c.tcgplayer_url, s.market_usd, s.variant
    FROM ptcg_price_snapshots s JOIN ptcg_cards c ON c.card_id = s.card_id
    WHERE s.captured_on = (SELECT MAX(captured_on) FROM ptcg_price_snapshots) AND s.market_usd IS NOT NULL
    ORDER BY c.card_id, s.market_usd DESC
""")
if not caras.empty:
    caras = caras.sort_values("market_usd", ascending=False).head(12)
    tarjetas(caras, modo="valor")

st.header("🇲🇽 Interes de busqueda en Mexico (Google Trends)")
st.caption("Que tanto busca la gente cada termino. 100 = el pico de ese termino en el periodo.")
try:
    trends_terms = q("SELECT DISTINCT t.term, w.label FROM trends_snapshots t JOIN trends_watch_terms w ON w.term = t.term ORDER BY w.label")
    if not trends_terms.empty:
        elegidos_tr = st.multiselect("Terminos a comparar", trends_terms["label"].tolist(), default=trends_terms["label"].tolist()[:4])
        if elegidos_tr:
            terms_sel = trends_terms[trends_terms["label"].isin(elegidos_tr)]["term"].tolist()
            serie_tr = q("""
                SELECT t.trend_date, w.label, t.interest
                FROM trends_snapshots t JOIN trends_watch_terms w ON w.term = t.term
                WHERE t.term = ANY(%(terms)s) ORDER BY t.trend_date
            """, {"terms": terms_sel})
            if not serie_tr.empty:
                st.line_chart(serie_tr.pivot_table(index="trend_date", columns="label", values="interest"))
        st.subheader("Interes promedio del periodo")
        prom = q("""
            SELECT w.label, ROUND(AVG(t.interest),1) AS promedio
            FROM trends_snapshots t JOIN trends_watch_terms w ON w.term = t.term
            GROUP BY w.label ORDER BY promedio DESC
        """)
        st.bar_chart(prom.set_index("label")["promedio"])
    else:
        st.caption("Aun no hay datos de Google Trends.")
except Exception as e:
    st.caption("Google Trends todavia no tiene datos o hubo un error temporal.")

st.header("🏆 Cartas gradeadas — salto de grado")
st.caption("Precio por grado (venta real eBay, USD). El salto PSA9->PSA10 te dice cuanto ganas si sale un 10.")
try:
    graded = q("""
        SELECT c.name, c.set_name, c.image_url,
               MAX(CASE WHEN s.grade='psa10' THEN s.median_usd END) AS psa10,
               MAX(CASE WHEN s.grade='psa9'  THEN s.median_usd END) AS psa9,
               MAX(CASE WHEN s.grade='psa8'  THEN s.median_usd END) AS psa8,
               ROUND(100.0 * (MAX(CASE WHEN s.grade='psa10' THEN s.median_usd END) - MAX(CASE WHEN s.grade='psa9' THEN s.median_usd END)) / NULLIF(MAX(CASE WHEN s.grade='psa9' THEN s.median_usd END),0), 0) AS salto_pct
        FROM graded_price_snapshots s
        JOIN graded_cards c ON c.tcgplayer_id = s.tcgplayer_id
        WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots)
        GROUP BY c.name, c.set_name, c.image_url
        ORDER BY psa10 DESC NULLS LAST
    """)
    if not graded.empty:
        for i in range(0, len(graded), 3):
            cols = st.columns(3)
            for j, (_, r) in enumerate(graded.iloc[i:i+3].iterrows()):
                with cols[j]:
                    if r.get("image_url"): st.image(r["image_url"], width=140)
                    st.markdown(f"**{r['name']}**")
                    st.caption(r["set_name"] or "")
                    p10 = f"${r['psa10']:,.0f}" if r['psa10'] else "-"
                    p9 = f"${r['psa9']:,.0f}" if r['psa9'] else "-"
                    p8 = f"${r['psa8']:,.0f}" if r['psa8'] else "-"
                    st.markdown(f"PSA 10: **{p10}**  \nPSA 9: {p9}  \nPSA 8: {p8}")
                    if r["salto_pct"]:
                        st.markdown(f"🚀 Salto 9→10: **+{r['salto_pct']:.0f}%**")
        st.subheader("Tabla comparativa")
        st.dataframe(graded.rename(columns={"name":"Carta","set_name":"Set","psa10":"PSA 10","psa9":"PSA 9","psa8":"PSA 8","salto_pct":"Salto 9→10 %"}).drop(columns=["image_url"]), use_container_width=True, hide_index=True)
    else:
        st.caption("Aun no hay datos de gradeadas.")
except Exception as e:
    st.caption("Precios gradeados todavia no disponibles.")

import re
st.header("🔎 Buscador por presupuesto, gradeadora y grado")
st.caption("Filtra cartas gradeadas por rango de precio, empresa y grado. Se ordenan por las que mas se venden (ventas eBay).")
try:
    base = q("""
        SELECT c.name, c.set_name, c.image_url, s.grade, s.median_usd, s.sales_count
        FROM graded_price_snapshots s
        JOIN graded_cards c ON c.tcgplayer_id = s.tcgplayer_id
        WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots)
          AND s.median_usd IS NOT NULL
    """)
    if base.empty:
        st.caption("Aun no hay datos de gradeadas.")
    else:
        def separar(g):
            if g == "ungraded": return ("Ungraded", "-")
            m = re.match(r"([a-z]+)(\d+)", str(g))
            if not m: return (str(g).upper(), "-")
            emp, num = m.group(1).upper(), m.group(2)
            if len(num) == 2 and num != "10": num = num[0] + "." + num[1]
            return (emp, num)
        base[["empresa","num_grado"]] = base["grade"].apply(lambda g: pd.Series(separar(g)))

        c1, c2, c3 = st.columns(3)
        empresas = sorted(base["empresa"].unique().tolist())
        emp_sel = c1.selectbox("Gradeadora", empresas, index=empresas.index("PSA") if "PSA" in empresas else 0)
        grados_disp = sorted(base[base["empresa"]==emp_sel]["num_grado"].unique().tolist(), reverse=True)
        grado_sel = c2.selectbox("Grado", grados_disp)
        rango = c3.slider("Presupuesto USD", 0, int(base["median_usd"].max())+1, (10, 50))

        filtro = base[(base["empresa"]==emp_sel) & (base["num_grado"]==grado_sel) & (base["median_usd"]>=rango[0]) & (base["median_usd"]<=rango[1])]
        filtro = filtro.sort_values("sales_count", ascending=False, na_position="last")

        st.markdown(f"**{len(filtro)} cartas** con {emp_sel} {grado_sel} entre ${rango[0]} y ${rango[1]}")
        if filtro.empty:
            st.info("Ninguna carta cae en ese rango. Prueba ampliar el presupuesto o cambiar el grado.")
        else:
            st.dataframe(
                filtro[["name","set_name","median_usd","sales_count"]].rename(columns={"name":"Carta","set_name":"Set","median_usd":f"Precio {emp_sel} {grado_sel} USD","sales_count":"Ventas eBay"}),
                use_container_width=True, hide_index=True
            )
except Exception as e:
    st.caption("Buscador todavia no disponible.")
