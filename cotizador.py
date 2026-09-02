"""
Cotizador Toshi Collectibles
----------------------------
Selecciona cartas y calcula al instante: costo total, precio de la pagina,
valor de mercado (Card Ladder) y hasta donde se puede negociar sin perder margen.

Lee la hoja de Google directamente con una cuenta de servicio (la hoja NO se
publica en la web).
"""

import re

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

MARGEN_OBJETIVO = 0.35          # 35% -> divisor 0.65
DIVISOR = 1 - MARGEN_OBJETIVO
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

st.set_page_config(page_title="Cotizador Toshi", page_icon="🃏", layout="wide")


# --------------------------------------------------------------------------
# Acceso
# --------------------------------------------------------------------------
def pedir_password() -> bool:
    """Muestra la pantalla de acceso. Devuelve True si la clave es correcta."""
    if st.session_state.get("acceso_ok"):
        return True

    st.title("🃏 Cotizador Toshi")
    clave = st.text_input("Contraseña", type="password")
    if not clave:
        st.stop()
    if clave != st.secrets["app"]["password"]:
        st.error("Contraseña incorrecta.")
        st.stop()

    st.session_state["acceso_ok"] = True
    return True


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------
def a_numero(valor) -> float:
    """Convierte '$1,234.56' o '1.234,56' a float. Devuelve 0.0 si no se puede."""
    if valor is None:
        return 0.0
    texto = str(valor).strip()
    if not texto:
        return 0.0
    texto = re.sub(r"[^\d,.\-]", "", texto)
    if "," in texto and "." in texto:
        texto = texto.replace(",", "")          # 1,234.56
    elif texto.count(",") == 1 and texto.count(".") == 0:
        texto = texto.replace(",", ".")         # 1234,56
    else:
        texto = texto.replace(",", "")
    try:
        return float(texto)
    except ValueError:
        return 0.0


@st.cache_data(ttl=300, show_spinner="Leyendo la hoja...")
def cargar_inventario() -> pd.DataFrame:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    hoja = gspread.authorize(creds).open_by_key(st.secrets["app"]["sheet_id"])
    filas = hoja.sheet1.get_all_values()

    # El encabezado real esta en la fila 2 (la 1 son notas sueltas)
    encabezado = [c.strip() for c in filas[1]]
    datos = pd.DataFrame(filas[2:], columns=encabezado)

    def col(*nombres):
        for n in nombres:
            for c in datos.columns:
                if c.lower().strip() == n.lower():
                    return c
        return None

    c_prod = col("Producto")
    c_costo = col("Costo Total")
    c_shop = col("Precio Shopify")
    c_cl = col("CL Value MXN")
    c_cl_usd = col("CL Value USD")
    c_disp = col("Disponibilidad")

    tabla = pd.DataFrame({
        "Carta": datos[c_prod].astype(str).str.strip(),
        "Costo": datos[c_costo].map(a_numero) if c_costo else 0.0,
        "Precio pagina": datos[c_shop].map(a_numero) if c_shop else 0.0,
        "CL Value MXN": datos[c_cl].map(a_numero) if c_cl else 0.0,
        "CL Value USD": datos[c_cl_usd].map(a_numero) if c_cl_usd else 0.0,
        "Estado": datos[c_disp].astype(str).str.strip() if c_disp else "",
    })

    tabla = tabla[tabla["Carta"] != ""]
    tabla = tabla[tabla["Costo"] > 0]
    # Si no hay precio en la pagina, usa el piso calculado
    sin_precio = tabla["Precio pagina"] <= 0
    tabla.loc[sin_precio, "Precio pagina"] = (
        tabla.loc[sin_precio, "Costo"] / DIVISOR
    ).round(0)
    return tabla.reset_index(drop=True)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
pedir_password()

st.title("🃏 Cotizador Toshi")
st.caption("Selecciona las cartas y revisa hasta dónde puedes negociar.")

try:
    inv = cargar_inventario()
except Exception as err:  # noqa: BLE001
    st.error(f"No se pudo leer la hoja: {err}")
    st.stop()

col_izq, col_der = st.columns([3, 2], gap="large")

with col_izq:
    st.subheader("Cartas")

    filtro = st.text_input("Buscar", placeholder="Charizard, PSA 10, Umbreon...")
    solo_disponibles = st.checkbox("Solo disponibles en Mérida", value=False)

    vista = inv.copy()
    if filtro:
        vista = vista[vista["Carta"].str.contains(filtro, case=False, na=False)]
    if solo_disponibles:
        vista = vista[vista["Estado"].str.upper().str.contains("MÉRIDA|MERIDA", na=False)]

    vista.insert(0, "Elegir", False)
    editada = st.data_editor(
        vista,
        hide_index=True,
        use_container_width=True,
        height=430,
        column_config={
            "Elegir": st.column_config.CheckboxColumn(required=True, width="small"),
            "Carta": st.column_config.TextColumn(disabled=True, width="large"),
            "Costo": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
            "Precio pagina": st.column_config.NumberColumn(disabled=True, format="$%.0f"),
            "CL Value MXN": st.column_config.NumberColumn(disabled=True, format="$%.0f"),
            "CL Value USD": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
            "Estado": st.column_config.TextColumn(disabled=True, width="small"),
        },
    )

elegidas = editada[editada["Elegir"]]

with col_der:
    st.subheader("Cotización")

    if elegidas.empty:
        st.info("Marca una o más cartas para ver los números.")
        st.stop()

    costo = float(elegidas["Costo"].sum())
    lista = float(elegidas["Precio pagina"].sum())
    mercado = float(elegidas["CL Value MXN"].sum())
    piso = costo / DIVISOR

    st.metric("Cartas seleccionadas", len(elegidas))

    a, b, c = st.columns(3)
    a.metric("Costo total", f"${costo:,.0f}")
    b.metric("Precio de lista", f"${lista:,.0f}")
    c.metric("Mercado (CL)", f"${mercado:,.0f}" if mercado else "—")

    st.divider()
    st.markdown("**Negociación**")

    desc = st.slider("Descuento sobre el precio de lista", 0, 40, 10, step=1)
    final = lista * (1 - desc / 100)
    utilidad = final - costo
    margen = (utilidad / final * 100) if final else 0.0

    d, e, f = st.columns(3)
    d.metric("Precio ofrecido", f"${final:,.0f}", f"-{desc}%")
    e.metric("Utilidad", f"${utilidad:,.0f}")
    f.metric("Margen", f"{margen:.0f}%")

    if final < piso:
        falta = piso - final
        st.error(
            f"Por debajo de tu piso de ${piso:,.0f} "
            f"(margen objetivo {MARGEN_OBJETIVO:.0%}). Te faltan ${falta:,.0f}."
        )
    elif margen < 20:
        st.warning(f"Margen bajo ({margen:.0f}%). Tu piso es ${piso:,.0f}.")
    else:
        st.success(f"Margen sano. Puedes bajar hasta ${piso:,.0f}.")

    st.caption(
        f"Descuento máximo sin romper el piso: "
        f"{max(0, (1 - piso / lista) * 100):.0f}%" if lista else ""
    )

    if mercado:
        dif = (final - mercado) / mercado * 100
        st.caption(f"El precio ofrecido queda {dif:+.0f}% respecto al mercado.")

    st.divider()
    resumen = elegidas[["Carta", "Costo", "Precio pagina", "CL Value MXN"]].copy()
    st.download_button(
        "Descargar cotización (CSV)",
        resumen.to_csv(index=False).encode("utf-8"),
        file_name="cotizacion_toshi.csv",
        mime="text/csv",
        use_container_width=True,
    )
