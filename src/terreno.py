"""Utilidades de terreno a partir de AWS Terrain Tiles (codificación Terrarium).

Las teselas son públicas (s3://elevation-tiles-prod) y combinan SRTM, GMTED y
otras fuentes. A zoom 9 el píxel mide ~300 m en Perú; a zoom 12, ~38 m.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io

import mercantile
import numpy as np
import requests
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "data" / "raw" / "terrain"
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
R_TIERRA = 6378137.0


def _bajar_tesela(z, x, y):
    ruta = CACHE / str(z) / f"{x}_{y}.png"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        for intento in range(4):
            try:
                r = requests.get(URL.format(z=z, x=x, y=y), timeout=60)
                r.raise_for_status()
                ruta.write_bytes(r.content)
                break
            except requests.RequestException:
                if intento == 3:
                    raise
    return ruta


def decodificar(rgb):
    rgb = rgb.astype(np.float32)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


class Mosaico:
    """DEM en Web Mercator armado con teselas de un zoom dado."""

    def __init__(self, oeste, sur, este, norte, z):
        self.z = z
        t0 = mercantile.tile(oeste, norte, z)
        t1 = mercantile.tile(este, sur, z)
        self.x0, self.y0, self.x1, self.y1 = t0.x, t0.y, t1.x, t1.y
        tiles = [(x, y) for x in range(self.x0, self.x1 + 1) for y in range(self.y0, self.y1 + 1)]
        with ThreadPoolExecutor(16) as ex:
            rutas = list(ex.map(lambda t: _bajar_tesela(z, *t), tiles))
        nx, ny = self.x1 - self.x0 + 1, self.y1 - self.y0 + 1
        self.dem = np.zeros((ny * 256, nx * 256), dtype=np.float32)
        for (x, y), ruta in zip(tiles, rutas):
            arr = np.asarray(Image.open(ruta).convert("RGB"))
            i, j = (y - self.y0) * 256, (x - self.x0) * 256
            self.dem[i:i + 256, j:j + 256] = decodificar(arr)
        # límites en metros Mercator
        ul = mercantile.xy_bounds(self.x0, self.y0, z)
        lr = mercantile.xy_bounds(self.x1, self.y1, z)
        self.mx0, self.my1, self.mx1, self.my0 = ul.left, ul.top, lr.right, lr.bottom
        self.res = (self.mx1 - self.mx0) / self.dem.shape[1]

    @property
    def limites_lonlat(self):
        o, n = mercantile.lnglat(self.mx0, self.my1)
        e, s = mercantile.lnglat(self.mx1, self.my0)
        return o, s, e, n

    def fila_col(self, lon, lat):
        lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
        mx = np.radians(lon) * R_TIERRA
        my = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * R_TIERRA
        col = (mx - self.mx0) / self.res
        fila = (self.my1 - my) / self.res
        return fila, col

    def muestrear(self, lon, lat):
        fila, col = self.fila_col(lon, lat)
        fila = np.clip(np.round(fila).astype(int), 0, self.dem.shape[0] - 1)
        col = np.clip(np.round(col).astype(int), 0, self.dem.shape[1] - 1)
        return self.dem[fila, col]

    def pendiente(self):
        """Pendiente en grados, corrigiendo la escala Mercator por latitud."""
        filas = np.arange(self.dem.shape[0])
        my = self.my1 - (filas + 0.5) * self.res
        lat = np.degrees(2 * np.arctan(np.exp(my / R_TIERRA)) - np.pi / 2)
        tam = self.res * np.cos(np.radians(lat))[:, None]
        gy, gx = np.gradient(self.dem)
        return np.degrees(np.arctan(np.hypot(gx / tam, gy / tam)))

    def sombreado(self, azimut=315.0, altitud=45.0, exag=1.0):
        filas = np.arange(self.dem.shape[0])
        my = self.my1 - (filas + 0.5) * self.res
        lat = np.degrees(2 * np.arctan(np.exp(my / R_TIERRA)) - np.pi / 2)
        tam = self.res * np.cos(np.radians(lat))[:, None]
        gy, gx = np.gradient(self.dem * exag)
        gx, gy = gx / tam, gy / tam
        pend = np.pi / 2 - np.arctan(np.hypot(gx, gy))
        asp = np.arctan2(-gx, gy)
        az, alt = np.radians(360 - azimut + 90), np.radians(altitud)
        hs = np.sin(alt) * np.sin(pend) + np.cos(alt) * np.cos(pend) * np.cos(az - asp)
        return np.clip(hs, 0, 1)


def terrain_rgb_terrarium(dem):
    """Codifica un DEM a PNG Terrarium (para deck.gl TerrainLayer)."""
    v = np.clip(dem, -32768, 32767) + 32768.0
    r = np.floor(v / 256.0)
    g = np.floor(v - r * 256.0)
    b = np.floor((v - r * 256.0 - g) * 256.0)
    return np.dstack([r, g, b]).astype(np.uint8)
