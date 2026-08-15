import os, re
from datetime import date, timedelta
import pandas as pd
import psycopg2
import requests as _rq
import streamlit as st

st.set_page_config(page_title="Toshi - Radar Pokemon", page_icon="🔥", layout="wide")

st.markdown("""
<style>
    .stApp { background: #faf8f5; }
    h1 { color: #1a1a1a !important; font-weight: 800 !important; letter-spacing: -0.5px; }
    h2, h3 { color: #8a6d1f !important; font-weight: 700 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 2px solid #e8e0d0; }
    .stTabs [data-baseweb="tab"] { font-weight: 600; color: #6b5d3f; padding: 8px 16px; }
    .stTabs [aria-selected="true"] { color: #b8860b !important; }
    .stButton>button { background: #1a1a1a; color: #d4af37; border: none; font-weight: 600; }
    .stDataFrame { border: 1px solid #e8e0d0; border-radius: 10px; }
    [data-testid="stCaptionContainer"] { color: #9a8d6f !important; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

def dsn():
    return st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL"))

@st.cache_data(ttl=1800)
def q(sql, params=None):
    with psycopg2.connect(dsn()) as conn:
        return pd.read_sql(sql, conn, params=params)

def guardar_busqueda(d):
    """Guarda una carta buscada en la base, para el archivo historico."""
    try:
        tid = str(d.get("tcgPlayerId") or d.get("id") or "")
        if not tid:
            return
        img = d.get("imageCdnUrl400") or d.get("imageCdnUrl200")
        mk = (d.get("prices") or {}).get("market")
        with psycopg2.connect(dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO graded_cards (tcgplayer_id, name, set_name, number, rarity, image_url, market_usd)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tcgplayer_id) DO UPDATE SET name=EXCLUDED.name, set_name=EXCLUDED.set_name,
                        rarity=EXCLUDED.rarity, image_url=EXCLUDED.image_url, market_usd=EXCLUDED.market_usd, last_seen=now()
                """, (tid, d.get("name"), d.get("setName"), d.get("cardNumber"), d.get("rarity"), img,
                      round(float(mk),2) if mk else None))
                sbg = (d.get("ebay") or {}).get("salesByGrade") or {}
                for g, v in sbg.items():
                    if not isinstance(v, dict): continue
                    gr = g.lower().replace(".","").replace("_","")
                    def n(x):
                        try: return round(float(x),2)
                        except: return None
                    cur.execute("""
                        INSERT INTO graded_price_snapshots (tcgplayer_id, grade, median_usd, average_usd, sales_count)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (tcgplayer_id, captured_on, grade) DO UPDATE SET
                            median_usd=EXCLUDED.median_usd, average_usd=EXCLUDED.average_usd, sales_count=EXCLUDED.sales_count
                    """, (tid, gr, n(v.get("medianPrice")), n(v.get("averagePrice")), v.get("count")))
            conn.commit()
    except Exception:
        pass

def sep_grade(g):
    if g == "ungraded": return ("Ungraded", "-")
    m = re.match(r"([a-z]+)(\d+)", str(g))
    if not m: return (str(g).upper(), "-")
    emp, num = m.group(1).upper(), m.group(2)
    if len(num) == 2 and num != "10": num = num[0] + "." + num[1]
    return (emp, num)

import os as _os
_logo = _os.path.join(_os.path.dirname(__file__), "logo.png")
_hc = st.columns([1, 9])
with _hc[0]:
    if _os.path.exists(_logo):
        st.image(_logo, width=90)
with _hc[1]:
    st.markdown("<h1 style='margin-bottom:0; padding-top:22px; margin-left:-30px;'>Toshi Collectibles</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9a8d6f; margin-top:0; margin-left:-30px; font-size:15px;'>Radar de mercado Pokemon</p>", unsafe_allow_html=True)
st.caption("Cartas mas vendidas + precios gradeados PSA/CGC/BGS (venta real eBay, USD)")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔍 Buscar carta", "🎯 Que comprar", "🔥 Mas vendidas", "💎 TCGplayer", "🇲🇽 Google Trends", "📅 Historico"])

with tab1:
    st.header("Buscar cualquier carta del catalogo")
    st.caption("Escribe el nombre. Consulta precios por grado al momento.")
    cbus1, cbus2 = st.columns([3, 1])
    busqueda = cbus1.text_input("Nombre de la carta", placeholder="ej. Charizard ex 151, Umbreon VMAX, Shibuya Pikachu...")
    idioma = cbus2.selectbox("Idioma", ["Ingles", "Japones"])
    if busqueda:
        api_key = st.secrets.get("PPT_API_KEY", os.environ.get("PPT_API_KEY"))
        if not api_key:
            st.error("Falta PPT_API_KEY en Secrets de Streamlit.")
        else:
            with st.spinner("Buscando..."):
                try:
                    r = _rq.get("https://www.pokemonpricetracker.com/api/v2/cards",
                                params={"search": busqueda, "limit": 5, "includeEbay": "true", **({"language": "japanese"} if idioma == "Japones" else {})},
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
                    if r.status_code != 200:
                        st.error(f"Error API (HTTP {r.status_code}).")
                    else:
                        data = r.json().get("data")
                        resultados = data if isinstance(data, list) else ([data] if data else [])
                        if not resultados:
                            st.warning("No se encontro esa carta.")
                        for d in resultados:
                            guardar_busqueda(d)
                            st.divider()
                            cc = st.columns([1, 2])
                            with cc[0]:
                                img = d.get("imageCdnUrl400") or d.get("imageCdnUrl200")
                                if img: st.image(img, width=160)
                            with cc[1]:
                                st.markdown(f"### {d.get('name')}")
                                st.caption(f"{d.get('setName') or ''} #{d.get('cardNumber') or ''} · {d.get('rarity') or ''}")
                                mk = (d.get('prices') or {}).get('market')
                                if mk: st.markdown(f"TCGplayer (cruda): **${mk:,.2f}**")
                                sbg = (d.get("ebay") or {}).get("salesByGrade") or {}
                                filas = []
                                for g, v in sbg.items():
                                    if not isinstance(v, dict): continue
                                    emp, num = sep_grade(g)
                                    filas.append({"Gradeadora": emp, "Grado": num, "Precio mediano USD": v.get("medianPrice"), "Ventas": v.get("count")})
                                if filas:
                                    st.dataframe(pd.DataFrame(filas).sort_values("Precio mediano USD", ascending=False), use_container_width=True, hide_index=True)
                                else:
                                    st.caption("Sin datos de ventas gradeadas.")
                except Exception as e:
                    st.error(f"Error: {str(e)[:150]}")

with tab2:
    st.header("Que comprar — filtro por presupuesto")
    st.caption("Filtra por presupuesto, gradeadora y grado. Ordenadas por ventas.")
    try:
        base = q("""
            SELECT c.name, c.set_name, s.grade, s.median_usd, s.sales_count
            FROM graded_price_snapshots s JOIN graded_cards c ON c.tcgplayer_id = s.tcgplayer_id
            WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots) AND s.median_usd IS NOT NULL
        """)
        if base.empty:
            st.info("Aun no hay datos.")
        else:
            base[["empresa","num_grado"]] = base["grade"].apply(lambda g: pd.Series(sep_grade(g)))
            c1, c2, c3 = st.columns(3)
            empresas = sorted(base["empresa"].unique().tolist())
            emp_sel = c1.selectbox("Gradeadora", empresas, index=empresas.index("PSA") if "PSA" in empresas else 0)
            grados_disp = sorted(base[base["empresa"]==emp_sel]["num_grado"].unique().tolist(), reverse=True)
            grado_sel = c2.selectbox("Grado", grados_disp)
            cmin, cmax = c3.columns(2)
            precio_min = cmin.number_input("Min USD", min_value=1, value=1, step=5)
            precio_max = cmax.number_input("Max USD", min_value=1, value=100, step=5)
            filtro = base[(base["empresa"]==emp_sel) & (base["num_grado"]==grado_sel) & (base["median_usd"]>=precio_min) & (base["median_usd"]<=precio_max)].sort_values("sales_count", ascending=False, na_position="last")
            st.markdown(f"**{len(filtro)} cartas** con {emp_sel} {grado_sel} entre ${precio_min} y ${precio_max}")
            if not filtro.empty:
                st.dataframe(filtro[["name","set_name","median_usd","sales_count"]].rename(columns={"name":"Carta","set_name":"Set","median_usd":f"Precio {emp_sel} {grado_sel}","sales_count":"Ventas eBay"}), use_container_width=True, hide_index=True)
            else:
                st.info("Ninguna en ese rango.")
    except Exception as e:
        st.caption("Filtro no disponible.")

with tab3:
    st.header("Mas vendidas del mercado")
    st.caption("Las que mas se mueven, con precio por grado. Salto 9->10 = cuanto ganas si sale un 10.")
    try:
        graded = q("""
            SELECT c.name, c.set_name, c.image_url,
                   MAX(CASE WHEN s.grade='psa10' THEN s.median_usd END) AS psa10,
                   MAX(CASE WHEN s.grade='psa9'  THEN s.median_usd END) AS psa9,
                   MAX(CASE WHEN s.grade='psa8'  THEN s.median_usd END) AS psa8,
                   MAX(s.sales_count) AS ventas,
                   ROUND(100.0 * (MAX(CASE WHEN s.grade='psa10' THEN s.median_usd END) - MAX(CASE WHEN s.grade='psa9' THEN s.median_usd END)) / NULLIF(MAX(CASE WHEN s.grade='psa9' THEN s.median_usd END),0), 0) AS salto_pct
            FROM graded_price_snapshots s JOIN graded_cards c ON c.tcgplayer_id = s.tcgplayer_id
            WHERE s.captured_on = (SELECT MAX(captured_on) FROM graded_price_snapshots)
            GROUP BY c.name, c.set_name, c.image_url ORDER BY ventas DESC NULLS LAST
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
                        if pd.notna(r["salto_pct"]): st.markdown(f"🚀 Salto 9→10: **+{r['salto_pct']:.0f}%**")
            st.subheader("Tabla completa")
            st.dataframe(graded.rename(columns={"name":"Carta","set_name":"Set","psa10":"PSA 10","psa9":"PSA 9","psa8":"PSA 8","salto_pct":"Salto 9→10 %","ventas":"Ventas eBay"}).drop(columns=["image_url"]), use_container_width=True, hide_index=True)
        else:
            st.caption("Aun no hay datos.")
    except Exception as e:
        st.caption("Datos no disponibles.")

with tab4:
    st.header("TCGplayer — cartas mas valiosas")
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
                        st.caption(f"{r['set_name']} #{r['number']}")
                        st.markdown(f"### ${r['market_usd']:.2f}")
        st.divider()
        st.subheader("Movimiento de precio")
        dias = st.slider("Ventana (dias)", 2, 180, 30)
        desde = date.today() - timedelta(days=dias)
        fechas = q("SELECT DISTINCT captured_on FROM ptcg_price_snapshots ORDER BY captured_on")
        if len(fechas) < 2:
            st.info("Necesito 2+ dias de datos para tendencias.")
        else:
            mov = q("""
                WITH v AS (SELECT card_id, variant, MIN(captured_on) AS ini, MAX(captured_on) AS fin FROM ptcg_price_snapshots WHERE captured_on >= %(d)s AND variant='holofoil' GROUP BY card_id, variant HAVING MIN(captured_on) <> MAX(captured_on))
                SELECT c.name, c.set_name, pi.market_usd AS ini, pf.market_usd AS fin, ROUND(100.0*(pf.market_usd-pi.market_usd)/NULLIF(pi.market_usd,0),1) AS pct
                FROM v JOIN ptcg_cards c ON c.card_id=v.card_id
                JOIN ptcg_price_snapshots pi ON pi.card_id=v.card_id AND pi.variant=v.variant AND pi.captured_on=v.ini
                JOIN ptcg_price_snapshots pf ON pf.card_id=v.card_id AND pf.variant=v.variant AND pf.captured_on=v.fin
                WHERE pi.market_usd >= 1 ORDER BY pct DESC NULLS LAST
            """, {"d": desde})
            suben = mov[mov["pct"]>0].head(10)
            if not suben.empty:
                st.markdown("**📈 Subieron**")
                st.dataframe(suben.rename(columns={"name":"Carta","set_name":"Set","ini":"Antes","fin":"Ahora","pct":"Cambio %"}), use_container_width=True, hide_index=True)
            bajan = mov[mov["pct"]<0].sort_values("pct").head(10)
            if not bajan.empty:
                st.markdown("**📉 Bajaron**")
                st.dataframe(bajan.rename(columns={"name":"Carta","set_name":"Set","ini":"Antes","fin":"Ahora","pct":"Cambio %"}), use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption("TCGplayer no disponible.")

with tab5:
    st.header("Interes de busqueda en Mexico")
    st.caption("100 = pico de ese termino en el periodo.")
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


with tab6:
    st.header("Historico de precios")
    st.caption("Evolucion de precio por grado de cualquier carta en tu base. Cada busqueda que haces alimenta este archivo.")
    try:
        cartas_hist = q("""
            SELECT DISTINCT c.tcgplayer_id, c.name, c.set_name
            FROM graded_cards c
            JOIN graded_price_snapshots s ON s.tcgplayer_id = c.tcgplayer_id
            GROUP BY c.tcgplayer_id, c.name, c.set_name
            HAVING COUNT(DISTINCT s.captured_on) >= 1
            ORDER BY c.name
        """)
        if cartas_hist.empty:
            st.info("Aun no hay cartas en el archivo. Busca cartas en la pestaña 'Buscar carta' y se iran guardando aqui.")
        else:
            cartas_hist["etiqueta"] = cartas_hist["name"] + " (" + cartas_hist["set_name"].fillna("") + ")"
            elegida = st.selectbox("Elige una carta", cartas_hist["etiqueta"].tolist())
            tid = cartas_hist[cartas_hist["etiqueta"]==elegida]["tcgplayer_id"].iloc[0]
            serie = q("""
                SELECT captured_on, grade, median_usd
                FROM graded_price_snapshots
                WHERE tcgplayer_id = %(t)s AND median_usd IS NOT NULL
                ORDER BY captured_on
            """, {"t": tid})
            if serie.empty:
                st.caption("Sin datos para esta carta.")
            else:
                dias_hist = serie["captured_on"].nunique()
                st.markdown(f"**{dias_hist} dia(s)** de datos guardados para esta carta.")
                grados_hist = sorted(serie["grade"].unique().tolist())
                sel_grados = st.multiselect("Grados a mostrar", grados_hist, default=[g for g in ["psa10","psa9"] if g in grados_hist] or grados_hist[:3])
                if sel_grados:
                    filtrada = serie[serie["grade"].isin(sel_grados)]
                    if filtrada["captured_on"].nunique() > 1:
                        st.line_chart(filtrada.pivot_table(index="captured_on", columns="grade", values="median_usd"))
                    else:
                        st.info("Necesitas al menos 2 dias distintos para ver la grafica. Vuelve manana o pasado cuando el bot haya guardado mas fotos.")
                    st.subheader("Datos guardados")
                    tabla_h = filtrada.pivot_table(index="captured_on", columns="grade", values="median_usd")
                    st.dataframe(tabla_h, use_container_width=True)
    except Exception as e:
        st.caption("Historico no disponible.")
