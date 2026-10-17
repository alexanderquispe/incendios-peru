"""Agrupa focos VIIRS en eventos de incendio y calcula sus atributos.

Dos focos pertenecen al mismo evento si están a ≤ EPS_M metros (en x e y) y a
≤ VENTANA_H horas entre sí; los eventos son las componentes conexas de ese
grafo. Es el criterio habitual para seguir incendios con detecciones activas.

Salidas en data/processed/:
- eventos.parquet / eventos.csv   un registro por evento de la temporada
- focos_temporada.parquet         focos de la temporada con su id de evento
"""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT, PRO = RAIZ / "data" / "raw", RAIZ / "data" / "interim", RAIZ / "data" / "processed"
PRO.mkdir(parents=True, exist_ok=True)

INICIO_TEMPORADA = pd.Timestamp("2026-07-01")
EPS_M = 1000          # distancia máxima entre focos vecinos
VENTANA_H = 48        # separación temporal máxima entre focos vecinos
CELDA_M = 375         # tamaño de celda para la huella de detección
RADIO_POB_M = 5000    # radio para población expuesta


def a_metros(lon, lat):
    lat0 = -9.0
    return np.column_stack([np.radians(lon) * 6371000 * np.cos(np.radians(lat0)),
                            np.radians(lat) * 6371000])


def agrupar(f):
    xy = a_metros(f.lon.values, f.lat.values)
    horas = (f.t_utc - f.t_utc.min()).dt.total_seconds().values / 3600
    # métrica de Chebyshev con el tiempo reescalado: |dx|,|dy| ≤ EPS y |dt| ≤ VENTANA
    pts = np.column_stack([xy, horas * EPS_M / VENTANA_H])
    pares = cKDTree(pts).query_pairs(EPS_M, p=np.inf, output_type="ndarray")
    n = len(f)
    g = coo_matrix((np.ones(len(pares)), (pares[:, 0], pares[:, 1])), shape=(n, n))
    _, etiquetas = connected_components(g, directed=False)
    return etiquetas


def huella_celdas(lon, lat):
    xy = a_metros(lon, lat)
    return np.unique(np.floor(xy / CELDA_M).astype(np.int64), axis=0)


def poblacion_cercana(eventos_focos):
    """Población WorldPop 2020 dentro de RADIO_POB_M de cualquier foco del evento."""
    with rasterio.open(RAW / "worldpop_per_2020_1km.tif") as src:
        pob = src.read(1)
        filas, cols = np.nonzero(pob > 0)
        xs, ys = rasterio.transform.xy(src.transform, filas, cols)
        valores = pob[filas, cols]
    arbol = cKDTree(a_metros(np.asarray(xs), np.asarray(ys)))
    out = {}
    for eid, g in eventos_focos:
        idx = arbol.query_ball_point(a_metros(g.lon.values, g.lat.values), RADIO_POB_M)
        celdas = set().union(*map(set, idx)) if len(idx) else set()
        out[eid] = float(valores[list(celdas)].sum()) if celdas else 0.0
    return out


def capitales():
    c = pd.read_csv(RAW / "limites" / "ubigeo_distrito.csv", dtype={"inei": str})
    c = c.dropna(subset=["latitude", "longitude"])
    return c, cKDTree(a_metros(c.longitude.values, c.latitude.values))


def moda(s):
    m = s.mode()
    return m.iloc[0] if len(m) else None


def main():
    focos = pd.read_parquet(INT / "focos_viirs.parquet")
    f = focos[focos.fecha >= INICIO_TEMPORADA].sort_values("t_utc").reset_index(drop=True)
    f["evento"] = agrupar(f)
    corte = f.t_local.max()

    # ids estables y legibles: por fecha de inicio
    inicio = f.groupby("evento").t_local.min().sort_values()
    nuevo = {e: f"E{str(i + 1).zfill(5)}" for i, e in enumerate(inicio.index)}
    f["evento"] = f.evento.map(nuevo)

    grupos = f.groupby("evento")
    ev = grupos.agg(
        inicio=("t_local", "min"), ultimo=("t_local", "max"), focos=("lat", "size"),
        dias_con_focos=("fecha", "nunique"), lat=("lat", "mean"), lon=("lon", "mean"),
        frp_max=("frp", "max"), frp_total=("frp", "sum"),
        elev_min=("elev_m", "min"), elev_med=("elev_m", "median"), elev_max=("elev_m", "max"),
        pendiente_med=("pendiente_g", "median"),
        departamento=("departamento", moda), provincia=("provincia", moda), distrito=("distrito", moda),
        ubigeo=("ubigeo", moda), region=("region", moda), cobertura=("cobertura", moda),
        n_distritos=("ubigeo", "nunique"),
        lat_min=("lat", "min"), lat_max=("lat", "max"), lon_min=("lon", "min"), lon_max=("lon", "max"),
    )
    ev["pct_bosque"] = grupos.cobertura.apply(lambda s: (s == "Bosque").mean() * 100).round(0)
    ev["anp"] = grupos.anp_nombre.apply(lambda s: "; ".join(sorted(s.dropna().unique())) or None)
    ev["anp_admin"] = grupos.anp_admin.apply(lambda s: moda(s.dropna()) if s.notna().any() else None)
    ev["focos_en_anp"] = grupos.anp_nombre.apply(lambda s: int(s.notna().sum()))
    ev["huella_ha"] = grupos.apply(lambda g: len(huella_celdas(g.lon.values, g.lat.values)) * CELDA_M ** 2 / 1e4)
    ev["duracion_dias"] = ((ev.ultimo - ev.inicio).dt.total_seconds() / 86400).round(1)
    horas_sin = (corte - ev.ultimo).dt.total_seconds() / 3600
    ev["horas_desde_ultimo"] = horas_sin.round(1)
    ev["estado"] = np.select([horas_sin <= 24, horas_sin <= 72], ["Activo", "En observación"], "Sin actividad reciente")

    # últimas 24 h: focos y huella nueva (celdas de 375 m con fuego por primera vez)
    reciente = corte - pd.Timedelta(hours=24)
    celdas = np.floor(a_metros(f.lon.values, f.lat.values) / CELDA_M).astype(np.int64)
    primera = (pd.DataFrame({"evento": f.evento, "cx": celdas[:, 0], "cy": celdas[:, 1], "t": f.t_local})
               .groupby(["evento", "cx", "cy"]).t.min())
    ev["focos_24h"] = f[f.t_local > reciente].groupby("evento").size().reindex(ev.index, fill_value=0)
    ev["huella_24h_ha"] = ((primera > reciente).groupby(level="evento").sum()
                           .reindex(ev.index, fill_value=0) * CELDA_M ** 2 / 1e4)

    # distancia a ANP (si no está dentro) y capital distrital más cercana
    anp = gpd.read_parquet(INT / "anp.parquet").to_crs(32718)
    pts = gpd.GeoSeries(gpd.points_from_xy(ev.lon, ev.lat), crs=4326).to_crs(32718)
    cerca = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=pts.values, index=ev.index, crs=32718),
                              anp[["anp_nombre", "geometry"]], how="left", distance_col="d")
    cerca = cerca[~cerca.index.duplicated(keep="first")]
    ev["anp_cercana"] = cerca.anp_nombre
    ev["dist_anp_km"] = (cerca.d / 1000).round(1)
    caps, arbol_caps = capitales()
    d, i = arbol_caps.query(a_metros(ev.lon.values, ev.lat.values))
    ev["capital_cercana"] = caps.capital.values[i]
    ev["dist_capital_km"] = (d / 1000).round(1)

    print("población expuesta…")
    significativos = ev.index[(ev.focos >= 3) | (ev.estado == "Activo")]
    pob = poblacion_cercana((eid, g) for eid, g in grupos if eid in set(significativos))
    ev["poblacion_5km"] = pd.Series(pob).reindex(ev.index).round(0)

    # índice de prioridad (0-100) con escalas fijas, para que sea comparable entre días:
    #   tamaño 1.0 = huella ≥ 2 000 ha; intensidad 1.0 = FRP acumulada ≥ 10 000 MW;
    #   exposición 1.0 = ≥ 50 000 personas a 5 km; ANP nacional/zona reservada 1.0,
    #   otra ANP 0.6, a ≤ 5 km de una ANP 0.3; actividad: activo 1.0, en observación 0.5.
    sig = ev.loc[significativos]
    escala_log = lambda v, ref, base=0.0: np.clip(np.log1p(np.maximum(v - base, 0)) / np.log1p(ref - base), 0, 1)
    componentes = pd.DataFrame({
        "actividad": sig.estado.map({"Activo": 1.0, "En observación": 0.5}).fillna(0.0),
        "tamano": escala_log(sig.huella_ha, 2000, base=14.0625),
        "intensidad": escala_log(sig.frp_total, 10000),
        "exposicion": escala_log(sig.poblacion_5km.fillna(0), 50000),
        "anp": np.select([sig.anp_admin.isin(["Nacional", "Zona reservada"]), sig.anp_admin.notna(),
                          sig.dist_anp_km <= 5], [1.0, 0.6, 0.3], 0.0),
    })
    pesos = {"actividad": 30, "tamano": 20, "intensidad": 20, "exposicion": 15, "anp": 15}
    ev["prioridad"] = sum(componentes[k] * w for k, w in pesos.items()).round(0)
    for k in pesos:
        ev[f"p_{k}"] = componentes[k].round(2)
    ev["significativo"] = ev.index.isin(significativos)

    ev = ev.reset_index().rename(columns={"index": "evento"})
    ev.to_parquet(PRO / "eventos.parquet")
    ev.sort_values("prioridad", ascending=False).to_csv(PRO / "eventos.csv", index=False)
    f.to_parquet(PRO / "focos_temporada.parquet")

    print(f"corte: {corte}; focos temporada: {len(f):,}; eventos: {len(ev):,}; significativos: {len(significativos):,}")
    print(ev.estado.value_counts().to_dict())
    print(ev.focos.describe(percentiles=[.5, .9, .99]).round(1).to_dict())
    print(ev.huella_ha.describe(percentiles=[.5, .9, .99]).round(0).to_dict())
    cols = ["evento", "departamento", "provincia", "distrito", "estado", "focos", "huella_ha", "duracion_dias",
            "frp_total", "poblacion_5km", "anp", "prioridad"]
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(ev.sort_values("prioridad", ascending=False)[cols].head(15))
        print(ev.sort_values("huella_ha", ascending=False)[cols].head(10))


if __name__ == "__main__":
    main()
