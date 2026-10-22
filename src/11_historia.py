"""Contexto histórico: récords por departamento, 2024 frente a 2026, y fuego sobre zonas de agua.

Todo con VIIRS S-NPP (data/interim/historico_snpp.parquet), la única serie comparable
2012–2026, y ventanas del mismo calendario cada año, cortadas en el último día completo.

1. Récord por departamento en tres ventanas (desde el 1 de julio, octubre y los
   últimos 10 días): focos de cada año, razón frente a la mediana 2012–2025 y puesto.
   Idea y gráfico ("cada departamento contra su propia historia") de Frank Pinares;
   ventana de los últimos días de Alexander Noblejas; récords departamentales también
   en Víctor Guardia y Amanda Gomez.
2. 2024 frente a 2026: focos por mes, por región natural y por cobertura, e incendios
   con huella ≥ 1 000 ha (analisis/comparar_2024_2026.py).
3. Fuego sobre zonas que producen agua (pregunta de Estefanny Mejía): focos sobre
   3 800 m a ≤ ~250 m de lagunas o humedales altoandinos (bofedales) de ESA WorldCover,
   focos dentro de áreas naturales protegidas y focos en bosque, por año.
4. Área quemada acumulada 2013–2024 por departamento, de MapBiomas Fuego Perú
   (Colección 1, CC-BY), extraída por Flavia Romero.

Salida: data/processed/historia.json
"""
from pathlib import Path
import importlib
import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
focos_mod = importlib.import_module("04_focos")
eventos_mod = importlib.import_module("05_eventos")

RAIZ = Path(__file__).resolve().parents[1]
INT, PRO = RAIZ / "data" / "interim", RAIZ / "data" / "processed"
CURSO = RAIZ / "data" / "curso"
BASE = list(range(2012, 2026))
MIN_FOCOS = 30  # promedio mínimo para hablar de récord en un departamento


def ventana(h, desde_md, hasta_md):
    md = h.fecha.dt.strftime("%m-%d")
    return h[(md >= desde_md) & (md <= hasta_md)]


def records(h, ventanas):
    out = {}
    for clave, (desde, hasta, etiqueta) in ventanas.items():
        t = ventana(h, desde, hasta).groupby(["departamento", "anio"]).size().unstack(fill_value=0)
        t = t.reindex(columns=BASE + [2026], fill_value=0)
        nac = t.sum()
        filas = []
        for dep, s in [("Perú", nac)] + list(t.iterrows()):
            base = s[BASE]
            med = float(base.median())
            filas.append({
                "departamento": dep, "anio_2026": int(s[2026]), "mediana": med, "promedio": round(float(base.mean()), 1),
                "maximo_previo": int(base.max()), "anio_maximo": int(base.idxmax()),
                "puesto": int((s > s[2026]).sum() + 1), "record": bool(s[2026] > base.max()),
                "razon_mediana": round(float(s[2026] / med), 2) if med > 0 else None,
                "suficiente": bool(base.mean() >= MIN_FOCOS),
                "por_anio": {str(a): int(v) for a, v in s.items()},
            })
        out[clave] = {"etiqueta": etiqueta, "desde": desde, "hasta": hasta, "filas": filas}
    return out


def agua_y_ecosistemas(h, hasta_md):
    v = ventana(h, "07-01", hasta_md).copy()
    dem = focos_mod.DEM()
    v["elev"] = dem.muestrear(v.lon.values, v.lat.values)
    z = np.load(INT / "cobertura_150m.npz")
    mos, oeste, norte, paso = z["clase"], float(z["oeste"]), float(z["norte"]), float(z["paso"])
    fila = np.floor((norte - v.lat.values) / paso).astype(int)
    col = np.floor((v.lon.values - oeste) / paso).astype(int)
    agua = np.zeros(len(v), bool)
    for di in (-1, 0, 1):  # ventana de 3 × 3 celdas de ~150 m
        for dj in (-1, 0, 1):
            c = mos[np.clip(fila + di, 0, mos.shape[0] - 1), np.clip(col + dj, 0, mos.shape[1] - 1)]
            agua |= np.isin(c, [80, 90])
    centro = mos[np.clip(fila, 0, mos.shape[0] - 1), np.clip(col, 0, mos.shape[1] - 1)]
    v["altoandino"] = v.elev >= 3800
    v["agua_alto"] = v.altoandino & agua
    v["bosque"] = centro == 10
    anp = gpd.read_parquet(INT / "anp.parquet")
    v["anp"] = focos_mod.unir_anp(v.reset_index(drop=True), anp).anp_nombre.values
    por_anio = v.groupby("anio").agg(focos=("lat", "size"), altoandino=("altoandino", "sum"), agua_alto=("agua_alto", "sum"),
                                     bosque=("bosque", "sum"), anp=("anp", lambda s: int(s.notna().sum())))
    d26 = v[v.anio == 2026]
    base = v[v.anio.isin(BASE)]
    por_dep = (pd.DataFrame({"anio_2026": d26[d26.agua_alto].groupby("departamento").size(),
                             "promedio": base[base.agua_alto].groupby(["departamento", "anio"]).size()
                             .unstack(fill_value=0).reindex(columns=BASE, fill_value=0).mean(axis=1)})
               .fillna(0).sort_values("anio_2026", ascending=False))
    anp26 = d26.anp.value_counts()
    anp_base = base[base.anp.notna()].groupby(["anp", "anio"]).size().unstack(fill_value=0).reindex(columns=BASE, fill_value=0).mean(axis=1)
    anp_tab = pd.DataFrame({"anio_2026": anp26, "promedio": anp_base.reindex(anp26.index).fillna(0)}).head(15)
    return {
        "por_anio": {str(a): {k: int(x) for k, x in r.items()} for a, r in por_anio.iterrows()},
        "agua_por_departamento": [{"departamento": d, "anio_2026": int(r.anio_2026), "promedio": round(float(r.promedio), 1)}
                                  for d, r in por_dep.head(12).iterrows()],
        "anp_2026": [{"anp": a, "anio_2026": int(r.anio_2026), "promedio": round(float(r.promedio), 1)} for a, r in anp_tab.iterrows()],
    }


def comparacion_2024(h, hasta_md):
    v = ventana(h, "07-01", hasta_md)
    v = v[v.anio.isin([2024, 2026])].copy()
    meses = v.groupby(["anio", v.fecha.dt.month]).size().unstack(fill_value=0)
    prom = ventana(h, "07-01", hasta_md)
    prom = prom[prom.anio.isin(BASE)].groupby(["anio", prom.fecha.dt.month]).size().unstack(fill_value=0).mean()
    dem = focos_mod.DEM()
    elev = dem.muestrear(v.lon.values, v.lat.values)
    v["region"] = focos_mod.region_natural(v.lon.values, v.lat.values, elev, dem)
    cob = importlib.import_module("03_cobertura")
    v["cobertura"] = pd.Series(cob.muestrear(v.lon.values, v.lat.values)).map(cob.CLASES).values
    region = pd.crosstab(v.region, v.anio)
    cobert = pd.crosstab(v.cobertura, v.anio).loc[lambda t: t.sum(axis=1).sort_values(ascending=False).index].head(4)
    dep = pd.crosstab(v.departamento, v.anio).assign(t=lambda t: t.sum(axis=1)).sort_values("t", ascending=False).head(10).drop(columns="t")
    grandes = {}
    for a in (2024, 2026):
        g = v[v.anio == a].assign(t_utc=lambda x: x.fecha + pd.Timedelta(hours=12)).sort_values("t_utc").reset_index(drop=True)
        g["inc"] = eventos_mod.agrupar(g)
        huella = g.groupby("inc").apply(lambda x: len(eventos_mod.huella_celdas(x.lon.values, x.lat.values)) * 14.0625)
        grandes[str(a)] = {"incendios_1000ha": int((huella >= 1000).sum()), "mayor_ha": round(float(huella.max()))}
    diaria = v.groupby(["anio", "fecha"]).size()
    return {
        "meses": {str(a): {str(m): int(x) for m, x in r.items()} for a, r in meses.iterrows()},
        "meses_promedio": {str(m): round(float(x)) for m, x in prom.items()},
        "region": {r: {str(a): int(x) for a, x in fila.items()} for r, fila in region.iterrows()},
        "cobertura": {c: {str(a): int(x) for a, x in fila.items()} for c, fila in cobert.iterrows()},
        "departamentos": {d: {str(a): int(x) for a, x in fila.items()} for d, fila in dep.iterrows()},
        "grandes": grandes,
        "pico": {str(a): {"fecha": diaria.loc[a].idxmax().strftime("%Y-%m-%d"), "focos": int(diaria.loc[a].max())} for a in (2024, 2026)},
        "frp_gw": {str(a): round(float(v[v.anio == a].frp.sum() / 1000), 1) for a in (2024, 2026)},
    }


def mapbiomas():
    ruta = CURSO / "mapbiomas_fuego_departamentos.json"
    return json.loads(ruta.read_text()) if ruta.exists() else None


def main():
    h = pd.read_parquet(INT / "historico_snpp.parquet")
    h["anio"] = h.fecha.dt.year
    hasta = h[h.anio == 2026].fecha.max() - pd.Timedelta(days=1)
    hmd = hasta.strftime("%m-%d")
    desde10 = (hasta - pd.Timedelta(days=9)).strftime("%m-%d")
    ventanas = {"temporada": ("07-01", hmd, f"1 jul – {hasta.day} oct"),
                "octubre": ("10-01", hmd, f"1 – {hasta.day} oct"),
                "ultimos10": (desde10, hmd, f"{(hasta - pd.Timedelta(days=9)).day} – {hasta.day} oct")}
    out = {"hasta": hasta.strftime("%Y-%m-%d"), "records": records(h, ventanas)}
    print("récords…", {k: [f["departamento"] for f in v["filas"] if f["record"] and f["suficiente"]] for k, v in out["records"].items()})
    out["comparacion_2024"] = comparacion_2024(h, hmd)
    print("2024 vs 2026", out["comparacion_2024"]["grandes"], out["comparacion_2024"]["pico"])
    out["agua"] = agua_y_ecosistemas(h, hmd)
    print("agua", {a: r for a, r in out["agua"]["por_anio"].items() if a in ("2020", "2024", "2025", "2026")})
    out["mapbiomas"] = mapbiomas()
    with open(PRO / "historia.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False)


if __name__ == "__main__":
    main()
