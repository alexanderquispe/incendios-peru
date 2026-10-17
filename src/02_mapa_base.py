"""Capas base: límites (INEI vía UBIGEO), áreas protegidas (SERNANP),
relieve nacional (AWS Terrain Tiles z9) y población (WorldPop 2020).

Salidas en data/interim/:
- distritos.parquet, provincias.parquet, departamentos.parquet, peru.parquet
- anp.parquet
- dem_z9.npz (DEM nacional en Web Mercator) y pendiente
- dashboard/assets/relieve_peru.png (sombreado para el mapa nacional)
"""
from pathlib import Path
import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from terreno import Mosaico  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT = RAIZ / "data" / "raw", RAIZ / "data" / "interim"
ASSETS = RAIZ / "dashboard" / "assets"
INT.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)

DEPTOS_TILDE = {
    "AMAZONAS": "Amazonas", "ANCASH": "Áncash", "APURIMAC": "Apurímac", "AREQUIPA": "Arequipa",
    "AYACUCHO": "Ayacucho", "CAJAMARCA": "Cajamarca", "CALLAO": "Callao", "CUSCO": "Cusco",
    "HUANCAVELICA": "Huancavelica", "HUANUCO": "Huánuco", "ICA": "Ica", "JUNIN": "Junín",
    "LA LIBERTAD": "La Libertad", "LAMBAYEQUE": "Lambayeque", "LIMA": "Lima", "LORETO": "Loreto",
    "MADRE DE DIOS": "Madre de Dios", "MOQUEGUA": "Moquegua", "PASCO": "Pasco", "PIURA": "Piura",
    "PUNO": "Puno", "SAN MARTIN": "San Martín", "TACNA": "Tacna", "TUMBES": "Tumbes",
    "UCAYALI": "Ucayali",
}
MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y"}


def _sin_tilde(p):
    return p.translate(str.maketrans("ÁÉÍÓÚÜáéíóúü", "AEIOUUaeiouu"))


def _diccionario_tildes():
    """Palabras con tilde tomadas de los nombres de capitales distritales del INEI.

    Los límites traen los nombres en mayúsculas y sin tildes; se restituyen las
    tildes palabra por palabra cuando la forma acentuada es única.
    """
    caps = pd.read_csv(RAW / "limites" / "ubigeo_distrito.csv", usecols=["capital"]).capital.dropna()
    formas = {}
    for nombre in caps:
        for p in str(nombre).replace("-", " ").split():
            if p != _sin_tilde(p):
                formas.setdefault(_sin_tilde(p).upper(), set()).add(p[:1].upper() + p[1:].lower())
    return {k: next(iter(v)) for k, v in formas.items() if len(v) == 1}


TILDES = _diccionario_tildes()


def nombre_propio(s):
    s = str(s).strip()
    if s.upper() in DEPTOS_TILDE:
        return DEPTOS_TILDE[s.upper()]
    out = []
    for i, p in enumerate(s.split()):
        if i > 0 and p.lower() in MINUSCULAS:
            out.append(p.lower())
        else:
            out.append(TILDES.get(p.upper(), p[:1].upper() + p[1:].lower()))
    return " ".join(out)


def limites():
    d = gpd.read_file(RAW / "limites" / "peru_distrital_simple.geojson").to_crs(4326)
    d = d.rename(columns={"IDDIST": "ubigeo", "IDPROV": "ubigeo_prov", "IDDPTO": "ubigeo_dep"})
    d["distrito"] = d["NOMBDIST"].map(nombre_propio)
    d["provincia"] = d["NOMBPROV"].map(nombre_propio)
    d["departamento"] = d["NOMBDEP"].map(nombre_propio)
    d["capital"] = d["NOM_CAP"].map(nombre_propio)
    d["ubigeo"] = d["ubigeo"].astype(str).str.zfill(6)

    ind = pd.read_csv(RAW / "limites" / "ubigeo_distrito.csv", dtype={"inei": str})
    ind = ind.rename(columns={"inei": "ubigeo", "pct_pobreza_total": "pobreza_pct",
                              "pct_pobreza_extrema": "pobreza_extrema_pct"})
    d = d.merge(ind[["ubigeo", "pobreza_pct", "pobreza_extrema_pct", "idh_2019"]], on="ubigeo", how="left")
    d["geometry"] = d.geometry.make_valid()
    d = d[["ubigeo", "ubigeo_prov", "ubigeo_dep", "distrito", "provincia", "departamento",
           "capital", "pobreza_pct", "pobreza_extrema_pct", "idh_2019", "geometry"]]
    d.to_parquet(INT / "distritos.parquet")

    prov = d.dissolve(by=["ubigeo_prov", "provincia", "departamento"], as_index=False)[
        ["ubigeo_prov", "provincia", "departamento", "geometry"]]
    prov.to_parquet(INT / "provincias.parquet")
    dep = d.dissolve(by=["ubigeo_dep", "departamento"], as_index=False)[["ubigeo_dep", "departamento", "geometry"]]
    dep.to_parquet(INT / "departamentos.parquet")
    peru = gpd.GeoDataFrame(geometry=[dep.union_all()], crs=4326)
    peru.to_parquet(INT / "peru.parquet")
    print(f"distritos {len(d)}, provincias {len(prov)}, departamentos {len(dep)}")
    return d, dep, peru


def anp():
    capas = {
        0: ("Nacional", "anp_nomb", "anp_cate"),
        1: ("Zona reservada", "zr_nomb", None),
        2: ("Conservación regional", "acr_nomb", None),
        3: ("Conservación privada", "acp_nomb", None),
    }
    partes = []
    for capa, (admin, col_nom, col_cat) in capas.items():
        g = gpd.read_file(RAW / "sernanp" / f"anp_capa_{capa}.geojson")
        g = g.assign(
            anp_nombre=g[col_nom].map(lambda s: str(s).strip()),
            anp_categoria=g[col_cat].map(lambda s: str(s).strip()) if col_cat else admin,
            anp_admin=admin,
        )[["anp_nombre", "anp_categoria", "anp_admin", "geometry"]]
        partes.append(g)
    a = pd.concat(partes, ignore_index=True)
    a = gpd.GeoDataFrame(a, crs=4326)
    a["geometry"] = a.geometry.make_valid()
    a.to_parquet(INT / "anp.parquet")
    print(f"ANP {len(a)} ({a.anp_admin.value_counts().to_dict()})")
    return a


def relieve(peru):
    o, s, e, n = peru.total_bounds
    m = Mosaico(o - 0.6, s - 0.6, e + 0.6, n + 0.6, z=9)
    np.savez_compressed(INT / "dem_z9.npz", dem=m.dem, mx0=m.mx0, my1=m.my1, res=m.res,
                        x0=m.x0, y0=m.y0, z=m.z)
    print(f"DEM z9 {m.dem.shape}, rango {m.dem.min():.0f}..{m.dem.max():.0f} m")

    m.dem = np.maximum(m.dem, 0)  # el mar sin batimetría
    # Sombreado neutro con canal alfa: sombras oscuras y luces claras, legible en tema claro y oscuro
    hs = m.sombreado(exag=2.0)
    ancho = 1200
    alto = int(round(m.dem.shape[0] * ancho / m.dem.shape[1]))
    hs_img = Image.fromarray((hs * 255).astype(np.uint8)).resize((ancho, alto), Image.LANCZOS)
    hs = np.asarray(hs_img).astype(np.float32) / 255.0
    plano = np.sin(np.radians(45))  # valor de sombreado en terreno plano
    sombra = np.clip((plano - hs) / plano, 0, 1)
    luz = np.clip((hs - plano) / (1 - plano), 0, 1)
    rgba = np.zeros((alto, ancho, 4), dtype=np.uint8)
    es_sombra = sombra > luz
    rgba[..., :3] = np.where(es_sombra[..., None], 20, 255).astype(np.uint8)
    rgba[..., 3] = (np.where(es_sombra, sombra * 150, luz * 90)).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(ASSETS / "relieve_peru.png", optimize=True)
    with open(ASSETS / "relieve_peru.json", "w") as f:
        json.dump({"bounds": [round(v, 5) for v in m.limites_lonlat]}, f)
    print("relieve_peru.png", (ASSETS / "relieve_peru.png").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    d, dep, peru = limites()
    anp()
    relieve(peru)
