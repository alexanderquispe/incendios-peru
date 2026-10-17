"""Contexto oficial, validación con incendios reportados y texto de metodología.

Las cifras oficiales provienen de comunicados y notas de prensa (revisadas el
17 oct 2026) y se registran con su fuente; no se mezclan con los conteos
satelitales. Los datos de validación se leen de los eventos calculados.
Salida: dashboard/data/contexto.json
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW, INT, PRO = RAIZ / "data" / "raw", RAIZ / "data" / "interim", RAIZ / "data" / "processed"
OUT = RAIZ / "dashboard" / "data" / "contexto.json"

OFICIAL = [
    ("Emergencias por incendios forestales en 2026", "401", "COEN, citado por Mongabay (13 oct)",
     "Mongabay", "https://es.mongabay.com/2026/10/peru-medio-centenar-incendios-forestales-trece-regiones-extienden-territorios-indigenas/"),
    ("Cobertura natural perdida en 2026", "8,599 ha", "COEN, citado por Mongabay (13 oct)",
     "Mongabay", "https://es.mongabay.com/2026/10/peru-medio-centenar-incendios-forestales-trece-regiones-extienden-territorios-indigenas/"),
    ("Incendios en curso al 13 oct, 13:00 h", "51 (35 activos, 16 controlados)", "COEN, citado por Mongabay",
     "Mongabay", "https://es.mongabay.com/2026/10/peru-medio-centenar-incendios-forestales-trece-regiones-extienden-territorios-indigenas/"),
    ("Fallecidos en 2026", "8 a 10 según la fuente", "Defensa Civil y COEN, citados por prensa (10–14 oct)",
     "La República", "https://larepublica.pe/sociedad/2026/10/11/59-incendios-forestales-activos-en-todo-el-peru-comunidades-pierden-cultivos-viviendas-y-ganado-762399"),
    ("Aviso SENAMHI N.º\u00a0010 (11–16 oct)", "Alerta roja en 9 regiones", "SENAMHI, citado por prensa (12 oct)",
     "El Popular", "https://elpopular.pe/actualidad/2026/10/12/senamhi-advierte-sobre-condiciones-climatologicas-que-favorecen-incendios-forestales-en-9-regiones-hasta-el-16-de-octubre-608568"),
    ("Distritos en riesgo muy alto", "520 (621,392 personas expuestas)", "CENEPRED, citado por Infobae (15 oct)",
     "Infobae", "https://www.infobae.com/peru/2026/10/16/incendios-forestales-en-peru-520-distritos-estan-en-riesgo-muy-alto-y-estas-son-las-regiones-mas-expuestas/"),
    ("Incendios extinguidos en áreas protegidas en 2026", "56 en 20 ANP", "MINAM/SERNANP, vía Andina (13 oct)",
     "Andina", "https://andina.pe/agencia/noticia-minam-extinguio-56-incendios-forestales-areas-naturales-protegidas-durante-2026-1095793.aspx"),
    ("Referencia 2024 (año récord)", "1,754 incendios, 63,710 ha, 35 fallecidos", "INDECI, vía Andina (25 nov 2024)",
     "Andina", "https://andina.pe/agencia/noticia-indeci-se-han-registrado-1754-incendios-forestales-lo-va-del-ano-y-hay-35-muertos-1009212.aspx"),
]


def fmt(v):
    return f"{v:,.0f}"  # estilo es-PE: coma de miles, punto decimal


def validacion(ev, focos):
    def ev_info(eid):
        return ev.set_index("evento").loc[eid]

    filas = []
    e = ev_info("E45347")
    filas.append({
        "incendio": "Río Tambo (Satipo, Junín), comunidad nativa Tsyapo",
        "reporte": "INDECI: 350 ha de cobertura natural y 80 ha de cultivos; amenaza a la Reserva Comunal Asháninka.",
        "enlace": {"nombre": "Andina, 13 oct", "url": "https://andina.pe/agencia/noticia-indeci-siete-nuevos-incendios-forestales-se-iniciaron-distritos-cinco-regiones-1095820.aspx"},
        "detectado": True,
        "detalle": f"{fmt(e.focos)} focos entre el {e.inicio.day} y el {e.ultimo.day} oct; huella de {fmt(e.huella_ha)} ha, "
                   f"a {e.dist_anp_km:.1f} km de la Reserva Comunal Asháninka. Sigue activo.",
    })
    e = ev_info("E37746")
    filas.append({
        "incendio": "Parque Nacional Huascarán, sector Llanganuco (Yungay, Áncash)",
        "reporte": "MINAM/SERNANP: unas 400 ha (100 dentro del parque); extinguido.",
        "enlace": {"nombre": "Andina, 13 oct", "url": "https://andina.pe/agencia/noticia-minam-extinguio-56-incendios-forestales-areas-naturales-protegidas-durante-2026-1095793.aspx"},
        "detectado": True,
        "detalle": f"{fmt(e.focos)} focos del {e.inicio.day} al {e.ultimo.day} oct, {fmt(e.focos_en_anp)} dentro del parque; "
                   f"huella de {fmt(e.huella_ha)} ha. Sin actividad desde el {e.ultimo.day} oct.",
    })
    nyc = ev[ev.anp.fillna("").str.contains("Nor Yauyos") & (ev.inicio >= "2026-10-01")]
    filas.append({
        "incendio": "Reserva Paisajística Nor Yauyos-Cochas (Lima)",
        "reporte": "MINAM/SERNANP: incendio activo al 13 oct.",
        "enlace": {"nombre": "Andina, 13 oct", "url": "https://andina.pe/agencia/noticia-minam-extinguio-56-incendios-forestales-areas-naturales-protegidas-durante-2026-1095793.aspx"},
        "detectado": len(nyc) > 0,
        "detalle": f"{len(nyc)} eventos en octubre con {fmt(nyc.focos_en_anp.sum())} focos dentro de la reserva "
                   f"(el más reciente, último foco el {nyc.ultimo.max().day} oct).",
    })
    st = focos[(focos.distrito == "Santa Teresa") & focos.fecha.between("2026-07-08", "2026-07-11")]
    filas.append({
        "incendio": "Santa Teresa, cerro Chilcapata (La Convención, Cusco)",
        "reporte": "COEN-INDECI: unas 10 ha el 9 jul.",
        "enlace": {"nombre": "Infobae, 10 jul", "url": "https://www.infobae.com/peru/2026/07/10/incendio-forestal-de-grandes-proporciones-afecta-zona-cercana-a-machu-picchu-y-consume-10-hectareas-de-vegetacion-en-cusco/"},
        "detectado": len(st) > 0,
        "detalle": f"{len(st)} focos en el distrito entre la noche del 9 y el 10 jul.",
    })
    filas.append({
        "incendio": "Santuario Histórico de Machupicchu, cerro Poques (Cusco)",
        "reporte": "SERNANP: 1.5 a 2.5 ha de bosque, del 3 al 8 ago; fuego superficial y subterráneo.",
        "enlace": {"nombre": "El Peruano, 5 ago", "url": "https://elperuano.pe/noticia/301857-minam-despliega-brigadas-especializadas-para-controlar-incendio-forestal-en-machupicchu"},
        "detectado": False,
        "detalle": "Sin focos en el santuario esas fechas. Un incendio de 2 ha bajo dosel queda por debajo de lo que VIIRS detecta de forma confiable.",
    })
    return filas


def metodo(resumen, calib):
    return [
        {"titulo": "Focos de calor", "parrafos": [
            "Un foco de calor es un píxel de 375 m en el que el sensor VIIRS registró una anomalía térmica compatible con fuego. "
            "Se usan los tres satélites con VIIRS (S-NPP, NOAA-20 y NOAA-21), que pasan sobre el Perú varias veces al día, de día y de noche. "
            "Un foco no equivale a un incendio forestal: también aparecen quemas agrícolas y de pastos. Las nubes y el humo denso pueden ocultar el fuego.",
            "Datos de 2025-06 a la fecha: INPE (Brasil), programa Queimadas, archivo mensual de focos de Sudamérica, filtrado al Perú. "
            "Los pases posteriores al último dato de INPE vienen de NASA FIRMS (tiempo casi real).",
            f"Serie histórica 2012–2025: NASA FIRMS, archivo estándar VIIRS S-NPP del Perú, solo focos de vegetación. "
            f"Antes de unir las dos fuentes se compararon mes a mes en julio–octubre de 2025: la diferencia entre INPE y FIRMS fue de {calib}.",
            "Se excluyen fuentes de calor permanentes (volcanes como Sabancaya y Ubinas, antorchas de gas e industrias): focos a menos de 500 m de "
            "detecciones que FIRMS clasifica como volcán u otra fuente estática entre 2012 y 2025. Solo se conservan focos dentro de los límites distritales del INEI.",
        ]},
        {"titulo": "Incendios (eventos)", "parrafos": [
            "Los focos se agrupan en eventos: dos focos pertenecen al mismo incendio si están a 1 km o menos y a 48 horas o menos entre sí, "
            "directamente o a través de otros focos. Estado: «Activo» si el último foco tiene menos de 24 horas; «En observación» entre 24 y 72 horas; "
            "«Sin actividad reciente» después. Un incendio puede seguir activo bajo nubes sin ser visto.",
            "Huella VIIRS: superficie de las celdas de 375 m con al menos un foco. Sirve para comparar tamaños entre incendios, pero no es el área quemada oficial: "
            "sobrestima los incendios pequeños (cada foco cuenta 14 ha) y subestima los que quedan bajo nubes.",
            "Área quemada (Sentinel-2): diferencia del índice normalizado de quemado (dNBR, bandas B8A y B12) entre la imagen despejada más reciente antes del inicio "
            "y la más reciente después, con máscara de nubes, sombras y agua. Se parte de los píxeles con dNBR de 0.27 o más a 750 m o menos de un foco y se suman "
            "los píxeles contiguos con dNBR de 0.10 o más y NBR posterior de 0.10 o menos (suelo carbonizado), hasta 3 km de los focos. Clases de severidad de Key y Benson (USGS). "
            "Si la imagen es anterior al primer foco, no se estima.",
            "En la vista 3D, la línea blanca es el borde del área quemada que muestra la imagen Sentinel-2 y la línea punteada, la zona a 250 m o menos de los focos VIIRS "
            "acumulados hasta el día elegido. No coinciden, y es esperable: VIIRS solo observa el fuego en sus pases de alrededor de la 01:30 y las 13:30 h, con píxeles de 375 m, "
            "y entre un pase y otro el frente puede quemar grandes extensiones de pajonal sin ser detectado.",
            "Avance máximo del frente: distancia máxima entre un foco nuevo del día y el foco previo más cercano del mismo incendio.",
        ]},
        {"titulo": "Índice de prioridad (0 a 100)", "parrafos": [
            "Suma ponderada, con escalas fijas para que el índice sea comparable entre días: actividad 30 (activo 1, en observación 0.5); "
            "tamaño 20 (huella, 1 = 2,000 ha o más, escala logarítmica); intensidad 20 (FRP acumulada, 1 = 10,000 MW o más); "
            "población a 5 km 15 (1 = 50,000 personas o más); área protegida 15 (dentro de ANP nacional o zona reservada 1; otra ANP 0.6; a 5 km o menos 0.3).",
            "Es una herramienta de orden para revisar primero lo más relevante; no sustituye la evaluación de campo.",
        ]},
        {"titulo": "Capas de contexto", "parrafos": [
            "Límites: distritos del INEI con UBIGEO (versión simplificada del repositorio peru-geojson). Áreas naturales protegidas: servicio geográfico de SERNANP "
            "(nacionales, zonas reservadas, de conservación regional y privada). Cobertura del suelo: ESA WorldCover 2021, clase mayoritaria alrededor de cada foco. "
            "Población: WorldPop 2020 (1 km). Relieve: AWS Terrain Tiles (SRTM y otras fuentes). Imágenes: Sentinel-2 L2A (Copernicus), vía Microsoft Planetary Computer.",
            "Región natural (aproximada): sierra si el foco está a 2,000 m o más; por debajo, costa o selva según el lado de la cordillera en que se encuentre.",
        ]},
        {"titulo": "Limitaciones", "parrafos": [
            "Los conteos satelitales no son comparables con los conteos de emergencias de INDECI: miden cosas distintas. "
            "Los datos de los últimos días pueden completarse cuando INPE y FIRMS reprocesen pases pendientes. "
            "La comparación histórica usa S-NPP; su sensor envejece, pero la proporción S-NPP/NOAA-20 de 2026 es similar a la de 2025.",
            f"Corte de datos: {resumen['corte_local']} (hora de Lima). Código y datos procesados en el repositorio del proyecto (scripts en Python).",
        ]},
    ]


def main():
    ev = pd.read_parquet(PRO / "eventos.parquet")
    focos = pd.read_parquet(INT / "focos_viirs.parquet")
    resumen = json.load(open(RAIZ / "dashboard" / "data" / "resumen.json"))

    # calibración INPE vs FIRMS (S-NPP, jul-oct 2025)
    import glob
    inpe = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(RAW / "inpe" / "inpe_peru_2025*.csv")))])
    inpe = inpe[inpe.satelite.isin(["NPP-375", "NPP-375D"])]
    inpe_m = pd.to_datetime(inpe.data_hora_gmt).dt.to_period("M").value_counts()
    firms = pd.read_csv(RAW / "firms" / "viirs-snpp_2025_Peru.csv")
    firms = firms[firms["type"] == 0]
    firms_m = pd.to_datetime(firms.acq_date).dt.to_period("M").value_counts()
    meses = [pd.Period(f"2025-{m:02d}") for m in (7, 8, 9, 10)]
    dif = [(inpe_m[m] / firms_m[m] - 1) * 100 for m in meses]
    calib = f"entre {min(dif):+.1f} % y {max(dif):+.1f} %"

    out = {
        "oficial": [{"indicador": a, "cifra": b, "fuente": c, "enlace": {"nombre": d, "url": e}} for a, b, c, d, e in OFICIAL],
        "validacion": validacion(ev, focos),
        "metodo": metodo(resumen, calib),
        "fuentes": "Fuentes: INPE Programa Queimadas; NASA FIRMS (VIIRS S-NPP, NOAA-20, NOAA-21); SERNANP; INEI; ESA WorldCover; "
                   "WorldPop; Copernicus Sentinel-2 vía Microsoft Planetary Computer; AWS Terrain Tiles. Cifras oficiales citadas con su fuente.",
        "calibracion_inpe_firms_pct": [round(v, 2) for v in dif],
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("contexto.json; calibración:", calib)
    for v in out["validacion"]:
        print(" -", v["incendio"], "→", v["detalle"])


if __name__ == "__main__":
    main()
