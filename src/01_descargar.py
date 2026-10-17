"""Descarga de insumos crudos.

Fuentes (todas públicas, sin autenticación):
- INPE Queimadas: focos de calor mensuales de Sudamérica (todos los satélites),
  filtrados a Perú mientras se descargan.
- NASA FIRMS: archivo anual por país (VIIRS S-NPP, 2012-2025) y archivos de
  los últimos 7 días (S-NPP, NOAA-20, NOAA-21) para Sudamérica.
- GADM 4.1: límites administrativos del Perú (departamento, provincia, distrito).
- WorldPop 2020 (1 km, ajustado a ONU): población.

Uso: python src/01_descargar.py
"""
from pathlib import Path
import io
import zipfile

import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

INPE = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/America_Sul/focos_mensal_{ym}.csv"
FIRMS_PAIS = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{y}/viirs-snpp_{y}_Peru.csv"
FIRMS_7D = {
    "snpp": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_7d.csv",
    "noaa20": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_7d.csv",
    "noaa21": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_7d.csv",
}
GADM = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_{n}.json.zip"
WORLDPOP = "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/PER/per_ppp_2020_1km_Aggregated_UNadj.tif"

# Meses INPE: 2025-06 en adelante (calibración con FIRMS 2025 + todo 2026)
MESES_INPE = [f"2025{m:02d}" for m in range(6, 13)] + [f"2026{m:02d}" for m in range(1, 11)]


def bajar(url, destino, forzar=False):
    if destino.exists() and not forzar:
        return destino
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    destino.write_bytes(r.content)
    print(f"  {destino.name}: {len(r.content) / 1e6:.1f} MB")
    return destino


def bajar_inpe_peru(ym, forzar=False):
    """Descarga un mes de INPE y conserva solo las filas de Perú."""
    destino = RAW / "inpe" / f"inpe_peru_{ym}.csv"
    destino.parent.mkdir(exist_ok=True)
    if destino.exists() and not forzar:
        return destino
    n = 0
    with requests.get(INPE.format(ym=ym), stream=True, timeout=600) as r:
        r.raise_for_status()
        lineas = r.iter_lines(decode_unicode=False)
        encabezado = next(lineas)
        idx_pais = encabezado.decode().split(",").index("pais")
        with open(destino, "wb") as f:
            f.write(encabezado + b"\n")
            for linea in lineas:
                if b"Peru" not in linea and b"Per\xc3\xba" not in linea:
                    continue
                if linea.split(b",")[idx_pais].strip().startswith(b"Per"):
                    f.write(linea + b"\n")
                    n += 1
    print(f"  INPE {ym}: {n:,} focos en Perú")
    return destino


def main():
    print("FIRMS archivo anual por país (VIIRS S-NPP)")
    (RAW / "firms").mkdir(exist_ok=True)
    for y in range(2012, 2026):
        bajar(FIRMS_PAIS.format(y=y), RAW / "firms" / f"viirs-snpp_{y}_Peru.csv")

    print("FIRMS últimos 7 días (siempre se refresca)")
    for sat, url in FIRMS_7D.items():
        bajar(url, RAW / "firms" / f"firms_7d_{sat}_sudamerica.csv", forzar=True)

    print("INPE mensual filtrado a Perú")
    for ym in MESES_INPE:
        # el mes en curso siempre se refresca
        bajar_inpe_peru(ym, forzar=(ym == MESES_INPE[-1]))

    print("GADM 4.1 Perú")
    for n in (1, 2, 3):
        destino = RAW / "gadm" / f"gadm41_PER_{n}.json"
        destino.parent.mkdir(exist_ok=True)
        if not destino.exists():
            r = requests.get(GADM.format(n=n), timeout=300)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                destino.write_bytes(z.read(z.namelist()[0]))
            print(f"  {destino.name}")

    print("WorldPop 2020")
    bajar(WORLDPOP, RAW / "worldpop_per_2020_1km.tif")


if __name__ == "__main__":
    main()
