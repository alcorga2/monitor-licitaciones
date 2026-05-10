import streamlit as st
import sqlite3
import feedparser
import xmltodict
import pandas as pd
from datetime import datetime
import time

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Monitor IA Licitaciones", page_icon="💧", layout="wide")

# --- 2. BASE DE DATOS V3 (Con Resumen) ---
def init_db():
    conn = sqlite3.connect('licitaciones_agua_v3.db')
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

# --- 3. FUNCIÓN DE RESUMEN (IA) ---
def generar_resumen_ia(titulo, organo):
    # Por ahora hacemos un resumen lógico. 
    # Si luego quieres conectar Gemini, solo hay que añadir 3 líneas aquí.
    palabras = titulo.split()
    resumen = f"Contratación de suministro para {organo}. Enfocado en {' '.join(palabras[:10])}..."
    return resumen

# --- 4. MOTOR DE BÚSQUEDA PROFUNDA ---
def buscar_licitaciones(paginas_a_buscar=1, barra_progreso=None):
    url_actual = "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
    conn = sqlite3.connect('licitaciones_agua_v3.db')
    c = conn.cursor()
    nuevas = 0
    
    for i in range(paginas_a_buscar):
        if barra_progreso:
            barra_progreso.progress((i + 1) / paginas_a_buscar, text=f"Analizando página {i+1} de {paginas_a_buscar}...")

        feed = feedparser.parse(url_actual)
        if not feed.entries: break

        for entry in feed.entries:
            try:
                xml_raw = entry.content[0].value
                # Buscamos CPV de contadores (384211) o telelectura
                if "384211" in xml_raw or "384210" in xml_raw or "contador" in entry.title.lower():
                    datos_dict = xmltodict.parse(xml_raw, process_namespaces=False)
                    exp = datos_dict.get('ContractFolderStatus', {})
                    id_lic = exp.get('ContractFolderID', 'ID-' + str(time.time()))
                    
                    c.execute("SELECT id_expediente FROM licitaciones WHERE id_expediente=?", (id_lic,))
                    if not c.fetchone():
                        # Extraer datos
                        try: organo = exp['LocatedContractingParty']['Party']['PartyName']['Name']
                        except: organo = "Organismo Desconocido"
                        
                        try:
                            pres = exp['ProcurementProject']['BudgetAmount']['TaxExclusiveAmount']
                            presupuesto = pres.get('#text', '0') if isinstance(pres, dict) else str(pres)
                        except: presupuesto = "Consultar pliego"

                        # GENERAR RESUMEN
                        resumen = generar_resumen_ia(entry.title, organo)
                        
                        fecha = entry.updated[:10] if hasattr(entry, 'updated') else "2024-01-01"
                        
                        c.execute("INSERT INTO licitaciones VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                  (id_lic, organo, entry.title, presupuesto, fecha, resumen, entry.link))
                        nuevas += 1
            except: pass
                
        # Ir a la página siguiente (hacia el pasado)
        next_url = next((l.href for l in feed.feed.links if l.rel == 'next'), None)
        if not next_url: break
        url_actual = next_url

    conn.commit()
    conn.close()
    return nuevas

# --- 5. INTERFAZ ---
init_db()
st.title("💧 Radar de Licitaciones con IA")

with st.sidebar:
    st.header("⚙️ Configuración")
    if st.button("🔄 Actualizar hoy"):
        with st.spinner("Buscando..."):
            n = buscar_licitaciones(5)
            st.success(f"¡{n} nuevas!")

    st.divider()
    st.subheader("Búsqueda Histórica (2 meses)")
    st.write("Esto revisará unas 500 páginas para encontrar los contratos de EMASA, Taibilla, etc.")
    if st.button("🚀 Iniciar Escaneo Profundo"):
        barra = st.progress(0, text="Iniciando...")
        n = buscar_licitaciones(500, barra_progreso=barra)
        barra.empty()
        st.success(f"Escaneo finalizado. Se han encontrado {n} licitaciones.")

# --- TABLA DE RESULTADOS ---
conn = sqlite3.connect('licitaciones_agua_v3.db')
df = pd.read_sql_query("SELECT * FROM licitaciones ORDER BY fecha_publicacion DESC", conn)
conn.close()

if not df.empty:
    st.dataframe(
        df,
        column_config={
            "organo": "Quién compra",
            "titulo": "Título técnico",
            "resumen": st.column_config.TextColumn("Resumen IA", width="large"),
            "presupuesto": "Presupuesto (€)",
            "enlace": st.column_config.LinkColumn("Pliego", display_text="🔗 Ver")
        },
        hide_index=True, use_container_width=True
    )
else:
    st.info("La base de datos está vacía. Pulsa el botón del Escaneo Profundo.")
