"""
App de Retenciones IVA / ISLR — Venezuela
Streamlit + Supabase (multi-tenant)
v1.0
"""

import streamlit as st
import pandas as pd
import hashlib
import io
import os
from datetime import datetime, date
from supabase import create_client, Client

# ── Configuración ──────────────────────────────────────────────
st.set_page_config(
    page_title="Retenciones IVA / ISLR",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")


@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { max-width: 1100px; padding-top: 1.5rem; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #1a472a 0%, #0d2818 100%); }
    [data-testid="stSidebar"] * { color: #e0e0e0 !important; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label { color: #a5d6a7 !important; }
    div.stButton > button {
        background: linear-gradient(135deg, #2e7d32, #1b5e20);
        color: white; border: none; border-radius: 8px;
        padding: 0.5rem 1.5rem; font-weight: 600;
    }
    div.stButton > button:hover { background: linear-gradient(135deg, #388e3c, #2e7d32); }
    .metric-card {
        background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
        border-radius: 12px; padding: 1.2rem; text-align: center;
        border-left: 4px solid #2e7d32;
    }
    .metric-card h3 { margin: 0; font-size: 0.85rem; color: #555; }
    .metric-card h1 { margin: 0; font-size: 1.6rem; color: #1b5e20; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════════════════════════
def login_page():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("## 📋 Retenciones IVA / ISLR")
        st.markdown("*Sistema de gestión de retenciones fiscales*")
        st.divider()
        username = st.text_input("👤 Usuario")
        password = st.text_input("🔑 Contraseña", type="password")
        if st.button("Iniciar Sesión", use_container_width=True):
            if not username or not password:
                st.error("Ingrese usuario y contraseña")
                return
            sb = get_supabase()
            pw_hash = hash_password(password)
            res = sb.table("usuarios").select("*").eq("username", username).eq("password_hash", pw_hash).eq("activo", True).execute()
            if res.data:
                u = res.data[0]
                st.session_state["user"] = u
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("Credenciales inválidas")


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
def empresa_id():
    return st.session_state["user"].get("empresa_id")


def es_admin():
    return st.session_state["user"]["rol"] == "admin"


def fmt(n):
    """Formato venezolano: 1.234,56"""
    if n is None:
        return "0,00"
    s = f"{abs(n):,.2f}"
    # swap , and .
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    if n < 0:
        s = "-" + s
    return s


def generar_numero_comprobante(sb, emp_id, tipo, fecha):
    """Genera número secuencial YYYYMM00000NNN."""
    anio = fecha.year
    mes = fecha.month
    # Buscar secuencia existente
    res = sb.table("secuencias_comprobantes").select("*").eq("empresa_id", emp_id).eq("tipo", tipo).eq("anio", anio).eq("mes", mes).execute()
    if res.data:
        seq = res.data[0]
        nuevo = seq["ultimo_numero"] + 1
        sb.table("secuencias_comprobantes").update({"ultimo_numero": nuevo}).eq("id", seq["id"]).execute()
    else:
        nuevo = 1
        sb.table("secuencias_comprobantes").insert({
            "empresa_id": emp_id, "tipo": tipo,
            "anio": anio, "mes": mes, "ultimo_numero": nuevo
        }).execute()
    return f"{anio}{mes:02d}{nuevo:010d}"


# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════
def page_dashboard():
    st.markdown("## 📊 Dashboard")
    sb = get_supabase()
    eid = empresa_id()
    if not eid:
        st.info("Panel de administrador. Seleccione una sección del menú.")
        return

    # Obtener datos de la empresa
    emp = sb.table("empresas").select("*").eq("id", eid).execute().data
    if emp:
        st.markdown(f"**{emp[0]['nombre']}** — RIF: {emp[0]['rif']}")
    st.divider()

    hoy = date.today()
    mes_actual = hoy.month
    anio_actual = hoy.year

    # Contadores
    facturas = sb.table("facturas").select("id, total_compra, monto_iva, created_at").eq("empresa_id", eid).execute().data or []
    ret_iva = sb.table("retenciones_iva").select("id, monto_retenido, created_at").eq("empresa_id", eid).execute().data or []
    ret_islr = sb.table("retenciones_islr").select("id, monto_retenido, created_at").eq("empresa_id", eid).execute().data or []
    provs = sb.table("proveedores").select("id").eq("empresa_id", eid).execute().data or []

    # Filtrar mes actual
    facturas_mes = [f for f in facturas if f.get("created_at", "")[:7] == f"{anio_actual}-{mes_actual:02d}"]
    ret_iva_mes = [r for r in ret_iva if r.get("created_at", "")[:7] == f"{anio_actual}-{mes_actual:02d}"]
    ret_islr_mes = [r for r in ret_islr if r.get("created_at", "")[:7] == f"{anio_actual}-{mes_actual:02d}"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="metric-card"><h3>Facturas (mes)</h3><h1>{len(facturas_mes)}</h1></div>""", unsafe_allow_html=True)
    with c2:
        total_iva = sum(r.get("monto_retenido", 0) or 0 for r in ret_iva_mes)
        st.markdown(f"""<div class="metric-card"><h3>Ret. IVA (mes)</h3><h1>{fmt(total_iva)}</h1></div>""", unsafe_allow_html=True)
    with c3:
        total_islr = sum(r.get("monto_retenido", 0) or 0 for r in ret_islr_mes)
        st.markdown(f"""<div class="metric-card"><h3>Ret. ISLR (mes)</h3><h1>{fmt(total_islr)}</h1></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="metric-card"><h3>Proveedores</h3><h1>{len(provs)}</h1></div>""", unsafe_allow_html=True)

    st.divider()

    # Últimas facturas
    st.markdown("### Últimas facturas registradas")
    if facturas:
        ultimas = sorted(facturas, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
        for f in ultimas:
            fdata = sb.table("facturas").select("*, proveedores(nombre, rif)").eq("id", f["id"]).execute().data
            if fdata:
                fd = fdata[0]
                prov_name = fd.get("proveedores", {}).get("nombre", "—") if fd.get("proveedores") else "—"
                st.markdown(f"- **{fd['numero_documento']}** | {fd['fecha_documento']} | {prov_name} | Total: {fmt(fd['total_compra'])}")
    else:
        st.info("No hay facturas registradas aún.")


# ══════════════════════════════════════════════════════════════
#  PROVEEDORES
# ══════════════════════════════════════════════════════════════
def page_proveedores():
    st.markdown("## 👥 Proveedores")
    sb = get_supabase()
    eid = empresa_id()
    if not eid:
        st.warning("Debe tener una empresa asignada.")
        return

    tab1, tab2 = st.tabs(["📋 Lista de Proveedores", "➕ Nuevo Proveedor"])

    # ── Lista ──
    with tab1:
        provs = sb.table("proveedores").select("*").eq("empresa_id", eid).order("nombre").execute().data or []
        if provs:
            df = pd.DataFrame(provs)[["nombre", "rif", "tipo_persona", "porcentaje_retencion_iva", "codigo_retencion_islr", "direccion", "telefono"]]
            df.columns = ["Nombre", "RIF", "Tipo Persona", "% Ret. IVA", "Cód. ISLR", "Dirección", "Teléfono"]
            df["% Ret. IVA"] = df["% Ret. IVA"].apply(lambda x: f"{x}%" if x else "Sin asignar")
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("### Editar Proveedor")
            opciones = {f"{p['nombre']} ({p['rif']})": p for p in provs}
            sel = st.selectbox("Seleccione proveedor", list(opciones.keys()), key="edit_prov")
            if sel:
                p = opciones[sel]
                with st.form("form_edit_prov"):
                    c1, c2 = st.columns(2)
                    with c1:
                        nombre = st.text_input("Nombre", value=p["nombre"])
                        rif = st.text_input("RIF", value=p["rif"])
                        direccion = st.text_input("Dirección", value=p.get("direccion") or "")
                    with c2:
                        telefono = st.text_input("Teléfono", value=p.get("telefono") or "")
                        tipo_p = st.selectbox("Tipo Persona", ["Juridica Domiciliada", "Natural Residente", "Juridica No Domiciliada", "Natural No Residente"],
                                              index=["Juridica Domiciliada", "Natural Residente", "Juridica No Domiciliada", "Natural No Residente"].index(p.get("tipo_persona", "Juridica Domiciliada")) if p.get("tipo_persona") in ["Juridica Domiciliada", "Natural Residente", "Juridica No Domiciliada", "Natural No Residente"] else 0)
                        pct_iva = st.selectbox("% Retención IVA", [75.0, 100.0],
                                               index=0 if p.get("porcentaje_retencion_iva") != 100 else 1)
                    # Códigos ISLR
                    codigos = sb.table("codigos_retencion_islr").select("codigo, descripcion").eq("activo", True).execute().data or []
                    cod_opciones = [f"{c['codigo']} - {c['descripcion']}" for c in codigos]
                    cod_actual = p.get("codigo_retencion_islr", "NORET")
                    idx_cod = 0
                    for i, c in enumerate(codigos):
                        if c["codigo"] == cod_actual:
                            idx_cod = i
                            break
                    cod_islr = st.selectbox("Código Retención ISLR", cod_opciones, index=idx_cod)
                    cod_islr_val = cod_islr.split(" - ")[0] if cod_islr else "NORET"

                    if st.form_submit_button("💾 Guardar Cambios"):
                        sb.table("proveedores").update({
                            "nombre": nombre, "rif": rif, "direccion": direccion,
                            "telefono": telefono, "tipo_persona": tipo_p,
                            "porcentaje_retencion_iva": pct_iva,
                            "codigo_retencion_islr": cod_islr_val,
                        }).eq("id", p["id"]).execute()
                        st.success("Proveedor actualizado")
                        st.rerun()
        else:
            st.info("No hay proveedores registrados.")

    # ── Nuevo ──
    with tab2:
        with st.form("form_new_prov"):
            st.markdown("### Registrar nuevo proveedor")
            c1, c2 = st.columns(2)
            with c1:
                nombre = st.text_input("Nombre / Razón Social *")
                rif = st.text_input("RIF * (ej: J123456789)")
                direccion = st.text_input("Dirección")
            with c2:
                telefono = st.text_input("Teléfono")
                tipo_p = st.selectbox("Tipo Persona", ["Juridica Domiciliada", "Natural Residente", "Juridica No Domiciliada", "Natural No Residente"])
                pct_iva = st.selectbox("% Retención IVA *", [75.0, 100.0])
            codigos = sb.table("codigos_retencion_islr").select("codigo, descripcion").eq("activo", True).execute().data or []
            cod_opciones = [f"{c['codigo']} - {c['descripcion']}" for c in codigos]
            cod_islr = st.selectbox("Código Retención ISLR", cod_opciones)
            cod_islr_val = cod_islr.split(" - ")[0] if cod_islr else "NORET"

            if st.form_submit_button("✅ Registrar Proveedor"):
                if not nombre or not rif:
                    st.error("Nombre y RIF son obligatorios")
                else:
                    sb.table("proveedores").insert({
                        "empresa_id": eid, "nombre": nombre.upper().strip(),
                        "rif": rif.upper().strip(), "direccion": direccion,
                        "telefono": telefono, "tipo_persona": tipo_p,
                        "porcentaje_retencion_iva": pct_iva,
                        "codigo_retencion_islr": cod_islr_val,
                    }).execute()
                    st.success(f"Proveedor {nombre} registrado exitosamente")
                    st.rerun()

        # Importar desde Excel
        st.divider()
        st.markdown("### 📥 Importar Proveedores desde Excel")
        archivo = st.file_uploader("Subir archivo Excel (.xls, .xlsx)", type=["xls", "xlsx"], key="import_prov")
        if archivo:
            try:
                df_imp = pd.read_excel(archivo, header=1)
                # Normalizar columnas
                df_imp.columns = [str(c).strip() for c in df_imp.columns]
                # Mapeo flexible
                col_map = {}
                for c in df_imp.columns:
                    cl = c.lower()
                    if "nombre" in cl or "proveedor" in cl or "razon" in cl or "razón" in cl:
                        col_map["nombre"] = c
                    elif "r.i.f" in cl or "rif" in cl:
                        col_map["rif"] = c
                    elif "tipo" in cl and "persona" in cl:
                        col_map["tipo_persona"] = c
                    elif "retenci" in cl or "código" in cl or "codigo" in cl:
                        col_map["codigo_retencion"] = c

                if "nombre" in col_map and "rif" in col_map:
                    df_clean = pd.DataFrame()
                    df_clean["nombre"] = df_imp[col_map["nombre"]].astype(str).str.strip().str.upper()
                    df_clean["rif"] = df_imp[col_map["rif"]].astype(str).str.strip().str.upper()
                    if "tipo_persona" in col_map:
                        df_clean["tipo_persona"] = df_imp[col_map["tipo_persona"]].astype(str).str.strip()
                    else:
                        df_clean["tipo_persona"] = "Juridica Domiciliada"
                    if "codigo_retencion" in col_map:
                        df_clean["codigo_retencion_islr"] = df_imp[col_map["codigo_retencion"]].astype(str).str.strip().str.upper()
                    else:
                        df_clean["codigo_retencion_islr"] = "NORET"

                    # Quitar filas vacías o headers repetidos
                    df_clean = df_clean[~df_clean["nombre"].isin(["NAN", "", "NOMBRE PROVEEDOR", "NOMBRE"])]
                    df_clean = df_clean[~df_clean["rif"].isin(["NAN", "", "N° R.I.F.", "RIF"])]
                    df_clean = df_clean.dropna(subset=["nombre", "rif"])

                    st.markdown(f"**{len(df_clean)} proveedores encontrados:**")
                    st.dataframe(df_clean, use_container_width=True, hide_index=True)

                    if st.button("⬆️ Importar todos", key="btn_import_prov"):
                        count = 0
                        for _, row in df_clean.iterrows():
                            # Verificar duplicado por RIF
                            existing = sb.table("proveedores").select("id").eq("empresa_id", eid).eq("rif", row["rif"]).execute().data
                            if not existing:
                                sb.table("proveedores").insert({
                                    "empresa_id": eid,
                                    "nombre": row["nombre"],
                                    "rif": row["rif"],
                                    "tipo_persona": row.get("tipo_persona", "Juridica Domiciliada"),
                                    "codigo_retencion_islr": row.get("codigo_retencion_islr", "NORET"),
                                }).execute()
                                count += 1
                        st.success(f"✅ {count} proveedores importados ({len(df_clean) - count} ya existían)")
                        st.rerun()
                else:
                    st.error("No se encontraron columnas de Nombre y RIF en el archivo")
            except Exception as e:
                st.error(f"Error al leer archivo: {e}")


# ══════════════════════════════════════════════════════════════
#  REGISTRO DE FACTURAS
# ══════════════════════════════════════════════════════════════
def page_facturas():
    st.markdown("## 🧾 Registro de Facturas de Compra")
    sb = get_supabase()
    eid = empresa_id()
    if not eid:
        st.warning("Debe tener una empresa asignada.")
        return

    tab1, tab2 = st.tabs(["➕ Nueva Factura", "📋 Facturas Registradas"])

    with tab1:
        provs = sb.table("proveedores").select("*").eq("empresa_id", eid).order("nombre").execute().data or []
        if not provs:
            st.warning("Primero debe registrar proveedores.")
            return

        st.markdown("### Datos de la Compra")

        with st.form("form_factura"):
            # Proveedor
            prov_opciones = {f"{p['nombre']} — {p['rif']}": p for p in provs}
            prov_sel = st.selectbox("Proveedor *", list(prov_opciones.keys()))
            prov = prov_opciones[prov_sel] if prov_sel else None

            # Si proveedor no tiene % IVA asignado
            prov_sin_iva = prov and prov.get("porcentaje_retencion_iva") is None if prov else False
            if prov_sin_iva:
                st.warning(f"⚠️ El proveedor {prov['nombre']} no tiene % de retención IVA asignado. Asígnelo abajo.")
                pct_iva_override = st.selectbox("% Retención IVA para este proveedor *", [75.0, 100.0], key="pct_iva_ov")
            else:
                pct_iva_override = None

            c1, c2, c3 = st.columns(3)
            with c1:
                tipo_doc = st.selectbox("Tipo Documento", ["01 Registro", "02 Nota de Débito", "03 Nota de Crédito"])
                numero_doc = st.text_input("Número de Documento *")
                numero_control = st.text_input("Número de Control")
            with c2:
                fecha_doc = st.date_input("Fecha Documento *", value=date.today())
                fecha_aplic = st.date_input("Fecha Aplicación", value=date.today())
                tipo_compra = st.selectbox("Tipo de Compra", ["Internas", "Importaciones"])
            with c3:
                tipo_trans = st.selectbox("Tipo Transacción", ["01 Registro", "02 Complemento", "03 Anulación"])
                credito_fiscal = st.selectbox("Crédito Fiscal", ["Deducible", "No Deducible"])
                observaciones = st.text_input("Observaciones")

            st.divider()
            st.markdown("### Montos")
            c1, c2, c3 = st.columns(3)
            with c1:
                monto_exento = st.number_input("Monto Exento (Bs)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                base_imponible = st.number_input("Base Imponible (Bs) *", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            with c2:
                alicuota_iva = st.selectbox("Alícuota IVA (%)", [16.0, 8.0, 0.0], index=0)
                monto_iva = round(base_imponible * alicuota_iva / 100, 2)
                st.metric("Monto IVA", fmt(monto_iva))
            with c3:
                igtf_pct = st.number_input("IGTF (%)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                igtf_monto = round((base_imponible + monto_iva) * igtf_pct / 100, 2) if igtf_pct > 0 else 0.0
                st.metric("Monto IGTF", fmt(igtf_monto))

            total_compra = round(monto_exento + base_imponible + monto_iva + igtf_monto, 2)
            st.markdown(f"### Total Compra: **{fmt(total_compra)} Bs**")

            st.divider()
            st.markdown("### Retenciones")
            aplicar_iva = st.checkbox("Aplicar Retención de IVA", value=True)
            aplicar_islr = st.checkbox("Aplicar Retención de ISLR", value=(prov["codigo_retencion_islr"] != "NORET") if prov else False)

            submitted = st.form_submit_button("💾 Guardar Factura y Generar Retenciones")

        if submitted:
            if not numero_doc:
                st.error("El número de documento es obligatorio")
                return
            if base_imponible <= 0 and monto_exento <= 0:
                st.error("Debe ingresar al menos Base Imponible o Monto Exento")
                return
            if prov_sin_iva and pct_iva_override:
                # Actualizar proveedor con el % IVA
                sb.table("proveedores").update({"porcentaje_retencion_iva": pct_iva_override}).eq("id", prov["id"]).execute()
                prov["porcentaje_retencion_iva"] = pct_iva_override

            # Guardar factura
            factura_data = {
                "empresa_id": eid,
                "proveedor_id": prov["id"],
                "tipo_documento": tipo_doc,
                "numero_documento": numero_doc.strip(),
                "numero_control": numero_control.strip() if numero_control else None,
                "fecha_documento": str(fecha_doc),
                "fecha_aplicacion": str(fecha_aplic),
                "tipo_compra": tipo_compra,
                "monto_exento": monto_exento,
                "base_imponible": base_imponible,
                "alicuota_iva": alicuota_iva,
                "monto_iva": monto_iva,
                "igtf_porcentaje": igtf_pct,
                "igtf_monto": igtf_monto,
                "total_compra": total_compra,
                "tipo_transaccion": tipo_trans,
                "credito_fiscal": credito_fiscal,
                "observaciones": observaciones,
            }
            res_fac = sb.table("facturas").insert(factura_data).execute()
            factura_id = res_fac.data[0]["id"]
            st.success(f"✅ Factura {numero_doc} registrada")

            # Retención IVA
            if aplicar_iva and monto_iva > 0:
                pct_ret_iva = prov.get("porcentaje_retencion_iva") or 75.0
                monto_ret_iva = round(monto_iva * pct_ret_iva / 100, 2)
                num_comp_iva = generar_numero_comprobante(sb, eid, "IVA", fecha_aplic)
                sb.table("retenciones_iva").insert({
                    "factura_id": factura_id,
                    "empresa_id": eid,
                    "numero_comprobante": num_comp_iva,
                    "fecha_retencion": str(fecha_aplic),
                    "porcentaje_retencion": pct_ret_iva,
                    "monto_iva": monto_iva,
                    "monto_retenido": monto_ret_iva,
                    "status": "Retenida",
                }).execute()
                st.success(f"✅ Retención IVA generada — Comprobante: {num_comp_iva} — Monto: {fmt(monto_ret_iva)}")

            # Retención ISLR
            if aplicar_islr and prov.get("codigo_retencion_islr", "NORET") != "NORET":
                cod = prov["codigo_retencion_islr"]
                cod_data = sb.table("codigos_retencion_islr").select("*").eq("codigo", cod).execute().data
                if cod_data:
                    pct_islr = cod_data[0]["porcentaje"]
                    concepto = cod_data[0].get("concepto_pago", "")
                    monto_ret_islr = round(base_imponible * pct_islr / 100, 2)
                    num_comp_islr = generar_numero_comprobante(sb, eid, "ISLR", fecha_aplic)
                    sb.table("retenciones_islr").insert({
                        "factura_id": factura_id,
                        "empresa_id": eid,
                        "numero_comprobante": num_comp_islr,
                        "fecha_retencion": str(fecha_aplic),
                        "codigo_retencion": cod,
                        "porcentaje_retencion": pct_islr,
                        "monto_original": total_compra,
                        "base_imponible": base_imponible,
                        "monto_retenido": monto_ret_islr,
                        "concepto_pago": concepto,
                    }).execute()
                    st.success(f"✅ Retención ISLR generada — Comprobante: {num_comp_islr} — Monto: {fmt(monto_ret_islr)}")

            st.rerun()

    with tab2:
        facturas = sb.table("facturas").select("*, proveedores(nombre, rif)").eq("empresa_id", eid).order("created_at", desc=True).execute().data or []
        if facturas:
            rows = []
            for f in facturas:
                prov_info = f.get("proveedores") or {}
                rows.append({
                    "Fecha": f["fecha_documento"],
                    "Nro Documento": f["numero_documento"],
                    "Nro Control": f.get("numero_control") or "",
                    "Proveedor": prov_info.get("nombre", ""),
                    "RIF": prov_info.get("rif", ""),
                    "Base Imp.": f["base_imponible"],
                    "IVA": f["monto_iva"],
                    "Total": f["total_compra"],
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No hay facturas registradas.")


# ══════════════════════════════════════════════════════════════
#  COMPROBANTES DE RETENCIÓN
# ══════════════════════════════════════════════════════════════
def page_comprobantes():
    st.markdown("## 📄 Comprobantes de Retención")
    sb = get_supabase()
    eid = empresa_id()
    if not eid:
        st.warning("Debe tener una empresa asignada.")
        return

    tab_iva, tab_islr = st.tabs(["🧾 Comprobantes IVA", "🧾 Comprobantes ISLR"])

    # Datos de la empresa
    emp = sb.table("empresas").select("*").eq("id", eid).execute().data
    emp_data = emp[0] if emp else {}

    with tab_iva:
        rets = sb.table("retenciones_iva").select("*, facturas(*, proveedores(*))").eq("empresa_id", eid).order("created_at", desc=True).execute().data or []
        if rets:
            for r in rets:
                fac = r.get("facturas") or {}
                prov = fac.get("proveedores") or {}
                with st.expander(f"📋 {r['numero_comprobante']} — {prov.get('nombre', '')} — {fmt(r['monto_retenido'])} Bs"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write(f"**Proveedor:** {prov.get('nombre', '')}")
                        st.write(f"**RIF:** {prov.get('rif', '')}")
                    with c2:
                        st.write(f"**Factura:** {fac.get('numero_documento', '')}")
                        st.write(f"**Fecha:** {r['fecha_retencion']}")
                    with c3:
                        st.write(f"**% Retención:** {r['porcentaje_retencion']}%")
                        st.write(f"**Monto Retenido:** {fmt(r['monto_retenido'])}")

                    pdf_bytes = generar_pdf_iva(emp_data, prov, fac, r)
                    st.download_button(
                        "📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"Comprobante_IVA_{r['numero_comprobante']}.pdf",
                        mime="application/pdf",
                        key=f"dl_iva_{r['id']}",
                    )
        else:
            st.info("No hay comprobantes de IVA generados.")

    with tab_islr:
        rets = sb.table("retenciones_islr").select("*, facturas(*, proveedores(*))").eq("empresa_id", eid).order("created_at", desc=True).execute().data or []
        if rets:
            for r in rets:
                fac = r.get("facturas") or {}
                prov = fac.get("proveedores") or {}
                with st.expander(f"📋 {r['numero_comprobante']} — {prov.get('nombre', '')} — {fmt(r['monto_retenido'])} Bs"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write(f"**Proveedor:** {prov.get('nombre', '')}")
                        st.write(f"**RIF:** {prov.get('rif', '')}")
                    with c2:
                        st.write(f"**Factura:** {fac.get('numero_documento', '')}")
                        st.write(f"**Código:** {r['codigo_retencion']}")
                    with c3:
                        st.write(f"**% Retención:** {r['porcentaje_retencion']}%")
                        st.write(f"**Monto Retenido:** {fmt(r['monto_retenido'])}")

                    pdf_bytes = generar_pdf_islr(emp_data, prov, fac, r)
                    st.download_button(
                        "📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"Comprobante_ISLR_{r['numero_comprobante']}.pdf",
                        mime="application/pdf",
                        key=f"dl_islr_{r['id']}",
                    )
        else:
            st.info("No hay comprobantes de ISLR generados.")


# ══════════════════════════════════════════════════════════════
#  GENERACIÓN DE PDFs
# ══════════════════════════════════════════════════════════════
def generar_pdf_iva(empresa, proveedor, factura, retencion):
    """Genera PDF del comprobante de retención IVA según formato SENIAT."""
    from fpdf import FPDF

    class PDFComprobante(FPDF):
        pass

    pdf = PDFComprobante(orientation="L", unit="mm", format="letter")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # ── Encabezado legal ──
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, 8)
    pdf.multi_cell(160, 3,
        "Documento que se emite de acuerdo a lo establecido en la Providencia Administrativa "
        "SNAT/2025/000054 - Art. 16, dictada el 2 de julio de 2025 y publicada en la Gaceta "
        "Oficial Nro. 43.171 del 16 de julio de 2025, y en conformidad con el Decreto "
        "Constituyente de Reforma Parcial del Decreto con Rango, Valor y Fuerza de Ley que "
        "establece el Impuesto al Valor Agregado, Gaceta Oficial Nro. 6.507 Extraordinario "
        "del 29 de enero de 2020, Art. 11.")

    # Número y fecha
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(185, 8)
    pdf.cell(35, 5, "Numero:", align="R")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(222, 8)
    pdf.cell(45, 5, retencion["numero_comprobante"], align="R")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(185, 14)
    pdf.cell(35, 5, "Fecha Emision:", align="R")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(222, 14)
    pdf.cell(45, 5, retencion["fecha_retencion"], align="R")

    # ── Título ──
    pdf.set_xy(10, 32)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "COMPROBANTE DE RETENCION DEL IMPUESTO AL VALOR AGREGADO", align="C")

    # ── Agente de Retención ──
    y = 44
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(140, 5, "NOMBRE O RAZON SOCIAL DEL AGENTE DE RETENCION")
    pdf.cell(50, 5, "RIF DEL AGENTE DE RETENCION")
    pdf.cell(50, 5, "PERIODO FISCAL")

    y += 5
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(10, y)
    pdf.cell(140, 5, empresa.get("nombre", ""))
    pdf.cell(50, 5, empresa.get("rif", ""))
    fecha_ret = retencion["fecha_retencion"]
    if isinstance(fecha_ret, str):
        partes = fecha_ret.split("-")
        anio_r, mes_r = partes[0], partes[1]
    else:
        anio_r, mes_r = fecha_ret.year, f"{fecha_ret.month:02d}"
    pdf.cell(50, 5, f"ANO: {anio_r} / MES: {mes_r}")

    y += 6
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(200, 5, "DIRECCION FISCAL DEL AGENTE DE RETENCION")
    pdf.cell(40, 5, "TELEFONO")
    y += 5
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, y)
    pdf.cell(200, 5, empresa.get("direccion", ""))
    pdf.cell(40, 5, empresa.get("telefono", ""))

    # ── Sujeto Retenido ──
    y += 8
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(180, 5, "NOMBRE O RAZON SOCIAL DEL SUJETO RETENIDO")
    pdf.cell(60, 5, "RIF DEL SUJETO RETENIDO")
    y += 5
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(10, y)
    pdf.cell(180, 5, proveedor.get("nombre", ""))
    pdf.cell(60, 5, proveedor.get("rif", ""))

    y += 5
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(180, 5, "DIRECCION")
    pdf.cell(60, 5, "TELEFONO")
    y += 5
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, y)
    pdf.cell(180, 5, proveedor.get("direccion", "") or "")
    pdf.cell(60, 5, proveedor.get("telefono", "") or "")

    # ── Tabla de detalles ──
    y += 10
    headers = ["Tipo Documento", "Fecha Documento", "Nro Documento", "Nro. Control",
               "Total Compras\nIncluyendo IVA", "Compras sin IVA", "Base Imponible",
               "Alicuota (%)", "Impuesto", "Porcentaje\nRetenido", "Impuesto\nRetenido"]
    widths = [22, 22, 24, 22, 25, 22, 24, 18, 20, 22, 22]

    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_xy(10, y)
    for i, h in enumerate(headers):
        x_pos = pdf.get_x()
        pdf.set_xy(x_pos, y)
        pdf.multi_cell(widths[i], 4, h, border=1, align="C")
        pdf.set_xy(x_pos + widths[i], y)

    y += 12
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, y)
    total_incl = factura.get("total_compra", 0) or 0
    sin_iva = factura.get("monto_exento", 0) or 0
    base_imp = factura.get("base_imponible", 0) or 0
    alicuota = factura.get("alicuota_iva", 16) or 16
    impuesto = factura.get("monto_iva", 0) or 0
    pct_ret = retencion.get("porcentaje_retencion", 75) or 75
    imp_ret = retencion.get("monto_retenido", 0) or 0

    vals = [
        factura.get("tipo_documento", "01 Registro"),
        factura.get("fecha_documento", ""),
        factura.get("numero_documento", ""),
        factura.get("numero_control", "") or "",
        fmt(total_incl),
        fmt(sin_iva),
        fmt(base_imp),
        f"{alicuota:.2f}",
        fmt(impuesto),
        f"{pct_ret:.2f}",
        fmt(imp_ret),
    ]

    for i, v in enumerate(vals):
        pdf.cell(widths[i], 6, str(v), border=1, align="C")

    # Total retenido
    y += 8
    pdf.set_xy(10, y)
    pdf.set_font("Helvetica", "B", 9)
    sum_w = sum(widths[:-1])
    pdf.cell(sum_w, 6, "", border=0)
    pdf.cell(widths[-1] + 20, 6, f"Total Retenido :   {fmt(imp_ret)}", border=0, align="R")

    # ── Firmas ──
    y += 25
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(30, y)
    pdf.cell(80, 4, "_______________________________", align="C")
    pdf.set_xy(160, y)
    pdf.cell(80, 4, "_________________________________", align="C")
    y += 5
    pdf.set_xy(30, y)
    pdf.cell(80, 4, "FIRMA Y SELLO AGENTE DE RETENCION", align="C")
    pdf.set_xy(160, y)
    pdf.cell(80, 4, "Recibi Conforme", align="C")
    y += 5
    pdf.set_xy(30, y)
    pdf.cell(80, 4, empresa.get("rif", ""), align="C")

    return pdf.output()


def generar_pdf_islr(empresa, proveedor, factura, retencion):
    """Genera PDF del comprobante de retención ISLR según formato legal."""
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="letter")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # ── Encabezado empresa ──
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_xy(10, 10)
    pdf.cell(130, 6, f"{empresa.get('nombre', '')} - {empresa.get('rif', '')}")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(150, 10)
    pdf.cell(55, 5, f"Numero: {retencion['numero_comprobante']}", align="R")
    pdf.set_xy(150, 16)
    pdf.cell(55, 5, f"Fecha Emision: {retencion['fecha_retencion']}", align="R")

    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, 18)
    dir_text = empresa.get("direccion", "") or ""
    pdf.cell(130, 4, dir_text)
    pdf.set_xy(10, 22)
    telf = empresa.get("telefono", "") or ""
    email = empresa.get("email", "") or ""
    pdf.cell(130, 4, f"Telf : {telf} / Email: {email}")

    # ── Título ──
    pdf.set_xy(10, 32)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "COMPROBANTE DE RETENCION DE IMPUESTO SOBRE LA RENTA", align="C")
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, 41)
    pdf.cell(0, 4, "Decreto Nro. 1.808 del Reglamento Parcial de Ley de ISLR en materia de Retenciones. Gaceta", align="C")
    pdf.set_xy(10, 45)
    pdf.cell(0, 4, "Oficial Nro. 36.203 de fecha 12/05/1997", align="C")

    # ── Agente de Retención ──
    y = 54
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(10, y)
    pdf.cell(0, 5, "DATOS DEL AGENTE DE RETENCION")
    y += 7
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(30, 5, "NOMBRE")
    pdf.set_xy(105, y)
    pdf.cell(20, 5, "N RIF")
    pdf.set_xy(155, y)
    pdf.cell(30, 5, "PERIODO FISCAL")
    y += 5
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(10, y)
    pdf.cell(90, 5, empresa.get("nombre", ""))
    pdf.set_xy(105, y)
    pdf.cell(40, 5, empresa.get("rif", ""))
    fecha_ret = retencion["fecha_retencion"]
    if isinstance(fecha_ret, str):
        partes = fecha_ret.split("-")
        anio_r, mes_r = partes[0], partes[1]
    else:
        anio_r, mes_r = fecha_ret.year, f"{fecha_ret.month:02d}"
    pdf.set_xy(155, y)
    pdf.cell(50, 5, f"ANO: {anio_r} / MES: {mes_r}")

    y += 6
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(30, 5, "DIRECCION")
    pdf.set_xy(155, y)
    pdf.cell(30, 5, "TELEFONO")
    y += 5
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, y)
    pdf.cell(140, 5, empresa.get("direccion", "") or "")
    pdf.set_xy(155, y)
    pdf.cell(50, 5, empresa.get("telefono", "") or "")

    # ── Beneficiario ──
    y += 10
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(10, y)
    pdf.cell(0, 5, "DATOS DEL BENEFICIARIO")
    y += 7
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(30, 5, "NOMBRE")
    pdf.set_xy(155, y)
    pdf.cell(20, 5, "N RIF")
    y += 5
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(10, y)
    pdf.cell(140, 5, proveedor.get("nombre", ""))
    pdf.set_xy(155, y)
    pdf.cell(50, 5, proveedor.get("rif", ""))

    y += 5
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(10, y)
    pdf.cell(30, 5, "DIRECCION")
    pdf.set_xy(155, y)
    pdf.cell(30, 5, "TELEFONO")
    y += 5
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, y)
    pdf.cell(140, 5, proveedor.get("direccion", "") or "")
    pdf.set_xy(155, y)
    pdf.cell(50, 5, proveedor.get("telefono", "") or "")

    # ── Concepto del pago ──
    y += 10
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(10, y)
    pdf.cell(40, 5, "CONCEPTO DEL PAGO")
    y += 5
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(10, y)
    pdf.cell(0, 5, retencion.get("concepto_pago", "") or "")

    # ── Tabla ──
    y += 10
    headers = ["Nro Doc", "Fecha\nDoc", "Nro. Control", "Monto\nOriginal", "Exento",
               "Base\nImponible", "%\nAlicuota", "Impuesto", "%\nRetenido", "Monto\nRetenido"]
    widths = [22, 18, 22, 22, 18, 22, 14, 18, 14, 22]

    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_xy(10, y)
    for i, h in enumerate(headers):
        x_pos = pdf.get_x()
        pdf.set_xy(x_pos, y)
        pdf.multi_cell(widths[i], 4, h, border=1, align="C")
        pdf.set_xy(x_pos + widths[i], y)

    y += 10
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(10, y)

    monto_orig = retencion.get("monto_original", 0) or 0
    exento = factura.get("monto_exento", 0) or 0
    base_imp = retencion.get("base_imponible", 0) or 0
    alicuota = factura.get("alicuota_iva", 16) or 16
    impuesto = factura.get("monto_iva", 0) or 0
    pct_ret = retencion.get("porcentaje_retencion", 0) or 0
    monto_ret = retencion.get("monto_retenido", 0) or 0

    vals = [
        factura.get("numero_documento", ""),
        factura.get("fecha_documento", ""),
        factura.get("numero_control", "") or "",
        fmt(monto_orig),
        fmt(exento),
        fmt(base_imp),
        f"{alicuota:.2f}",
        fmt(impuesto),
        f"{pct_ret:.2f}",
        fmt(monto_ret),
    ]
    for i, v in enumerate(vals):
        pdf.cell(widths[i], 6, str(v), border=1, align="C")

    # Total
    y += 8
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(10, y)
    sum_w = sum(widths[:-1])
    pdf.cell(sum_w, 6, "", border=0)
    pdf.cell(widths[-1] + 20, 6, f"Total Retenido :   {fmt(monto_ret)}", border=0, align="R")

    # ── Firmas ──
    y += 30
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(20, y)
    pdf.cell(70, 4, "_______________________________", align="C")
    pdf.set_xy(120, y)
    pdf.cell(70, 4, "_________________________________", align="C")
    y += 5
    pdf.set_xy(20, y)
    pdf.cell(70, 4, "FIRMA Y SELLO AGENTE DE RETENCION", align="C")
    pdf.set_xy(120, y)
    pdf.cell(70, 4, "Recibi Conforme", align="C")
    y += 5
    pdf.set_xy(20, y)
    pdf.cell(70, 4, empresa.get("rif", ""), align="C")

    return pdf.output()


# ══════════════════════════════════════════════════════════════
#  ADMINISTRACIÓN
# ══════════════════════════════════════════════════════════════
def page_admin():
    st.markdown("## ⚙️ Administración")
    sb = get_supabase()

    if not es_admin():
        st.error("Acceso restringido a administradores.")
        return

    tab1, tab2, tab3 = st.tabs(["🏢 Empresas", "👤 Usuarios", "📊 Códigos ISLR"])

    # ── Empresas ──
    with tab1:
        empresas = sb.table("empresas").select("*").order("nombre").execute().data or []
        if empresas:
            df = pd.DataFrame(empresas)[["id", "nombre", "rif", "direccion", "telefono", "email"]]
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Nueva Empresa")
        with st.form("form_nueva_empresa"):
            c1, c2 = st.columns(2)
            with c1:
                nombre_e = st.text_input("Nombre / Razón Social *")
                rif_e = st.text_input("RIF *")
                direccion_e = st.text_input("Dirección Fiscal")
            with c2:
                telefono_e = st.text_input("Teléfono")
                email_e = st.text_input("Email")
                zona_postal_e = st.text_input("Zona Postal")
            if st.form_submit_button("✅ Crear Empresa"):
                if nombre_e and rif_e:
                    sb.table("empresas").insert({
                        "nombre": nombre_e.upper().strip(),
                        "rif": rif_e.upper().strip(),
                        "direccion": direccion_e,
                        "telefono": telefono_e,
                        "email": email_e,
                        "zona_postal": zona_postal_e,
                    }).execute()
                    st.success(f"Empresa {nombre_e} creada")
                    st.rerun()
                else:
                    st.error("Nombre y RIF son obligatorios")

    # ── Usuarios ──
    with tab2:
        usuarios = sb.table("usuarios").select("id, username, nombre, rol, empresa_id, activo").order("username").execute().data or []
        if usuarios:
            df_u = pd.DataFrame(usuarios)
            st.dataframe(df_u, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Nuevo Usuario")
        empresas = sb.table("empresas").select("id, nombre").order("nombre").execute().data or []
        emp_opciones = {f"{e['nombre']} (ID: {e['id']})": e["id"] for e in empresas}

        with st.form("form_nuevo_usuario"):
            c1, c2 = st.columns(2)
            with c1:
                username_u = st.text_input("Usuario *")
                password_u = st.text_input("Contraseña *", type="password")
                nombre_u = st.text_input("Nombre completo *")
            with c2:
                rol_u = st.selectbox("Rol", ["cliente", "admin"])
                if emp_opciones:
                    emp_sel = st.selectbox("Empresa", list(emp_opciones.keys()))
                    emp_id_u = emp_opciones[emp_sel]
                else:
                    st.warning("No hay empresas. Créelas primero.")
                    emp_id_u = None
            if st.form_submit_button("✅ Crear Usuario"):
                if username_u and password_u and nombre_u:
                    sb.table("usuarios").insert({
                        "username": username_u.strip(),
                        "password_hash": hash_password(password_u),
                        "nombre": nombre_u,
                        "rol": rol_u,
                        "empresa_id": emp_id_u,
                    }).execute()
                    st.success(f"Usuario {username_u} creado")
                    st.rerun()
                else:
                    st.error("Complete todos los campos obligatorios")

    # ── Códigos ISLR ──
    with tab3:
        codigos = sb.table("codigos_retencion_islr").select("*").order("codigo").execute().data or []
        if codigos:
            df_c = pd.DataFrame(codigos)[["codigo", "descripcion", "concepto_pago", "porcentaje", "activo"]]
            df_c.columns = ["Código", "Descripción", "Concepto de Pago", "% Retención", "Activo"]
            st.dataframe(df_c, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### Nuevo Código ISLR")
        with st.form("form_nuevo_codigo"):
            c1, c2 = st.columns(2)
            with c1:
                cod_nuevo = st.text_input("Código *")
                desc_nuevo = st.text_input("Descripción *")
            with c2:
                concepto_nuevo = st.text_input("Concepto de Pago")
                pct_nuevo = st.number_input("% Retención *", min_value=0.0, max_value=100.0, value=2.0, step=0.5)
            if st.form_submit_button("✅ Agregar Código"):
                if cod_nuevo and desc_nuevo:
                    sb.table("codigos_retencion_islr").insert({
                        "codigo": cod_nuevo.upper().strip(),
                        "descripcion": desc_nuevo,
                        "concepto_pago": concepto_nuevo,
                        "porcentaje": pct_nuevo,
                    }).execute()
                    st.success(f"Código {cod_nuevo} agregado")
                    st.rerun()


# ══════════════════════════════════════════════════════════════
#  MAIN / ROUTER
# ══════════════════════════════════════════════════════════════
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
        return

    user = st.session_state["user"]

    # Sidebar
    with st.sidebar:
        st.markdown(f"### 📋 Retenciones")
        st.markdown(f"👤 **{user['nombre']}**")
        st.markdown(f"🔑 Rol: `{user['rol']}`")
        st.divider()

        opciones_menu = ["📊 Dashboard", "👥 Proveedores", "🧾 Facturas", "📄 Comprobantes"]
        if es_admin():
            opciones_menu.append("⚙️ Administración")

        pagina = st.radio("Navegación", opciones_menu, label_visibility="collapsed")
        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    # Router
    if "Dashboard" in pagina:
        page_dashboard()
    elif "Proveedores" in pagina:
        page_proveedores()
    elif "Facturas" in pagina:
        page_facturas()
    elif "Comprobantes" in pagina:
        page_comprobantes()
    elif "Administración" in pagina:
        page_admin()


if __name__ == "__main__":
    main()
