"""Clima y riesgo de crecimiento de los incendios activos (Open-Meteo, sin clave).

Para cada incendio de vegetación probable, activo o en observación (y los que tienen
vista 3D), se pide el tiempo horario de los 14 días previos y los 7 siguientes en
el centro de sus focos de las últimas 72 h. Con eso:

- FFWI de Fosberg por hora (humedad, temperatura y viento; 0 si llovió ≥ 2 mm en
  las 24 h previas) y sequía antecedente D = días seguidos sin lluvia (< 1 mm) / 14.
  Índice de crecimiento IC = percentil 90 del FFWI de las próximas 72 h × (0,5 + 0,5·D).
  Semáforo provisional: rojo ≥ 35, ámbar 20–35. El índice se eligió al comparar la
  regla 30-30-30, Angström y FFWI sobre los pronósticos de las entregas del curso:
  la 30-30-30 no marca ningún incendio esta semana y Angström no discrimina.
- Horas críticas en 72 h: humedad < 30 %, ráfaga ≥ 30 km/h y sin lluvia en 24 h
  (regla de la misma hora de Jose Navarro; umbrales de la 30-30-30).
- Corredor del viento (Isabella Albarrán): el frente avanza cada hora hacia donde
  sopla el viento, a 0,10 × viento × factor de sequedad ((70 − HR)/40 entre 0 y 1),
  y se detiene si llovió ≥ 2 mm en las 24 h previas; tope de 15 km. Se cuenta la
  población WorldPop 2026 dentro del corredor a 24 y 72 h. Es una guía para
  anticipar, no una predicción del frente.
- HDW (Srock et al. 2018, en superficie) para la serie diaria, como en la entrega de
  Adriana Garcés.

Salidas:
- data/raw/clima/openmeteo_<fecha>.json   respuesta cruda (caché del día)
- data/interim/clima_diario.parquet       incendio × día
- data/interim/clima_riesgo.parquet       un registro por incendio, con el corredor
"""
from pathlib import Path
import json
import math
import sys
import time

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from exposicion_util import Poblacion  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT, PRO = RAIZ / "data" / "raw", RAIZ / "data" / "interim", RAIZ / "data" / "processed"
URL = "https://api.open-meteo.com/v1/forecast"
HORARIAS = ["temperature_2m", "relative_humidity_2m", "vapour_pressure_deficit", "wind_speed_10m",
            "wind_direction_10m", "wind_gusts_10m", "precipitation"]
LOTE = 50
ROJO, AMBAR = 35, 20
TOPE_KM = 15


def candidatos(ev, focos, corte):
    sel = ev[ev.estado.isin(["Activo", "En observación"]) & (ev.evidencia == "probable")]
    detalle = RAIZ / "dashboard" / "data" / "eventos" / "seleccion.json"
    if detalle.exists():
        sel = pd.concat([sel, ev[ev.evento.isin(json.loads(detalle.read_text()))]]).drop_duplicates("evento")
    recientes = focos[focos.t_local > corte - pd.Timedelta(hours=72)]
    centro = recientes.groupby("evento")[["lat", "lon"]].mean()
    sel = sel.set_index("evento")
    sel[["lat_c", "lon_c"]] = centro.reindex(sel.index).values
    sel["lat_c"] = sel.lat_c.fillna(sel.lat)
    sel["lon_c"] = sel.lon_c.fillna(sel.lon)
    return sel[["lat_c", "lon_c", "huella_ha"]].reset_index()


def pedir(puntos, fecha):
    cache = RAW / "clima" / f"openmeteo_{fecha}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    previo = json.loads(cache.read_text()) if cache.exists() else {}
    faltan = puntos[~puntos.evento.isin(previo)]
    for i in range(0, len(faltan), LOTE):
        lote = faltan.iloc[i:i + LOTE]
        params = {"latitude": ",".join(f"{v:.4f}" for v in lote.lat_c), "longitude": ",".join(f"{v:.4f}" for v in lote.lon_c),
                  "hourly": ",".join(HORARIAS), "timezone": "America/Lima", "past_days": 14, "forecast_days": 7,
                  "wind_speed_unit": "kmh"}
        for intento in range(4):
            r = requests.get(URL, params=params, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10 * (intento + 1))
        r.raise_for_status()
        datos = r.json()
        datos = datos if isinstance(datos, list) else [datos]
        for eid, d in zip(lote.evento, datos):
            previo[eid] = {"elevacion": d.get("elevation"), "hourly": d["hourly"]}
        cache.write_text(json.dumps(previo))
        print(f"  clima: {min(i + LOTE, len(faltan))}/{len(faltan)} incendios")
    return previo


def ffwi(t_c, hr, viento_kmh):
    """Fire Weather Index de Fosberg (1978): T en °F, viento en mph; 0–100."""
    t = t_c * 9 / 5 + 32
    h = np.clip(hr, 0, 100)
    m = np.where(h < 10, 0.03229 + 0.281073 * h - 0.000578 * h * t,
                 np.where(h < 50, 2.22749 + 0.160107 * h - 0.01478 * t,
                          21.0606 + 0.005565 * h ** 2 - 0.00035 * h * t - 0.483199 * h))
    x = np.clip(m, 0, 30) / 30
    eta = 1 - 2 * x + 1.5 * x ** 2 - 0.5 * x ** 3
    u = viento_kmh / 1.609
    return np.minimum(100, eta * np.sqrt(1 + u ** 2) / 0.3002)


def horario(d):
    h = pd.DataFrame(d["hourly"])
    h["time"] = pd.to_datetime(h.time)
    h["lluvia_24h"] = h.precipitation.rolling(24, min_periods=1).sum()
    h["ffwi"] = np.where(h.lluvia_24h >= 2, 0, ffwi(h.temperature_2m, h.relative_humidity_2m, h.wind_speed_10m))
    h["hdw"] = h.vapour_pressure_deficit * 10 * h.wind_speed_10m / 3.6
    h["critica"] = (h.relative_humidity_2m < 30) & (h.wind_gusts_10m >= 30) & (h.lluvia_24h < 2)
    return h


def diario(h):
    h = h.assign(fecha=h.time.dt.normalize())
    g = h.groupby("fecha")
    out = pd.DataFrame({
        "t_max": g.temperature_2m.max(), "hr_min": g.relative_humidity_2m.min(),
        "racha_max_kmh": g.wind_gusts_10m.max(), "lluvia_mm": g.precipitation.sum(min_count=1),
        "ffwi_max": g.ffwi.max(), "hdw": g.hdw.max(), "horas_criticas": g.critica.sum(), "horas": g.size(),
    })
    return out[out.horas == 24].drop(columns="horas").reset_index()


def dias_secos(dia, hoy):
    previos = dia[dia.fecha < hoy].sort_values("fecha", ascending=False)
    n = 0
    for v in previos.lluvia_mm:
        if v >= 1:
            break
        n += 1
    return n


def corredor(h, lon0, lat0, desde, horas):
    """Trayectoria del frente hora a hora (lon, lat) y su avance en km."""
    tramo = h[(h.time >= desde) & (h.time < desde + pd.Timedelta(hours=horas))]
    seco = np.clip((70 - tramo.relative_humidity_2m.to_numpy()) / 40, 0, 1)
    ros = np.where(tramo.lluvia_24h.to_numpy() >= 2, 0, 0.10 * tramo.wind_speed_10m.to_numpy() * seco)  # km por hora
    rumbo = np.radians((tramo.wind_direction_10m.to_numpy() + 180) % 360)  # hacia donde sopla
    dx, dy = np.cumsum(ros * np.sin(rumbo)), np.cumsum(ros * np.cos(rumbo))
    total = float(np.hypot(dx[-1], dy[-1])) if len(dx) else 0.0
    if total > TOPE_KM:
        dx, dy = dx * TOPE_KM / total, dy * TOPE_KM / total
        total = TOPE_KM
    lon = lon0 + dx / (111.32 * math.cos(math.radians(lat0)))
    lat = lat0 + dy / 111.32
    return np.r_[lon0, lon], np.r_[lat0, lat], total


def main():
    ev = pd.read_parquet(PRO / "eventos.parquet")
    focos = pd.read_parquet(PRO / "focos_temporada.parquet")
    corte = focos.t_local.max()
    hoy = corte.normalize()
    puntos = candidatos(ev, focos, corte)
    print(f"incendios con pronóstico: {len(puntos)}")
    crudo = pedir(puntos, corte.strftime("%Y-%m-%d"))
    wp = Poblacion()
    ult24 = focos[focos.t_local > corte - pd.Timedelta(hours=24)].groupby("evento")[["lon", "lat"]].mean()
    diarios, filas = [], []
    desde = corte.floor("h") + pd.Timedelta(hours=1)
    for p in puntos.itertuples():
        if p.evento not in crudo:
            continue
        h = horario(crudo[p.evento])
        dia = diario(h).assign(evento=p.evento)
        diarios.append(dia)
        prox = h[(h.time >= desde) & (h.time < desde + pd.Timedelta(hours=72))]
        d_sec = dias_secos(dia, hoy)
        ic = float(np.percentile(prox.ffwi, 90)) * (0.5 + 0.5 * min(d_sec / 14, 1)) if len(prox) else np.nan
        lon0, lat0 = (ult24.loc[p.evento] if p.evento in ult24.index else (p.lon_c, p.lat_c))
        ancho = max(1000, math.sqrt(p.huella_ha * 1e4 / math.pi) + 375)
        fila = {"evento": p.evento, "lon_c": p.lon_c, "lat_c": p.lat_c, "ic": round(ic, 1),
                "semaforo": "rojo" if ic >= ROJO else "ambar" if ic >= AMBAR else "verde",
                "ffwi_p90_72h": round(float(np.percentile(prox.ffwi, 90)), 1), "dias_secos": d_sec,
                "horas_criticas_72h": int(prox.critica.sum()), "lluvia_72h_mm": round(float(prox.precipitation.sum()), 1),
                "lluvia_7d_previa_mm": round(float(dia[(dia.fecha < hoy) & (dia.fecha >= hoy - pd.Timedelta(days=7))].lluvia_mm.sum()), 1),
                "hr_min_72h": round(float(prox.relative_humidity_2m.min()), 0), "racha_max_72h": round(float(prox.wind_gusts_10m.max()), 0),
                "t_max_72h": round(float(prox.temperature_2m.max()), 1)}
        for horas in (24, 72):
            lon, lat, km = corredor(h, float(lon0), float(lat0), desde, horas)
            # puntos cada ~200 m sobre la trayectoria para medir el ancho del corredor
            n = max(2, int(km / 0.2))
            t = np.linspace(0, len(lon) - 1, n)
            lon_d, lat_d = np.interp(t, np.arange(len(lon)), lon), np.interp(t, np.arange(len(lat)), lat)
            radio = ancho + 0.25 * km * 1000
            fila[f"avance_{horas}h_km"] = round(km, 1)
            fila[f"pob_corredor_{horas}h"] = round(wp.suma(wp.celdas(lon_d, lat_d, radio)), 0)
            fila[f"ruta_{horas}h"] = [[round(a, 4), round(b, 4)] for a, b in zip(lon[::3].tolist() + [lon[-1]], lat[::3].tolist() + [lat[-1]])]
            fila[f"ancho_{horas}h_m"] = round(radio)
        dx, dy = fila["ruta_24h"][-1][0] - fila["ruta_24h"][0][0], fila["ruta_24h"][-1][1] - fila["ruta_24h"][0][1]
        fila["rumbo_24h"] = round((math.degrees(math.atan2(dx * math.cos(math.radians(lat0)), dy)) + 360) % 360)
        filas.append(fila)
    tabla = pd.concat(diarios, ignore_index=True)
    tabla["pronostico"] = tabla.fecha >= hoy
    tabla.to_parquet(INT / "clima_diario.parquet")
    riesgo = pd.DataFrame(filas)
    riesgo.to_parquet(INT / "clima_riesgo.parquet")
    print(riesgo.semaforo.value_counts().to_dict())
    print(riesgo[["ic", "ffwi_p90_72h", "dias_secos", "horas_criticas_72h", "lluvia_72h_mm", "hr_min_72h", "avance_24h_km",
                  "pob_corredor_24h"]].describe().round(1).to_string())
    print(riesgo.merge(ev[["evento", "distrito", "departamento", "estado"]]).sort_values("ic", ascending=False)
          [["evento", "distrito", "departamento", "estado", "ic", "semaforo", "dias_secos", "lluvia_72h_mm", "horas_criticas_72h",
            "avance_24h_km", "pob_corredor_24h"]].head(12).to_string())


if __name__ == "__main__":
    main()
