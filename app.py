import streamlit as st
import sqlite3
import requests
import re
import pandas as pd
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Monitor IA Licitaciones", page_icon="💧", layout="wide")

# --- 2. BASE DE DATOS V4 ---
def init_db():
    conn = sqlite3.connect('licitaciones_agua_v4.db')
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

# --- 3. EXTRACCIÓN SEGURA (Evita fallos de formato XML) ---
def extraer_dato(patron, texto, por_defecto="Desconocido"):
    match = re.search(patron, texto)
    return match.group(1) if match else por_defecto

# --- 4. MOTOR TURBO (Extra rápido para evitar el bloqueo de la nube) ---
def buscar_licitaciones_turbo(paginas_a_buscar=1, barra=None):
    url = "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
    conn = sqlite3.connect('licitaciones_agua_v4.db')
    c = conn.cursor()
    nuevas = 0

    for i in range(paginas_a_buscar):
        if barra:
            porcentaje = int(((i + 1) / paginas_a_buscar) * 100)
            barra.progress((i + 1) / paginas_a_buscar, text=f"⚡ Modo Turbo: Viajando al pasado... Página {i+1} analizada ({porcentaje}%)")

        try:
            # Descargamos la página directamente (mucho más rápido)
            resp = requests.get(url, timeout=10)
            contenido = resp.text

            # Dividimos el texto en los diferentes expedientes
            entradas = contenido.split('<entry>')
            
            for entrada in entradas[1:]: # Ignoramos la cabecera
                titulo = extraer_dato(r'<title>([^<]+)</title>', entrada, "")
                
                # Búsqueda infalible en el texto crudo
                if "384211" in entrada or "384210" in entrada or "contador " in titulo.lower() or "telelectura" in titulo.lower():
                    id_lic = extraer_dato(r'<cbc:ContractFolderID>([^<]+)</cbc:ContractFolderID>', entrada, str(datetime.now().timestamp()))
                    
                    c.execute("SELECT id_expediente FROM licitaciones WHERE id_expediente=?", (id_lic,))
                    if not c.fetchone():
                        # Extracción usando Regex (ignora los problemas de "namespaces" de Hacienda)
                        organo = extraer_dato(r'<cbc:Name>([^<]+)</cbc:Name>', entrada, "Organismo Público")
                        presupuesto = extraer_dato(r'<cbc:TaxExclusiveAmount[^>]*>([^<]+)</cbc:TaxExclusiveAmount>', entrada, "0")
                        enlace = extraer_dato(r'<link href="([^"]+)"', entrada, "https://contrataciondelestado.es")
                        fecha = extraer_dato(r'<updated>([^<]{10})', entrada, "Reciente")
                        
                        # Resumen preparado para IA
                        resumen = f"Renovación/Suministro para {organo}. Tipo de proyecto: {titulo[:80]}..."
                        
                        c.execute("INSERT INTO licitaciones VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                  (id_lic, organo, titulo, presupuesto, fecha, resumen, enlace))
                        nuevas += 1

            # Buscamos el enlace a la siguiente página (más antigua)
            next_match = re.search(r'<link href="([^"]+)" rel="next"', contenido)
            if next_match:
                url = next_match.group(1).replace("&amp;", "&")
            else:
                break # Fin del historial
        except Exception:
            pass # Si el Estado corta la conexión 1 segundo, seguimos con la siguiente página

    conn.commit()
    conn.close()
    return nuevas

# --- 5. INTERFAZ ---
init_db()
st.title("💧 Radar de Licitaciones (Motor Turbo)")

with st.sidebar:
    st.header("⚙️ Configuración")
    if st.button("🔄 Actualizar hoy"):
        with st.spinner("Buscando..."):
            n = buscar_licitaciones_turbo(10)
            if n > 0: st.success(f"¡{n} nuevas!")
            else: st.info("Nada nuevo.")

    st.divider()
    st.subheader("Búsqueda Histórica Profunda")
    st.write("Usa el nuevo Motor Turbo para leer 1.000 páginas en segundos y saltar los bloqueos de la nube.")
    
    if st.button("🚀 Iniciar Escáner Turbo (1.000 págs)"):
        barra = st.progress(0, text="Arrancando motor...")
        n = buscar_licitaciones_turbo(1000, barra)
        barra.empty()
        if n > 0:
            st.success(f"¡Caza exitosa! Se han rescatado {n} licitaciones del pasado.")
            st.balloons()
        else:
            st.warning("El escaneo ha terminado. Si no sale nada, el Estado no ha reportado movimientos de contadores en los últimos 3 meses.")

# --- TABLA DE RESULTADOS ---
conn = sqlite3.connect('licitaciones_agua_v4.db')
df = pd.read_sql_query("SELECT * FROM licitaciones ORDER BY fecha_publicacion DESC", conn)
conn.close()

col1, col2 = st.columns(2)
col1.metric("Licitaciones Cazadas", len(df))

st.divider()

if not df.empty:
    st.dataframe(
        df,
        column_config={
            "id_expediente": "ID",
            "organo": "Órgano de Contratación",
            "titulo": "Título técnico",
            "resumen": st.column_config.TextColumn("Resumen (Preparado para IA)", width="medium"),
            "presupuesto": "Pto. (€)",
            "fecha_publicacion": "Fecha",
            "enlace": st.column_config.LinkColumn("Pliego", display_text="🔗 Ver")
        },
        hide_index=True, use_container_width=True
    )
else:
    st.info("Base de datos vacía. Pulsa el botón del Escáner Turbo para llenarla a la máxima velocidad.")
