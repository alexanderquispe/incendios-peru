# Monitor de Incendios Forestales del Perú

Tablero de situación de la temporada de incendios 2026 construido con datos satelitales públicos.
Inspirado en el prototipo de análisis de incendios de [@DilumSanjaya](https://x.com/DilumSanjaya/status/2108241054298415258),
que usaba terreno procedural y datos simulados. Esta versión usa datos reales del Perú: focos VIIRS, relieve real, imágenes
Sentinel-2 y límites oficiales.

**Sitio web:** https://alexanderquispe.github.io/incendios-peru/ (GitHub Pages; se publica solo con cada cambio en `main`, ver `.github/workflows/pages.yml` y `src/sitio.py`). También está en https://claude.ai/artifact/UsyGgMV7ysFBEDzzrW5DeU.

**Repositorio:** https://github.com/alexanderquispe/incendios-peru. Quienes colaboraron en el curso tienen permiso de escritura: trabaje en una rama propia y abra un *pull request* hacia `main`.

> Herramienta independiente. No es un producto oficial del Estado peruano ni reemplaza los reportes del COEN, INDECI, SERFOR o SERNANP.

## Qué muestra

El tablero tiene ocho pestañas. Integra el trabajo de 32 alumnas y alumnos del curso de Data Science con Python
(sesión 14, [entregas](https://github.com/d2cml-ai/Data-Science-Python/issues/194)); ver *Aportes del curso*.

| Pestaña | Contenido |
|---|---|
| Situación | Titular con la conclusión del día, cifras clave con su contexto 2012–2026, cuatro listas para decidir (crecen más, clima a favor, más población cerca, áreas protegidas), mapa nacional y lista de prioridad. Solo cuenta incendios de vegetación probables |
| Incendios | Vista 3D de ~20 incendios (relieve, Sentinel-2, área quemada, avance diario); tabla de área quemada con su rango por umbral, % sin dato y cobertura quemada; las mismas cicatrices medidas por los alumnos; qué se quemó (WorldCover 10 m) |
| Clima y riesgo | Índice de crecimiento a 72 h (Fosberg + sequía antecedente), horas críticas, lluvia, corredor del viento y población en él, serie diaria de 14 días por incendio |
| ¿A quién afecta? | Personas a 1, 2, 5 y 10 km sin doble conteo (WorldPop 2026), edificaciones (Google Open Buildings), establecimientos de salud (RENIPRESS), centros poblados sin 4G (OSIPTEL), % del departamento, sensibilidad a la definición de incendio y exposición alrededor del área quemada |
| Agua y ecosistemas | Fuego en cabeceras de cuenca (> 3,800 m) y junto a lagunas y bofedales, dentro de áreas protegidas, y área quemada 2013–2024 de MapBiomas |
| Temporada | Focos por día y acumulados frente a 2012–2025, cada departamento frente a su propia historia (tres ventanas), 2024 frente a 2026 y tabla de departamentos |
| Respuesta | Línea de tiempo de las acciones del Estado en Río Tambo (COEN), marco normativo con su antigüedad, cifras oficiales y validación |
| Método y créditos | Metodología, fuentes y limitaciones; quiénes colaboraron y qué aportó cada uno |

## Hallazgos al corte (17 oct 2026, 02:01 h de Lima)

- **Octubre es el más intenso desde 2012**: 12,984 focos S-NPP entre el 1 y el 16 de octubre, +126 % sobre el promedio 2012–2025
  y por encima del récord previo (2020: 11,776).
- **Temporada tardía**: del 1 de julio al 16 de octubre el acumulado va 17 % por debajo del promedio (puesto 12 de 15); julio,
  agosto y setiembre quedaron bajo el promedio.
- 56 incendios activos con huella mayor a 100 ha; 2,812 focos en 24 h (9 % menos que las 24 h previas) y 13,915 en 7 días.
- Los que más se extendieron en 24 h: Manantay (Ucayali, +492 ha de huella), San Juan de Jarpa (Junín) y Chichas (Arequipa, +422 ha cada uno).
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
| Población | WorldPop 2026, 100 m, restringido a zonas con edificaciones (WorldPop 2020, 1 km, para la prioridad histórica) |
| Edificaciones | Google Open Buildings v3 (confianza ≥ 0.75), copia GeoParquet de VIDA en source.coop, consultada con DuckDB |
| Salud | RENIPRESS (SUSALUD), Plataforma Nacional de Datos Abiertos: establecimientos públicos activos I-1 a III |
| Conectividad | OSIPTEL: cobertura móvil por centro poblado (4G garantizada) |
| Clima | Open-Meteo, pronóstico horario y 14 días previos (sin clave) |
| Área quemada 2013–2024 | MapBiomas Fuego Perú, Colección 1 (CC-BY), por departamento |
| Acciones del Estado | COEN-INDECI, Reporte complementario N.º 14680 (21 oct 2026) |
| Relieve | AWS Terrain Tiles (Terrarium) |
| Imágenes | Sentinel-2 L2A (Copernicus) vía Microsoft Planetary Computer |

INPE y FIRMS se calibraron entre sí en julio–octubre de 2025: la diferencia mensual en S-NPP fue de −1.4 % a +0.9 %.
Desde el 13 de octubre de 2026 INPE repite focos (misma hora, posición y satélite con otro identificador; ≈ 4 % de octubre):
se eliminan en `src/04_focos.py`.

## Método (resumen)

- **Fuentes estáticas**: se excluyen focos a < 500 m de detecciones FIRMS tipo volcán u otra fuente estática (2012–2025).
- **Eventos**: componentes conexas de focos a ≤ 1 km y ≤ 48 h. Estado *Activo* (< 24 h), *En observación* (24–72 h), *Sin actividad reciente*.
- **Evidencia**: *incendio de vegetación probable* (≥ 3 focos, ≥ 2 pases, ≥ 50 % en vegetación natural), *posible quema urbana o
  fuente fija* (≥ 5,000 personas a 1 km, ≥ 50 % en zona urbana o suelo desnudo, o 1–2 focos en un punto que ardió ≥ 5 días de los
  180 previos) y *sin confirmar*. Las cifras principales solo usan los probables.
- **Huella VIIRS**: celdas de 375 m con al menos un foco. Sirve para comparar incendios; no es el área quemada oficial.
- **Área quemada**: dNBR de Sentinel-2 (B8A/B12) con máscara SCL (nubes, sombras, agua, nieve + 60 m). Imagen previa anterior a la
  hora del primer foco; posterior, la primera despejada después del último foco; en la selva, mosaico píxel a píxel de varias tomas.
  Umbral doble sembrado con los focos: núcleo con dNBR ≥ 0.27 a ≤ 750 m de un foco y crecimiento por píxeles contiguos con
  dNBR ≥ 0.10 y NBR posterior ≤ 0.10, hasta 3 km. Se publica también el área con solo dNBR ≥ 0.27 y el % sin dato.
  Cobertura quemada con ESA WorldCover 10 m. Clases de Key y Benson (USGS).
- **Exposición**: celdas WorldPop 2026 a 1, 2, 5 y 10 km de los focos de las últimas 72 h, unidas sin doble conteo; edificaciones,
  salud y centros poblados a ≤ 1 y 5 km; alrededor del área quemada, dentro y a 100 m, 500 m y 1 km del borde.
- **Riesgo de crecimiento**: percentil 90 del FFWI de Fosberg en 72 h × (0.5 + 0.5 × días secos / 14); FFWI = 0 con ≥ 2 mm en 24 h.
  Horas críticas (humedad < 30 %, ráfaga ≥ 30 km/h, sin lluvia). Corredor del viento: avance horario = 0.10 × viento × sequedad, tope 15 km.
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
  05_eventos.py      agrupamiento en incendios, evidencia, estado, población, prioridad
  06_detalle.py      terreno, texturas Sentinel-2, dNBR, cobertura quemada y avance diario de ~20 incendios
  09_clima.py        pronóstico Open-Meteo, índice de crecimiento y corredor del viento
  10_exposicion.py   personas, edificaciones, salud y conectividad cerca de los incendios
  11_historia.py     récords por departamento, 2024 vs 2026, fuego en cabeceras y ANP
  07_exportar.py     JSON del tablero
  08_contexto.py     cifras oficiales, validación, metodología, acciones, normas y créditos
  exposicion_util.py WorldPop 2026 en memoria y consulta de Open Buildings con caché
  terreno.py         utilidades de teselas de elevación
  actualizar.py      corre todo en orden
  servir.py          servidor local del tablero
  sitio.py           arma el sitio de GitHub Pages en _site/
dashboard/           página (index.html, pestanas.js), datos (data/) e imágenes (assets/)
data/curso/          aportes curados del curso: créditos, acciones del Estado, normas, cifras de los alumnos, MapBiomas
analisis/            análisis puntuales (2024 frente a 2026)
data/processed/eventos.csv   tabla de incendios de la temporada (uno por fila)
```

## Uso

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python src/actualizar.py      # ~45 min; descarga y regenera todo
.venv/bin/python src/servir.py          # http://localhost:8765
```

Para actualizar el tablero publicado, vuelva a correr `src/actualizar.py` y publique `dashboard/index.html` con sus archivos
en el mismo enlace.

## Limitaciones

- Un foco de calor no es un incendio forestal: incluye quemas agrícolas y de pastos. Los conteos satelitales no se comparan
  con los conteos de emergencias de INDECI.
- Nubes y humo ocultan el fuego; un incendio puede seguir activo sin ser visto.
- La zona con focos VIIRS no es el borde del fuego. VIIRS solo observa en sus pases (~01:30 y ~13:30 h) con píxeles de 375 m, y entre
  pases el frente puede quemar grandes extensiones sin ser detectado. En Alto Pichigua (Espinar, Cusco), 170 de los 178 focos son de
  los pases de mediodía, y el área quemada en Sentinel-2 (2,511 ha) supera la huella VIIRS (1,420 ha). El borde que vale es el de Sentinel-2.
- La imagen infrarroja muestra todas las quemas, también las anteriores al incendio; el dNBR las separa porque ya estaban quemadas
  en la imagen previa.
- Los datos de los últimos días pueden completarse cuando INPE y FIRMS reprocesen pases pendientes.
- La región natural y la cobertura son aproximaciones para orientar, no clasificaciones oficiales.
- La exposición depende de la definición de incendio y del radio: el tablero muestra la sensibilidad. WorldCover casi no distingue
  chacras (23 % de los focos cae en superficie agrícola MIDAGRI y 1.9 % en «cultivo»). Faltan escuelas (ESCALE), comunidades nativas
  (BDPI) y superficie agrícola a escala nacional: no tienen descarga automática pública.
- El índice de crecimiento y el corredor del viento usan umbrales provisionales y un modelo de ~10 km: sirven para anticipar, no
  predicen el frente.

## Aportes del curso

Este tablero integra métodos, datos y hallazgos de las entregas de la sesión 14 del curso de Data Science con Python
([issue #194](https://github.com/d2cml-ai/Data-Science-Python/issues/194)). El detalle de qué aportó cada persona está en
`data/curso/creditos.json` y en la pestaña *Método y créditos*.

Adriana Garcés, Alessandra Valeria Murga Rimac, Alexander Noblejas, Amanda Gomez, Ana Karen Zamalloa Lima, Cristian Moises Wong Pagan, Diego Enrique Sime Rendón, Estefanny Mejía, Fabricio Luna Palacios, Fiorella Ampuero, Fiorella del Rocío Becerril Mercado, Flavia Romero Piedra, Frank Pinares Gutiérrez, Gabriela Pozo, Greicy Rodriguez, Hideki Harada, Isabella Albarrán Chávez, Ivette Mamani Flores, Jhanela Carhuaz Fuster, Jose Navarro, Josselin Yauri Condor, Josué Soria, Lory Acosta, Luis Guevara Vega, Mirian de la Cruz Condori, Noelia Fernanda Leon Ruiz, Oscar Andres Chávez Inocente, Ricardo Antonio Macedo Villegas, Roddy Huarhua, Rodrigo Norabuena, Víctor Guardia y Ximena Pinillos Zegarra.
