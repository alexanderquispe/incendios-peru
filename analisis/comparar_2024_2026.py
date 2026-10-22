"""¿Por qué 2024 se ve mucho peor que 2026? Comparación con la misma fuente y la misma ventana.

Usa solo VIIRS S-NPP (data/interim/historico_snpp.parquet), la única serie comparable
2012–2026, entre el 1 de julio y el último día completo de 2026 (16 oct). Mide:
1. cuántos focos y en qué mes;
2. dónde (departamento, región natural, cobertura ESA WorldCover, áreas protegidas);
3. intensidad (FRP) y extensión (celdas de 375 m con fuego);
4. tamaño de los incendios, con el mismo agrupamiento de src/05_eventos.py (1 km, 48 h);
5. población a ≤ 5 km de algún foco (WorldPop 2020).

Uso: .venv/bin/python analisis/comparar_2024_2026.py
Salida: tablas en pantalla y data/processed/comparacion_2024_2026.csv
"""
from pathlib import Path
import importlib
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
focos_mod = importlib.import_module("04_focos")
eventos_mod = importlib.import_module("05_eventos")
exportar_mod = importlib.import_module("07_exportar")
cobertura = importlib.import_module("03_cobertura")

INT, PRO = RAIZ / "data" / "interim", RAIZ / "data" / "processed"
ANIOS = [2024, 2026]
BASE = range(2012, 2026)
MESES = {7: "jul", 8: "ago", 9: "set", 10: "oct"}


def ventana(h, hasta_md):
    md = h.fecha.dt.strftime("%m-%d")
    return h[(md >= "07-01") & (md <= hasta_md)].copy()


def atributos(v):
    """Región natural, cobertura y ANP con las mismas funciones del pipeline."""
    dem = focos_mod.DEM()
    elev = dem.muestrear(v.lon.values, v.lat.values)
    v["region"] = focos_mod.region_natural(v.lon.values, v.lat.values, elev, dem)
    v["cobertura"] = pd.Series(cobertura.muestrear(v.lon.values, v.lat.values)).map(cobertura.CLASES).values
    anp = gpd.read_parquet(INT / "anp.parquet")
    v["anp"] = focos_mod.unir_anp(v.reset_index(drop=True), anp).anp_nombre.values
    return v


def personas_dia(v, radio=5000):
    """Suma, día por día, la población WorldPop a ≤ radio de algún foco de ese día."""
    with rasterio.open(RAIZ / "data" / "raw" / "worldpop_per_2020_1km.tif") as src:
        pob = src.read(1)
        filas, cols = np.nonzero(pob > 0)
        xs, ys = rasterio.transform.xy(src.transform, filas, cols)
        valores = pob[filas, cols]
    arbol = cKDTree(exportar_mod.a_metros(np.asarray(xs), np.asarray(ys)))
    total = {}
    for (a, _), g in v.groupby(["anio", "fecha"]):
        idx = arbol.query_ball_point(exportar_mod.a_metros(g.lon.values, g.lat.values), radio)
        celdas = np.unique(np.concatenate([np.asarray(i, dtype=int) for i in idx]))
        total[a] = total.get(a, 0.0) + float(valores[celdas].sum())
    return total


def incendios(g):
    """Agrupa focos en incendios (≤ 1 km y ≤ 48 h); el histórico solo trae la fecha, se usa el mediodía."""
    g = g.assign(t_utc=g.fecha + pd.Timedelta(hours=12)).sort_values("t_utc").reset_index(drop=True)
    g["inc"] = eventos_mod.agrupar(g)
    filas = []
    for _, x in g.groupby("inc"):
        filas.append({"focos": len(x), "huella_ha": len(eventos_mod.huella_celdas(x.lon.values, x.lat.values)) * 14.0625,
                      "departamento": x.departamento.mode().iloc[0], "provincia": x.provincia.mode().iloc[0],
                      "inicio": x.fecha.min().date(), "fin": x.fecha.max().date()})
    return pd.DataFrame(filas).sort_values("huella_ha", ascending=False)


def main():
    h = pd.read_parquet(INT / "historico_snpp.parquet")
    h["anio"] = h.fecha.dt.year
    hasta = h[h.anio == 2026].fecha.max() - pd.Timedelta(days=1)  # último día completo
    hasta_md = hasta.strftime("%m-%d")
    v = ventana(h, hasta_md)
    v["mes"] = v.fecha.dt.month
    print(f"Ventana: 1 jul – {hasta:%d %b} de cada año · VIIRS S-NPP\n")

    # 1. cuántos y cuándo
    por_mes = v.groupby(["anio", "mes"]).size().unstack(fill_value=0).rename(columns=MESES)
    por_mes["total"] = por_mes.sum(axis=1)
    tabla = por_mes.loc[ANIOS].copy()
    tabla.loc["promedio 2012–2025"] = por_mes.loc[list(BASE)].mean().round(0)
    print("1. Focos por mes (oct solo hasta el día de corte)")
    print(tabla.astype(int).to_string(), "\n")

    diaria = v.groupby(["anio", "fecha"]).size()
    p90 = diaria.loc[list(BASE)].quantile(0.9)
    for a in ANIOS:
        d = diaria.loc[a]
        print(f"   {a}: día pico {d.idxmax():%d %b} con {d.max():,} focos; "
              f"{(d > p90).sum()} días sobre el p90 histórico ({p90:,.0f} focos/día)")
    resto = h[(h.anio == 2024) & (h.fecha > f"2024-{hasta_md}") & (h.fecha <= "2024-11-30")]
    print(f"   2024 sumó {len(resto):,} focos más entre el {hasta_md[-2:]} oct y el 30 nov "
          f"(+{len(resto) / por_mes.loc[2024, 'total'] * 100:.0f} % sobre lo ya visto)\n")

    # 2. dónde
    v = v[v.anio.isin(ANIOS)].copy()
    v = atributos(v)
    def reparto(col, n=None):
        t = pd.crosstab(v[col].fillna("—"), v.anio)
        t = t.loc[t.sum(axis=1).sort_values(ascending=False).index]
        if n:
            t = t.head(n)
        t["2024 / 2026"] = (t[2024] / t[2026].replace(0, np.nan)).round(1)
        return t
    print("2a. Departamentos con más focos (suma de ambos años)")
    print(reparto("departamento", 10).to_string(), "\n")
    print("2b. Región natural (focos y % del año)")
    r = reparto("region")
    r[["% 2024", "% 2026"]] = (r[ANIOS] / r[ANIOS].sum() * 100).round(0).values
    print(r.to_string(), "\n")
    print("2c. Cobertura del suelo, ESA WorldCover 2021 (%)")
    print(pd.crosstab(v.cobertura, v.anio, normalize="columns").mul(100).round(0)
          .sort_values(2024, ascending=False).head(5).to_string(), "\n")

    # 3. intensidad y extensión
    filas = {}
    for a in ANIOS:
        g = v[v.anio == a]
        filas[a] = {
            "focos": len(g),
            "FRP total (GW)": g.frp.sum() / 1000,
            "FRP mediana (MW)": g.frp.median(),
            "focos con FRP ≥ 20 MW": int((g.frp >= 20).sum()),
            "extensión con fuego (ha, celdas 375 m)": len(eventos_mod.huella_celdas(g.lon.values, g.lat.values)) * 14.0625,
            "focos en áreas protegidas": int(g.anp.notna().sum()),
            "áreas protegidas con focos": int(g.anp.nunique()),
            "focos en bosque": int((g.cobertura == "Bosque").sum()),
        }
    print("   calculando población expuesta día a día…")
    pdias = personas_dia(v)
    for a in ANIOS:
        filas[a]["personas-día a ≤ 5 km de un foco (millones)"] = pdias[a] / 1e6

    # 4. tamaño de los incendios
    inc = {a: incendios(v[v.anio == a]) for a in ANIOS}
    for a in ANIOS:
        filas[a]["incendios ≥ 1,000 ha"] = int((inc[a].huella_ha >= 1000).sum())
        filas[a]["incendios ≥ 5,000 ha"] = int((inc[a].huella_ha >= 5000).sum())
        filas[a]["huella del mayor incendio (ha)"] = inc[a].huella_ha.max()
    comp = pd.DataFrame(filas)
    comp["2024 / 2026"] = (comp[2024] / comp[2026]).round(1)
    print("3–5. Intensidad, extensión, exposición y tamaño")
    with pd.option_context("display.float_format", "{:,.1f}".format):
        print(comp.to_string(), "\n")

    for a in ANIOS:
        print(f"Los 8 incendios más extensos de {a} (huella VIIRS)")
        print(inc[a].head(8).to_string(index=False, formatters={"huella_ha": "{:,.0f}".format}), "\n")

    comp.to_csv(PRO / "comparacion_2024_2026.csv")
    print(f"guardado: {PRO / 'comparacion_2024_2026.csv'}")


if __name__ == "__main__":
    main()
