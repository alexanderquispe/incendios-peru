"""Detalle 3D de los incendios priorizados.

Para cada evento seleccionado genera:
- terreno (PNG Terrarium) en una malla lon/lat regular, para deck.gl TerrainLayer
- texturas: relieve sombreado y, si hay imagen sin nubes, Sentinel-2 L2A en color
  natural y en infrarrojo de onda corta (el área quemada se ve rojo oscuro)
- severidad del quemado (dNBR, Sentinel-2 antes/después) y hectáreas por clase
- avance diario: perímetro acumulado aproximado, área, avance máximo del frente,
  FRP y rango de altitud de los focos de cada día

Salidas: dashboard/data/eventos/<id>.json y dashboard/assets/eventos/<id>_*.png|jpg
"""
from pathlib import Path
import json
import math
import sys
import warnings

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
from shapely import affinity
from shapely.geometry import MultiPoint, mapping

sys.path.insert(0, str(Path(__file__).parent))
from terreno import Mosaico, terrain_rgb_terrarium  # noqa: E402

warnings.filterwarnings("ignore")
RAIZ = Path(__file__).resolve().parents[1]
PRO = RAIZ / "data" / "processed"
OUT_DATA = RAIZ / "dashboard" / "data" / "eventos"
OUT_IMG = RAIZ / "dashboard" / "assets" / "eventos"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_IMG.mkdir(parents=True, exist_ok=True)

R = 6371000.0
ANCHO_DEM = 384       # columnas de la malla de terreno
ANCHO_TEX = 1024      # columnas de las texturas
RADIO_FOCO_M = 250    # radio con que se dibuja cada foco al armar el perímetro
CLASES_DNBR = [  # USGS (Key y Benson 2006)
    (0.10, 0.27, "Baja", (250, 204, 21, 170)),
    (0.27, 0.44, "Moderada baja", (249, 115, 22, 190)),
    (0.44, 0.66, "Moderada alta", (220, 38, 38, 210)),
    (0.66, 9.99, "Alta", (127, 29, 29, 230)),
]
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


def seleccionar(ev):
    activos = ev[ev.significativo & (ev.estado == "Activo")].sort_values("prioridad", ascending=False)
    sel = list(activos.evento.head(8))
    sel += [e for e in ev[ev.significativo].sort_values("huella_ha", ascending=False).evento if e not in sel][:3]
    en_anp = ev[ev.anp_admin.isin(["Nacional"]) & ev.significativo].sort_values("focos_en_anp", ascending=False)
    sel += [e for e in en_anp.evento if e not in sel][:2]
    # activos dentro o a ≤ 5 km de un área protegida
    cerca_anp = activos[activos.anp_admin.notna() | (activos.dist_anp_km <= 5)]
    sel += [e for e in cerca_anp.evento if e not in sel][:2]
    return sel


def caja(det):
    o, e = det.lon.min(), det.lon.max()
    s, n = det.lat.min(), det.lat.max()
    pad = max(0.025, 0.35 * max(e - o, n - s))
    o, e, s, n = o - pad, e + pad, s - pad, n + pad
    # caja aproximadamente cuadrada en metros
    lat0 = (s + n) / 2
    ancho_m = (e - o) * math.cos(math.radians(lat0))
    alto_m = n - s
    if ancho_m < alto_m:
        extra = (alto_m / math.cos(math.radians(lat0)) - (e - o)) / 2
        o, e = o - extra, e + extra
    else:
        extra = (ancho_m - alto_m) / 2
        s, n = s - extra, n + extra
    return o, s, e, n


def malla(o, s, e, n, ancho):
    lat0 = (s + n) / 2
    alto = int(round(ancho * (n - s) / ((e - o) * math.cos(math.radians(lat0)))))
    lons = o + (np.arange(ancho) + 0.5) * (e - o) / ancho
    lats = n - (np.arange(alto) + 0.5) * (n - s) / alto
    return np.meshgrid(lons, lats)


def dem_evento(o, s, e, n):
    lat0 = (s + n) / 2
    ancho_m = (e - o) * 111320 * math.cos(math.radians(lat0))
    z = int(np.clip(math.floor(math.log2(900 * 156543.03 * math.cos(math.radians(lat0)) / ancho_m)), 9, 13))
    m = Mosaico(o, s, e, n, z)
    salida = {}
    for clave, ancho in (("dem", ANCHO_DEM), ("dem_tex", ANCHO_TEX)):
        LON, LAT = malla(o, s, e, n, ancho)
        f, c = m.fila_col(LON, LAT)
        salida[clave] = map_coordinates(m.dem, [f, c], order=1, mode="nearest").astype(np.float32)
    salida["z"] = z
    return salida


def sombreado(dem, o, s, e, n):
    alto, ancho = dem.shape
    lat0 = (s + n) / 2
    dx = (e - o) / ancho * 111320 * math.cos(math.radians(lat0))
    dy = (n - s) / alto * 110540
    gy, gx = np.gradient(dem, dy, dx)
    pend = np.pi / 2 - np.arctan(np.hypot(gx, -gy))
    asp = np.arctan2(gx, gy)
    az, alt = np.radians(315), np.radians(40)
    hs = np.sin(alt) * np.sin(pend) + np.cos(alt) * np.cos(pend) * np.cos(az - asp)
    hs = np.clip(hs, 0, 1)
    # tinte hipsométrico sobrio: verdes apagados abajo, ocres y gris arriba
    t = np.clip((dem - np.percentile(dem, 2)) / max(np.ptp(dem), 1), 0, 1)
    paleta = np.array([[118, 140, 104], [170, 160, 112], [176, 142, 104], [150, 138, 130], [222, 222, 222]], float)
    pos = t * (len(paleta) - 1)
    i0 = np.floor(pos).astype(int).clip(0, len(paleta) - 2)
    w = (pos - i0)[..., None]
    color = paleta[i0] * (1 - w) + paleta[i0 + 1] * w
    rgb = color * (0.35 + 0.75 * hs[..., None])
    return np.clip(rgb, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- Sentinel-2
def _leer_banda(href, dst_shape, dst_transform, resampling):
    dst = np.zeros(dst_shape, dtype=np.float32)
    with rasterio.open(href) as src:
        reproject(rasterio.band(src, 1), dst, dst_transform=dst_transform, dst_crs="EPSG:4326",
                  resampling=resampling, src_nodata=0, dst_nodata=0)
    return dst


def escena(items, bandas, dst_shape, dst_transform):
    """Mosaico de los items (misma fecha) para las bandas pedidas, en reflectancia."""
    out = {b: np.zeros(dst_shape, np.float32) for b in bandas}
    for it in items:
        offset = -1000 if str(it.properties.get("s2:processing_baseline", "04.00")) >= "04.00" else 0
        for b in bandas:
            res = Resampling.nearest if b == "SCL" else Resampling.bilinear
            arr = _leer_banda(it.assets[b].href, dst_shape, dst_transform, res)
            vacio = out[b] == 0
            if b == "SCL":
                out[b][vacio] = arr[vacio]
            else:
                refl = np.where(arr > 0, (arr + offset) / 10000.0, 0)
                out[b][vacio] = refl[vacio]
    return out


def fraccion_despejada(scl):
    valido = scl > 0
    if valido.mean() < 0.9:
        return 0.0
    despejado = np.isin(scl, [4, 5, 6, 7, 11])  # vegetación, suelo, agua, no clasificado, nieve
    return float(despejado[valido].mean())


def buscar_imagenes(o, s, e, n, inicio, corte):
    cat = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)
    busq = cat.search(collections=["sentinel-2-l2a"], bbox=[o, s, e, n],
                      datetime=f"{(inicio - pd.Timedelta(days=90)).date()}/{(corte + pd.Timedelta(days=1)).date()}",
                      query={"eo:cloud_cover": {"lt": 70}})
    items = list(busq.items())
    por_fecha = {}
    for it in items:
        por_fecha.setdefault(it.datetime.date(), []).append(it)
    return dict(sorted(por_fecha.items()))


def sentinel(o, s, e, n, inicio, ultimo, corte, shape):
    transform = from_bounds(o, s, e, n, shape[1], shape[0])
    try:
        fechas = buscar_imagenes(o, s, e, n, inicio, corte)
    except Exception as ex:  # el servicio puede fallar; el tablero usa el relieve
        print("   STAC no disponible:", ex)
        return None
    chico = (max(64, shape[0] // 8), max(64, shape[1] // 8))
    t_chico = from_bounds(o, s, e, n, chico[1], chico[0])
    despejado = {}
    for fecha, items in fechas.items():
        try:
            scl = escena(items, ["SCL"], chico, t_chico)["SCL"]
            despejado[fecha] = fraccion_despejada(scl)
        except Exception:
            despejado[fecha] = 0.0
    ini = inicio.date()
    post = [f for f in despejado if f >= ini and despejado[f] >= 0.80]
    pre = [f for f in despejado if f < ini and despejado[f] >= 0.80]
    if not post:
        return {"post": None, "pre": None, "despejado": {str(k): round(v, 2) for k, v in despejado.items()}}
    f_post = post[-1]
    img = escena(fechas[f_post], ["B04", "B03", "B02", "B8A", "B12", "SCL"], shape, transform)
    res = {"post": str(f_post), "pre": None, "img_post": img}
    if pre:
        f_pre = pre[-1]
        res["pre"] = str(f_pre)
        res["img_pre"] = escena(fechas[f_pre], ["B8A", "B12", "SCL"], shape, transform)
    return res


def a_png_color(r, g, b, maximo):
    rgb = np.dstack([r, g, b]) / maximo
    rgb = np.clip(rgb, 0, 1) ** (1 / 1.4)
    return (rgb * 255).astype(np.uint8)


def nbr(img):
    return (img["B8A"] - img["B12"]) / np.maximum(img["B8A"] + img["B12"], 1e-4)


# ---------------------------------------------------------------- avance diario
def a_xy(lon, lat, lat0):
    return np.column_stack([np.radians(lon) * R * math.cos(math.radians(lat0)), np.radians(lat) * R])


def a_lonlat(geom, lat0):
    k = 180 / math.pi / R
    return affinity.scale(geom, xfact=k / math.cos(math.radians(lat0)), yfact=k, origin=(0, 0))


def avance(det, lat0):
    det = det.sort_values("t_local")
    xy = a_xy(det.lon.values, det.lat.values, lat0)
    dias = sorted(det.fecha.unique())
    filas, perims = [], []
    celdas_acum = set()
    for i, d in enumerate(dias):
        hoy = (det.fecha == d).values
        hasta = (det.fecha <= d).values
        celdas_hoy = {tuple(c) for c in np.floor(xy[hoy] / 375).astype(int)}
        nuevas = celdas_hoy - celdas_acum
        celdas_acum |= celdas_hoy
        previo = (det.fecha < d).values
        avance_m = None
        if previo.any():
            dist, _ = cKDTree(xy[previo]).query(xy[hoy])
            avance_m = float(np.max(dist))
        poli = MultiPoint([tuple(p) for p in xy[hasta]]).buffer(RADIO_FOCO_M, quad_segs=6)
        poli = poli.buffer(120).buffer(-120).simplify(40)
        perims.append({"type": "Feature", "properties": {"dia": i, "fecha": str(pd.Timestamp(d).date())},
                       "geometry": mapping(a_lonlat(poli, lat0))})
        sub = det[hoy]
        filas.append({
            "fecha": str(pd.Timestamp(d).date()), "focos": int(hoy.sum()),
            "area_nueva_ha": round(len(nuevas) * 375 ** 2 / 1e4, 1),
            "area_acum_ha": round(len(celdas_acum) * 375 ** 2 / 1e4, 1),
            "avance_max_m": None if avance_m is None else round(avance_m),
            "frp_total": round(float(sub.frp.sum()), 1), "frp_max": round(float(sub.frp.max()), 1),
            "elev_min": int(sub.elev_evento.min()), "elev_max": int(sub.elev_evento.max()),
        })
    return filas, perims


def redondear_geojson(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [redondear_geojson(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: redondear_geojson(v, nd) for k, v in obj.items()}
    return obj


def procesar(ev_row, focos, corte):
    eid = ev_row.evento
    det = focos[focos.evento == eid].copy()
    o, s, e, n = caja(det)
    lat0 = (s + n) / 2
    print(f"{eid} {ev_row.distrito} ({ev_row.departamento}): {len(det)} focos")

    d = dem_evento(o, s, e, n)
    dem, dem_tex = d["dem"], d["dem_tex"]
    Image.fromarray(terrain_rgb_terrarium(dem)).save(OUT_IMG / f"{eid}_dem.png", optimize=True)
    Image.fromarray(sombreado(dem_tex, o, s, e, n)).save(OUT_IMG / f"{eid}_relieve.jpg", quality=84)

    # altitud de cada foco en el DEM fino del evento
    f_idx = (n - det.lat.values) / (n - s) * dem_tex.shape[0] - 0.5
    c_idx = (det.lon.values - o) / (e - o) * dem_tex.shape[1] - 0.5
    det["elev_evento"] = map_coordinates(dem_tex, [f_idx, c_idx], order=1, mode="nearest")

    texturas = ["relieve"]
    sev = None
    s2 = sentinel(o, s, e, n, ev_row.inicio, ev_row.ultimo, corte, dem_tex.shape)
    info_s2 = {"post": None, "pre": None}
    if s2 and s2.get("post"):
        img = s2["img_post"]
        Image.fromarray(a_png_color(img["B04"], img["B03"], img["B02"], 0.22)).save(
            OUT_IMG / f"{eid}_natural.jpg", quality=84)
        Image.fromarray(a_png_color(img["B12"], img["B8A"], img["B04"], 0.45)).save(
            OUT_IMG / f"{eid}_infrarrojo.jpg", quality=84)
        texturas += ["natural", "infrarrojo"]
        info_s2 = {"post": s2["post"], "pre": s2["pre"]}
        if s2.get("pre"):
            pre = s2["img_pre"]
            nube = lambda scl: np.isin(scl, [0, 1, 3, 8, 9, 10])
            dnbr = nbr(pre) - nbr(img)
            dnbr[nube(pre["SCL"]) | nube(img["SCL"]) | (img["SCL"] == 6) | (pre["SCL"] == 6)] = np.nan
            # solo cerca de los focos del evento (≤ 1.5 km), para no contar cambios ajenos
            LON, LAT = malla(o, s, e, n, dem_tex.shape[1])
            arbol = cKDTree(a_xy(det.lon.values, det.lat.values, lat0))
            dist, _ = arbol.query(a_xy(LON.ravel(), LAT.ravel(), lat0))
            cerca = (dist <= 1500).reshape(LON.shape)
            px_ha = ((e - o) / dem_tex.shape[1] * 111320 * math.cos(math.radians(lat0))) * \
                    ((n - s) / dem_tex.shape[0] * 110540) / 1e4
            rgba = np.zeros(dem_tex.shape + (4,), np.uint8)
            sev = {"pre": s2["pre"], "post": s2["post"], "clases": []}
            for lo, hi, nombre, color in CLASES_DNBR:
                m = (dnbr >= lo) & (dnbr < hi)
                rgba[m & cerca] = color
                sev["clases"].append({"clase": nombre, "ha": round(float((m & cerca).sum() * px_ha), 0)})
            sev["total_ha"] = round(sum(c["ha"] for c in sev["clases"]), 0)
            sev["pct_sin_dato"] = round(float(np.isnan(dnbr[cerca]).mean() * 100), 0)
            Image.fromarray(rgba, "RGBA").save(OUT_IMG / f"{eid}_dnbr.png", optimize=True)

    filas, perims = avance(det, lat0)
    t0 = det.t_local.min()
    sat = {"S-NPP": 0, "NOAA-20": 1, "NOAA-21": 2}
    focos_out = [[round(r.lon, 5), round(r.lat, 5), int(r.elev_evento),
                  round((r.t_local - t0).total_seconds() / 3600, 2), round(float(r.frp), 1),
                  sat[r.satelite], int(sorted(det.fecha.unique()).index(r.fecha))]
                 for r in det.sort_values("t_local").itertuples()]
    hist, bordes = np.histogram(det.elev_evento, bins=np.arange(
        math.floor(det.elev_evento.min() / 100) * 100, math.ceil(det.elev_evento.max() / 100) * 100 + 101, 100))
    out = {
        "evento": eid, "bounds": [round(v, 5) for v in (o, s, e, n)], "zoom_dem": d["z"],
        "dem_rango": [int(np.nanmin(dem)), int(np.nanmax(dem))],
        "inicio_local": str(t0), "texturas": texturas, "sentinel": info_s2, "severidad": sev,
        "focos_cols": ["lon", "lat", "elev", "h_desde_inicio", "frp", "sat", "dia"],
        "focos": focos_out, "dias": filas,
        "perimetros": redondear_geojson({"type": "FeatureCollection", "features": perims}),
        "altitud_hist": {"desde": [int(b) for b in bordes[:-1]], "focos": [int(h) for h in hist]},
    }
    with open(OUT_DATA / f"{eid}.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"   texturas={texturas} S2 post={info_s2['post']} pre={info_s2['pre']} "
          f"sev={None if not sev else sev['total_ha']} ha; días={len(filas)}")
    return eid


def main():
    ev = pd.read_parquet(PRO / "eventos.parquet")
    focos = pd.read_parquet(PRO / "focos_temporada.parquet")
    corte = focos.t_local.max()
    sel = seleccionar(ev)
    if len([a for a in sys.argv[1:] if not a.startswith("--")]):
        sel = [a for a in sys.argv[1:] if not a.startswith("--")]
    hechos = []
    forzar = "--forzar" in sys.argv
    if forzar:  # datos nuevos: los ids de evento cambian, se borra todo lo anterior
        for viejo in list(OUT_DATA.glob("*.json")) + list(OUT_IMG.glob("*")):
            viejo.unlink()
    for eid in sel:
        if not forzar and (OUT_DATA / f"{eid}.json").exists():
            hechos.append(eid)  # ya generado en una corrida anterior con los mismos datos
            continue
        hechos.append(procesar(ev.set_index("evento").loc[eid].rename(eid).pipe(
            lambda r: r.to_frame().T.assign(evento=eid).iloc[0]), focos, corte))
    with open(OUT_DATA / "seleccion.json", "w") as fh:
        json.dump(hechos, fh)


if __name__ == "__main__":
    main()
