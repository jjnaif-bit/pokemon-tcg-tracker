import os, re
from datetime import date, timedelta
import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="Toshi - Radar Pokemon", page_icon="🔥", layout="wide")

def dsn():
    return st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL"))

@st.cache_data(ttl=1800)
def q(sql, params=None):
    with psycopg2.connect(dsn()) as conn:
        return pd.read_sql(sql, conn, params=params)

st.title("🔥 Toshi Collectibles — Radar de mercado Pokemon")
st.caption("Cartas mas vendidas del mercado + precios gradeados PSA/CGC/BGS (venta real eBay, USD)")

st.header("🔎 Buscador — que comprar")
st.caption("Filtra por presupuesto, gradeadora y grado. Ordenadas por las que mas se venden.")
try:
    base = q("""
        SELECT c.name, c.set_name, c.image_url, s.grade, s.median_usd, s.sales_count
        FROM graded_price_snapshots s
        JOIN graded_cards c ON c.tcgplayer_id = s.tcgplayer_id
        WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots)
          AND s.median_usd IS NOT NULL
    """)
    if base.empty:
        st.info("Aun no hay datos. Corre el modulo de mercado primero.")
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
        tope = int(base["median_usd"].max()) + 1
        rango = c3.slider("Presupuesto USD", 0, tope, (10, min(100, tope)))
        filtro = base[(base["empresa"]==emp_sel) & (base["num_grado"]==grado_sel) & (base["median_usd"]>=rango[0]) & (base["median_usd"]<=rango[1])].sort_values("sales_count", ascending=False, na_position="last")
        st.markdown(f"**{len(filtro)} cartas** con {emp_sel} {grado_sel} entre ${rango[0]} y ${rango[1]}")
        if filtro.empty:
            st.info("Ninguna en ese rango. Amplia el presupuesto o cambia el grado.")
        else:
            st.dataframe(filtro[["name","set_name","median_usd","sales_count"]].rename(columns={"name":"Carta","set_name":"Set","median_usd":f"Precio {emp_sel} {grado_sel} USD","sales_count":"Ventas eBay"}), use_container_width=True, hide_index=True)
except Exception as e:
    st.caption("Buscador no disponible aun.")

st.header("🔥 Mas vendidas del mercado")
st.caption("Las cartas que mas se mueven ahora, con precio por grado. El salto 9->10 te dice cuanto ganas si sale un 10.")
try:
    graded = q("""
        SELECT c.name, c.set_name, c.image_url,
               MAX(CASE WHEN s.grade='psa10' THEN s.median_usd END) AS psa10,
               MAX(CASE WHEN s.grade='psa9'  THEN s.median_usd END) AS psa9,
               MAX(CASE WHEN s.grade='psa8'  THEN s.median_usd END) AS psa8,
               MAX(s.sales_count) AS ventas,
               ROUND(100.0 * (MAX(CASE WHEN s.grade='psa10' THEN s.median_usd END) - MAX(CASE WHEN s.grade='psa9' THEN s.median_usd END)) / NULLIF(MAX(CASE WHEN s.grade='psa9' THEN s.median_usd END),0), 0) AS salto_pct
        FROM graded_price_snapshots s
        JOIN graded_cards c ON c.tcgplayer_id = s.tcgplayer_id
        WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots)
        GROUP BY c.name, c.set_name, c.image_url
        ORDER BY ventas DESC NULLS LAST
    """)
    if not graded.empty:
        for i in range(0, min(len(graded), 12), 3):
            cols = st.columns(3)
            for j, (_, r) in enumerate(graded.iloc[i:i+3].iterrows()):
                with cols[j]:
                    if r.get("image_url"): st.image(r["image_url"], width=140)
                    st.markdown(f"**{r['name']}**")
                    st.caption(r["set_name"] or "")
                    p10 = f"${r['psa10']:,.0f}" if pd.notna(r['psa10']) else "-"
                    p9 = f"${r['psa9']:,.0f}" if pd.notna(r['psa9']) else "-"
                    p8 = f"${r['psa8']:,.0f}" if pd.notna(r['psa8']) else "-"
                    st.markdown(f"PSA 10: **{p10}**  \nPSA 9: {p9}  \nPSA 8: {p8}")
                    if pd.notna(r["salto_pct"]):
                        st.markdown(f"🚀 Salto 9→10: **+{r['salto_pct']:.0f}%**")
        st.subheader("Tabla completa")
        tabla = graded.rename(columns={"name":"Carta","set_name":"Set","psa10":"PSA 10","psa9":"PSA 9","psa8":"PSA 8","salto_pct":"Salto 9→10 %","ventas":"Ventas eBay"}).drop(columns=["image_url"])
        st.dataframe(tabla, use_container_width=True, hide_index=True)
    else:
        st.caption("Aun no hay datos de gradeadas.")
except Exception as e:
    st.caption("Datos de mercado no disponibles aun.")

st.header("💎 TCGplayer — cartas mas valiosas")
try:
    caras = q("""
        SELECT DISTINCT ON (c.card_id) c.name, c.set_name, c.number, c.rarity, c.image_small, s.market_usd, s.variant
        FROM ptcg_price_snapshots s JOIN ptcg_cards c ON c.card_id = s.card_id
        WHERE s.captured_on = (SELECT MAX(captured_on) FROM ptcg_price_snapshots) AND s.market_usd IS NOT NULL
        ORDER BY c.card_id, s.market_usd DESC
    """)
    if not caras.empty:
        caras = caras.sort_values("market_usd", ascending=False).head(9)
        for i in range(0, len(caras), 3):
            cols = st.columns(3)
            for j, (_, r) in enumerate(caras.iloc[i:i+3].iterrows()):
                with cols[j]:
                    if r.get("image_small"): st.image(r["image_small"], width=130)
                    st.markdown(f"**{r['name']}**")
                    st.caption(f"{r['set_name']} #{r['number']} · {r['rarity'] or ''}")
                    st.markdown(f"### ${r['market_usd']:.2f}")
                    st.caption(r["variant"])
except Exception as e:
    st.caption("TCGplayer no disponible.")

st.header("📈 TCGplayer — movimiento de precio")
dias = st.slider("Ventana (dias)", 2, 180, 30)
desde = date.today() - timedelta(days=dias)
try:
    fechas = q("SELECT DISTINCT captured_on FROM ptcg_price_snapshots ORDER BY captured_on")
    if len(fechas) < 2:
        st.info("Necesito 2+ dias de datos TCGplayer para ver tendencias.")
    else:
        mov = q("""
            WITH v AS (
                SELECT card_id, variant, MIN(captured_on) AS ini, MAX(captured_on) AS fin
                FROM ptcg_price_snapshots WHERE captured_on >= %(d)s AND variant='holofoil'
                GROUP BY card_id, variant HAVING MIN(captured_on) <> MAX(captured_on)
            )
            SELECT c.name, c.set_name,
                   pi.market_usd AS ini, pf.market_usd AS fin,
                   ROUND(100.0*(pf.market_usd-pi.market_usd)/NULLIF(pi.market_usd,0),1) AS pct
            FROM v JOIN ptcg_cards c ON c.card_id=v.card_id
            JOIN ptcg_price_snapshots pi ON pi.card_id=v.card_id AND pi.variant=v.variant AND pi.captured_on=v.ini
            JOIN ptcg_price_snapshots pf ON pf.card_id=v.card_id AND pf.variant=v.variant AND pf.captured_on=v.fin
            WHERE pi.market_usd >= 1 ORDER BY pct DESC NULLS LAST
        """, {"d": desde})
        suben = mov[mov["pct"]>0].head(10)
        if not suben.empty:
            st.subheader("📈 Subieron")
            st.dataframe(suben.rename(columns={"name":"Carta","set_name":"Set","ini":"Antes USD","fin":"Ahora USD","pct":"Cambio %"}), use_container_width=True, hide_index=True)
        bajan = mov[mov["pct"]<0].sort_values("pct").head(10)
        if not bajan.empty:
            st.subheader("📉 Bajaron")
            st.dataframe(bajan.rename(columns={"name":"Carta","set_name":"Set","ini":"Antes USD","fin":"Ahora USD","pct":"Cambio %"}), use_container_width=True, hide_index=True)
except Exception as e:
    st.caption("Movimiento no disponible.")

st.header("🇲🇽 Interes de busqueda en Mexico (Google Trends)")
st.caption("Que tanto busca la gente cada termino. 100 = pico de ese termino en el periodo.")
try:
    tt = q("SELECT DISTINCT t.term, w.label FROM trends_snapshots t JOIN trends_watch_terms w ON w.term=t.term ORDER BY w.label")
    if not tt.empty:
        eleg = st.multiselect("Terminos", tt["label"].tolist(), default=tt["label"].tolist()[:4])
        if eleg:
            terms = tt[tt["label"].isin(eleg)]["term"].tolist()
            serie = q("SELECT t.trend_date, w.label, t.interest FROM trends_snapshots t JOIN trends_watch_terms w ON w.term=t.term WHERE t.term = ANY(%(t)s) ORDER BY t.trend_date", {"t": terms})
            if not serie.empty:
                st.line_chart(serie.pivot_table(index="trend_date", columns="label", values="interest"))
        prom = q("SELECT w.label, ROUND(AVG(t.interest),1) AS p FROM trends_snapshots t JOIN trends_watch_terms w ON w.term=t.term GROUP BY w.label ORDER BY p DESC")
        st.bar_chart(prom.set_index("label")["p"])
    else:
        st.caption("Aun no hay datos de Google Trends.")
except Exception as e:
    st.caption("Google Trends no disponible.")
