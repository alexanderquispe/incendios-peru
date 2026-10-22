"""Utilidades de exposición: población WorldPop 2026 (100 m) y edificaciones Google Open Buildings.

La población a cierta distancia de un incendio se cuenta sin doble conteo: se marcan
las celdas de 100 m cuyo centro está a ≤ radio de algún foco (o del área quemada) y
se suma su población. Para totales nacionales se unen los índices de celdas de
todos los incendios.

Edificaciones: Google Open Buildings v3 (confianza ≥ 0,75) desde la copia GeoParquet
de VIDA en source.coop, leída con DuckDB por caja; se guarda una caché por celda
de 0,25°. Método tomado de Rodrigo Norabuena (curso de Data Science, sesión 14).
"""
from pathlib import Path
import math

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage as ndi

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT = RAIZ / "data" / "raw", RAIZ / "data" / "interim"
WORLDPOP_2026 = RAW / "worldpop_per_2026_100m_constrained.tif"
VIDA = ("https://data.source.coop/vida/google-microsoft-open-buildings/geoparquet/by_country_s2/country_iso=PER/"
        "{}.parquet")
VIDA_CELDAS = ["10394307939971104768", "10466365534009032704", "10502394331027996672"]
CONF_MIN = 0.75
TESELA = 0.25
CACHE_EDIF = INT / "edificaciones"
M_GRADO = 111320.0


class Poblacion:
    """WorldPop 2026 constrained, 100 m, en memoria (≈ 1.3 GB)."""

    def __init__(self):
        with rasterio.open(WORLDPOP_2026) as src:
            self.pob = src.read(1)
            self.t = src.transform
        self.pob[~(self.pob > 0)] = 0
        self.alto, self.ancho = self.pob.shape
        self.res = self.t.a

    def fila_col(self, lon, lat):
        c = ((np.asarray(lon) - self.t.c) / self.t.a).astype(int)
        f = ((np.asarray(lat) - self.t.f) / self.t.e).astype(int)
        return f, c

    def distancia(self, lon, lat, radio_max, mascara=None, ventana=None):
        """Distancia (m) de cada celda de una ventana a los puntos (o a una máscara ya rasterizada)."""
        lon, lat = np.atleast_1d(lon), np.atleast_1d(lat)
        lat0 = float(np.mean(lat))
        dy = self.res * M_GRADO
        dx = dy * math.cos(math.radians(lat0))
        if ventana is None:
            mf, mc = math.ceil(radio_max / dy) + 1, math.ceil(radio_max / dx) + 1
            f, c = self.fila_col(lon, lat)
            f0, f1 = max(0, f.min() - mf), min(self.alto, f.max() + mf + 1)
            c0, c1 = max(0, c.min() - mc), min(self.ancho, c.max() + mc + 1)
            semilla = np.zeros((f1 - f0, c1 - c0), bool)
            semilla[f - f0, c - c0] = True
        else:
            f0, f1, c0, c1 = ventana
            semilla = mascara
        d = ndi.distance_transform_edt(~semilla, sampling=(dy, dx))
        return d, (f0, f1, c0, c1)

    def celdas(self, lon, lat, radio):
        """Índices planos de las celdas pobladas a ≤ radio de algún punto."""
        d, (f0, f1, c0, c1) = self.distancia(lon, lat, radio)
        ff, cc = np.nonzero(d <= radio)
        ff, cc = ff + f0, cc + c0
        idx = ff * self.ancho + cc
        return idx[self.pob.ravel()[idx] > 0]

    def por_radios(self, lon, lat, radios):
        """Población acumulada a ≤ cada radio (lista en el mismo orden)."""
        d, (f0, f1, c0, c1) = self.distancia(lon, lat, max(radios))
        p = self.pob[f0:f1, c0:c1]
        return [float(p[d <= r].sum()) for r in radios]

    def suma(self, idx):
        return float(self.pob.ravel()[np.unique(idx)].sum())


def _tesela(o, s):
    return f"{math.floor(o / TESELA) * TESELA:.2f}_{math.floor(s / TESELA) * TESELA:.2f}"


def edificaciones(o, s, e, n):
    """Centros de las edificaciones (lon, lat) dentro de la caja, con caché por teselas de 0,25°."""
    import duckdb
    CACHE_EDIF.mkdir(parents=True, exist_ok=True)
    partes, con = [], None
    for x in np.arange(math.floor(o / TESELA) * TESELA, e, TESELA):
        for y in np.arange(math.floor(s / TESELA) * TESELA, n, TESELA):
            ruta = CACHE_EDIF / f"{_tesela(x, y)}.parquet"
            if not ruta.exists():
                if con is None:
                    con = duckdb.connect()
                    con.execute("INSTALL httpfs; LOAD httpfs; SET enable_progress_bar=false;")
                archivos = [VIDA.format(c) for c in VIDA_CELDAS]
                # el centro de la caja decide la tesela: cada edificación queda en una sola
                df = con.execute(f"""
                    SELECT (bbox.xmin + bbox.xmax) / 2 AS lon, (bbox.ymin + bbox.ymax) / 2 AS lat, area_in_meters AS area_m2
                    FROM read_parquet({archivos})
                    WHERE bbox.xmax >= {x} AND bbox.xmin < {x + TESELA} AND bbox.ymax >= {y} AND bbox.ymin < {y + TESELA}
                      AND bf_source = 'google' AND confidence >= {CONF_MIN}""").df()
                df = df[(df.lon >= x) & (df.lon < x + TESELA) & (df.lat >= y) & (df.lat < y + TESELA)]
                df.astype("float32").to_parquet(ruta)
            partes.append(pd.read_parquet(ruta))
    t = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["lon", "lat", "area_m2"])
    return t[(t.lon >= o) & (t.lon <= e) & (t.lat >= s) & (t.lat <= n)].reset_index(drop=True)


def a_xy(lon, lat, lat0):
    return np.column_stack([np.radians(lon) * 6371000 * math.cos(math.radians(lat0)), np.radians(lat) * 6371000])
