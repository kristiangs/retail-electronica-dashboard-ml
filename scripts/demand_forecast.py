"""
demand_forecast.py
--------------------------------------------------------------------------
Pronostico de demanda mensual por producto usando scikit-learn.

Este script forma parte del pipeline: Faker (generacion) -> Power Query
(limpieza) -> Power Pivot (modelo) -> Power BI (visualizacion).
Se ejecuta ANTES de refrescar el .pbix: lee los archivos mensuales de la
carpeta de datos, entrena un modelo de regresion y exporta un CSV
(forecast.csv) con la prediccion del proximo mes por producto. Power BI
solo tiene que apuntar a ese CSV como una tabla mas del modelo.

Requisitos:
    pip install pandas scikit-learn openpyxl --break-system-packages

Estructura de carpetas esperada (igual a RETAIL_ELECTRONICA):
    RETAIL_ELECTRONICA/
        datos_brutos/        <- ventas_YYYY_MM.csv + catalogos
        scripts/
            generar_datos.py
            demand_forecast.py   <- este archivo
        outputs/
            forecast.csv          <- se genera aqui
--------------------------------------------------------------------------
"""

import glob
import os

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

# ============================== CONFIG ====================================
# Las rutas se calculan a partir de la ubicacion de este archivo, no de donde
# se ejecute el comando python -- asi funciona igual sin importar si corres
# el script parado en "scripts/" o en la raiz del proyecto.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ruta a la carpeta con los 48 archivos mensuales generados por generar_datos.py
CARPETA_DATOS = os.path.join(SCRIPT_DIR, "..", "datos_brutos")
PATRON_ARCHIVOS = "ventas_*.csv"         # solo los archivos de ventas, no los catalogos
ARCHIVO_SALIDA = os.path.join(SCRIPT_DIR, "..", "outputs", "forecast.csv")  # esto es lo que Power BI va a leer

COL_PRODUCTO_ID = "id_producto"
COL_PRODUCTO_NOMBRE = "nombre_producto"
COL_MES = "mes"                          # numero de mes (1-12), se combina con año abajo
COL_ANIO = "año"                         # deja en None si no existe una columna de año
COL_MONTO_TOTAL = "monto_total"
COL_PRECIO_UNITARIO = "precio_unitario"
COL_UNIDADES = "cantidad"                # ya existe como columna real, no se estima
COL_STOCK_MINIMO = "stock_minimo"
COL_STOCK_ACTUAL = None                  # no existe en este dataset por ahora
# ============================================================================


def cargar_datos_mensuales(carpeta: str) -> pd.DataFrame:
    """Lee y concatena los archivos mensuales de ventas de la carpeta de datos."""
    archivos = glob.glob(os.path.join(carpeta, PATRON_ARCHIVOS))
    if not archivos:
        raise FileNotFoundError(
            f"No se encontraron archivos '{PATRON_ARCHIVOS}' en {carpeta}"
        )

    dfs = [pd.read_csv(archivo) for archivo in sorted(archivos)]
    return pd.concat(dfs, ignore_index=True)


def calcular_unidades(df: pd.DataFrame) -> pd.DataFrame:
    """Si no hay columna de unidades vendidas, se estima con monto/precio."""
    if COL_UNIDADES and COL_UNIDADES in df.columns:
        df["unidades"] = df[COL_UNIDADES]
    else:
        df["unidades"] = df[COL_MONTO_TOTAL] / df[COL_PRECIO_UNITARIO]
    return df


def construir_serie_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega ventas a nivel producto-mes.

    Si existe columna de año (COL_ANIO), se combina con COL_MES en una
    llave de periodo ordenable (año*100 + mes, ej. 202101). Sin esto,
    dos ventas de "enero" de años distintos se mezclarian como si
    fueran el mismo periodo.
    """
    df = df.copy()
    if COL_ANIO and COL_ANIO in df.columns:
        df["periodo"] = df[COL_ANIO].astype(int) * 100 + df[COL_MES].astype(int)
    else:
        df["periodo"] = df[COL_MES]

    agg = (
        df.groupby([COL_PRODUCTO_ID, "periodo"])
        .agg(unidades=("unidades", "sum"))
        .reset_index()
        .sort_values([COL_PRODUCTO_ID, "periodo"])
    )
    return agg


def crear_features(agg: pd.DataFrame) -> pd.DataFrame:
    """Crea variables de rezago (lags) y promedio movil por producto."""
    agg = agg.copy()
    agg["mes_idx"] = agg.groupby(COL_PRODUCTO_ID).cumcount()

    for lag in (1, 2, 3):
        agg[f"lag_{lag}"] = agg.groupby(COL_PRODUCTO_ID)["unidades"].shift(lag)

    agg["rolling_mean_3"] = (
        agg.groupby(COL_PRODUCTO_ID)["unidades"]
        .shift(1)
        .rolling(3)
        .mean()
        .reset_index(level=0, drop=True)
    )

    le = LabelEncoder()
    agg["producto_enc"] = le.fit_transform(agg[COL_PRODUCTO_ID])
    return agg, le


def entrenar_modelo(agg: pd.DataFrame):
    """Entrena un RandomForest sobre las filas con historia suficiente."""
    features = ["producto_enc", "mes_idx", "lag_1", "lag_2", "lag_3", "rolling_mean_3"]
    datos_entrenables = agg.dropna(subset=features)

    if len(datos_entrenables) < 10:
        raise ValueError(
            "No hay suficiente historia mensual para entrenar el modelo. "
            "Se necesitan al menos ~4 meses de datos por producto."
        )

    X = datos_entrenables[features]
    y = datos_entrenables["unidades"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    modelo = RandomForestRegressor(n_estimators=200, random_state=42)
    modelo.fit(X_train, y_train)

    if len(X_test) > 0:
        mae = mean_absolute_error(y_test, modelo.predict(X_test))
        print(f"MAE en set de validacion: {mae:.2f} unidades")

    return modelo, features


def predecir_proximo_mes(agg: pd.DataFrame, modelo, features, encoder):
    """Toma la ultima fila conocida de cada producto y predice el periodo siguiente."""
    ultimo = agg.sort_values("mes_idx").groupby(COL_PRODUCTO_ID).tail(1).copy()

    ultimo["mes_idx"] = ultimo["mes_idx"] + 1
    ultimo["lag_3"] = ultimo["lag_2"]
    ultimo["lag_2"] = ultimo["lag_1"]
    ultimo["lag_1"] = ultimo["unidades"]
    ultimo["rolling_mean_3"] = ultimo[["lag_1", "lag_2", "lag_3"]].mean(axis=1)

    ultimo = ultimo.dropna(subset=features)
    ultimo["unidades_estimadas"] = modelo.predict(ultimo[features]).round(1)
    return ultimo[[COL_PRODUCTO_ID, "unidades_estimadas"]]


def calcular_recomendacion_stock(pred: pd.DataFrame, df_original: pd.DataFrame) -> pd.DataFrame:
    """Cruza la prediccion con stock_minimo (y stock_actual si existe) para alertar."""
    cols_ref = [COL_PRODUCTO_ID, COL_STOCK_MINIMO]
    if COL_PRODUCTO_NOMBRE in df_original.columns:
        cols_ref.insert(1, COL_PRODUCTO_NOMBRE)
    if COL_STOCK_ACTUAL and COL_STOCK_ACTUAL in df_original.columns:
        cols_ref.append(COL_STOCK_ACTUAL)

    ref = df_original[cols_ref].drop_duplicates(subset=COL_PRODUCTO_ID)
    resultado = pred.merge(ref, on=COL_PRODUCTO_ID, how="left")

    # stock recomendado = demanda estimada + colchon de seguridad (stock_minimo)
    resultado["stock_recomendado"] = (
        resultado["unidades_estimadas"] + resultado[COL_STOCK_MINIMO]
    ).round(0)

    if COL_STOCK_ACTUAL and COL_STOCK_ACTUAL in resultado.columns:
        resultado["alerta_quiebre"] = (
            resultado[COL_STOCK_ACTUAL] < resultado["unidades_estimadas"]
        )
    else:
        resultado["alerta_quiebre"] = None  # no hay stock_actual disponible

    return resultado


def main():
    df = cargar_datos_mensuales(CARPETA_DATOS)
    df = calcular_unidades(df)

    serie = construir_serie_mensual(df)
    serie_feat, encoder = crear_features(serie)

    modelo, features = entrenar_modelo(serie_feat)
    pred = predecir_proximo_mes(serie_feat, modelo, features, encoder)

    resultado = calcular_recomendacion_stock(pred, df)
    resultado.to_csv(ARCHIVO_SALIDA, index=False)

    print(f"\nForecast exportado a {ARCHIVO_SALIDA} ({len(resultado)} productos)")
    print(resultado.head(10).to_string(index=False))


if __name__ == "__main__":
    main()