"""Cobertura del suelo ESA WorldCover 2021 (v200) para Perú.

Lee la vista general 1/16 de cada tesela COG (≈150 m) directamente desde el
bucket público de AWS y arma un mosaico nacional en EPSG:4326.
Salida: data/interim/cobertura_150m.npz
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box

RAIZ = Path(__file__).resolve().parents[1]
INT = RAIZ / "data" / "interim"
URL = ("/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
       "ESA_WorldCover_10m_2021_v200_{lat}{lon}_Map.tif")
FACTOR = 16
PX = 36000 // FACTOR  # píxeles por tesela de 3°

CLASES = {
    10: "Bosque", 20: "Matorral", 30: "Pastizal", 40: "Cultivo", 50: "Urbano",
    60: "Suelo desnudo", 70: "Nieve y hielo", 80: "Agua", 90: "Humedal herbáceo",
    95: "Manglar", 100: "Musgo y liquen",
}


def nombre_tesela(lat, lon):
    ns = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
    ew = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
    return URL.format(lat=ns, lon=ew)


def leer(lat, lon):
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(nombre_tesela(lat, lon)) as src:
            return lat, lon, src.read(1, out_shape=(PX, PX))


def main():
    peru = gpd.read_parquet(INT / "peru.parquet").geometry.iloc[0]
    tes = [(la, lo) for la in range(-21, 3, 3) for lo in range(-84, -66, 3)
           if box(lo, la, lo + 3, la + 3).intersects(peru)]
    lat0, lat1 = min(t[0] for t in tes), max(t[0] for t in tes) + 3
    lon0, lon1 = min(t[1] for t in tes), max(t[1] for t in tes) + 3
    mos = np.zeros(((lat1 - lat0) // 3 * PX, (lon1 - lon0) // 3 * PX), dtype=np.uint8)
    with ThreadPoolExecutor(8) as ex:
        for la, lo, arr in ex.map(lambda t: leer(*t), tes):
            i = (lat1 - (la + 3)) // 3 * PX
            j = (lo - lon0) // 3 * PX
            mos[i:i + PX, j:j + PX] = arr
    np.savez_compressed(INT / "cobertura_150m.npz", clase=mos, oeste=lon0, norte=lat1, paso=3 / PX)
    print(f"{len(tes)} teselas, mosaico {mos.shape}")


def muestrear(lon, lat, ventana=1):
    """Clase mayoritaria en una ventana (2*ventana+1)^2 alrededor de cada punto."""
    z = np.load(INT / "cobertura_150m.npz")
    mos, oeste, norte, paso = z["clase"], float(z["oeste"]), float(z["norte"]), float(z["paso"])
    fila = np.floor((norte - np.asarray(lat)) / paso).astype(int)
    col = np.floor((np.asarray(lon) - oeste) / paso).astype(int)
    vals = []
    for di in range(-ventana, ventana + 1):
        for dj in range(-ventana, ventana + 1):
            f = np.clip(fila + di, 0, mos.shape[0] - 1)
            c = np.clip(col + dj, 0, mos.shape[1] - 1)
            vals.append(mos[f, c])
    vals = np.stack(vals, axis=1)
    clases = np.array(sorted(CLASES))
    conteo = (vals[:, :, None] == clases[None, None, :]).sum(axis=1)
    return clases[conteo.argmax(axis=1)]


if __name__ == "__main__":
    main()
