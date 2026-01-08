## LIBRERIAS
import requests
import pandas as pd
import numpy as np
import warnings
import streamlit as st
import plotly.express as px

# FUNCIONES

# Funcion para cargar y limpiar datos
def cargar_csv(ruta):
    # Intento con 2 encoding
    try:
        df = pd.read_csv(ruta, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(ruta, encoding="latin-1")
    

    #Normalizo primera columna
    df.rename(columns={df.columns[0]: "fecha"}, inplace=True)
    # Corrijo fechas
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce",dayfirst=True)
    # Establezco fecha como indice
    df = df.set_index("fecha").sort_index()

    # Gener los Nan cuando no hay dato
    df = df.apply(pd.to_numeric, errors="coerce")

    #NAN INICIALES
    # Ubico la primera fecha donde hay dato
    primera_fecha_valida = df.dropna(how="any").index.min()
    #Corto df a partir de ahi
    if primera_fecha_valida is not None:
        df = df.loc[primera_fecha_valida:]

    # Advertencia por poca información si parte de 2024
    if primera_fecha_valida is not None and primera_fecha_valida.year >= 2024:
        warnings.warn(
            "Poca información disponible tras el corte inicial",
            UserWarning
        )

    # Manejo de Nan posteriores
    for col in df.columns:
        # Lista de booleanos donde es nan
        is_na = df[col].isna()

        # Detectar rachas consecutivas
        # Convierto la lista a numerico para poder sumar por grupos generados donde no es nan con suma acumulativa
        rachas = (is_na.astype(int).groupby(is_na.ne(is_na.shift()).cumsum()).sum())

        # Si hay más de un NA consecutivo genero warning
        if rachas.max() and rachas.max() > 1:
            warnings.warn(
                f"Dato aproximado en {col}: vacíos consecutivos",
                UserWarning)

        # Si quedan Nan le asigno el dato anterior con su respectivo warning
        df[col] = df[col].ffill()

    return df



def anualizar_inflacion_mensual(inflacion_m):
    # Convertir a numérico por si hay strings
    inflacion_m = pd.to_numeric(inflacion_m, errors='coerce')
    
    # Eliminar duplicados por fecha y ordenar
    inflacion_m = inflacion_m[~inflacion_m.index.duplicated(keep='first')].sort_index()
    
    # Anualizar
    inflacion_anualizada = ((1 + inflacion_m / 100) ** 12 - 1) * 100
    
    return inflacion_anualizada



def ventana(series, window=3):
    # Dados la longitud de periodos  que incluirá la ventana obtengo su promedio
    return series.rolling(window).mean()


def crecimiento_yoy(series):
    # Calcula el crecimiento interanual (YoY) en porcentaje
    return series.pct_change(12) * 100


def crecimiento_mom(series):
    # Calcula el crecimiento mensual (MoM) en porcentaje
    return series.pct_change(1) * 100

# INDICADORES
ruta = "./FINAMEX/"


def generar_indicadores_mensual():
    indicadores = {}

    # INFLACIÓN
    #Leo datos
    inflacion = cargar_csv(f"{ruta}inflacion.csv")

    # Agrego a indicadores
    indicadores["Inflacion general anual"] = inflacion["General anual"]
    indicadores["Inflacion subyacente anual"] = inflacion["Subyacente anual"]

    # Calculo de mensual a anualizada
    indicadores["Inflacion mensual anualizada"] = anualizar_inflacion_mensual(inflacion["General mensual"])
    indicadores["Inflacion mensual anualizada"] = indicadores["Inflacion mensual anualizada"].dropna()
        
    # Calculo inflación suavizada por una ventana movil a 3 meses
    indicadores["Inflación suavizada a 3 meses"] = ventana(inflacion["General mensual"], window=3)


    # ACTIVIDAD ECONÓMICA
    # IGAE
    #Leo datos
    igae = cargar_csv(f"{ruta}igae.csv")
    # Calculo crecimiento YoY
    indicadores["IGAE YoY"] = crecimiento_yoy(igae["IGAE Mensual"])
    # Calculo crecimiento MoM del indicador desestacionalizado
    indicadores["IGAE desestacionalizado MoM"] = crecimiento_mom(igae["IGAE des"])

    # Producción industrial (crecimiento trimestral anualizado)
    prod_ind = cargar_csv(f"{ruta}produccion.csv")
    #Corrijo tipo de dato
    prod_ind["Produccion industrial"] = pd.to_numeric(prod_ind["Produccion industrial"], errors="coerce")
    # Fenero promedio de la ventana movil
    ma_3 = ventana(prod_ind["Produccion industrial"], window=3)
    # Obtengo crecimiento recorriendo con shift 3 posiciones. Anualizo
    crecimiento_pi = (ma_3 / ma_3.shift(3)) ** 4 - 1
    # Agrego a indicadores
    indicadores["Produccion industrial"] = crecimiento_pi * 100

    # Desocupación
    # Leo datos
    desoc = cargar_csv(f"{ruta}desocupado.csv")
    indicadores["Desocupación"] = desoc["Tasa"]

    # Salarios
    # Leo datos
    remu = cargar_csv(f"{ruta}remuneraciones.csv")
    # Obtengo crecimientos
    indicadores["Remuneración comercio"] = crecimiento_yoy(remu["Comercio"])
    indicadores["Remuneración manufactura"] = crecimiento_yoy(remu["Manufactura"])

    
    return pd.concat(indicadores, axis=1, join="inner")
    
def generar_indicadores_diarios():
    indicadores_diarios ={}
    # CONDICIONES FINANCIERAS
    # Tasa de referencia
    tasas = cargar_csv(f"{ruta}objetivo.csv")
    indicadores_diarios["Tasa objetivo"] = tasas["Tasa objetivo"]

    # Tasa real 
    # Junto las tasas por fecha
    # Leo datos
    inflacion = cargar_csv(f"{ruta}inflacion.csv")
    inflacion_m = inflacion["General mensual"]
    # Lo genero diario para poder restar. Genero una fila por dia y relleno con dato anterior
    inflacion_d = inflacion_m.resample("D").ffill()
    # Opcional: renombrar para claridad
    inflacion_d.name = "Inflacion_diaria"
    # Unir con tasas diarias
    real = tasas[["Tasa objetivo"]].join(inflacion_d, how="inner")
    # Calcular tasa real
    real["tasa_real"] = real["Tasa objetivo"] - real["Inflacion_diaria"]
    # Guardar en indicadores
    indicadores_diarios["Tasa real"] = real["tasa_real"]

    # Tipo de cambio
    tipo = cargar_csv(f"{ruta}tipo.csv")
    indicadores_diarios["Tipo de cambio"] = crecimiento_yoy(tipo["Tipo de cambio"])

    # Spread soberano
    # Leo datos
    bono_m = cargar_csv(f"{ruta}bono_m.csv")
    treasury = cargar_csv(f"{ruta}DGS10.csv")
    # Obtengo spread
    indicadores_diarios["Spread"] = bono_m["Bono M 10"] - treasury["DGS10"]

    # Diferencia Bono M 10Y – Tasa objetivo
    indicadores_diarios["Diferencia BonoM y Objetivo"] = (real["Tasa objetivo"] - bono_m["Bono M 10"])

    return pd.concat(indicadores_diarios, axis=1, join="inner")


indicadores_m = generar_indicadores_mensual()
indicadores_d = generar_indicadores_diarios()
# Streamlit
st.set_page_config(
    page_title="Dashboard Económico",
    layout="wide"
)

st.title("Dashboard Económico - FINAMEX")
st.markdown("Visualización de indicadores macroeconómicos y financieros.")

# Pestañas
tabs = st.tabs(["Inflación", "Actividad Económica", "Condiciones Financieras"])

#  PESTAÑA: Inflación
with tabs[0]:
    st.subheader("Indicadores de Inflación")
    
    inflacion_cols = [
        "Inflacion general anual",
        "Inflacion subyacente anual",
        "Inflacion mensual anualizada",
        "Inflación suavizada a 3 meses"
    ]
    df_inflacion = indicadores_m[inflacion_cols].dropna(how="any").reset_index()

    def inflacion_leyenda(valor):
        if valor > 6:
            return "Alta presión inflacionaria"
        elif valor > 4:
            return "Moderada presión"
        else:
            return "Controlada"
    
    for col in inflacion_cols:
        df_plot = df_inflacion[["fecha", col]].copy()
        df_plot["Interpretación"] = df_plot[col].apply(inflacion_leyenda)
        
        fig = px.scatter(
            df_plot,
            x="fecha",
            y=col,
            color="Interpretación",
            title=col,
            color_discrete_map={
                "Alta presión inflacionaria": "red",
                "Moderada presión": "orange",
                "Controlada": "navy"
            }
        )

        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            title=dict(
                text=col,
                font=dict(color="darkblue", size=22, family="Arial Black")
            ),
            xaxis=dict(
                title="Fecha",
                title_font=dict(color="#001f3f", size=14),
                tickfont=dict(color="#001f3f", size=12)
            ),
            yaxis=dict(
                title="Porcentaje",
                title_font=dict(color="#001f3f", size=14),
                tickfont=dict(color="#001f3f", size=12)
            ),
            legend=dict(
                font=dict(color="#001f3f", size=12)
            )
        )
        st.plotly_chart(fig, use_container_width=True)

# PESTAÑA: Actividad Económica
with tabs[1]:
    st.subheader("Indicadores de Actividad Económica")
    
    actividad_cols = [
        "IGAE YoY",
        "IGAE desestacionalizado MoM",
        "Produccion industrial"
    ]
    df_actividad = indicadores_m[actividad_cols].dropna(how="any").reset_index()
    
    for col in actividad_cols:
        fig = px.scatter(
            df_actividad,
            x="fecha",
            y=col,
            title=col,
            color_discrete_sequence=["navy"],  # todos los puntos azul marino
        )
        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            title=dict(
                text=col,
                font=dict(color="darkblue", size=22, family="Arial Black")
            ),
            xaxis=dict(
                title="Fecha",
                title_font=dict(color="#001f3f", size=14),
                tickfont=dict(color="#001f3f", size=12)
            ),
            yaxis=dict(
                title="Porcentaje / Valor",
                title_font=dict(color="#001f3f", size=14),
                tickfont=dict(color="#001f3f", size=12)
            ),
            legend=dict(
                font=dict(color="#001f3f", size=12)
            )
        )
        st.plotly_chart(fig, use_container_width=True)

# PESTAÑA: Condiciones Financieras
with tabs[2]:
    st.subheader("Condiciones Financieras")
    
    fin_cols = [
        "Tasa objetivo",
        "Tasa real",
        "Tipo de cambio",
        "Spread",
        "Diferencia BonoM y Objetivo"
    ]
    df_fin = indicadores_d[fin_cols].dropna(how="any").reset_index()
    
    for col in fin_cols:
        df_plot = df_fin[["fecha", col]].copy()
        
        fig = px.scatter(
            df_plot,
            x="fecha",
            y=col,
            title=col,
            color_discrete_sequence=["navy"]  # puntos azul marino
        )
        
        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            title=dict(
                text=col,
                font=dict(color="darkblue", size=22, family="Arial Black")
            ),
            xaxis=dict(
                title="Fecha",
                title_font=dict(color="#001f3f", size=14),
                tickfont=dict(color="#001f3f", size=12)
            ),
            yaxis=dict(
                title="Porcentaje / Valor",
                title_font=dict(color="#001f3f", size=14),
                tickfont=dict(color="#001f3f", size=12)
            ),
            legend=dict(
                font=dict(color="#001f3f", size=12)
            )
        )
        st.plotly_chart(fig, use_container_width=True)

st.markdown("*Fuente de los datos: INEGI y Banxico*")
