"""¿A quién afecta? Personas, edificaciones, salud y conectividad cerca de los incendios.

Integra los métodos de varias entregas del curso de Data Science (sesión 14):
- distancias de 1, 2, 5 y 10 km desde los focos de las últimas 72 h, sin doble conteo
  entre incendios ni entre focos (Rodrigo Norabuena, Josselin Yauri, Greicy Rodriguez);
- solo incendios de vegetación probables (Diego Sime, Rodrigo Norabuena); se informa
  cuánto cambia la cifra con otras definiciones (Josselin Yauri, Ricardo Macedo);
- edificaciones de Google Open Buildings v3, confianza ≥ 0,75 (Roddy Huarhua,
  Ximena Pinillos, Luis Guevara, Rodrigo Norabuena);
- establecimientos de salud públicos (RENIPRESS/SUSALUD) y centros poblados con o sin
  cobertura 4G (OSIPTEL) (Diego Sime);
- % de la población del departamento a ≤ 5 km (Josselin Yauri);
- en los incendios con área quemada Sentinel-2: edificaciones y personas dentro y a
  ≤ 100 m, 500 m y 1 km del borde (Roddy Huarhua, Greicy Rodriguez).

Población: WorldPop 2026, 100 m, restringida a zonas con edificaciones.

Salidas en data/processed/:
- exposicion_incendios.parquet   un registro por incendio activo o en observación probable
- exposicion_resumen.json         totales nacionales, por departamento y sensibilidad
- exposicion_quemado.parquet      exposición al área quemada de los incendios con 3D
"""
from pathlib import Path
import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio import features
from scipy.spatial import cKDTree
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent))
from exposicion_util import Poblacion, a_xy, edificaciones  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT, PRO = RAIZ / "data" / "raw", RAIZ / "data" / "interim", RAIZ / "data" / "processed"
EVENTOS_3D = RAIZ / "dashboard" / "data" / "eventos"
RADIOS = [1000, 2000, 5000, 10000]
PUBLICO = ["GOBIERNO REGIONAL", "MINSA", "ESSALUD", "SANIDAD DEL EJERCITO DEL PERU", "SANIDAD DE LA FUERZA AEREA DEL PERU",
           "SANIDAD DE LA MARINA DE GUERRA DEL PERU", "SANIDAD DE LA POLICIA NACIONAL DEL PERU", "MUNICIPALIDAD PROVINCIAL",
           "MUNICIPALIDAD DISTRITAL", "INPE", "OTRO"]


def salud():
    r = pd.read_csv(RAW / "servicios" / "renipress.csv", sep=";", encoding="utf-8-sig", dtype=str)
    r = r[(r.ESTADO == "ACTIVO") & r.CATEGORIA.str.match(r"^(I|II|III)-", na=False) & r.INSTITUCION.isin(PUBLICO)].copy()
    r["lat"] = pd.to_numeric(r.NORTE, errors="coerce")
    r["lon"] = pd.to_numeric(r.ESTE, errors="coerce")
    r = r[r.lat.between(-18.5, 0.1) & r.lon.between(-81.5, -68.5)]
    return r[["NOMBRE", "CATEGORIA", "INSTITUCION", "DISTRITO", "lat", "lon"]].reset_index(drop=True)


def centros_poblados():
    o = pd.read_csv(RAW / "servicios" / "osiptel_cobertura_ccpp.csv", sep=";", encoding="latin1", dtype=str)
    o.columns = o.columns.str.strip()
    cg4 = [c for c in o.columns if c.endswith("_4G_CG")]
    pct = o[cg4].apply(lambda s: pd.to_numeric(s.str.replace("%", "").str.strip(), errors="coerce"))
    o["con_4g"] = (pct.fillna(0) > 0).any(axis=1)
    o["lat"] = pd.to_numeric(o.Latitud, errors="coerce")
    o["lon"] = pd.to_numeric(o.Longitud, errors="coerce")
    o = o[o.lat.between(-18.5, 0.1) & o.lon.between(-81.5, -68.5)]
    return o[["CentroPoblado", "Clasificacion", "con_4g", "lat", "lon"]].reset_index(drop=True)


def departamentos_raster(wp):
    dep = gpd.read_parquet(INT / "departamentos.parquet")
    nombres = list(dep.departamento)
    r = features.rasterize(((g, i + 1) for i, g in enumerate(dep.geometry)), out_shape=wp.pob.shape,
                           transform=wp.t, dtype="uint8")
    return nombres, r.ravel()


def main():
    ev = pd.read_parquet(PRO / "eventos.parquet")
    focos = pd.read_parquet(PRO / "focos_temporada.parquet")
    corte = focos.t_local.max()
    wp = Poblacion()
    nombres_dep, dep_celda = departamentos_raster(wp)
    pob_dep = np.bincount(dep_celda, weights=wp.pob.ravel(), minlength=len(nombres_dep) + 1)

    vivos = ev[ev.estado.isin(["Activo", "En observación"])]
    recientes = focos[(focos.t_local > corte - pd.Timedelta(hours=72)) & focos.evento.isin(vivos.evento)]
    sal, ccpp = salud(), centros_poblados()
    print(f"establecimientos públicos de salud: {len(sal):,}; centros poblados OSIPTEL: {len(ccpp):,}")

    filas, celdas = [], {r: {} for r in RADIOS}
    for e in vivos.itertuples():
        g = recientes[recientes.evento == e.evento]
        if g.empty:
            g = focos[focos.evento == e.evento]
        lon, lat = g.lon.values, g.lat.values
        fila = {"evento": e.evento, "evidencia": e.evidencia, "estado": e.estado, "focos": e.focos}
        for r in RADIOS:
            idx = wp.celdas(lon, lat, r)
            celdas[r][e.evento] = idx
            fila[f"pob_{r // 1000}km"] = round(wp.suma(idx))
        if e.evidencia == "probable":
            lat0 = float(lat.mean())
            arbol = cKDTree(a_xy(lon, lat, lat0))
            m = 5000 / 111320
            o, s_, e_, n = lon.min() - m / np.cos(np.radians(lat0)), lat.min() - m, lon.max() + m / np.cos(np.radians(lat0)), lat.max() + m
            b = edificaciones(o, s_, e_, n)
            d = arbol.query(a_xy(b.lon.values, b.lat.values, lat0))[0] if len(b) else np.array([])
            for r in RADIOS[:3]:
                fila[f"edif_{r // 1000}km"] = int((d <= r).sum())
            for nombre, capa in (("salud", sal), ("ccpp", ccpp)):
                dd = arbol.query(a_xy(capa.lon.values, capa.lat.values, lat0))[0]
                cerca = capa[dd <= 5000].assign(dist_km=dd[dd <= 5000] / 1000).sort_values("dist_km")
                fila[f"{nombre}_5km"] = len(cerca)
                if nombre == "salud":
                    fila["salud_cercanos"] = [{"nombre": x.NOMBRE.title(), "categoria": x.CATEGORIA, "km": round(x.dist_km, 1)}
                                              for x in cerca.head(3).itertuples()]
                    fila["salud_mas_cercano_km"] = round(float(dd.min() / 1000), 1)
                else:
                    fila["ccpp_sin_4g_5km"] = int((~cerca.con_4g).sum())
        filas.append(fila)
    tabla = pd.DataFrame(filas)
    tabla.to_parquet(PRO / "exposicion_incendios.parquet")

    # totales sin doble conteo y sensibilidad a la definición de incendio
    def union(ids, r):
        idx = [celdas[r][i] for i in ids if i in celdas[r]]
        return np.unique(np.concatenate(idx)) if idx else np.array([], int)

    definiciones = {
        "probables": vivos[vivos.evidencia == "probable"].evento,
        "probables_activos": vivos[(vivos.evidencia == "probable") & (vivos.estado == "Activo")].evento,
        "todos_3focos": vivos[vivos.focos >= 3].evento,
        "todos": vivos.evento,
    }
    sens = {k: {f"{r // 1000}km": round(wp.suma(union(ids, r))) for r in RADIOS} | {"incendios": int(len(ids))}
            for k, ids in definiciones.items()}
    idx5 = union(definiciones["probables"], 5000)
    por_dep = np.bincount(dep_celda[idx5], weights=wp.pob.ravel()[idx5], minlength=len(nombres_dep) + 1)
    deps = [{"departamento": nombres_dep[i - 1], "pob_5km": round(float(por_dep[i])),
             "pct": round(float(por_dep[i] / pob_dep[i] * 100), 2)}
            for i in range(1, len(nombres_dep) + 1) if por_dep[i] >= 1]
    prob = tabla[tabla.evidencia == "probable"]
    resumen = {
        "corte": corte.strftime("%Y-%m-%d %H:%M"),
        "sensibilidad": sens,
        "departamentos": sorted(deps, key=lambda d: -d["pob_5km"]),
        "edificaciones_5km": int(prob.edif_5km.sum()), "edificaciones_1km": int(prob.edif_1km.sum()),
        "salud_5km": int(prob.salud_5km.sum()), "ccpp_5km": int(prob.ccpp_5km.sum()),
        "ccpp_sin_4g_5km": int(prob.ccpp_sin_4g_5km.sum()),
        "fuentes": {"salud_total": int(len(sal)), "ccpp_total": int(len(ccpp))},
    }
    with open(PRO / "exposicion_resumen.json", "w") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=1)
    print(json.dumps(sens, indent=1))
    print(prob.sort_values("pob_5km", ascending=False).head(10).drop(columns=["salud_cercanos"]).to_string())

    # incendios con área quemada Sentinel-2: dentro y a ≤ 100 m, 500 m y 1 km del borde
    sel = json.loads((EVENTOS_3D / "seleccion.json").read_text()) if (EVENTOS_3D / "seleccion.json").exists() else []
    quem = []
    for eid in sel:
        d = json.loads((EVENTOS_3D / f"{eid}.json").read_text())
        sev = d.get("severidad")
        if not sev or not sev.get("perimetro"):
            continue
        geom = shape(sev["perimetro"])
        o, s_, e_, n = geom.bounds
        lat0 = (s_ + n) / 2
        utm = gpd.GeoSeries([geom], crs=4326).estimate_utm_crs()
        g_m = gpd.GeoSeries([geom], crs=4326).to_crs(utm).iloc[0]
        m = 1100 / 111320
        b = edificaciones(o - m, s_ - m, e_ + m, n + m)
        pts = gpd.GeoSeries(gpd.points_from_xy(b.lon, b.lat), crs=4326).to_crs(utm)
        dist = pts.distance(g_m).values if len(b) else np.array([])
        fila = {"evento": eid}
        for nombre, r in (("dentro", 0), ("100m", 100), ("500m", 500), ("1km", 1000)):
            fila[f"edif_{nombre}"] = int((dist <= r).sum())
        # población: celdas de 100 m cuyo centro cae dentro o a ≤ 1 km del área quemada
        for nombre, buf in (("dentro", 0), ("1km", 1000)):
            zona = gpd.GeoSeries([g_m.buffer(buf)], crs=utm).to_crs(4326).iloc[0]
            f0, c0 = wp.fila_col(zona.bounds[0], zona.bounds[3])
            f1, c1 = wp.fila_col(zona.bounds[2], zona.bounds[1])
            win = wp.pob[f0:f1 + 1, c0:c1 + 1]
            from rasterio.transform import from_origin
            t = from_origin(wp.t.c + c0 * wp.t.a, wp.t.f + f0 * wp.t.e, wp.t.a, -wp.t.e)
            mask = features.geometry_mask([zona], out_shape=win.shape, transform=t, invert=True)
            fila[f"pob_{nombre}"] = round(float(win[mask].sum()))
        quem.append(fila)
    q = pd.DataFrame(quem)
    q.to_parquet(PRO / "exposicion_quemado.parquet")
    print(q.to_string())


if __name__ == "__main__":
    main()
