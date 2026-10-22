"""Focos de calor VIIRS (375 m) para Perú: limpieza, unión y atributos.

- 2025-06 a la fecha: INPE (S-NPP día y noche, NOAA-20, NOAA-21) y, para los
  pases posteriores al último dato de INPE, NASA FIRMS NRT.
- 2012-2025: NASA FIRMS S-NPP (procesamiento estándar), solo focos tipo 0
  (vegetación), para la serie histórica comparable.

Salidas en data/interim/:
- focos_viirs.parquet      focos 2025-06 → hoy con atributos
- historico_snpp.parquet   serie S-NPP 2012 → hoy (comparación interanual)
Solo se conservan focos dentro de los límites distritales del INEI.
- qa_fuentes.csv           cotejo INPE vs FIRMS en días superpuestos
"""
from pathlib import Path
import glob
import importlib
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
cobertura = importlib.import_module("03_cobertura")

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT = RAIZ / "data" / "raw", RAIZ / "data" / "interim"
UTC_PERU = pd.Timedelta(hours=-5)
SAT_INPE = {"NPP-375": "S-NPP", "NPP-375D": "S-NPP", "NOAA-20": "NOAA-20", "NOAA-21": "NOAA-21"}
SAT_FIRMS = {"snpp": "S-NPP", "noaa20": "NOAA-20", "noaa21": "NOAA-21"}


def a_metros(lon, lat):
    """Proyección equirectangular local (suficiente para distancias < 50 km)."""
    lat0 = -9.0
    x = np.radians(lon) * 6371000 * np.cos(np.radians(lat0))
    y = np.radians(lat) * 6371000
    return np.column_stack([x, y])


def leer_inpe():
    df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(RAW / "inpe" / "*.csv")))])
    df = df[df.satelite.isin(SAT_INPE)].copy()
    out = pd.DataFrame({
        "t_utc": pd.to_datetime(df.data_hora_gmt),
        "lat": df.lat.astype(float), "lon": df.lon.astype(float),
        "frp": pd.to_numeric(df.frp, errors="coerce"),
        "satelite": df.satelite.map(SAT_INPE),
        "dia_noche": np.where(df.satelite.eq("NPP-375D"), "N", None),
        "confianza": None, "fuente": "INPE",
    })
    # día/noche para todos según la hora local del pase
    h = (out.t_utc + UTC_PERU).dt.hour
    out["dia_noche"] = np.where((h >= 6) & (h < 18), "D", "N")
    # INPE repite focos desde el 13 oct 2026: mismo satélite, misma hora y misma posición con otro id
    # (≈ 4 % de octubre). Se deja uno; detectado por Frank Pinares (curso de Data Science, sesión 14).
    clave = out.assign(_la=out.lat.round(4), _lo=out.lon.round(4))
    dup = clave.duplicated(["satelite", "t_utc", "_la", "_lo"])
    print(f"INPE: {dup.sum():,} focos duplicados eliminados")
    return out[~dup.values]


def leer_firms_7d(peru_bbox):
    partes = []
    for clave, sat in SAT_FIRMS.items():
        f = pd.read_csv(RAW / "firms" / f"firms_7d_{clave}_sudamerica.csv")
        o, s, e, n = peru_bbox
        f = f[f.longitude.between(o, e) & f.latitude.between(s, n)]
        partes.append(pd.DataFrame({
            "t_utc": pd.to_datetime(f.acq_date + " " + f.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M"),
            "lat": f.latitude, "lon": f.longitude, "frp": f.frp, "satelite": sat,
            "dia_noche": f.daynight, "confianza": f.confidence, "fuente": "FIRMS",
        }))
    return pd.concat(partes, ignore_index=True)


def leer_firms_historico():
    partes = []
    for ruta in sorted(glob.glob(str(RAW / "firms" / "viirs-snpp_*_Peru.csv"))):
        f = pd.read_csv(ruta)
        partes.append(f)
    h = pd.concat(partes, ignore_index=True)
    return h


def fuentes_estaticas(hist):
    """Volcanes, antorchas de gas e industrias: FIRMS tipo 1 y 2 (2012-2025)."""
    e = hist[hist["type"].isin([1, 2])]
    return cKDTree(a_metros(e.longitude.values, e.latitude.values))


def quitar_estaticos(df, arbol, radio=500):
    d, _ = arbol.query(a_metros(df.lon.values, df.lat.values), k=1, distance_upper_bound=radio)
    return df[~np.isfinite(d)].copy(), int(np.isfinite(d).sum())


def unir_admin(df, distritos):
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    cols = ["ubigeo", "distrito", "provincia", "departamento"]
    j = gpd.sjoin(g, distritos[cols + ["geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    return pd.DataFrame(j.drop(columns=["geometry", "index_right"], errors="ignore"))


def unir_anp(df, anp):
    g = gpd.GeoDataFrame(df[["lon", "lat"]], geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    orden = {"Nacional": 0, "Zona reservada": 1, "Conservación regional": 2, "Conservación privada": 3}
    a = anp.assign(_o=anp.anp_admin.map(orden)).sort_values("_o")
    j = gpd.sjoin(g, a[["anp_nombre", "anp_categoria", "anp_admin", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    return j[["anp_nombre", "anp_categoria", "anp_admin"]]


def region_natural(lon, lat, elev, dem):
    """Costa / Sierra / Selva aproximadas con el relieve.

    Sierra: ≥ 2 000 m. Debajo de esa cota, el punto es de Costa si la cordillera
    (≥ 3 000 m) más cercana en su misma latitud está al este; si está al oeste,
    es de Selva (vertiente amazónica).
    """
    fila, col = dem.fila_col(lon, lat)
    fila = np.clip(np.round(fila).astype(int), 0, dem.dem.shape[0] - 1)
    col = np.round(col).astype(int)
    alto = dem.dem >= 3000
    res = np.where(elev >= 2000, "Sierra", "")
    for f in np.unique(fila[elev < 2000]):
        cols_alto = np.flatnonzero(alto[f])
        if len(cols_alto) == 0:  # sin cordillera alta en la fila: usar ≥ 2 500 m
            cols_alto = np.flatnonzero(dem.dem[f] >= 2500)
        idx = np.flatnonzero((fila == f) & (elev < 2000))
        if len(cols_alto) == 0:
            res[idx] = "Selva"
            continue
        pos = np.searchsorted(cols_alto, col[idx])
        izq = cols_alto[np.clip(pos - 1, 0, len(cols_alto) - 1)]
        der = cols_alto[np.clip(pos, 0, len(cols_alto) - 1)]
        d_izq = np.where(pos > 0, col[idx] - izq, np.inf)
        d_der = np.where(pos < len(cols_alto), der - col[idx], np.inf)
        res[idx] = np.where(d_der < d_izq, "Costa", "Selva")
    return res


class DEM:
    def __init__(self):
        z = np.load(INT / "dem_z9.npz")
        self.dem = np.maximum(z["dem"], 0)
        self.mx0, self.my1, self.res = float(z["mx0"]), float(z["my1"]), float(z["res"])

    def fila_col(self, lon, lat):
        x = np.radians(lon) * 6378137.0
        y = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * 6378137.0
        return (self.my1 - y) / self.res, (x - self.mx0) / self.res

    def muestrear(self, lon, lat):
        f, c = self.fila_col(lon, lat)
        f = np.clip(np.round(f).astype(int), 0, self.dem.shape[0] - 1)
        c = np.clip(np.round(c).astype(int), 0, self.dem.shape[1] - 1)
        return self.dem[f, c]

    def pendiente_en(self, lon, lat):
        f, c = self.fila_col(lon, lat)
        f = np.clip(np.round(f).astype(int), 1, self.dem.shape[0] - 2)
        c = np.clip(np.round(c).astype(int), 1, self.dem.shape[1] - 2)
        tam = self.res * np.cos(np.radians(lat))
        dzdx = (self.dem[f, c + 1] - self.dem[f, c - 1]) / (2 * tam)
        dzdy = (self.dem[f + 1, c] - self.dem[f - 1, c]) / (2 * tam)
        return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def main():
    distritos = gpd.read_parquet(INT / "distritos.parquet")
    peru = gpd.read_parquet(INT / "peru.parquet")
    anp = gpd.read_parquet(INT / "anp.parquet")
    o, s, e, n = peru.total_bounds
    bbox = (o - 0.05, s - 0.05, e + 0.05, n + 0.05)

    hist = leer_firms_historico()
    arbol = fuentes_estaticas(hist)

    # --- focos recientes: INPE hasta el día anterior al inicio de FIRMS 7d, luego FIRMS
    inpe = leer_inpe()
    firms = leer_firms_7d(bbox)
    corte = firms.t_utc.dt.floor("D").min() + pd.Timedelta(days=1)  # primer día UTC completo en FIRMS
    solape = pd.concat([inpe[inpe.t_utc >= corte], firms[firms.t_utc >= corte]], ignore_index=True)
    solape = unir_admin(quitar_estaticos(solape, arbol)[0], distritos).dropna(subset=["ubigeo"])
    qa = (solape.assign(fecha_utc=solape.t_utc.dt.date)
          .groupby(["fecha_utc", "satelite", "fuente"]).size().unstack("fuente"))
    # INPE resulta más completo que el archivo FIRMS de 7 días en los días superpuestos
    # (ver qa_fuentes.csv): se usa INPE hasta su último pase y FIRMS solo para lo posterior.
    focos = pd.concat([inpe, firms[firms.t_utc > inpe.t_utc.max()]], ignore_index=True)
    focos = focos[focos.lon.between(bbox[0], bbox[2]) & focos.lat.between(bbox[1], bbox[3])]
    focos, n_est = quitar_estaticos(focos, arbol)
    focos = unir_admin(focos, distritos)
    focos = focos[focos.ubigeo.notna()].reset_index(drop=True)

    focos["t_local"] = focos.t_utc + UTC_PERU
    focos["fecha"] = focos.t_local.dt.normalize()
    dem = DEM()
    focos["elev_m"] = dem.muestrear(focos.lon.values, focos.lat.values).round(0)
    focos["pendiente_g"] = dem.pendiente_en(focos.lon.values, focos.lat.values).round(1)
    focos["region"] = region_natural(focos.lon.values, focos.lat.values, focos.elev_m.values, dem)
    cl = cobertura.muestrear(focos.lon.values, focos.lat.values)
    focos["cobertura"] = pd.Series(cl).map(cobertura.CLASES).values
    focos = pd.concat([focos, unir_anp(focos, anp).reset_index(drop=True)], axis=1)
    focos = focos.sort_values("t_utc").reset_index(drop=True)
    focos.to_parquet(INT / "focos_viirs.parquet")

    # --- serie histórica comparable (S-NPP)
    h = hist[hist["type"] == 0]
    h = pd.DataFrame({
        "t_utc": pd.to_datetime(h.acq_date + " " + h.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M"),
        "lat": h.latitude, "lon": h.longitude, "frp": h.frp,
    })
    s26 = inpe[(inpe.satelite == "S-NPP") & (inpe.t_utc >= "2026-01-01")][["t_utc", "lat", "lon", "frp"]]
    # los últimos días que INPE aún no tiene, desde FIRMS S-NPP
    s26 = pd.concat([s26, firms[(firms.satelite == "S-NPP") & (firms.t_utc > inpe.t_utc.max())]
                     [["t_utc", "lat", "lon", "frp"]]])
    s26, _ = quitar_estaticos(s26, arbol)
    h = pd.concat([h, s26], ignore_index=True)
    h = unir_admin(h, distritos)
    h = h[h.ubigeo.notna()]
    h["fecha"] = (h.t_utc + UTC_PERU).dt.normalize()
    h[["fecha", "lat", "lon", "frp", "ubigeo", "provincia", "departamento"]].to_parquet(INT / "historico_snpp.parquet")

    qa.to_csv(INT / "qa_fuentes.csv")
    print(f"focos VIIRS: {len(focos):,} ({focos.t_local.min()} → {focos.t_local.max()})")
    print(f"fuentes estáticas excluidas: {n_est:,}; último pase INPE (UTC): {inpe.t_utc.max()}")
    print(f"histórico S-NPP: {len(h):,} ({h.fecha.min().date()} → {h.fecha.max().date()})")
    print(qa.tail(12))
    print(focos.region.value_counts().to_dict())
    print(focos.cobertura.value_counts().to_dict())
    print(focos.anp_admin.value_counts().to_dict())


if __name__ == "__main__":
    main()
