import streamlit as st
import sqlite3
import requests
import re
import pandas as pd
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Monitor IA Licitaciones", page_icon="💧", layout="wide")

def init_db():
    conn = sqlite3.connect('licitaciones_agua_v5.db')
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

# --- 2. MOTOR DE RADAR (Seguro contra bloqueos del Estado) ---
def radar_diario(paginas_a_buscar=10, barra=None):
    url = "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
    conn = sqlite3.connect('licitaciones_agua_v5.db')
    c = conn.cursor()
    nuevas = 0

    for i in range(paginas_a_buscar):
        if barra:
            barra.progress((i + 1) / paginas_a_buscar, text=f"Rastreando bandeja de entrada del Estado (Pág {i+1}/{paginas_a_buscar})...")

        try:
            # Añadimos un pequeño "engaño" para que el Estado no sepa que somos un robot de la nube
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
            resp = requests.get(url, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                break # Si el Estado nos frena, paramos educadamente

            entradas = resp.text.split('<entry>')
            
            for entrada in entradas[1:]:
                titulo = extraer_dato(r'<title>([^<]+)</title>', entrada, "")
                
                if "384211" in entrada or "384210" in entrada or "contador" in titulo.lower() or "telelectura" in titulo.lower():
                    id_lic = extraer_dato(r'<cbc:ContractFolderID>([^<]+)</cbc:ContractFolderID>', entrada, str(datetime.now().timestamp()))
                    
                    c.execute("SELECT id_expediente FROM licitaciones WHERE id_expediente=?", (id_lic,))
                    if not c.fetchone():
                        organo = extraer_dato(r'<cbc:Name>([^<]+)</cbc:Name>', entrada, "Organismo Público")
                        presupuesto = extraer_dato(r'<cbc:TaxExclusiveAmount[^>]*>([^<]+)</cbc:TaxExclusiveAmount>', entrada, "0")
                        enlace = extraer_dato(r'<link href="([^"]+)"', entrada, "https://contrataciondelestado.es")
                        fecha = extraer_dato(r'<updated>([^<]{10})', entrada, "Reciente")
                        
                        resumen = f"📌 Oportunidad detectada para {organo}. Consiste en: {titulo[:100]}..."
                        
                        c.execute("INSERT INTO licitaciones VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                  (id_lic, organo, titulo, presupuesto, fecha, resumen, enlace))
                        nuevas += 1

            next_match = re.search(r'<link href="([^"]+)" rel="next"', resp.text)
            if next_match:
                url = next_match.group(1).replace("&amp;", "&")
            else:
                break
        except Exception:
            break # Salida de seguridad si hay corte de red

    conn.commit()
    conn.close()
    return nuevas

# --- 3. INTERFAZ ---
init_db()
st.title("💧 Radar Diario de Licitaciones")
st.markdown("Herramienta de monitorización continua. Detecta nuevas oportunidades publicadas en los últimos días.")

with st.sidebar:
    st.header("⚙️ Panel de Control")
    st.write("Usa este radar una vez al día para atrapar las nuevas publicaciones antes que la competencia.")
    
    if st.button("🔄 Ejecutar Radar Diario"):
        barra = st.progress(0, text="Conectando con el Estado...")
        # Máximo 15 páginas para no ser bloqueados
        n = radar_diario(15, barra)
        barra.empty()
        if n > 0:
            st.success(f"¡Atención! {n} nuevas licitaciones encontradas hoy.")
        else:
            st.info("Bandeja limpia. No se han detectado contadores de agua recientemente.")

# --- TABLA DE RESULTADOS ---
conn = sqlite3.connect('licitaciones_agua_v5.db')
df = pd.read_sql_query("SELECT * FROM licitaciones ORDER BY fecha_publicacion DESC", conn)
conn.close()

st.divider()

if not df.empty:
    st.subheader(f"📋 Expedientes Activos ({len(df)})")
    st.dataframe(
        df,
        column_config={
            "id_expediente": "ID",
            "organo": "Órgano de Contratación",
            "titulo": "Título técnico",
            "resumen": st.column_config.TextColumn("Resumen (Preparado para IA)", width="medium"),
            "presupuesto": "Pto. (€)",
            "fecha_publicacion": "Fecha",
            "enlace": st.column_config.LinkColumn("Pliego", display_text="🔗 Ver Oficial")
        },
        hide_index=True, use_container_width=True
    )
else:
    st.info("Aún no hay datos. Ejecuta el Radar Diario. Si no sale nada hoy, ¡es que los ayuntamientos no han trabajado este fin de semana!")
