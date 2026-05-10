import streamlit as st
import sqlite3
import requests
import re
import pandas as pd
from datetime import datetime
import google.generativeai as genai

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Monitor IA Licitaciones", page_icon="💧", layout="wide")

# --- 2. CONFIGURACIÓN DE LA IA (GEMINI) ---
# Intentamos leer la llave secreta que pusimos en Streamlit Secrets
API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if API_KEY:
    genai.configure(api_key=API_KEY)

def generar_resumen_ia(titulo, organo, presupuesto):
    if not API_KEY:
        return "🤖 Falta configurar la API Key en los Secrets de Streamlit."
    
    try:
        # Usamos el modelo ultrarrápido de Gemini
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Actúa como un experto comercial. Haz un resumen de máximo 2 líneas de esta licitación pública.
        Dime qué buscan exactamente, quién es el cliente y valora si el presupuesto es alto o normal.
        Cliente: {organo}
        Título: {titulo}
        Presupuesto: {presupuesto} euros.
        """
        respuesta = model.generate_content(prompt)
        return respuesta.text.strip()
    except Exception as e:
        return "⚠️ La IA no pudo resumir este expediente."

# --- 3. BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('licitaciones_agua_v6.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS licitaciones (
            id_expediente TEXT PRIMARY KEY,
            organo TEXT,
            titulo TEXT,
            presupuesto TEXT,
            fecha_publicacion TEXT,
            resumen TEXT,
            enlace TEXT
        )
    ''')
    conn.commit()
    conn.close()

def extraer_dato(patron, texto, por_defecto="Desconocido"):
    match = re.search(patron, texto)
    return match.group(1) if match else por_defecto

# --- 4. MOTOR DE RADAR (CON IA) ---
def radar_diario(paginas_a_buscar=10, barra=None):
    url = "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
    conn = sqlite3.connect('licitaciones_agua_v6.db')
    c = conn.cursor()
    nuevas = 0

    for i in range(paginas_a_buscar):
        if barra:
            barra.progress((i + 1) / paginas_a_buscar, text=f"Rastreando y leyendo con IA (Pág {i+1}/{paginas_a_buscar})...")

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(url, headers=headers, timeout=15)
            
            if resp.status_code != 200: break

            entradas = resp.text.split('<entry>')
            for entrada in entradas[1:]:
                titulo = extraer_dato(r'<title>([^<]+)</title>', entrada, "")
                
                # Filtro: Contadores o Telelectura
                if "384211" in entrada or "384210" in entrada or "contador" in titulo.lower() or "telelectura" in titulo.lower():
                    id_lic = extraer_dato(r'<cbc:ContractFolderID>([^<]+)</cbc:ContractFolderID>', entrada, str(datetime.now().timestamp()))
                    
                    c.execute("SELECT id_expediente FROM licitaciones WHERE id_expediente=?", (id_lic,))
                    if not c.fetchone():
                        organo = extraer_dato(r'<cbc:Name>([^<]+)</cbc:Name>', entrada, "Organismo Público")
                        presupuesto = extraer_dato(r'<cbc:TaxExclusiveAmount[^>]*>([^<]+)</cbc:TaxExclusiveAmount>', entrada, "0")
                        enlace = extraer_dato(r'<link href="([^"]+)"', entrada, "https://contrataciondelestado.es")
                        fecha = extraer_dato(r'<updated>([^<]{10})', entrada, "Reciente")
                        
                        # ✨ AQUÍ ENTRA LA MAGIA DE LA IA ✨
                        resumen = generar_resumen_ia(titulo, organo, presupuesto)
                        
                        c.execute("INSERT INTO licitaciones VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                  (id_lic, organo, titulo, presupuesto, fecha, resumen, enlace))
                        nuevas += 1

            next_match = re.search(r'<link href="([^"]+)" rel="next"', resp.text)
            if next_match: url = next_match.group(1).replace("&amp;", "&")
            else: break
        except Exception: break

    conn.commit()
    conn.close()
    return nuevas

# --- 5. INTERFAZ ---
init_db()
st.title("💧 Radar de Licitaciones con IA (Gemini)")
st.markdown("Monitoriza el mercado y genera resúmenes comerciales automáticos.")

with st.sidebar:
    st.header("⚙️ Panel de Control")
    if st.button("🔄 Ejecutar Radar Diario"):
        barra = st.progress(0, text="Conectando con el Estado...")
        n = radar_diario(15, barra)
        barra.empty()
        if n > 0: st.success(f"¡Atención! {n} nuevas licitaciones encontradas hoy.")
        else: st.info("Bandeja limpia. No hay novedades.")

# --- TABLA DE RESULTADOS ---
conn = sqlite3.connect('licitaciones_agua_v6.db')
df = pd.read_sql_query("SELECT * FROM licitaciones ORDER BY fecha_publicacion DESC", conn)
conn.close()

st.divider()

if not df.empty:
    st.subheader(f"📋 Expedientes Activos ({len(df)})")
    st.dataframe(
        df,
        column_config={
            "id_expediente": "ID",
            "organo": "Cliente",
            "titulo": "Título Técnico",
            "resumen": st.column_config.TextColumn("🤖 Resumen Comercial (IA)", width="large"),
            "presupuesto": "Pto. (€)",
            "fecha_publicacion": "Fecha",
            "enlace": st.column_config.LinkColumn("Pliego", display_text="🔗 Abrir")
        },
        hide_index=True, use_container_width=True
    )
else:
    st.info("Base de datos limpia. Ejecuta el Radar para que la IA comience a leer.")
