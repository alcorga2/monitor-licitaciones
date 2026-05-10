import streamlit as st
import sqlite3
import feedparser
import xmltodict
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Monitor de Licitaciones", page_icon="💧", layout="wide")

def init_db():
    conn = sqlite3.connect('licitaciones_agua_v2.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS licitaciones (
            id_expediente TEXT PRIMARY KEY,
            organo TEXT,
            titulo TEXT,
            presupuesto TEXT,
            fecha_publicacion TEXT,
            enlace TEXT
        )
    ''')
    conn.commit()
    conn.close()

def buscar_licitaciones(paginas_a_buscar=1, barra_progreso=None):
    url_actual = "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
    conn = sqlite3.connect('licitaciones_agua_v2.db')
    c = conn.cursor()
    nuevas = 0
    
    for i in range(paginas_a_buscar):
        if barra_progreso:
            porcentaje = int(((i + 1) / paginas_a_buscar) * 100)
            barra_progreso.progress((i + 1) / paginas_a_buscar, text=f"Rastreando el Estado: Página {i+1} de {paginas_a_buscar}... ({porcentaje}%)")

        feed = feedparser.parse(url_actual)
        
        for entry in feed.entries:
            try:
                if hasattr(entry, 'content'):
                    xml_raw = entry.content[0].value
                    titulo = entry.title.lower()
                    
                    tiene_cpv = "384211" in xml_raw or "384210" in xml_raw
                    tiene_palabras = "contador" in titulo or "telelectura" in titulo
                    
                    if tiene_cpv or tiene_palabras:
                        datos_dict = xmltodict.parse(xml_raw, process_namespaces=False)
                        expediente = datos_dict.get('ContractFolderStatus', {})
                        id_licitacion = expediente.get('ContractFolderID', 'DESCONOCIDO')
                        
                        c.execute("SELECT id_expediente FROM licitaciones WHERE id_expediente=?", (id_licitacion,))
                        if not c.fetchone():
                            organo = "No especificado"
                            try: organo = expediente['LocatedContractingParty']['Party']['PartyName']['Name']
                            except: pass
                                
                            presupuesto = "0"
                            try:
                                valor = expediente['ProcurementProject']['BudgetAmount']['TaxExclusiveAmount']
                                presupuesto = valor.get('#text', '0') if isinstance(valor, dict) else str(valor)
                            except: pass

                            fecha_real = entry.updated[:10] if hasattr(entry, 'updated') else datetime.now().strftime("%Y-%m-%d")
                            
                            c.execute("INSERT INTO licitaciones VALUES (?, ?, ?, ?, ?, ?)", 
                                      (id_licitacion, organo, entry.title, presupuesto, fecha_real, entry.link))
                            nuevas += 1
            except Exception: pass 
                
        siguiente_url = None
        if hasattr(feed, 'feed') and hasattr(feed.feed, 'links'):
            for link in feed.feed.links:
                if link.rel == 'next': 
                    siguiente_url = link.href
                    break
        if not siguiente_url: break
        url_actual = siguiente_url 

    conn.commit()
    conn.close()
    return nuevas

def inyectar_datos_demo():
    conn = sqlite3.connect('licitaciones_agua_v2.db')
    c = conn.cursor()
    datos = [
        ("DEMO-001", "Mancomunidad de los Canales del Taibilla", "Suministro de contadores mecanicos y ultrasonicos. Anos 2026-2028", "451881", "2026-05-21", "https://contrataciondelestado.es"),
        ("DEMO-002", "Gipuzkoako Urak - Consorcio de Aguas", "Suministro y sustitucion de contadores de agua con sistema de telelectura", "12800000", "2026-05-15", "https://contrataciondelestado.es"),
        ("DEMO-003", "Empresa Municipal de Aguas de Cadiz (EMASA)", "Suministro de contadores de telelectura, instalacion, lectura remota", "1500000", "2026-05-10", "https://contrataciondelestado.es")
    ]
    for d in datos:
        c.execute("INSERT OR IGNORE INTO licitaciones VALUES (?, ?, ?, ?, ?, ?)", d)
    conn.commit()
    conn.close()

# --- INTERFAZ ---
init_db()

st.title("💧 Dashboard: Licitaciones de Contadores de Agua")
st.markdown("Tu radar diario conectado a la Plataforma de Contratación.")

with st.sidebar:
    st.header("⚙️ Panel de Control")
    
    st.write("**1. Radar Diario (Uso habitual)**")
    if st.button("🔄 Buscar Novedades de Hoy"):
        with st.spinner("Buscando nuevas publicaciones..."):
            encontradas = buscar_licitaciones(paginas_a_buscar=5)
        if encontradas > 0: st.success(f"¡{encontradas} nuevas!")
        else: st.info("Sin novedades hoy.")
            
    st.divider()
    
    st.write("**2. Datos de Prueba**")
    st.write("Si el mercado está parado, inyecta las licitaciones de tu captura para ver cómo funciona la tabla.")
    if st.button("🧪 Inyectar Datos Demo"):
        inyectar_datos_demo()
        st.success("Datos de prueba cargados. Actualiza la página.")

# --- MOSTRAR DATOS ---
conn = sqlite3.connect('licitaciones_agua_v2.db')
df = pd.read_sql_query("SELECT * FROM licitaciones ORDER BY fecha_publicacion DESC", conn)
conn.close()

col1, col2 = st.columns(2)
col1.metric("Total Licitaciones en Base de Datos", len(df))
col2.metric("Última actualización", datetime.now().strftime("%H:%M"))

st.divider()

if not df.empty:
    st.subheader("📋 Base de Datos de Licitaciones")
    st.dataframe(
        df,
        column_config={
            "id_expediente": "ID",
            "organo": "Órgano de Contratación",
            "titulo": "Objeto del Contrato",
            "presupuesto": "Presupuesto (€)",
            "fecha_publicacion": "Apertura / Fecha",
            "enlace": st.column_config.LinkColumn("Enlace", display_text="🔗 Ver Pliego")
        },
        hide_index=True,
        use_container_width=True
    )
else:
    st.info("Sin datos. Espera a que el Estado publique algo nuevo, o carga los datos Demo.")