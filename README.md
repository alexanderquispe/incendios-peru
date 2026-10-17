# Monitor de Incendios Forestales del Perú

Tablero de situación de la temporada de incendios 2026 construido con datos satelitales públicos.
Inspirado en el prototipo de análisis de incendios de [@DilumSanjaya](https://x.com/DilumSanjaya/status/2108241054298415258),
que usaba terreno procedural y datos simulados. Esta versión usa datos reales del Perú: focos VIIRS, relieve real, imágenes
Sentinel-2 y límites oficiales.

**Tablero publicado:** https://claude.ai/artifact/UsyGgMV7ysFBEDzzrW5DeU (privado hasta que se comparta desde el menú *Share*).

> Herramienta independiente. No es un producto oficial del Estado peruano ni reemplaza los reportes del COEN, INDECI, SERFOR o SERNANP.

## Qué muestra

| Sección | Contenido |
|---|---|
| Situación nacional | Incendios activos > 100 ha, focos 24 h / 7 días, octubre y temporada frente a 2012–2025, áreas protegidas con focos, población a ≤ 5 km de focos recientes |
| Dónde está el fuego | Mapa nacional con focos por antigüedad, incendios activos, áreas protegidas y animación de la temporada; lista de incendios activos ordenada por un índice de prioridad (0–100) |
| El incendio, día por día | Vista 3D de 15 incendios priorizados: relieve real, imagen Sentinel-2 (color natural e infrarrojo), perímetro acumulado por día, severidad del quemado (dNBR) y gráficos de huella, intensidad (FRP) y altitud |
| Cómo va la temporada | Focos S-NPP acumulados desde el 1 de julio por año (2012–2026) y focos diarios frente al rango histórico |
| Departamentos | Focos 24 h / 7 días / temporada, tendencia de 30 días, anomalía frente a 2012–2025, incendios activos y focos en ANP |
| Contexto oficial y validación | Cifras del COEN, INDECI, SENAMHI, CENEPRED y MINAM/SERNANP con su fuente; cotejo de incendios reportados con las detecciones |

## Hallazgos al corte (17 oct 2026, 02:01 h de Lima)

- **Octubre es el más intenso desde 2012**: 12,984 focos S-NPP entre el 1 y el 16 de octubre, +126 % sobre el promedio 2012–2025
  y por encima del récord previo (2020: 11,776).
- **Temporada tardía**: del 1 de julio al 16 de octubre el acumulado va 17 % por debajo del promedio (puesto 12 de 15); julio,
  agosto y setiembre quedaron bajo el promedio.
- 56 incendios activos con huella mayor a 100 ha; 2,812 focos en 24 h y 13,915 en 7 días.
- Los incendios activos más extensos están en Curahuasi y San Pedro de Cachora (Abancay, Apurímac) y en Río Tambo
  (Satipo, Junín), a 8.7 km de la Reserva Comunal Asháninka.
- 28 áreas naturales protegidas con focos en 7 días (Imiria, Pacaya-Samiria y Subcuenca del Cotahuasi, las más afectadas).
- Validación: se detectaron los incendios reportados en Río Tambo, Huascarán–Llanganuco, Nor Yauyos-Cochas y Santa Teresa;
  el de Machupicchu (cerro Poques, 2.5 ha bajo dosel) no fue visible para VIIRS.

## Fuentes

| Dato | Fuente |
|---|---|
| Focos de calor 2025-06 → hoy | INPE, Programa Queimadas: archivo mensual de focos de Sudamérica (S-NPP, NOAA-20, NOAA-21) |
| Pases más recientes | NASA FIRMS, VIIRS NRT (últimos 7 días) |
| Serie histórica 2012–2025 | NASA FIRMS, archivo estándar VIIRS S-NPP por país (solo focos de vegetación, `type = 0`) |
| Límites | INEI con UBIGEO ([peru-geojson](https://github.com/juaneladio/peru-geojson)); tildes restituidas con [ubigeo-peru-aumentado](https://github.com/jmcastagnetto/ubigeo-peru-aumentado) |
| Áreas naturales protegidas | SERNANP, `geoservicios.sernanp.gob.pe` (ANP nacionales, zonas reservadas, ACR y ACP) |
| Cobertura del suelo | ESA WorldCover 2021 v200 |
| Población | WorldPop 2020, 1 km |
| Relieve | AWS Terrain Tiles (Terrarium) |
| Imágenes | Sentinel-2 L2A (Copernicus) vía Microsoft Planetary Computer |

INPE y FIRMS se calibraron entre sí en julio–octubre de 2025: la diferencia mensual en S-NPP fue de −1.4 % a +0.9 %.

## Método (resumen)

- **Fuentes estáticas**: se excluyen focos a < 500 m de detecciones FIRMS tipo volcán u otra fuente estática (2012–2025).
- **Eventos**: componentes conexas de focos a ≤ 1 km y ≤ 48 h. Estado *Activo* (< 24 h), *En observación* (24–72 h), *Sin actividad reciente*.
- **Huella VIIRS**: celdas de 375 m con al menos un foco. Sirve para comparar incendios; no es el área quemada oficial.
- **Área quemada**: dNBR de Sentinel-2 (B8A/B12), pre y post, con máscara SCL y solo a ≤ 1.5 km de los focos; clases de Key y Benson (USGS).
- **Prioridad (0–100)**: actividad 30, tamaño 20, intensidad 20, población a 5 km 15, área protegida 15, con escalas fijas (ver `src/05_eventos.py`).
- **Región natural**: sierra ≥ 2,000 m; debajo, costa o selva según la vertiente.

Detalle completo en la sección *Metodología, fuentes y limitaciones* del tablero.

## Estructura

```
src/
  01_descargar.py    descarga INPE, FIRMS, límites, WorldPop
  02_mapa_base.py    límites INEI, ANP SERNANP, relieve nacional
  03_cobertura.py    mosaico ESA WorldCover (~150 m)
  04_focos.py        unión de fuentes, limpieza y atributos de cada foco
  05_eventos.py      agrupamiento en incendios, estado, exposición, prioridad
  06_detalle.py      terreno, texturas Sentinel-2, dNBR y avance diario de los incendios priorizados
  07_exportar.py     JSON del tablero
  08_contexto.py     cifras oficiales, validación y texto de metodología
  terreno.py         utilidades de teselas de elevación
  actualizar.py      corre todo en orden
  servir.py          servidor local del tablero
dashboard/           página (index.html), datos (data/) e imágenes (assets/)
data/processed/eventos.csv   tabla de incendios de la temporada (uno por fila)
```

## Uso

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python src/actualizar.py      # ~20 min; descarga y regenera todo
.venv/bin/python src/servir.py          # http://localhost:8765
```

Para actualizar el tablero publicado, vuelva a correr `src/actualizar.py` y publique `dashboard/index.html` con sus archivos
en el mismo enlace.

## Limitaciones

- Un foco de calor no es un incendio forestal: incluye quemas agrícolas y de pastos. Los conteos satelitales no se comparan
  con los conteos de emergencias de INDECI.
- Nubes y humo ocultan el fuego; un incendio puede seguir activo sin ser visto.
- Los datos de los últimos días pueden completarse cuando INPE y FIRMS reprocesen pases pendientes.
- La región natural y la cobertura son aproximaciones para orientar, no clasificaciones oficiales.
