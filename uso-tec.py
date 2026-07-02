import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Configuración visual
st.set_page_config(page_title="Dashboard Tecnología Conci", layout="wide")

# --- 0. CONFIGURACIÓN DEL LAGO DE DATOS EN GITHUB ---
# Corregido a formato RAW para que Pandas pueda leerlo directamente
URL_GITHUB_RAW = "https://raw.githubusercontent.com/s-dagatti/uso-tec/main/Hoja%201.csv"
URL_LICENCIAS_RAW = "https://raw.githubusercontent.com/s-dagatti/uso-tec/main/Licencias.csv"


@st.cache_data(ttl=300)  # Se cachea por 5 minutos para que la navegación sea ultra rápida
def cargar_datos_desde_github(url):
    try:
        # Importante: Si tu CSV de GitHub usa punto y coma, cambiá sep=',' por sep=';'
        df = pd.read_csv(url, sep=',')
        return df
    except Exception as e:
        st.error(f"Error al conectar con el servidor de datos: {e}")
        return None


# --- 1. FUNCIONES DE PROCESAMIENTO ---
def procesar_datos_base(df):
    df.columns = [c.strip() for c in df.columns]
    
    # Manejo especial si la columna 'Fecha de terminación' viene duplicada
    if isinstance(df['Fecha de terminación'], pd.DataFrame):
        df['Fecha de terminación'] = pd.to_datetime(df['Fecha de terminación'].iloc[:, 0], errors='coerce')
    else:
        df['Fecha de terminación'] = pd.to_datetime(df['Fecha de terminación'], errors='coerce')
        
    cols_tech = [c for c in df.columns if any(k.lower() in c.lower() for k in ['activo (%)', 'activado (%)'])]
    for col in cols_tech:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # YA NO MULTIPLICAMOS POR 100 porque los datos ya vienen como enteros/decimales de porcentaje (ej: 12.5)
        # Filtro de ruido: Si querés seguir ignorando registros menores al 1% de uso, dejamos esta línea:
        df.loc[df[col] < 1.0, col] = np.nan
        
    return df


def filtrar_aptitud(df):
    def check(row):
        monitor = str(row.get('Monitor', '')).upper()
        version = str(row.get('Versión Monitor', ''))
        es_gen = any(g in monitor for g in ['4200', '4600', '4240', '4640', 'G5'])
        try:
            v_num = int(''.join(filter(str.isdigit, version.split('-')[0].split('.')[0]))[:2])
            es_sw = v_num >= 23
        except:
            es_sw = False
        return es_gen and es_sw

    df['Es_Apta'] = df.apply(check, axis=1)
    return df


# --- 2. INTERFAZ Y CARGA ---
st.title("🚜 Dashboard de Adopción Tecnológica - Conci")

st.sidebar.header("Estado de los Datos")

# Carga automática e independiente de SharePoint o PCs locales
df_raw = cargar_datos_desde_github(URL_GITHUB_RAW)
df_lic_raw = cargar_datos_desde_github(URL_LICENCIAS_RAW)

if df_raw is not None:
    st.sidebar.success("✅ Base de datos en la nube conectada")
else:
    st.sidebar.error("❌ Falló la conexión automática.")
    archivo_manual = st.sidebar.file_uploader("Subí el archivo manual de respaldo", type="csv")
    if archivo_manual:
        df_raw = pd.read_csv(archivo_manual)

# --- 3. PROCESAMIENTO GENERAL (Fuera del Bloque Else) ---
if df_raw is not None:
    df_raw['Sucursal'] = df_raw['Sucursal'].fillna("Sin Asignar").astype(str)
    df_full = procesar_datos_base(df_raw)
    df_full = filtrar_aptitud(df_full)

    # --- FILTRO DE FECHA (MES/AÑO) EN SIDEBAR ---
    st.sidebar.subheader("📅 Periodo de Análisis")
    min_date = df_full['Fecha de terminación'].min().to_pydatetime()
    max_date = df_full['Fecha de terminación'].max().to_pydatetime()

    periodo_seleccionado = st.sidebar.slider(
        "Seleccioná la última fecha de análisis (R12)",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="MM/YYYY"
    )

    # Filtramos el dataframe base según la fecha seleccionada
    df_full = df_full[
        (df_full['Fecha de terminación'] >= periodo_seleccionado[0]) &
        (df_full['Fecha de terminación'] <= periodo_seleccionado[1])
    ]

    # Identificación de Tiers
    col_at = [c for c in df_full.columns if 'AutoTrac' in c and 'Activo' in c]
    df_full['Tier_1'] = df_full[col_at[0]] if col_at else np.nan

    dict_t2 = {
        'AutoPath': [c for c in df_full.columns if 'AutoPath' in c],
        'ATTA (Maniobras)': [c for c in df_full.columns if 'maniobras' in c.lower()],
        'Guiado Pasivo': [c for c in df_full.columns if 'pasivo' in c.lower()],
        'Machine Sync': [c for c in df_full.columns if 'Machine Sync' in c]
    }

    cols_avanzadas = [col for lista in dict_t2.values() for col in lista]
    df_full['Tier_2'] = df_full[cols_avanzadas].mean(axis=1)

    ultima_fecha = df_full['Fecha de terminación'].max()

    # --- FILTROS SIDEBAR ---
    sucursales = st.sidebar.multiselect("1. Filtrar Sucursal", options=sorted(df_full['Sucursal'].unique().tolist()))
    if sucursales: 
        df_full = df_full[df_full['Sucursal'].isin(sucursales)]

    organizaciones = st.sidebar.multiselect("2. Filtrar Organización",
                                            options=sorted(df_full['Organización'].dropna().unique().tolist()))
    if organizaciones: 
        df_full = df_full[df_full['Organización'].isin(organizaciones)]

    tipos = st.sidebar.multiselect("3. Filtrar Tipo de Máquina",
                                   options=sorted(df_full['Tipo'].dropna().unique().tolist()))
    if tipos: 
        df_full = df_full[df_full['Tipo'].isin(tipos)]

    df_latest = df_full[df_full['Fecha de terminación'] == ultima_fecha].copy()
    df_aptas_latest = df_latest[df_latest['Es_Apta'] == True].copy()

 # --- NAVEGACIÓN ---
    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["🪪 Gestión de Licencias", "🌡️ Termómetro General", "Análisis Tier 1: AutoTrac", "Análisis Tier 2: Avanzado", "Cosechadoras", "CropCare"]
    )


    # ---------------------------------------------------------
    # TAB 0: GESTIÓN DE LICENCIAS
    # ---------------------------------------------------------
    with tab0:
        st.header("🪪 Control y Estado de Licencias")
        
        if df_lic_raw is not None:
            # 1. Limpieza rápida de columnas por si hay espacios
            df_lic_raw.columns = [c.strip() for c in df_lic_raw.columns]
            df_lic_raw['Sucursal'] = df_lic_raw['Sucursal'].fillna("Sin Asignar").astype(str).str.strip()
            df_lic_raw['Nombre de licencia'] = df_lic_raw['Nombre de licencia'].fillna("Sin Nombre").astype(str).str.strip()
            df_lic_raw['Nombre del cliente'] = df_lic_raw['Nombre del cliente'].fillna("Sin Organización").astype(str).str.strip()
            df_lic_raw['Estado'] = df_lic_raw['Estado'].fillna("Sin Estado").astype(str).str.strip()
            df_lic_raw['Número de licencia'] = df_lic_raw['Número de licencia'].fillna("").astype(str).str.strip()
            
            # --- PARSEO SEGURO DE FECHAS PARA EL GRÁFICO HISTÓRICO Y TABLA ---
            meses_es = {'ene': 'Jan', 'feb': 'Feb', 'mar': 'Mar', 'abr': 'Apr', 'may': 'May', 'jun': 'Jun',
                        'jul': 'Jul', 'ago': 'Aug', 'sept': 'Sep', 'oct': 'Oct', 'nov': 'Nov', 'dic': 'Dec'}
            
            def parsear_fecha_es(fecha_str):
                if pd.isna(fecha_str) or str(fecha_str).strip() == '---':
                    return pd.NaT
                fecha_str = str(fecha_str).lower().strip()
                for es, en in meses_es.items():
                    if es in fecha_str:
                        fecha_str = fecha_str.replace(es, en)
                        break
                try:
                    return pd.to_datetime(fecha_str, format='%d %b %Y', errors='coerce')
                except:
                    return pd.to_datetime(fecha_str, errors='coerce')

            # Usamos 'Fecha de terminación' para la lógica temporal
            df_lic_raw['Fecha_Real'] = df_lic_raw['Fecha de terminación'].apply(parsear_fecha_es)
            
            # 2. FILTROS PRINCIPALES (Arriba de todo, afectan a ambas sub-pestañas)
            col_filtros1, col_filtros2, col_filtros3 = st.columns(3)
            
            with col_filtros1:
                lista_sucursales = sorted(df_lic_raw['Sucursal'].unique())
                sucursal_sel = st.selectbox("🏢 Filtrar por Sucursal:", ["Todas"] + lista_sucursales, key="sb_lic_sucursal")
                
            with col_filtros2:
                lista_licencias = sorted(df_lic_raw['Nombre de licencia'].unique())
                licencia_sel = st.selectbox("🪪 Filtrar por Tipo de Licencia:", ["Todas"] + lista_licencias, key="sb_lic_tipo")
                
            with col_filtros3:
                buscar_nro_lic = st.text_input("🔍 Buscar por Nro de Licencia:", value="", key="ti_lic_numero").strip()
            
            # Aplicamos la cascada de filtros generales (incluyendo el buscador por número)
            df_lic_filtrado = df_lic_raw.copy()
            if sucursal_sel != "Todas":
                df_lic_filtrado = df_lic_filtrado[df_lic_filtrado['Sucursal'] == sucursal_sel]
            if licencia_sel != "Todas":
                df_lic_filtrado = df_lic_filtrado[df_lic_filtrado['Nombre de licencia'] == licencia_sel]
            if buscar_nro_lic != "":
                df_lic_filtrado = df_lic_filtrado[df_lic_filtrado['Número de licencia'].str.contains(buscar_nro_lic, case=False, na=False)]
            
            # --- CREACIÓN DE SUB-PESTAÑAS ---
            sub_tab1, sub_tab2 = st.tabs(["📋 Panel Principal", "📊 Análisis por Uso"])
            
            # =========================================================
            # SUB-PESTAÑA 1: PANEL PRINCIPAL
            # =========================================================
            with sub_tab1:
                # Conteo de estados sobre los datos filtrados
                activas = len(df_lic_filtrado[df_lic_filtrado['Estado'] == 'Activo'])
                no_activadas = len(df_lic_filtrado[df_lic_filtrado['Estado'] == 'No activado'])
                
                # Columnas de KPI
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric("Licencias Activas", activas)
                kpi2.metric("Licencias No Activadas", no_activadas)
                kpi3.metric("Total Licencias", len(df_lic_filtrado))
                
                st.divider()
                
                # GRÁFICOS EN PARALELO
                col_graf1, col_graf2 = st.columns(2)
                
                with col_graf1:
                    st.subheader("📊 Distribución por Tipo de Licencia")
                    if not df_lic_filtrado.empty:
                        df_pie_lic = df_lic_filtrado.groupby('Nombre de licencia').size().reset_index(name='Cantidad')
                        fig_pie_lic = px.pie(
                            df_pie_lic, 
                            names='Nombre de licencia', 
                            values='Cantidad',
                            hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Pastel
                        )
                        fig_pie_lic.update_traces(
                            textinfo='percent+label',
                            hovertemplate="<b>%{label}</b><br>Cantidad: %{value}<br>Porcentaje: %{percent}<extra></extra>"
                        )
                        st.plotly_chart(fig_pie_lic, use_container_width=True)
                    else:
                        st.info("No hay datos para mostrar con los filtros seleccionados.")
                    
                with col_graf2:
                    st.subheader("🏢 Distribución por Sucursal")
                    if not df_lic_filtrado.empty:
                        df_bar_lic = df_lic_filtrado.groupby(['Sucursal', 'Nombre de licencia']).size().reset_index(name='Cantidad')
                        fig_bar_lic = px.bar(
                            df_bar_lic,
                            x='Sucursal',
                            y='Cantidad',
                            color='Nombre de licencia',
                            barmode='stack', 
                            text_auto=True,
                            color_discrete_sequence=px.colors.qualitative.Pastel
                        )
                        fig_bar_lic.update_layout(
                            xaxis_title="Sucursal",
                            yaxis_title="Cantidad de Licencias",
                            legend_title="Tipo de Licencia",
                            hovermode="x unified"
                        )
                        st.plotly_chart(fig_bar_lic, use_container_width=True)
                    else:
                        st.info("No hay datos para mostrar.")

                st.divider()

                # GRÁFICO HISTÓRICO DE VENCIMIENTOS
                st.subheader("📅 Cronograma Histórico de Vencimientos")
                df_venc = df_lic_filtrado[df_lic_filtrado['Fecha_Real'].notnull()].copy()
                df_acumulado_filtros = df_lic_filtrado.copy()
                
                if not df_venc.empty:
                    min_date = df_venc['Fecha_Real'].min().date()
                    max_date = df_venc['Fecha_Real'].max().date()
                    
                    if min_date == max_date:
                        st.info(f"Todas las licencias seleccionadas vencen el mismo día: {min_date}")
                        df_venc_final = df_venc.copy()
                        df_acumulado_filtros = df_venc.copy()
                    else:
                        rango_fechas = st.slider(
                            "📆 Seleccionar rango de fechas de vencimiento a visualizar:",
                            min_value=min_date,
                            max_value=max_date,
                            value=(min_date, max_date),
                            format="DD/MM/YYYY"
                        )
                        
                        df_venc_final = df_venc[
                            (df_venc['Fecha_Real'].dt.date >= rango_fechas[0]) & 
                            (df_venc['Fecha_Real'].dt.date <= rango_fechas[1])
                        ].copy()
                        
                        df_acumulado_filtros = df_lic_filtrado[
                            ((df_lic_filtrado['Fecha_Real'].dt.date >= rango_fechas[0]) & 
                             (df_lic_filtrado['Fecha_Real'].dt.date <= rango_fechas[1])) |
                            (df_lic_filtrado['Fecha_Real'].isnull())
                        ].copy()

                    if not df_venc_final.empty:
                        df_venc_final['Mes_Vencimiento'] = df_venc_final['Fecha_Real'].dt.to_period('M')
                        df_venc_grouped = df_venc_final.groupby(['Mes_Vencimiento', 'Nombre de licencia']).size().reset_index(name='Cantidad')
                        df_venc_grouped['Mes_Vencimiento'] = df_venc_grouped['Mes_Vencimiento'].astype(str)
                        df_venc_grouped = df_venc_grouped.sort_values('Mes_Vencimiento')
                        
                        fig_hist_venc = px.bar(
                            df_venc_grouped,
                            x='Mes_Vencimiento',
                            y='Cantidad',
                            color='Nombre de licencia',
                            barmode='stack',
                            text_auto=True,
                            color_discrete_sequence=px.colors.qualitative.Safe
                        )
                        fig_hist_venc.update_layout(
                            xaxis_title="Período (Año-Mes)", yaxis_title="Cantidad de Licencias a Vencer",
                            legend_title="Tipo de Licencia", xaxis={'type': 'category'}, hovermode="x unified"
                        )
                        st.plotly_chart(fig_hist_venc, use_container_width=True)
                
                st.divider()

                # SECCIÓN DE TABLA DETALLADA
                st.subheader("🔍 Listado Detallado de Licencias")
                col_tbl_filtro1, col_tbl_filtro2 = st.columns(2)
                
                with col_tbl_filtro1:
                    lista_orgs = sorted(df_acumulado_filtros['Nombre del cliente'].unique())
                    org_sel = st.selectbox("🚜 Filtrar por Organización / Cliente:", ["Todas"] + lista_orgs, key="sb_lic_org")
                    
                with col_tbl_filtro2:
                    lista_estados = sorted(df_acumulado_filtros['Estado'].unique())
                    estado_sel = st.selectbox("🟢 Filtrar por Estado de Licencia:", ["Todos"] + lista_estados, key="sb_lic_estado_tbl")
                
                df_tabla_final = df_acumulado_filtros.copy()
                if org_sel != "Todas":
                    df_tabla_final = df_tabla_final[df_tabla_final['Nombre del cliente'] == org_sel]
                if estado_sel != "Todos":
                    df_tabla_final = df_tabla_final[df_tabla_final['Estado'] == estado_sel]
                
                if not df_tabla_final.empty:
                    columnas_mapeo = {
                        'Número de licencia': 'numero de licencia', 'Nombre del cliente': 'organización',
                        'Modelo': 'Modelo de maquina', 'Nombre de licencia': 'Nombre de licencia',
                        'Estado': 'Estado', 'Fecha de inicio': 'Fecha de inicio',
                        'Fecha de terminación': 'Fecha de terminacion', 'Fecha de vencimiento de pedido': 'Fecha de vencimiento',
                        'Sucursal': 'Sucursal'
                    }
                    df_display = df_tabla_final[list(columnas_mapeo.keys())].copy()
                    df_display = df_display.rename(columns=columnas_mapeo)
                    orden_columnas = ['numero de licencia', 'organización', 'Modelo de maquina', 'Nombre de licencia',
                                      'Estado', 'Fecha de inicio', 'Fecha de terminacion', 'Fecha de vencimiento', 'Sucursal']
                    st.dataframe(df_display[orden_columnas], use_container_width=True, hide_index=True)
                    st.caption(f"Mostrando {len(df_display)} registros encontrados.")
                else:
                    st.info("No hay registros para mostrar con los criterios seleccionados.")

            # =========================================================
            # SUB-PESTAÑA 2: ANÁLISIS POR USO Y GLOSARIO
            # =========================================================
            with sub_tab2:
                # --- DICCIONARIO MAESTRO DE LICENCIAS Y SUS FUNCIONES ---
                glosario_licencias = {
                    "Renovable avanzada": [
                        "AutoTrac™", "Compartir datos en campo", "Guiado pasivo de implemento AutoTrac™",
                        "Automatización de maniobras AutoTrac™", "Machine Sync", "Razones de inactividad",
                        "Capa de fondo de satélite", "AutoPath™"
                    ],
                    "Renovable escencial": [
                        "AutoTrac™", "Compartir datos en campo", "Razones de inactividad", "Capa de fondo de satélite"
                    ],
                    "Control de secciones renovable": [
                        "Control de secciones"
                    ],
                    "Cosechadora S7/X9 Ultimate": [
                        "Capa de fondo de satélite", "Razones de inactividad", "Auto Unload", "Compartir datos en campo",
                        "Automatización de maniobras AutoTrac™", "Machine Sync", "AutoPath™", 
                        "Automatización de ajustes de cosecha", "Gestión inteligente de potencia (IPM)", 
                        "Vistas satelitales", "Cámaras delanteras",
                        "Automatización de la velocidad de avance" # <-- Agregada aquí
                    ],
                    "G5 Advanced - Aplicación autopropulsada": [
                        "Capa de fondo de satélite", "Automatización de maniobras AutoTrac™", "Razones de inactividad",
                        "Compartir datos en campo", "AutoPath™",
                        "Control de secciones", "Pulsación" # <-- Agregadas aquí
                    ],
                    "G5 Advanced - Cosechadora": [
                        "Capa de fondo de satélite", "Razones de inactividad", "Compartir datos en campo",
                        "Automatización de maniobras AutoTrac™", "Machine Sync", "AutoPath™"
                    ],
                    "G5 Advanced - Tractor de la serie 7/8/9": [
                        "Capa de fondo de satélite", "Razones de inactividad", "Compartir datos en campo",
                        "Guiado pasivo de implemento AutoTrac™", "Automatización de maniobras AutoTrac™", 
                        "Machine Sync", "AutoPath™"
                    ],
                    "G5 Advanced - Universal": [
                        "Capa de fondo de satélite", "Razones de inactividad", "Compartir datos en campo",
                        "Automatización de maniobras AutoTrac™", "Machine Sync", "AutoPath™", 
                        "Guiado pasivo de implemento AutoTrac™"
                    ]
                }

                # Mapeo de nombres a columnas de telemetría de la Hoja 1
                mapeo_columnas_telemetria = {
                    "AutoTrac™": "AutoTrac™ Activo (%)",
                    "AutoPath™": "AutoPath™ Activo (%)",
                    "Automatización de maniobras AutoTrac™": "Automatización de maniobras AutoTrac™ Activo (%)",
                    "Guiado pasivo de implemento AutoTrac™": "Guiado pasivo de implemento AutoTrac™ Activo (%)",
                    "Machine Sync": "John Deere Machine Sync Vehículo guía activo (%)",
                    "Control de secciones": "Tiempo de control de secciones Activo (%)",
                    "Pulsación": "Pulsación Activo (%)", # <-- Mapeo para ExactApply
                    "Automatización de ajustes de cosecha": "Automatización de ajustes de cosecha Activo (%)",
                    "Automatización de la velocidad de avance": "Automatización de la velocidad de avance Activo (%)" # <-- Mapeo para Cosechadoras S7/X9
                }

                st.divider()

                # --- 1. GLOSARIO DE LICENCIAS (AISLADO) ---
                st.subheader("📚 Glosario de Funciones por Licencia")
                with st.expander("🔍 Consultar qué incluye cada tipo de licencia", expanded=False):
                    st.markdown("*Este selector es informativo y no altera las tablas o gráficos del panel.*")
                    licencia_glosario_sel = st.selectbox(
                        "Seleccioná una licencia para ver sus características:",
                        options=list(glosario_licencias.keys()),
                        key="sb_glosario_interno"
                    )
                    st.markdown(f"### Funciones incluidas en **{licencia_glosario_sel}**:")
                    for funcion in glosario_licencias[licencia_glosario_sel]:
                        st.markdown(f"• {funcion}")
                
                st.divider()
                
                # --- 2. ESTADÍSTICAS CONSOLIDADAS (APLICANDO FILTROS SUPERIORES Y SIDEBAR) ---
                st.subheader("📈 Estadísticas Consolidadas de Uso General")
                
                if df_full is not None and not df_full.empty:
                    df_base_uso = df_full.copy()
                    
                    df_base_uso.columns = [c.strip() for c in df_base_uso.columns]
                    df_base_uso['Fecha de terminación'] = pd.to_datetime(df_base_uso['Fecha de terminación'], errors='coerce')
                    
                    ultima_fecha_act = df_base_uso['Fecha de terminación'].max()
                    
                    if not pd.isna(ultima_fecha_act):
                        df_uso_actual = df_base_uso[df_base_uso['Fecha de terminación'] == ultima_fecha_act].copy()
                        
                        df_uso_actual = df_uso_actual[df_uso_actual['Nro Licencia'].notnull() & (df_uso_actual['Nro Licencia'].astype(str).str.strip() != "") & (df_uso_actual['Nro Licencia'].astype(str).str.strip() != "#N/A")]
                        
                        if sucursal_sel != "Todas":
                            df_uso_actual = df_uso_actual[df_uso_actual['Sucursal'] == sucursal_sel]
                        if licencia_sel != "Todas":
                            df_uso_actual = df_uso_actual[df_uso_actual['Tipo Licencia'] == licencia_sel]
                        if buscar_nro_lic != "":
                            df_uso_actual = df_uso_actual[df_uso_actual['Nro Licencia'].astype(str).str.contains(buscar_nro_lic, case=False, na=False)]
                        
                        for col in df_uso_actual.columns:
                            if '%' in col or 'Activo' in col:
                                df_uso_actual[col] = pd.to_numeric(df_uso_actual[col], errors='coerce').fillna(0)

                        if not df_uso_actual.empty:
                            st.markdown(f"**Distribución de Licencias por Tipo de Equipo (Actualizado al {ultima_fecha_act.strftime('%d/%m/%Y')})**")
                            df_chart_uso = df_uso_actual.groupby(['Tipo', 'Tipo Licencia']).size().reset_index(name='Cantidad')
                            
                            fig_bar_uso_maquina = px.bar(
                                df_chart_uso,
                                x='Tipo',
                                y='Cantidad',
                                color='Tipo Licencia',
                                barmode='stack',
                                text_auto=True,
                                color_discrete_sequence=px.colors.qualitative.Plotly
                            )
                            fig_bar_uso_maquina.update_layout(
                                xaxis_title="Tipo de Equipo", yaxis_title="Cantidad de Licencias",
                                legend_title="Tipo de Licencia", hovermode="x unified"
                            )
                            st.plotly_chart(fig_bar_uso_maquina, use_container_width=True)
                        else:
                            st.info("No hay licencias activas que coincidan con los filtros seleccionados (Sidebar o Filtros Superiores).")
                        
                        st.divider()
                        
                        # --- 3. SECCIÓN DE TABS POR TIPO DE LICENCIA (REVISADA) ---
                        st.subheader("🎯 Monitoreo de Funciones Específicas Habilitadas")
                        st.markdown("Seleccioná la pestaña de la licencia que querés auditar para ver el porcentaje de uso real de las funciones que tiene contratadas el cliente.")
                        
                        if not df_uso_actual.empty:
                            lista_nombres_licencias = list(glosario_licencias.keys())
                            tabs_licencias = st.tabs(lista_nombres_licencias)
                            
                        for i, nombre_lic in enumerate(lista_nombres_licencias):
                                with tabs_licencias[i]:
                                    df_lic_especifica = df_uso_actual[df_uso_actual['Tipo Licencia'] == nombre_lic].copy()
                                    
                                    if not df_lic_especifica.empty:
                                        columnas_visibles = {
                                            'Organización': 'Organización',
                                            'Modelo': 'Modelo',
                                            'Nro Licencia': 'Número de Licencia',
                                            'Fecha de terminación': 'Fecha de Vencimiento'
                                        }
                                        
                                        funciones_contratadas = glosario_licencias[nombre_lic]
                                        columnas_dinamicas_formatear = []
                                        
                                        for func in funciones_contratadas:
                                            if func in mapeo_columnas_telemetria:
                                                col_csv = mapeo_columnas_telemetria[func]
                                                if col_csv in df_lic_especifica.columns:
                                                    columnas_visibles[col_csv] = f"Uso {func} (%)"
                                                    columnas_dinamicas_formatear.append(f"Uso {func} (%)")
                                        
                                        cols_validas_esp = [c for c in columnas_visibles.keys() if c in df_lic_especifica.columns]
                                        df_tabla_especifica = df_lic_especifica[cols_validas_esp].rename(columns=columnas_visibles)
                                        
                                        columnas_ordenadas = ['Organización', 'Modelo', 'Número de Licencia', 'Fecha de Vencimiento'] + columnas_dinamicas_formatear
                                        cols_finales_mostrar = [c for c in columnas_ordenadas if c in df_tabla_especifica.columns]
                                        df_tabla_especifica = df_tabla_especifica[cols_finales_mostrar]
                                        
                                        # =========================================================
                                        # ADICIÓN DE KPIS Y COLORES PARA "RENOVABLE AVANZADA"
                                        # =========================================================
                                        if nombre_lic == "Renovable avanzada":
                                            # 1. Cálculo de KPIs
                                            col_at_ref = "Uso AutoTrac™ (%)"
                                            # Buscamos columnas avanzadas contratadas que no sean AutoTrac
                                            cols_avanzadas_ref = [c for c in columnas_dinamicas_formatear if "AutoTrac™" not in c]
                                            
                                            avg_autotrac = df_tabla_especifica[col_at_ref].mean() if col_at_ref in df_tabla_especifica.columns else 0
                                            
                                            if cols_avanzadas_ref:
                                                avg_avanzadas = df_tabla_especifica[cols_avanzadas_ref].mean(axis=1).mean()
                                            else:
                                                avg_avanzadas = 0
                                                
                                            # Renderizamos las tarjetas de KPI
                                            kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
                                            with kpi_col1:
                                                st.metric(label="Promedio Uso AutoTrac™", value=f"{avg_autotrac:.1f}%")
                                            with kpi_col2:
                                                st.metric(label="Promedio Funciones Avanzadas", value=f"{avg_avanzadas:.1f}%", help="AutoPath, Maniobras, Machine Sync, Guiado Pasivo, etc.")
                                            with kpi_col3:
                                                st.metric(label="Equipos en la Licencia", value=str(len(df_tabla_especifica)))
                                            
                                            st.markdown("---")
                                            
                                            # 2. Función para pintar filas según las reglas del negocio
                                            def colorear_filas_avanzada(row):
                                                at_val = row.get(col_at_ref, 0)
                                                # Convertimos a flotante por si acaso viene como string
                                                try: at_num = float(str(at_val).replace('%', ''))
                                                except: at_num = 0
                                                
                                                # Sacamos el máximo o promedio de las otras tecnologías avanzadas de la fila
                                                vals_avanzados = []
                                                for c_av in cols_avanzadas_ref:
                                                    try: vals_avanzados.append(float(str(row.get(c_av, 0)).replace('%', '')))
                                                    except: pass
                                                max_av_num = max(vals_avanzados) if vals_avanzados else 0
                                                
                                                # Definición de estilos CSS (Background-color suave para que se lea el texto)
                                                verde = 'background-color: rgba(40, 167, 69, 0.25); color: white;'
                                                amarillo = 'background-color: rgba(255, 193, 7, 0.25); color: white;'
                                                rojo = 'background-color: rgba(220, 53, 69, 0.25); color: white;'
                                                
                                                # Regla: Verde (Buen uso) -> AT > 60% Y cualquier otra > 20%
                                                if at_num > 60.0 and max_av_num > 20.0:
                                                    return [verde] * len(row)
                                                # Regla: Amarillo (Uso medio) -> AT > 60% pero nada avanzado, O viceversa (Avanzado > 20% pero AT bajo)
                                                elif (at_num > 60.0 and max_av_num <= 20.0) or (at_num <= 60.0 and max_av_num > 20.0):
                                                    return [amarillo] * len(row)
                                                # Regla: Rojo -> Todo bajo
                                                else:
                                                    return [rojo] * len(row)
                                            
                                            # Formateamos la fecha antes de mostrar
                                            if 'Fecha de Vencimiento' in df_tabla_especifica.columns:
                                                df_tabla_especifica['Fecha de Vencimiento'] = df_tabla_especifica['Fecha de Vencimiento'].dt.strftime('%d/%m/%Y')
                                            
                                            # Aplicamos los estilos y mostramos la tabla
                                            df_estilizado = df_tabla_especifica.style.apply(colorear_filas_avanzada, axis=1)
                                            
                                            # Formateamos visualmente los floats a porcentaje para la visualización limpia
                                            format_dict = {col: '{:.1f}%'.format for col in columnas_dinamicas_formatear}
                                            df_estilizado = df_estilizado.format(format_dict)
                                            
                                            st.dataframe(df_estilizado, use_container_width=True, hide_index=True)
                                            
                                        else:
                                            # Para el resto de las licencias mantiene el comportamiento estándar sin pintar filas
                                            if 'Fecha de Vencimiento' in df_tabla_especifica.columns:
                                                df_tabla_especifica['Fecha de Vencimiento'] = df_tabla_especifica['Fecha de Vencimiento'].dt.strftime('%d/%m/%Y')
                                            
                                            for col_formato in columnas_dinamicas_formatear:
                                                df_tabla_especifica[col_formato] = df_tabla_especifica[col_formato].map('{:.1f}%'.format)
                                                
                                            st.dataframe(df_tabla_especifica, use_container_width=True, hide_index=True)
                                            
                                        st.caption(f"Mostrando {len(df_tabla_especifica)} equipos con licencia tipo '{nombre_lic}' activa.")
                                    else:
                                        st.info(f"No se registran equipos operando con la licencia '{nombre_lic}' bajo los filtros actuales.")
                
                # --- 4. SECCIÓN DE LICENCIAS SIN REGISTRO DE USO ---
                st.subheader("⚠️ Licencias Adquiridas Sin Registro de Uso")
                st.markdown("""
                Este análisis compara el maestro de **Licencias** contra los reportes de actividad de la **Hoja 1** (restringido a la última fecha de actualización disponible).
                """)
                
                if df_raw is not None and df_lic_filtrado is not None:
                    df_uso = df_raw.copy()
                    df_uso.columns = [c.strip() for c in df_uso.columns]
                    df_uso['Fecha de terminación'] = pd.to_datetime(df_uso['Fecha de terminación'], errors='coerce')
                    
                    ultima_fecha_uso = df_uso['Fecha de terminación'].max()
                    
                    if not pd.isna(ultima_fecha_uso):
                        df_uso_reciente = df_uso[df_uso['Fecha de terminación'] == ultima_fecha_uso]
                        licencias_con_uso = df_uso_reciente['Nro Licencia'].dropna().astype(str).str.strip().unique()
                        
                        df_sin_uso = df_lic_filtrado[~df_lic_filtrado['Número de licencia'].isin(licencias_con_uso)].copy()
                        df_sin_uso = df_sin_uso.drop_duplicates(subset=['Número de licencia'])
                        
                        if not df_sin_uso.empty:
                            columnas_mapeo_uso = {
                                'Número de licencia': 'Número de licencia', 'Nombre del cliente': 'Organización',
                                'Nombre de licencia': 'Nombre de licencia', 'Fecha de terminación': 'Fecha de terminación',
                                'N.° de serie': 'N° de serie del Monitor', 'Sucursal': 'Sucursal'
                            }
                            cols_validas = [c for c in columnas_mapeo_uso.keys() if c in df_sin_uso.columns]
                            df_display_uso = df_sin_uso[cols_validas].copy().rename(columns=columnas_mapeo_uso)
                            
                            orden_columnas_uso = ['Número de licencia', 'Organización', 'Nombre de licencia', 'Fecha de terminación', 'N° de serie del Monitor', 'Sucursal']
                            orden_final_uso = [c for c in orden_columnas_uso if c in df_display_uso.columns]
                            df_display_uso = df_display_uso[orden_final_uso]
                            
                            st.error(f"🚨 Se detectaron {len(df_display_uso)} licencias sin reportar actividad en la última actualización del {ultima_fecha_uso.strftime('%d/%m/%Y')}.")
                            st.dataframe(df_display_uso, use_container_width=True, hide_index=True)
                        else:
                            st.success("🎉 ¡Excelente! Todas las licencias que coinciden con los filtros aplicados registran uso en la última actualización.")

    # ---------------------------------------------------------
    # TAB 1: TERMÓMETRO GENERAL
    # ---------------------------------------------------------
    with tab1:
        with st.expander("📖 Metodología y Definiciones del Dashboard"):
            st.markdown("""
            ### 🛠️ ¿Qué es una Máquina Apta?
            * **Hardware:** Gen 4 (4200/4600/4240/4640) o G5.
            * **Software:** Versión **23-3** o superior.
            ### 📊 Tiers
            * **Tier 1:** Uso de **AutoTrac™**.
            * **Tier 2:** Promedio de **AutoPath™, ATTA, Guiado Pasivo y Machine Sync**.
            """)

        if not df_latest.empty:
            st.info(f"📅 Reporte al cierre: {ultima_fecha.strftime('%d/%m/%Y')}")

            t2_avgs_list = [df_aptas_latest[cols].mean().mean() for cols in dict_t2.values() if cols]
            kpi_t2_prom_prom = np.nanmean(t2_avgs_list) if t2_avgs_list else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Flota Periodo", len(df_latest))
            m2.metric("Equipos Aptos", len(df_aptas_latest))
            m3.metric("Uso AutoTrac™ (T1)", f"{df_aptas_latest['Tier_1'].mean():.1f}%")
            m4.metric("Uso Avanzado (T2)", f"{kpi_t2_prom_prom:.1f}%")

            st.divider()
            c_ga, c_gb = st.columns(2)
            with c_ga:
                st.subheader("Adopción por Tipo")
                if not df_aptas_latest.empty:
                    st.bar_chart(df_aptas_latest.groupby('Tipo')[['Tier_1', 'Tier_2']].mean())
            with c_gb:
                st.subheader("Relación T1 vs T2")
                if not df_aptas_latest.empty:
                    st.scatter_chart(df_aptas_latest, x='Tier_1', y='Tier_2', color='Tipo')

            st.subheader("Estrategia de Foco")
            with st.expander("🔍 Clientes con Brecha Real (T1 Alto / T2 ≥ 1%)", expanded=True):
                f_b = df_aptas_latest[df_aptas_latest['Tier_2'] >= 1.0].copy()
                if not f_b.empty:
                    f_b['Brecha'] = f_b['Tier_1'].fillna(0) - f_b['Tier_2'].fillna(0)
                    res_brecha = f_b[f_b['Brecha'] > 0][
                        ['Organización', 'Modelo', 'Tipo', 'Tier_1', 'Tier_2', 'Brecha', 'Sucursal']].sort_values(
                        'Brecha', ascending=False)
                    st.dataframe(
                        res_brecha.style.format({'Tier_1': '{:.1f}%', 'Tier_2': '{:.1f}%', 'Brecha': '{:.1f}%'}),
                        use_container_width=True)

            st.subheader("Foco: Organizaciones en Adopción Inicial (Tier 2 entre 1% y 10%)")
            foco_inicial = df_aptas_latest[
                (df_aptas_latest['Tier_2'] >= 1.0) & (df_aptas_latest['Tier_2'] <= 10.0)].copy()
            if not foco_inicial.empty:
                st.dataframe(
                    foco_inicial[['Organización', 'Modelo', 'Tipo', 'Tier_1', 'Tier_2', 'Sucursal']].sort_values(
                        'Tier_2', ascending=False).style.format({'Tier_1': '{:.1f}%', 'Tier_2': '{:.1f}%'}),
                    use_container_width=True)
                col_t1, col_t2 = st.columns(2)
                with col_t1: 
                    st.plotly_chart(px.pie(foco_inicial, names='Tipo', title='Tipos (Adopción Inicial)', hole=0.4), use_container_width=True)
                with col_t2: 
                    st.plotly_chart(px.pie(foco_inicial, names='Modelo', title='Modelos (Adopción Inicial)', hole=0.4), use_container_width=True)

    # ---------------------------------------------------------
    # TAB 2: ANÁLISIS TIER 1
    # ---------------------------------------------------------
    with tab2:
        st.header("Profundización en Tier 1: AutoTrac™")
        if not df_aptas_latest.empty:
            st.metric(label="Uso Promedio AutoTrac™ (Últ. Fecha)", value=f"{df_aptas_latest['Tier_1'].mean():.1f}%")
            st.subheader("Uso de AutoTrac™ por Tipo de Maquinaria")
            df_at_tipo = df_aptas_latest.groupby('Tipo')['Tier_1'].mean().reset_index().sort_values('Tier_1', ascending=False)
            st.plotly_chart(px.bar(df_at_tipo, x='Tipo', y='Tier_1', text_auto='.1f', color='Tier_1',
                                   color_continuous_scale='Greens'), use_container_width=True)
            st.divider()
            st.subheader("📋 Ranking por Unidad (Última Actualización)")
            rango_uso = st.slider("Filtrar por nivel de avance de AutoTrac™ (%)", 0.0, 100.0, (0.0, 100.0), step=5.0)
            col_serie = next(
                (c for c in df_aptas_latest.columns if any(k in c.lower() for k in ['serie', 'pin', 'nro'])),
                'Número de serie')
            df_ranking = df_aptas_latest[(df_aptas_latest['Tier_1'].fillna(0) >= rango_uso[0]) & (
                    df_aptas_latest['Tier_1'].fillna(0) <= rango_uso[1])].copy()
            st.dataframe(df_ranking[['Organización', 'Modelo', col_serie, 'Tier_1', 'Sucursal']].sort_values('Tier_1', ascending=False).style.format(
                {'Tier_1': '{:.1f}%'}), use_container_width=True)
            st.divider()
            df_hist_aptas = df_full[df_full['Es_Apta'] == True].copy()
            df_evol = df_hist_aptas.groupby('Fecha de terminación').agg(Promedio_Tier_1=('Tier_1', 'mean'),
                                                                       Cant_Maquinas=('Tier_1', 'count')).reset_index().sort_values('Fecha de terminación')
            fig_hist = go.Figure()
            fig_hist.add_trace(
                go.Bar(x=df_evol['Fecha de terminación'], y=df_evol['Cant_Maquinas'], name='Nro. Máquinas',
                       marker_color='rgba(46, 139, 87, 0.6)', yaxis='y'))
            fig_hist.add_trace(
                go.Scatter(x=df_evol['Fecha de terminación'], y=df_evol['Promedio_Tier_1'], name='% Uso Promedio',
                           line=dict(color='orange', width=4), yaxis='y2'))
            fig_hist.update_layout(xaxis=dict(title='Fecha de Cierre'),
                                   yaxis=dict(title='Cantidad de Máquinas', side='left'),
                                   yaxis2=dict(title='Uso Promedio (%)', side='right', overlaying='y', range=[0, 100]),
                                   legend=dict(x=0, y=1.1, orientation='h'), hovermode='x unified')
            st.plotly_chart(fig_hist, use_container_width=True)

    # ---------------------------------------------------------
    # TAB 3: ANÁLISIS TIER 2
    # ---------------------------------------------------------
    with tab3:
        st.header("🚀 Análisis Tier 2: Tecnologías Avanzadas")
        sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs(
            ["General Avanzado", "Potenciales Machine Sync", "Potenciales AutoPath", "Potenciales ATTA"])

        with sub_tab1:
            if not df_aptas_latest.empty:
                tech_averages = {name: df_aptas_latest[cols].mean().mean() for name, cols in dict_t2.items() if cols}
                prom_t2_final = np.nanmean(list(tech_averages.values())) if tech_averages else 0
                st.metric(label="Uso Promedio Paquete Tier 2 (Media de Tecnologías)", value=f"{prom_t2_final:.1f}%")
                st.divider()
                st.subheader("Desglose por Tecnología")
                cols_metrics = st.columns(len(tech_averages))
                for i, (name, val) in enumerate(tech_averages.items()):
                    cols_metrics[i].metric(name, f"{val:.1f}%")
                st.divider()
                st.subheader("Uso por Tipo de Máquina")
                t_list = []
                for n, c in dict_t2.items():
                    if c:
                        td = df_aptas_latest.groupby('Tipo')[c].mean().mean(axis=1).reset_index()
                        td['Tecnología'] = n
                        td.columns = ['Tipo', 'Uso (%)', 'Tecnología']
                        t_list.append(td)
                if t_list: 
                    st.plotly_chart(px.bar(pd.concat(t_list), x='Tipo', y='Uso (%)', color='Tecnología', barmode='group',
                                           text_auto='.1f', color_discrete_sequence=px.colors.qualitative.Prism), use_container_width=True)

                st.divider()
                st.subheader("Detalle por Unidad")
                fs1, fs2, fs3, fs4 = st.columns(4)
                with fs1: r_ap = st.slider("AutoPath (%)", 0.0, 100.0, (0.0, 100.0), key="s_ap")
                with fs2: r_atta = st.slider("ATTA (%)", 0.0, 100.0, (0.0, 100.0), key="s_atta")
                with fs3: r_gp = st.slider("Guiado Pasivo (%)", 0.0, 100.0, (0.0, 100.0), key="s_gp")
                with fs4: r_ms = st.slider("Machine Sync (%)", 0.0, 100.0, (0.0, 100.0), key="s_ms")

                col_s = next((c for c in df_aptas_latest.columns if any(k in c.lower() for k in ['serie', 'pin'])), 'Número de serie')
                df_det = df_aptas_latest[['Organización', 'Modelo', col_s]].copy()
                for t, cs in dict_t2.items(): 
                    df_det[t] = df_aptas_latest[cs].mean(axis=1) if cs else 0
                df_det_f = df_det[
                    (df_det['AutoPath'].fillna(0) >= r_ap[0]) & (df_det['AutoPath'].fillna(0) <= r_ap[1]) & (
                            df_det['ATTA (Maniobras)'].fillna(0) >= r_atta[0]) & (
                            df_det['ATTA (Maniobras)'].fillna(0) <= r_atta[1]) & (
                            df_det['Guiado Pasivo'].fillna(0) >= r_gp[0]) & (
                            df_det['Guiado Pasivo'].fillna(0) <= r_gp[1]) & (
                            df_det['Machine Sync'].fillna(0) >= r_ms[0]) & (
                            df_det['Machine Sync'].fillna(0) <= r_ms[1])].dropna(subset=list(dict_t2.keys()), how='all')
                st.dataframe(df_det_f.sort_values('Organización').style.format({t: '{:.1f}%' for t in dict_t2.keys()}, na_rep='0.0%'), use_container_width=True)

                st.divider()
                st.subheader("📈 Evolución Histórica Tier 2")
                df_hist_aptas = df_full[df_full['Es_Apta'] == True].copy()

                st.write("#### Evolución General del Paquete")
                df_ev_t2_gen = df_hist_aptas.groupby('Fecha de terminación').agg(Uso=('Tier_2', 'mean'), Cant=('Tier_2', 'count')).reset_index().sort_values('Fecha de terminación')
                fig_gen = go.Figure()
                fig_gen.add_trace(
                    go.Bar(x=df_ev_t2_gen['Fecha de terminación'], y=df_ev_t2_gen['Cant'], name='Máquinas',
                           marker_color='rgba(158, 202, 225, 0.6)', yaxis='y'))
                fig_gen.add_trace(go.Scatter(x=df_ev_t2_gen['Fecha de terminación'], y=df_ev_t2_gen['Uso'],
                                             name='% Uso Promedio Tier 2', line=dict(color='purple', width=4), yaxis='y2'))
                fig_gen.update_layout(yaxis2=dict(overlaying='y', side='right', range=[0, 100]), hovermode='x unified')
                st.plotly_chart(fig_gen, use_container_width=True)

                st.write("#### Evolución por Tecnología Individual")
                c1, c2 = st.columns(2)
                c3, c4 = st.columns(2)
                cols_g = [c1, c2, c3, c4]
                for i, (t_name, c_list) in enumerate(dict_t2.items()):
                    if c_list:
                        df_ev_ind = df_hist_aptas.groupby('Fecha de terminación').agg(Uso=(c_list[0], 'mean'), Cant=(c_list[0], 'count')).reset_index()
                        fig_ind = go.Figure()
                        fig_ind.add_trace(
                            go.Bar(x=df_ev_ind['Fecha de terminación'], y=df_ev_ind['Cant'], name='Máquinas',
                                   marker_color='rgba(31, 119, 180, 0.6)', yaxis='y'))
                        fig_ind.add_trace(
                            go.Scatter(x=df_ev_ind['Fecha de terminación'], y=df_ev_ind['Uso'], name='% Uso',
                                       line=dict(color='firebrick', width=3), yaxis='y2'))
                        fig_ind.update_layout(title=f"{t_name}", yaxis2=dict(overlaying='y', side='right', range=[0, 100]), height=350)
                        cols_g[i].plotly_chart(fig_ind, use_container_width=True)

        with sub_tab2:
            st.subheader("🎯 Potenciales Machine Sync")
            trac_ms_list = ['7M 200', '7M 215', '7M 230', '7230R']
            cos_models = ['S760', 'S770', 'S780', 'S790', 'S7 600', 'S7 700', 'S7 800', 'S7 900']
            df_ms_cos = df_aptas_latest[(df_aptas_latest['Tipo'] == 'Cosechadora') & (df_aptas_latest['Modelo'].isin(cos_models))]
            df_ms_trac = df_aptas_latest[(df_aptas_latest['Tipo'] == 'Tractor') & (df_aptas_latest['Modelo'].isin(trac_ms_list))]
            if not df_ms_cos.empty and not df_ms_trac.empty:
                col_sync = dict_t2['Machine Sync'][0] if dict_t2['Machine Sync'] else None
                df_m_ms = pd.merge(df_ms_cos[['Organización', 'Modelo', col_sync, 'Sucursal']].rename(
                    columns={'Modelo': 'Cosechadora', col_sync: 'Machine Sync (%)'}),
                    df_ms_trac[['Organización', 'Modelo']].rename(columns={'Modelo': 'Tractor'}),
                    on='Organización').drop_duplicates()
                if not df_m_ms.empty:
                    st.dataframe(df_m_ms.style.apply(lambda r: ['background-color: #ffcccc' if (
                                pd.isna(r['Machine Sync (%)']) or r['Machine Sync (%)'] < 1.0) else 'background-color: #ccffcc'] * len(r), axis=1).format(
                        {'Machine Sync (%)': '{:.1f}%'}, na_rep='0.0%'), use_container_width=True)

                    col_b, col_p = st.columns(2)
                    with col_b:
                        df_pot_ms = df_m_ms[df_m_ms['Machine Sync (%)'].fillna(0) < 1.0]
                        if not df_pot_ms.empty:
                            df_chart_ms = df_pot_ms.groupby('Sucursal')['Organización'].nunique().reset_index(name='Cant. Organizaciones')
                            st.plotly_chart(
                                px.bar(df_chart_ms.sort_values('Cant. Organizaciones', ascending=False), x='Sucursal',
                                       y='Cant. Organizaciones', title='Potenciales por Sucursal (Sync)',
                                       text_auto=True, color='Sucursal'), use_container_width=True)
                    with col_p:
                        df_pie = df_m_ms.drop_duplicates('Organización').copy()
                        df_pie['Estado'] = np.where(df_pie['Machine Sync (%)'] >= 1.0, 'Con Uso', 'Potencial')
                        fig_ms_pie = px.pie(df_pie, names='Estado', title='Estado de Adopción (Total Orgs)', hole=0.4,
                                            color_discrete_map={'Con Uso': '#2ca02c', 'Potencial': '#d62728'})
                        st.plotly_chart(fig_ms_pie, use_container_width=True)
                else:
                    st.info("No se encontraron coincidencias en la última actualización.")

        with sub_tab3:
            st.subheader("🎯 Potenciales AutoPath™")
            trac_ap_list = ['7M 200', '7M 215', '7M 230', '7200J', '7210J', '7215J', '7230J', '7230R', '8245R', '8250R',
                            '8270R', '8295R', '8320R', '8335R', '8345R', '8370R', '8370RT', '8400R', '9420R', '9470R',
                            '9520R', '9570R', '9R 390']
            pulv_models = ['M4025', 'M4030', 'M4040', '4730']
            df_ap_trac = df_aptas_latest[(df_aptas_latest['Tipo'] == 'Tractor') & (df_aptas_latest['Modelo'].isin(trac_ap_list))]
            df_ap_pulv = df_aptas_latest[(df_aptas_latest['Tipo'] == 'Pulverizadora') & (df_aptas_latest['Modelo'].isin(pulv_models))]
            if not df_ap_trac.empty and not df_ap_pulv.empty:
                col_ap = dict_t2['AutoPath'][0] if dict_t2['AutoPath'] else None
                df_m_ap = pd.merge(df_ap_trac[['Organización', 'Modelo']].rename(columns={'Modelo': 'Tractor'}),
                                   df_ap_pulv[['Organización', 'Modelo', col_ap, 'Sucursal']].rename(
                                       columns={'Modelo': 'Pulverizadora', col_ap: 'AutoPath (%)'}),
                                   on='Organización').drop_duplicates()
                if not df_m_ap.empty:
                    st.dataframe(df_m_ap.style.apply(lambda r: ['background-color: #ffcccc' if (
                                pd.isna(r['AutoPath (%)']) or r['AutoPath (%)'] < 1.0) else 'background-color: #ccffcc'] * len(r), axis=1).format(
                        {'AutoPath (%)': '{:.1f}%'}, na_rep='0.0%'), use_container_width=True)

                    col_b, col_p = st.columns(2)
                    with col_b:
                        df_pot_ap = df_m_ap[df_m_ap['AutoPath (%)'].fillna(0) < 1.0]
                        if not df_pot_ap.empty:
                            df_chart_ap = df_pot_ap.groupby('Sucursal')['Organización'].nunique().reset_index(name='Cant. Organizaciones')
                            st.plotly_chart(
                                px.bar(df_chart_ap.sort_values('Cant. Organizaciones', ascending=False), x='Sucursal',
                                       y='Cant. Organizaciones', title='Potenciales por Sucursal (AutoPath)',
                                       text_auto=True, color='Sucursal'), use_container_width=True)
                    with col_p:
                        df_pie_ap = df_m_ap.drop_duplicates('Organización').copy()
                        df_pie_ap['Estado'] = np.where(df_pie_ap['AutoPath (%)'] >= 1.0, 'Con Uso', 'Potencial')
                        fig_ap_pie = px.pie(df_pie_ap, names='Estado', title='Estado de Adopción (Total Orgs)',
                                            hole=0.4, color_discrete_map={'Con Uso': '#2ca02c', 'Potencial': '#d62728'})
                        st.plotly_chart(fig_ap_pie, use_container_width=True)
                else:
                    st.info("No se encontraron coincidencias en la última actualización.")

        with sub_tab4:
            st.subheader("🎯 Potenciales ATTA (Maniobras)")
            atta_models = ['S790', 'S780', 'S770', 'S760', 'S7 900', 'S7 800', 'S7 700', 'S7 600', '7M 200', '7M 215',
                           '7M 230', '8245R', '8250R', '8270R', '8295R', '8320R', '8335R', '8345R', '8370R', '8370RT',
                           '8400R', '9R390', '9R 390', 'M4040', 'M4030', 'M4025']
            df_atta_pot = df_aptas_latest[df_aptas_latest['Modelo'].isin(atta_models)].copy()
            if not df_atta_pot.empty:
                col_atta = dict_t2['ATTA (Maniobras)'][0] if dict_t2['ATTA (Maniobras)'] else None
                st.dataframe(df_atta_pot[['Organización', 'Modelo', col_atta, 'Sucursal']].rename(
                    columns={col_atta: 'ATTA (%)'}).style.apply(lambda r: ['background-color: #ffcccc' if (
                            pd.isna(r['ATTA (%)']) or r['ATTA (%)'] < 1.0) else 'background-color: #ccffcc'] * len(r),
                                                                axis=1).format({'ATTA (%)': '{:.1f}%'}, na_rep='0.0%'),
                             use_container_width=True)

                col_b, col_p = st.columns(2)
                with col_b:
                    df_pot_atta = df_atta_pot[df_atta_pot[col_atta].fillna(0) < 1.0]
                    if not df_pot_atta.empty:
                        df_ch_atta = df_pot_atta.groupby('Sucursal')['Organización'].nunique().reset_index(name='Cant. Orgs')
                        st.plotly_chart(
                            px.bar(df_ch_atta.sort_values('Cant. Orgs', ascending=False), x='Sucursal', y='Cant. Orgs',
                                   title='Potenciales por Sucursal (ATTA)', text_auto=True, color='Sucursal'),
                            use_container_width=True)
                with col_p:
                    df_pie_att = df_atta_pot.drop_duplicates('Organización').copy()
                    df_pie_att['Estado'] = np.where(df_pie_att[col_atta] >= 1.0, 'Con Uso', 'Potencial')
                    fig_att_pie = px.pie(df_pie_att, names='Estado', title='Estado de Adopción (Total Orgs)', hole=0.4,
                                         color_discrete_map={'Con Uso': '#2ca02c', 'Potencial': '#d62728'})
                    st.plotly_chart(fig_att_pie, use_container_width=True)

    # ---------------------------------------------------------
    # TAB 4: COSECHADORAS
    # ---------------------------------------------------------
    with tab4:
        st.header("Análisis Específico de Cosechadoras")
        sub_tab_s7, sub_tab_s700 = st.tabs(["Serie S7", "Serie S700"])

        with sub_tab_s7:
            st.subheader("Desempeño Serie S7")
            models_s7 = ['S7 900', 'S7 800', 'S7 700', 'S7 600']
            df_s7 = df_aptas_latest[df_aptas_latest['Modelo'].isin(models_s7)].copy()

            if not df_s7.empty:
                col_ajustes = 'Automatización de ajustes de cosecha Activo (%)'
                col_velocidad = 'Automatización de la velocidad de avance Activo (%)'
                col_atta_s7 = 'Automatización de maniobras AutoTrac™ Activo (%)'

                # KPIs
                k1, k2, k3 = st.columns(3)
                k1.metric("Ajustes Cosecha", f"{df_s7[col_ajustes].mean():.1f}%")
                k2.metric("Velocidad Avance", f"{df_s7[col_velocidad].mean():.1f}%")
                k3.metric("Maniobras ATTA", f"{df_s7[col_atta_s7].mean():.1f}%")

                st.divider()
                st.write("**Detalle Unidades S7 (Semáforo)**")

                def aplicar_semaforo_s7(row):
                    styles = [''] * len(row)
                    v = row[col_velocidad]
                    if pd.isna(v) or v < 50:
                        styles[3] = 'background-color: #ffcccc'  # Rojo
                    elif 50 <= v <= 60:
                        styles[3] = 'background-color: #ffffcc'  # Amarillo
                    a = row[col_atta_s7]
                    if pd.isna(a) or a < 15: 
                        styles[4] = 'background-color: #ffcccc'  # Rojo
                    return styles

                st.dataframe(
                    df_s7[['Organización', 'Modelo', col_ajustes, col_velocidad, col_atta_s7, 'Sucursal']]
                    .sort_values('Organización')
                    .style.apply(aplicar_semaforo_s7, axis=1)
                    .format({col_ajustes: '{:.1f}%', col_velocidad: '{:.1f}%', col_atta_s7: '{:.1f}%'}, na_rep='0.0%'),
                    use_container_width=True)

                st.divider()
                st.write("📈 **Evolución Histórica Serie S7**")
                df_hist_s7 = df_full[(df_full['Es_Apta'] == True) & (df_full['Modelo'].isin(models_s7))].copy()
                df_ev_s7 = df_hist_s7.groupby('Fecha de terminación').agg(
                    Ajustes=(col_ajustes, 'mean'),
                    Velocidad=(col_velocidad, 'mean'),
                    ATTA=(col_atta_s7, 'mean'),
                    Cant=(col_ajustes, 'count')
                ).reset_index().sort_values('Fecha de terminación')

                fig_s7 = go.Figure()
                fig_s7.add_trace(go.Bar(x=df_ev_s7['Fecha de terminación'], y=df_ev_s7['Cant'], name='Máquinas',
                                        marker_color='rgba(200, 200, 200, 0.5)', yaxis='y'))
                fig_s7.add_trace(go.Scatter(x=df_ev_s7['Fecha de terminación'], y=df_ev_s7['Ajustes'], name='% Ajustes',
                                            line=dict(width=3), yaxis='y2'))
                fig_s7.add_trace(go.Scatter(x=df_ev_s7['Fecha de terminación'], y=df_ev_s7['Velocidad'], name='% Velocidad',
                                            line=dict(width=3), yaxis='y2'))
                fig_s7.add_trace(go.Scatter(x=df_ev_s7['Fecha de terminación'], y=df_ev_s7['ATTA'], name='% ATTA',
                                            line=dict(width=3), yaxis='y2'))
                fig_s7.update_layout(yaxis2=dict(overlaying='y', side='right', range=[0, 100]), hovermode='x unified', height=450)
                st.plotly_chart(fig_s7, use_container_width=True)

                # --- TORTAS DE ADOPCIÓN POR ORGANIZACIÓN ---
                st.divider()
                st.write("**Nivel de Adopción por Organización (S7)**")
                col_t1, col_t2 = st.columns(2)

                with col_t1:
                    df_org_vel = df_s7.groupby('Organización')[col_velocidad].max().reset_index()
                    df_org_vel['Estado'] = np.where(df_org_vel[col_velocidad] >= 50, 'Uso Óptimo (>50%)', 'Bajo Uso (<50%)')
                    fig_pie_vel = px.pie(df_org_vel, names='Estado', title='Org. con Automatización de Velocidad',
                                         hole=0.4, color_discrete_map={'Uso Óptimo (>50%)': '#2ca02c', 'Bajo Uso (<50%)': '#d62728'})
                    st.plotly_chart(fig_pie_vel, use_container_width=True)

                with col_t2:
                    df_org_atta = df_s7.groupby('Organización')[col_atta_s7].max().reset_index()
                    df_org_atta['Estado'] = np.where(df_org_atta[col_atta_s7] >= 15, 'Uso Óptimo (>15%)', 'Bajo Uso (<15%)')
                    fig_pie_atta = px.pie(df_org_atta, names='Estado', title='Org. con Automatización de Maniobras (ATTA)',
                                          hole=0.4, color_discrete_map={'Uso Óptimo (>15%)': '#2ca02c', 'Bajo Uso (<15%)': '#d62728'})
                    st.plotly_chart(fig_pie_atta, use_container_width=True)
            else:
                st.info("No hay modelos S7 registrados.")

        with sub_tab_s700:
            st.subheader("Desempeño Serie S700")
            models_s700 = ['S790', 'S780', 'S770', 'S760']
            df_s700 = df_aptas_latest[df_aptas_latest['Modelo'].isin(models_s700)].copy()

            if not df_s700.empty:
                col_maintain = 'Auto Maintain Activado (%)'
                col_harvest = 'Harvest Smart Activado (%)'

                # KPIs
                k1, k2 = st.columns(2)
                k1.metric("Auto Maintain", f"{df_s700[col_maintain].mean():.1f}%")
                k2.metric("Harvest Smart", f"{df_s700[col_harvest].mean():.1f}%")

                st.divider()
                st.write("**Detalle Unidades S700**")
                st.dataframe(df_s700[['Organización', 'Modelo', col_maintain, col_harvest, 'Sucursal']].sort_values(
                    'Organización').style.format({col_maintain: '{:.1f}%', col_harvest: '{:.1f}%'}, na_rep='0.0%'),
                             use_container_width=True)
            else:
                st.info("No hay modelos S700 registrados.")

        # ---------------------------------------------------------
        # TAB 5: PULVERIZADORAS
        # ---------------------------------------------------------
        with tab5:
            st.header("💧 Análisis CropCare")

            # 1. Filtrado por tipo de maquinaria usando tu DataFrame base filtrado por fechas
            df_pulv = df_full[df_full['Tipo'].str.upper() == 'PULVERIZADORA'].copy()

            if df_pulv.empty:
                st.warning("No se encontraron registros de 'Pulverizadora' para el período o filtros seleccionados.")
            else:
                col_pulsacion = 'Pulsación Activo (%)'
                col_secciones = 'Tiempo de control de secciones Activo (%)'
                col_at_pulv = 'Tier_1'  # Columna de AutoTrac calculada previamente en tu script global

                # Identificamos la última fecha disponible específicamente para pulverizadoras
                ultima_fecha_pulv = df_pulv['Fecha de terminación'].max()
                df_pulv_actual = df_pulv[df_pulv['Fecha de terminación'] == ultima_fecha_pulv]

                fecha_formateada = ultima_fecha_pulv.strftime('%d/%m/%Y') if pd.notnull(ultima_fecha_pulv) else "N/A"
                st.subheader(f"📊 Resumen Actual (Última Fecha: {fecha_formateada})")

                # 2. Cálculo de Promedios Actuales y Totales de Flota
                promedio_pulsacion = df_pulv_actual[col_pulsacion].mean()
                promedio_secciones = df_pulv_actual[col_secciones].mean()
                promedio_autotrac = df_pulv_actual[col_at_pulv].mean()
                total_pulverizadoras_actual = len(df_pulv_actual)  # Flota total de la última fecha (debería dar 91)

                col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
                with col_kpi1:
                    st.metric(label="Pulverizadoras Totales", value=total_pulverizadoras_actual)

                with col_kpi2:
                    val_autotrac = f"{promedio_autotrac:.1f}%" if pd.notnull(promedio_autotrac) else "Sin Datos"
                    st.metric(label="Promedio AutoTrac™ (Tier 1)", value=val_autotrac)

                with col_kpi3:
                    val_secciones = f"{promedio_secciones:.1f}%" if pd.notnull(promedio_secciones) else "Sin Datos"
                    st.metric(label="Promedio Control de Secciones", value=val_secciones)

                with col_kpi4:
                    val_pulsacion = f"{promedio_pulsacion:.1f}%" if pd.notnull(promedio_pulsacion) else "Sin Datos"
                    st.metric(label="Promedio Pulsación Activo", value=val_pulsacion)

                st.divider()

                # 3. Tabla de uso individual por equipo en el período actual
                st.subheader("Uso Individual por Pulverizadora (Último Reporte)")
                col_serie_pulv = next(
                    (c for c in df_pulv_actual.columns if any(k in c.lower() for k in ['serie', 'pin'])),
                    'Número de serie de la máquina')

                tabla_individual = df_pulv_actual[[
                    'Organización', 'Modelo', col_serie_pulv, col_at_pulv, col_pulsacion, col_secciones, 'Sucursal'
                ]].copy()

                st.dataframe(
                    tabla_individual.sort_values('Organización')
                    .style.format({col_at_pulv: '{:.1f}%', col_pulsacion: '{:.1f}%', col_secciones: '{:.1f}%'},
                                  na_rep='N/D'),
                    use_container_width=True
                )

                st.divider()

                # 4. Histórico de adopción (Gráfico mixto: Uso % vs Cantidad de Máquinas con AutoTrac)
                st.subheader("📈 Evolución Histórica del Uso de Tecnología")

                # Cant_Maquinas considera únicamente las filas con registros válidos de AutoTrac (Tier_1)
                df_hist_tendencia = df_pulv.groupby('Fecha de terminación').agg(
                    Prom_Pulsacion=(col_pulsacion, 'mean'),
                    Prom_Secciones=(col_secciones, 'mean'),
                    Prom_AutoTrac=(col_at_pulv, 'mean'),
                    Cant_Maquinas=(col_at_pulv, 'count')
                ).reset_index().sort_values('Fecha de terminación')

                if not df_hist_tendencia.empty:
                    fig_pulv_hist = go.Figure()

                    # Barras para la cantidad de máquinas pulverizadoras con AutoTrac (Eje Y izquierdo)
                    fig_pulv_hist.add_trace(
                        go.Bar(
                            x=df_hist_tendencia['Fecha de terminación'],
                            y=df_hist_tendencia['Cant_Maquinas'],
                            name='Equipos con AutoTrac',
                            marker_color='rgba(180, 180, 180, 0.4)',
                            yaxis='y'
                        )
                    )

                    # Línea para el histórico de Pulsación (Eje Y derecho)
                    fig_pulv_hist.add_trace(
                        go.Scatter(
                            x=df_hist_tendencia['Fecha de terminación'],
                            y=df_hist_tendencia['Prom_Pulsacion'],
                            name='% Pulsación Activo',
                            line=dict(color='#2ca02c', width=3),
                            yaxis='y2'
                        )
                    )

                    # Línea para el histórico de Control de Secciones (Eje Y derecho)
                    fig_pulv_hist.add_trace(
                        go.Scatter(
                            x=df_hist_tendencia['Fecha de terminación'],
                            y=df_hist_tendencia['Prom_Secciones'],
                            name='% Control de Secciones',
                            line=dict(color='#9467bd', width=3),
                            yaxis='y2'
                        )
                    )

                    # Línea para el histórico de AutoTrac (Eje Y derecho)
                    fig_pulv_hist.add_trace(
                        go.Scatter(
                            x=df_hist_tendencia['Fecha de terminación'],
                            y=df_hist_tendencia['Prom_AutoTrac'],
                            name='% AutoTrac™',
                            line=dict(color='orange', width=3),
                            yaxis='y2'
                        )
                    )

                    # Configuración de los dos ejes Y y el diseño
                    fig_pulv_hist.update_layout(
                        xaxis=dict(title='Fecha de Cierre'),
                        yaxis=dict(title='Cantidad de Equipos con AutoTrac', side='left'),
                        yaxis2=dict(title='Uso Promedio (%)', side='right', overlaying='y', range=[0, 100]),
                        legend=dict(x=0, y=1.1, orientation='h'),
                        hovermode='x unified',
                        height=450
                    )

                    st.plotly_chart(fig_pulv_hist, use_container_width=True)

                st.divider()

                # 5. Gráficos de Torta: Adopción por Tecnología con Hover Corregido
                st.subheader("🎯 Estado de Adopción por Tecnología (Último Reporte)")

                if not df_pulv_actual.empty:
                    col_pie1, col_pie2, col_pie3 = st.columns(3)
                    mapa_colores = {'Con Uso': '#2ca02c', 'Sin Datos / Bajo Uso': '#d62728'}

                    with col_pie1:
                        df_pie_at = df_pulv_actual.copy()
                        df_pie_at['Estado_AT'] = np.where(
                            df_pie_at[col_at_pulv].notnull() & (df_pie_at[col_at_pulv] >= 1.0), 'Con Uso',
                            'Sin Datos / Bajo Uso')

                        df_counts_at = df_pie_at.groupby('Estado_AT').size().reset_index(name='Cant. Equip')

                        fig_pie_at = px.pie(df_counts_at, names='Estado_AT', values='Cant. Equip',
                                            title='Equipos con AutoTrac™',
                                            hole=0.4, color='Estado_AT', color_discrete_map=mapa_colores)

                        # CORRECCIÓN: Eliminado 'hoisttext' y configurado el template del hover interactivo
                        fig_pie_at.update_traces(textinfo='percent+label',
                                                 hovertemplate="<b>%{label}</b><br>Cantidad: %{value}<br>Porcentaje: %{percent}<extra></extra>")
                        st.plotly_chart(fig_pie_at, use_container_width=True)

                    with col_pie2:
                        df_pie_sec = df_pulv_actual.copy()
                        df_pie_sec['Estado_Sec'] = np.where(
                            df_pie_sec[col_secciones].notnull() & (df_pie_sec[col_secciones] >= 1.0), 'Con Uso',
                            'Sin Datos / Bajo Uso')

                        df_counts_sec = df_pie_sec.groupby('Estado_Sec').size().reset_index(name='Cant. Equip')

                        fig_pie_sec = px.pie(df_counts_sec, names='Estado_Sec', values='Cant. Equip',
                                             title='Equipos con Control de Secciones',
                                             hole=0.4, color='Estado_Sec', color_discrete_map=mapa_colores)

                        fig_pie_sec.update_traces(textinfo='percent+label',
                                                  hovertemplate="<b>%{label}</b><br>Cantidad: %{value}<br>Porcentaje: %{percent}<extra></extra>")
                        st.plotly_chart(fig_pie_sec, use_container_width=True)

                    with col_pie3:
                        df_pie_puls = df_pulv_actual.copy()
                        df_pie_puls['Estado_Puls'] = np.where(
                            df_pie_puls[col_pulsacion].notnull() & (df_pie_puls[col_pulsacion] >= 1.0), 'Con Uso',
                            'Sin Datos / Bajo Uso')

                        df_counts_puls = df_pie_puls.groupby('Estado_Puls').size().reset_index(name='Cant. Equip')

                        fig_pie_puls = px.pie(df_counts_puls, names='Estado_Puls', values='Cant. Equip',
                                              title='Equipos con ExactApply (Pulsación)',
                                              hole=0.4, color='Estado_Puls', color_discrete_map=mapa_colores)

                        fig_pie_puls.update_traces(textinfo='percent+label',
                                                   hovertemplate="<b>%{label}</b><br>Cantidad: %{value}<br>Porcentaje: %{percent}<extra></extra>")
                        st.plotly_chart(fig_pie_puls, use_container_width=True)
                        
else:
    st.info("👋 ¡Hola Suyai! No se detectaron datos cargados automáticamente. Si la conexión a la nube falló, usá el cargador manual de la barra lateral.")
