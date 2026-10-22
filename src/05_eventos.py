"""Agrupa focos VIIRS en eventos de incendio y calcula sus atributos.

Dos focos pertenecen al mismo evento si están a ≤ EPS_M metros (en x e y) y a
≤ VENTANA_H horas entre sí; los eventos son las componentes conexas de ese
grafo. Es el criterio habitual para seguir incendios con detecciones activas.

Cada evento recibe además una clasificación de la evidencia (columna `evidencia`),
adaptada de las entregas de Diego Sime y Rodrigo Norabuena (curso de Data Science, sesión 14):
- "probable": incendio de vegetación probable, con ≥ 3 focos vistos en ≥ 2 pases
  satelitales y ≥ 50 % de sus focos en vegetación natural (WorldCover);
- "urbano": posible quema urbana o fuente fija, con ≥ 5 000 personas a 1 km,
  ≥ 50 % de focos en zona urbana o suelo desnudo, o 1–2 focos en un punto con
  detecciones en ≥ 5 días distintos de los 180 previos;
- "sin_confirmar": el resto (1–2 focos o un solo pase en vegetación).
Las cifras principales del tablero usan solo los incendios probables.

Salidas en data/processed/:
- eventos.parquet / eventos.csv   un registro por evento de la temporada
- focos_temporada.parquet         focos de la temporada con su id de evento
"""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from exposicion_util import Poblacion  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT, PRO = RAIZ / "data" / "raw", RAIZ / "data" / "interim", RAIZ / "data" / "processed"
PRO.mkdir(parents=True, exist_ok=True)

INICIO_TEMPORADA = pd.Timestamp("2026-07-01")
EPS_M = 1000          # distancia máxima entre focos vecinos
VENTANA_H = 48        # separación temporal máxima entre focos vecinos
CELDA_M = 375         # tamaño de celda para la huella de detección
RADIO_POB_M = 5000    # radio para población expuesta
VEG_NATURAL = ["Bosque", "Matorral", "Pastizal", "Humedal herbáceo", "Manglar", "Musgo y liquen"]
ARTIFICIAL = ["Urbano", "Suelo desnudo"]


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
    """Población WorldPop 2026 (100 m) a ≤ 1 km y ≤ RADIO_POB_M de cualquier foco del evento."""
    wp = Poblacion()
    return {eid: wp.por_radios(g.lon.values, g.lat.values, [1000, RADIO_POB_M]) for eid, g in eventos_focos}


def fuente_fija(f, ev, todos):
    """Eventos de 1–2 focos en un punto que arde una y otra vez: detecciones a ≤ 500 m en ≥ 5 días
    distintos de los 180 previos (botaderos, ladrilleras, industria, quemas que se repiten)."""
    chicos = ev.index[ev.focos <= 2]
    previos = todos[["lon", "lat", "fecha"]].reset_index(drop=True)
    arbol = cKDTree(a_metros(previos.lon.values, previos.lat.values))
    g = f[f.evento.isin(chicos)]
    vecinos = arbol.query_ball_point(a_metros(g.lon.values, g.lat.values), 500)
    dias = previos.fecha.values
    marca = []
    for vs, d in zip(vecinos, g.fecha.values):
        dv = dias[vs]
        marca.append(len(np.unique(dv[(dv < d) & (dv >= d - np.timedelta64(180, "D"))])) >= 5)
    return pd.Series(marca, index=g.index).groupby(g.evento).any().reindex(ev.index, fill_value=False)


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
    f["pase"] = f.satelite + f.t_utc.dt.floor("10min").astype(str)  # un pase = un satélite en una pasada

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
    ev["pct_veg_natural"] = grupos.cobertura.apply(lambda s: s.isin(VEG_NATURAL).mean() * 100).round(0)
    ev["pct_artificial"] = grupos.cobertura.apply(lambda s: s.isin(ARTIFICIAL).mean() * 100).round(0)
    ev["pases"] = grupos.pase.nunique()
    ev["satelites"] = grupos.satelite.nunique()
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
    significativos = ev.index[(ev.focos >= 3) | ev.estado.isin(["Activo", "En observación"])]
    pob = poblacion_cercana((eid, g) for eid, g in grupos if eid in set(significativos))
    pob = pd.DataFrame(pob, index=["poblacion_1km", "poblacion_5km"]).T.reindex(ev.index).round(0)
    ev[["poblacion_1km", "poblacion_5km"]] = pob

    # evidencia: incendio de vegetación probable, posible fuente urbana o industrial, o sin confirmar
    fija = fuente_fija(f, ev, focos)
    urbano = (ev.poblacion_1km >= 5000) | (ev.pct_artificial >= 50) | fija
    probable = (ev.focos >= 3) & (ev.pases >= 2) & (ev.pct_veg_natural >= 50) & ~urbano
    ev["fuente_fija"] = fija
    ev["evidencia"] = np.select([probable, urbano], ["probable", "urbano"], "sin_confirmar")

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
    print(pd.crosstab(ev.estado, ev.evidencia).to_string())
    print(ev.focos.describe(percentiles=[.5, .9, .99]).round(1).to_dict())
    print(ev.huella_ha.describe(percentiles=[.5, .9, .99]).round(0).to_dict())
    cols = ["evento", "departamento", "provincia", "distrito", "estado", "focos", "huella_ha", "duracion_dias",
            "frp_total", "poblacion_5km", "anp", "prioridad"]
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(ev.sort_values("prioridad", ascending=False)[cols].head(15))
        print(ev.sort_values("huella_ha", ascending=False)[cols].head(10))


if __name__ == "__main__":
    main()
