"""Exporta los datos del tablero a dashboard/data/*.json.

Todo número que muestra el tablero sale de aquí; el HTML no contiene cifras.
"""
from pathlib import Path
import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT, PRO = RAIZ / "data" / "raw", RAIZ / "data" / "interim", RAIZ / "data" / "processed"
OUT = RAIZ / "dashboard" / "data"
OUT.mkdir(parents=True, exist_ok=True)
INICIO = pd.Timestamp("2026-07-01")
ANIOS_BASE = range(2012, 2026)


def guardar(nombre, obj):
    with open(OUT / nombre, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print(f"  {nombre}: {(OUT / nombre).stat().st_size / 1024:.0f} KB")


def limpio(v):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M")
    return v


def a_metros(lon, lat):
    return np.column_stack([np.radians(lon) * 6371000 * np.cos(np.radians(-9.0)), np.radians(lat) * 6371000])


def poblacion_union(lon, lat, radio=5000):
    with rasterio.open(RAW / "worldpop_per_2020_1km.tif") as src:
        pob = src.read(1)
        filas, cols = np.nonzero(pob > 0)
        xs, ys = rasterio.transform.xy(src.transform, filas, cols)
        valores = pob[filas, cols]
    arbol = cKDTree(a_metros(np.asarray(xs), np.asarray(ys)))
    idx = arbol.query_ball_point(a_metros(np.asarray(lon), np.asarray(lat)), radio)
    celdas = set().union(*map(set, idx)) if len(idx) else set()
    return float(valores[list(celdas)].sum()) if celdas else 0.0


def ventana_anual(h, desde_md, hasta_md):
    md = h.fecha.dt.strftime("%m-%d")
    return h[(md >= desde_md) & (md <= hasta_md)]


def main():
    focos = pd.read_parquet(INT / "focos_viirs.parquet")
    ev = pd.read_parquet(PRO / "eventos.parquet")
    hist = pd.read_parquet(INT / "historico_snpp.parquet")
    corte = focos.t_local.max()
    hoy = corte.normalize()
    hasta_md = (hoy - pd.Timedelta(days=1)).strftime("%m-%d")  # último día completo
    temporada = focos[focos.fecha >= INICIO]
    f24 = focos[focos.t_local > corte - pd.Timedelta(hours=24)]
    f48 = focos[focos.t_local > corte - pd.Timedelta(hours=48)]
    f7 = focos[focos.t_local > corte - pd.Timedelta(days=7)]
    hist["anio"] = hist.fecha.dt.year

    # ------------------------------------------------------------ comparación S-NPP
    v_temp = ventana_anual(hist, "07-01", hasta_md).groupby("anio").size()
    v_oct = ventana_anual(hist, "10-01", hasta_md).groupby("anio").size()
    def resumen_ventana(s):
        base = s.loc[list(ANIOS_BASE)]
        return {"anio_2026": int(s[2026]), "promedio_2012_2025": round(float(base.mean())),
                "anomalia_pct": round((s[2026] / base.mean() - 1) * 100),
                "puesto_2026": int(s.rank(ascending=False, method="min")[2026]), "anios": int(len(s)),
                "maximo_previo": {"anio": int(base.idxmax()), "focos": int(base.max())},
                "por_anio": {str(k): int(v) for k, v in s.items()}}

    activos = ev[ev.estado == "Activo"]
    prob = activos[activos.evidencia == "probable"]
    expo = json.load(open(PRO / "exposicion_resumen.json")) if (PRO / "exposicion_resumen.json").exists() else None

    anp7 = f7[f7.anp_nombre.notna()]
    regiones7 = f7.region.value_counts(normalize=True).mul(100).round(0)
    cob7 = f7.cobertura.value_counts(normalize=True).mul(100).round(0)
    dep7 = f7.departamento.value_counts()

    resumen = {
        "corte_local": corte.strftime("%Y-%m-%d %H:%M"),
        "ultimo_dia_completo": (hoy - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "inicio_temporada": INICIO.strftime("%Y-%m-%d"),
        "generado_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M"),
        "focos_24h": int(len(f24)), "focos_24h_previas": int(len(f48) - len(f24)),
        "focos_7d": int(len(f7)), "focos_temporada": int(len(temporada)),
        "eventos_activos": int(len(activos)),
        "eventos_activos_probables": int(len(prob)),
        "eventos_activos_100ha": int((prob.huella_ha >= 100).sum()),
        "eventos_activos_3focos": int((activos.focos >= 3).sum()),
        "eventos_activos_evidencia": {k: int(v) for k, v in activos.evidencia.value_counts().items()},
        "eventos_observacion": int((ev.estado == "En observación").sum()),
        "eventos_observacion_probables": int(((ev.estado == "En observación") & (ev.evidencia == "probable")).sum()),
        "eventos_temporada_sig": int(ev.significativo.sum()),
        "eventos_temporada_probables": int((ev.evidencia == "probable").sum()),
        "poblacion_5km_probables": expo["sensibilidad"]["probables"]["5km"] if expo else None,
        "poblacion_5km_probables_activos": expo["sensibilidad"]["probables_activos"]["5km"] if expo else None,
        "poblacion_5km_todos": expo["sensibilidad"]["todos"]["5km"] if expo else None,
        "focos_anp_7d": int(len(anp7)), "anp_con_focos_7d": int(anp7.anp_nombre.nunique()),
        "anp_7d": [{"anp": k, "focos": int(v)} for k, v in anp7.anp_nombre.value_counts().head(8).items()],
        "region_7d_pct": {k: int(v) for k, v in regiones7.items()},
        "cobertura_7d_pct": {k: int(v) for k, v in cob7.items()},
        "departamentos_7d_top": [{"departamento": k, "focos": int(v)} for k, v in dep7.head(5).items()],
        "snpp_temporada": resumen_ventana(v_temp), "snpp_octubre": resumen_ventana(v_oct),
        "ventana_temporada": f"1 jul – {pd.Timestamp('2026-' + hasta_md).strftime('%d')} oct",
        "dias_temporada": int((hoy - INICIO).days),
    }
    guardar("resumen.json", resumen)

    # ------------------------------------------------------------ series
    dias = pd.date_range("2026-06-01", hoy - pd.Timedelta(days=1))
    diaria = focos.groupby(["fecha", "region"]).size().unstack(fill_value=0).reindex(dias, fill_value=0)
    h = hist.copy()
    h["doy"] = h.fecha.dt.dayofyear - np.where(h.fecha.dt.is_leap_year & (h.fecha.dt.month > 2), 1, 0)
    snpp_diaria = h.groupby(["anio", "doy"]).size().unstack(0, fill_value=0).reindex(range(1, 366), fill_value=0)
    suav = snpp_diaria.rolling(7, center=True, min_periods=1).mean()
    doy_ini, doy_fin = 182, int(dias[-1].dayofyear - (1 if dias[-1].is_leap_year else 0))
    base = suav[list(ANIOS_BASE)]
    rango = range(152, 336)  # 1 jun - 1 dic
    acum = snpp_diaria.loc[doy_ini:].cumsum()
    series = {
        "fechas": [d.strftime("%Y-%m-%d") for d in dias],
        "viirs_por_region": {r: diaria[r].astype(int).tolist() for r in ["Selva", "Sierra", "Costa"] if r in diaria},
        "snpp_clima": {
            "doy": list(rango),
            "p10": base.loc[rango].quantile(0.1, axis=1).round(1).tolist(),
            "p50": base.loc[rango].median(axis=1).round(1).tolist(),
            "p90": base.loc[rango].quantile(0.9, axis=1).round(1).tolist(),
            "anio_2024": suav.loc[rango, 2024].round(1).tolist(),
            "anio_2026": [round(float(v), 1) if d <= doy_fin - 3 else None for d, v in zip(rango, suav.loc[rango, 2026])],
        },
        "snpp_acumulado": {
            "doy": list(range(doy_ini, 336)),
            "anios": {str(a): acum[a].reindex(range(doy_ini, 336)).astype(int).tolist() for a in acum.columns if a < 2026},
            "anio_2026": acum[2026].loc[doy_ini:doy_fin].astype(int).tolist(),
        },
    }
    guardar("series.json", series)

    # ------------------------------------------------------------ departamentos
    tot_dep = temporada.groupby("departamento").size()
    f30 = focos[focos.fecha > hoy - pd.Timedelta(days=31)]
    dias30 = pd.date_range(hoy - pd.Timedelta(days=30), hoy - pd.Timedelta(days=1))
    s30 = f30.groupby(["departamento", "fecha"]).size().unstack(fill_value=0).reindex(columns=dias30, fill_value=0)
    vt = ventana_anual(hist, "07-01", hasta_md).groupby(["departamento", "anio"]).size().unstack(fill_value=0)
    ev_sig = ev[ev.significativo]
    filas = []
    for dep in sorted(set(tot_dep.index) | set(vt.index)):
        base_dep = vt.loc[dep, list(ANIOS_BASE)] if dep in vt.index else pd.Series(dtype=float)
        a26 = int(vt.loc[dep, 2026]) if dep in vt.index and 2026 in vt.columns else 0
        prom = float(base_dep.mean()) if len(base_dep) else 0
        act = activos[activos.departamento == dep]
        principal = act.sort_values("prioridad", ascending=False).head(1)
        filas.append({
            "departamento": dep,
            "focos_24h": int((f24.departamento == dep).sum()), "focos_7d": int((f7.departamento == dep).sum()),
            "focos_temporada": int(tot_dep.get(dep, 0)),
            "snpp_2026": a26, "snpp_promedio": round(prom),
            "anomalia_pct": None if prom < 30 else round((a26 / prom - 1) * 100),
            "puesto_2026": int(vt.loc[dep].rank(ascending=False, method="min")[2026]) if dep in vt.index else None,
            "eventos_activos": int(len(act)), "eventos_activos_100ha": int((act.huella_ha >= 100).sum()),
            "huella_ha": round(float(ev_sig[ev_sig.departamento == dep].huella_ha.sum())),
            "focos_anp_temporada": int(temporada[(temporada.departamento == dep)].anp_nombre.notna().sum()),
            "serie30": s30.loc[dep].astype(int).tolist() if dep in s30.index else [0] * len(dias30),
            "evento_principal": None if principal.empty else principal.evento.iloc[0],
        })
    guardar("departamentos.json", {"dias30": [d.strftime("%Y-%m-%d") for d in dias30], "filas": filas})

    # ------------------------------------------------------------ provincias (7 días)
    p7 = f7.groupby(["departamento", "provincia"]).size().rename("focos_7d").reset_index()
    p24 = f24.groupby(["departamento", "provincia"]).size().rename("focos_24h")
    pa = activos.groupby(["departamento", "provincia"]).size().rename("eventos_activos")
    p7 = p7.join(p24, on=["departamento", "provincia"]).join(pa, on=["departamento", "provincia"]).fillna(0)
    p7 = p7.sort_values("focos_7d", ascending=False).head(40)
    guardar("provincias.json", [{k: limpio(v) if not isinstance(v, float) else int(v) for k, v in r.items()}
                                for r in p7.to_dict("records")])

    # ------------------------------------------------------------ focos para el mapa (temporada)
    t = temporada.sort_values("t_local")
    dist_idx = {u: i for i, u in enumerate(sorted(t.ubigeo.unique()))}
    dist_tab = (t.drop_duplicates("ubigeo").set_index("ubigeo")[["distrito", "provincia", "departamento"]]
                .loc[sorted(dist_idx)])
    guardar("focos_mapa.json", {
        "nota": "lon y lat ×1e4; h = horas antes del corte; frp en MW ×10; sat 0=S-NPP 1=NOAA-20 2=NOAA-21",
        "corte_local": corte.strftime("%Y-%m-%d %H:%M"),
        "lon": (t.lon * 1e4).round().astype(int).tolist(), "lat": (t.lat * 1e4).round().astype(int).tolist(),
        # hacia arriba, para que h <= 24 coincida con la ventana de 24 h de los indicadores
        "h": np.ceil((corte - t.t_local).dt.total_seconds() / 3600).astype(int).tolist(),
        "frp": (t.frp.fillna(0) * 10).round().astype(int).tolist(),
        "sat": t.satelite.map({"S-NPP": 0, "NOAA-20": 1, "NOAA-21": 2}).astype(int).tolist(),
        "distrito": t.ubigeo.map(dist_idx).astype(int).tolist(),
        "distritos": dist_tab.reset_index().values.tolist(),
    })

    # ------------------------------------------------------------ eventos
    sel = json.load(open(OUT / "eventos" / "seleccion.json")) if (OUT / "eventos" / "seleccion.json").exists() else []
    cols = ["evento", "estado", "departamento", "provincia", "distrito", "ubigeo", "inicio", "ultimo",
            "horas_desde_ultimo", "duracion_dias", "focos", "dias_con_focos", "huella_ha", "focos_24h",
            "huella_24h_ha", "frp_total", "frp_max",
            "elev_min", "elev_med", "elev_max", "pendiente_med", "region", "cobertura", "pct_bosque",
            "anp", "anp_admin", "focos_en_anp", "anp_cercana", "dist_anp_km", "capital_cercana",
            "dist_capital_km", "poblacion_1km", "poblacion_5km", "prioridad", "p_actividad", "p_tamano", "p_intensidad",
            "p_exposicion", "p_anp", "lat", "lon", "evidencia", "pases", "satelites", "pct_veg_natural", "fuente_fija"]
    # eventos para el tablero: activos o en observación, y los de la temporada con ≥ 10 focos o en ANP
    filtro = ev.significativo & ((ev.estado != "Sin actividad reciente") | (ev.focos >= 10) | ev.anp.notna())
    e = ev[filtro].sort_values("prioridad", ascending=False)[cols].copy()
    e["lat"], e["lon"] = e.lat.round(4), e.lon.round(4)
    e["huella_ha"] = e.huella_ha.round(0)
    e["frp_total"] = e.frp_total.round(0)
    e["detalle"] = e.evento.isin(sel)
    # clima y exposición de los incendios activos o en observación probables (09_clima, 10_exposicion)
    if (INT / "clima_riesgo.parquet").exists():
        cr = pd.read_parquet(INT / "clima_riesgo.parquet")
        cc = ["ic", "semaforo", "dias_secos", "lluvia_72h_mm", "lluvia_7d_previa_mm", "hr_min_72h", "racha_max_72h", "t_max_72h",
              "horas_criticas_72h", "avance_24h_km", "avance_72h_km", "rumbo_24h", "pob_corredor_24h", "pob_corredor_72h"]
        e = e.merge(cr[["evento"] + cc], on="evento", how="left")
    if (PRO / "exposicion_incendios.parquet").exists():
        ex = pd.read_parquet(PRO / "exposicion_incendios.parquet")
        ce = ["pob_1km", "pob_2km", "pob_10km", "edif_1km", "edif_2km", "edif_5km", "salud_5km", "salud_mas_cercano_km",
              "ccpp_5km", "ccpp_sin_4g_5km"]
        e = e.merge(ex[["evento"] + [c for c in ce if c in ex]], on="evento", how="left")
    guardar("eventos.json", {"cols": list(e.columns),
                             "filas": [[limpio(v) for v in fila] for fila in e.itertuples(index=False)]})

    # ------------------------------------------------------------ clima: series diarias y corredores
    if (INT / "clima_riesgo.parquet").exists():
        cd = pd.read_parquet(INT / "clima_diario.parquet")
        cd = cd[cd.fecha >= hoy - pd.Timedelta(days=7)]
        series_c = {}
        for eid, g in cd.groupby("evento"):
            g = g.sort_values("fecha")
            series_c[eid] = {"fecha": g.fecha.dt.strftime("%Y-%m-%d").tolist(), "ffwi": g.ffwi_max.round(1).tolist(),
                             "lluvia": g.lluvia_mm.round(1).tolist(), "hr_min": g.hr_min.round(0).tolist(),
                             "racha": g.racha_max_kmh.round(0).tolist(), "t_max": g.t_max.round(1).tolist(),
                             "horas_criticas": g.horas_criticas.astype(int).tolist()}
        ruta = lambda v: [[float(p[0]), float(p[1])] for p in v]
        rutas = {r.evento: {"r24": ruta(r.ruta_24h), "r72": ruta(r.ruta_72h), "a24": int(r.ancho_24h_m), "a72": int(r.ancho_72h_m)}
                 for r in cr.itertuples()}
        guardar("clima.json", {"hoy": hoy.strftime("%Y-%m-%d"), "umbrales": {"rojo": 35, "ambar": 20},
                               "series": series_c, "rutas": rutas,
                               "semaforo": cr.semaforo.value_counts().to_dict(),
                               "lluvia_72h_mediana": round(float(cr.lluvia_72h_mm.median()), 1)})

    # ------------------------------------------------------------ exposición
    if expo:
        ex = pd.read_parquet(PRO / "exposicion_incendios.parquet")
        cerca = {r.evento: [dict(x) for x in r.salud_cercanos] for r in ex.itertuples()
                 if isinstance(r.salud_cercanos, (list, np.ndarray)) and len(r.salud_cercanos)}
        guardar("exposicion.json", {**expo, "salud_cercanos": cerca})

    # ------------------------------------------------------------ área quemada (Sentinel-2) de los incendios con 3D
    alumnos = json.load(open(RAIZ / "data" / "curso" / "cifras_alumnos.json"))
    eq = pd.read_parquet(PRO / "exposicion_quemado.parquet").set_index("evento") if (PRO / "exposicion_quemado.parquet").exists() else pd.DataFrame()
    filas_q = []
    for eid in sel:
        ruta = OUT / "eventos" / f"{eid}.json"
        if not ruta.exists():
            continue
        d = json.load(open(ruta))
        r = ev.set_index("evento").loc[eid]
        sev = d.get("severidad")
        fila = {"evento": eid, "distrito": r.distrito, "provincia": r.provincia, "departamento": r.departamento,
                "region": r.region, "estado": r.estado, "huella_ha": round(float(r.huella_ha)), "focos": int(r.focos),
                "inicio": r.inicio.strftime("%Y-%m-%d"), "ultimo": r.ultimo.strftime("%Y-%m-%d"),
                "sentinel": d["sentinel"], "medido": bool(sev)}
        if sev:
            fila.update({k: sev.get(k) for k in ("total_ha", "ha_027", "pct_sin_dato", "focos_antes_dentro_pct", "focos_despues",
                                                   "fuego_activo", "clases", "cobertura", "pre", "post")})
        if eid in eq.index:
            fila["exposicion"] = {k: int(v) for k, v in eq.loc[eid].items()}
        filas_q.append(fila)
    # las mediciones de los alumnos van al incendio del distrito con más focos (el que estudiaron)
    principal = {}
    for f in filas_q:
        if f["focos"] > principal.get(f["distrito"], {"focos": -1})["focos"]:
            principal[f["distrito"]] = f
    for f in filas_q:
        f["alumnos"] = alumnos["incendios"].get(f["distrito"]) if principal[f["distrito"]] is f else None
    guardar("quemado.json", {"nota_alumnos": alumnos["nota"], "filas": filas_q})

    # ------------------------------------------------------------ historia (11_historia) y créditos
    if (PRO / "historia.json").exists():
        guardar("historia.json", json.load(open(PRO / "historia.json")))

    # ------------------------------------------------------------ límites simplificados
    def poligonal(geom):
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            return geom
        partes = [p for p in getattr(geom, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
        return unary_union(partes) if partes else None

    def geojson(gdf, tol, props, nombre):
        g = gdf.copy()
        g["geometry"] = g.geometry.simplify(tol, preserve_topology=True).apply(poligonal)
        g = g[g.geometry.notna() & ~g.geometry.is_empty]
        g = g[props + ["geometry"]]
        txt = g.to_json(drop_id=True)
        d = json.loads(txt)
        def r(c):
            return [r(x) for x in c] if isinstance(c, list) and c and isinstance(c[0], list) else [round(c[0], 4), round(c[1], 4)]
        for f in d["features"]:
            f["geometry"]["coordinates"] = r(f["geometry"]["coordinates"])
        guardar(nombre, d)
    dep = gpd.read_parquet(INT / "departamentos.parquet")
    dep["lon_c"] = dep.geometry.representative_point().x.round(3)
    dep["lat_c"] = dep.geometry.representative_point().y.round(3)
    geojson(dep, 0.004, ["departamento", "lon_c", "lat_c"], "departamentos.geojson")
    geojson(gpd.read_parquet(INT / "provincias.parquet"), 0.006, ["provincia", "departamento"], "provincias.geojson")
    anp = gpd.read_parquet(INT / "anp.parquet")
    geojson(anp, 0.003, ["anp_nombre", "anp_categoria", "anp_admin"], "anp.geojson")


if __name__ == "__main__":
    main()
