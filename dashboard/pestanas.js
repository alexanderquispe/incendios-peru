/* Pestañas que integran los aportes del curso de Data Science (sesión 14):
   clima y riesgo, ¿a quién afecta?, agua y ecosistemas, área quemada, récords, 2024 vs 2026,
   respuesta del Estado, normas y créditos. Usa las utilidades globales de index.html
   (el, fmt, fmt1, token, rgb, svgBase, tooltip, ponerTip, D, ...). */
"use strict";

const NOMBRE_EVID = { probable: "Probable", sin_confirmar: "Sin confirmar", urbano: "Urbana o fija" };
const AYUDA_EVID = {
  probable: "Incendio de vegetación probable: 3 o más focos, vistos en 2 o más pases, en vegetación natural",
  sin_confirmar: "1 o 2 focos, o un solo pase: puede ser una quema pequeña",
  urbano: "Posible quema urbana, industrial o en un punto que arde una y otra vez",
};
const evid = e => el("span", { class: "evid " + e, text: NOMBRE_EVID[e] || e, title: AYUDA_EVID[e] || "" });
const NOMBRE_SEM = { rojo: "Alto", ambar: "Medio", verde: "Bajo" };
const sem = s => el("span", { class: "semaforo " + s, text: NOMBRE_SEM[s] || "—" });
const lugar = e => el("span", { class: "lugar" }, e.distrito, el("small", { text: `${e.provincia} · ${e.departamento}` }));
const kmTxt = v => (v == null ? "—" : `${fmt1.format(v)} km`);
const RUMBOS = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"];
const rumboTxt = g => RUMBOS[Math.round(((g % 360) + 360) % 360 / 45) % 8];
const vivosProbables = () => D.eventos.filter(e => e.evidencia === "probable" && e.estado !== "Sin actividad reciente");
function filaTabla(celdas, attrs = {}) { return el("tr", attrs, ...celdas.map(c => (c instanceof Node && c.tagName === "TD" ? c : el("td", {}, c)))); }
function td(v, cls) { return el("td", { class: cls || null }, v); }
function encabezado(tabla, cols) {
  tabla.replaceChildren(el("thead", {}, el("tr", {}, ...cols.map(c => el("th", { scope: "col", text: c })))), el("tbody"));
  return tabla.querySelector("tbody");
}

/* ---------------------------------------------------------------- situación: cuarta lista */
function pintarTriageRiesgo() {
  const ol = $("#tri-riesgo");
  if (!D.clima) { ol.replaceChildren(el("li", { class: "vacio", text: "Sin pronóstico disponible." })); return; }
  const lista = vivosProbables().filter(e => e.ic != null).sort((a, b) => b.ic - a.ic).slice(0, 5);
  const verdes = D.clima.semaforo.verde || 0, total = Object.values(D.clima.semaforo).reduce((a, b) => a + b, 0);
  ol.replaceChildren(...lista.map((e, i) => filaTriage(i, e.distrito, e.departamento, fmt1.format(e.ic), e.ic / 50, "riesgo",
    `${NOMBRE_SEM[e.semaforo]} · ${fmt.format(e.lluvia_72h_mm)} mm de lluvia en 72 h · ${e.dias_secos} días secos`,
    () => { mostrarPestana("clima"); seleccionarClima(e.evento); }, e.detalle)));
  if (verdes === total) ol.append(el("li", { class: "vacio", text: `Los ${fmt.format(total)} incendios vigilados están en nivel bajo: llueve o lloverá en casi todos.` }));
}

/* ---------------------------------------------------------------- clima y riesgo */
const C = { sel: null };
function pintarClima() {
  if (!D.clima) { $("#clima-intro").textContent = "El pronóstico no está disponible en esta actualización."; return; }
  const lista = vivosProbables().filter(e => e.ic != null).sort((a, b) => b.ic - a.ic);
  const n = lista.length, s = D.clima.semaforo;
  const conLluvia = lista.filter(e => e.lluvia_72h_mm >= 5).length;
  const criticas = lista.filter(e => e.horas_criticas_72h > 0).length;
  const maxPob = d3.max(lista, e => e.pob_corredor_72h) || 0;
  $("#t-clima").textContent = (s.rojo || 0) + (s.ambar || 0) === 0
    ? "Las lluvias llegaron: ningún incendio tiene clima a favor para crecer en 72 h"
    : `${fmt.format((s.rojo || 0) + (s.ambar || 0))} incendios tienen clima a favor para crecer en 72 h`;
  $("#clima-intro").textContent = `Pronóstico horario de Open-Meteo para ${fmt.format(n)} incendios de vegetación probables activos o en observación. ` +
    `${fmt.format(conLluvia)} recibirán 5 mm de lluvia o más en las próximas 72 h (mediana: ${fmt1.format(D.clima.lluvia_72h_mediana)} mm). ` +
    `El viento empuja el fuego, pero con suelo húmedo avanza poco: el corredor de 72 h abarca como máximo ${fmtHab(maxPob)} personas.`;
  const tile = (et, v, nota, cls) => el("div", { class: "cifra " + (cls || "") }, el("span", { class: "eyebrow", text: et }), el("span", { class: "valor", text: v }), el("span"), el("span", { class: "nota", text: nota }));
  $("#clima-cifras").replaceChildren(
    tile("Nivel alto o medio", fmt.format((s.rojo || 0) + (s.ambar || 0)), `de ${fmt.format(n)} incendios vigilados`, (s.rojo || 0) ? "critico" : ""),
    tile("Con horas críticas en 72 h", fmt.format(criticas), "humedad < 30 %, ráfaga ≥ 30 km/h y sin lluvia, a la vez"),
    tile("Con lluvia ≥ 5 mm en 72 h", fmt.format(conLluvia), `de ${fmt.format(n)}; la lluvia corta el avance`),
    tile("Días secos seguidos, máximo", fmt.format(d3.max(lista, e => e.dias_secos) || 0), "sequía antecedente: más días, más combustible seco"));
  const tb = encabezado($("#tabla-clima"), ["Incendio", "Nivel e índice", "Días secos", "Lluvia 72 h", "Hum. mín. · ráfaga", "Horas críticas", "Avance 24 h", "Corredor 72 h"]);
  $("#tabla-clima").classList.add("sel");
  for (const e of lista) {
    const tr = filaTabla([
      lugar(e),
      el("span", { class: "num" }, sem(e.semaforo), " ", fmt1.format(e.ic), el("span", { class: "mini-barra" }, el("i", { style: `width:${Math.min(100, e.ic / 50 * 100)}%` }))),
      td(fmt.format(e.dias_secos)), td(`${fmt1.format(e.lluvia_72h_mm)} mm`), td(`${fmt.format(e.hr_min_72h)} % · ${fmt.format(e.racha_max_72h)} km/h`),
      td(fmt.format(e.horas_criticas_72h), e.horas_criticas_72h ? "" : "cero"),
      td(e.avance_24h_km ? `${fmt1.format(e.avance_24h_km)} km, ${rumboTxt(e.rumbo_24h)}` : "—"),
      td(`${fmtHab(e.pob_corredor_72h || 0)} hab.`),
    ], { "data-ev": e.evento, tabindex: "0", onclick: () => seleccionarClima(e.evento), onkeydown: ev => { if (ev.key === "Enter") seleccionarClima(e.evento); } });
    tb.append(tr);
  }
  seleccionarClima(C.sel || lista[0]?.evento);
}
function seleccionarClima(id) {
  if (!id || !D.clima) return;
  C.sel = id;
  for (const tr of document.querySelectorAll("#tabla-clima tbody tr")) tr.setAttribute("aria-selected", tr.dataset.ev === id);
  const e = D.evPorId.get(id), s = D.clima.series[id], r = D.clima.rutas[id];
  if (!e || !s) return;
  const ficha = $("#ficha-clima");
  const rosa = rosaViento(r, e);
  ficha.replaceChildren(
    el("div", { class: "ficha-cabeza" }, el("h3", { text: e.distrito }), el("span", { class: "tenue", text: `${e.provincia} · ${e.departamento}` }),
      el("span", { class: "fila" }, pill(e.estado), sem(e.semaforo), `índice ${fmt1.format(e.ic)}`)),
    el("div", { class: "grafico", style: "padding:0" }, el("span", { class: "eyebrow", text: "Últimos 7 días y próximos 7" }), el("div", { id: "g-clima-serie" })),
    rosa,
    el("p", { class: "nota-chica", text: "Barras: lluvia diaria. Línea: índice de Fosberg máximo del día (0–100). La franja marca el pronóstico. El corredor supone que el frente avanza al 10 % del viento cuando el aire está seco y se detiene con lluvia; sirve para anticipar, no predice el frente." }));
  dibujarSerieClima(s);
}
function rosaViento(r, e) {
  const W = 132, c = W / 2, R = 54;
  const svg = d3.create("svg").attr("width", W).attr("height", W).attr("viewBox", `0 0 ${W} ${W}`).attr("role", "img");
  svg.append("circle").attr("cx", c).attr("cy", c).attr("r", R).attr("fill", "none").attr("stroke", token("--line-2"));
  svg.append("circle").attr("cx", c).attr("cy", c).attr("r", R / 2).attr("fill", "none").attr("stroke", token("--line")).attr("stroke-dasharray", "2 3");
  for (const [t, ang] of [["N", 0], ["E", 90], ["S", 180], ["O", 270]]) {
    const a = ang * Math.PI / 180;
    svg.append("text").attr("x", c + Math.sin(a) * (R + 8)).attr("y", c - Math.cos(a) * (R + 8) + 4).attr("text-anchor", "middle")
      .attr("font-size", 10).attr("fill", token("--ink-3")).text(t);
  }
  const k72 = r ? Math.max(1, e.avance_72h_km) : 1, esc = R / Math.max(2, k72);
  const flecha = (km, color, ancho) => {
    if (!km) return;
    const a = (e.rumbo_24h || 0) * Math.PI / 180, x = c + Math.sin(a) * km * esc, y = c - Math.cos(a) * km * esc;
    svg.append("line").attr("x1", c).attr("y1", c).attr("x2", x).attr("y2", y).attr("stroke", color).attr("stroke-width", ancho).attr("stroke-linecap", "round");
    svg.append("circle").attr("cx", x).attr("cy", y).attr("r", ancho + 1).attr("fill", color);
  };
  flecha(e.avance_72h_km, token("--fire-old"), 3);
  flecha(e.avance_24h_km, token("--fire-24"), 3.5);
  svg.append("circle").attr("cx", c).attr("cy", c).attr("r", 4).attr("fill", token("--ink"));
  svg.attr("aria-label", e.avance_24h_km ? `El viento empujaría el frente ${fmt1.format(e.avance_24h_km)} km hacia el ${rumboTxt(e.rumbo_24h)} en 24 h` : "Sin avance esperado");
  const texto = e.avance_72h_km
    ? [el("strong", { text: `${fmt1.format(e.avance_24h_km)} km en 24 h y ${fmt1.format(e.avance_72h_km)} km en 72 h, hacia el ${rumboTxt(e.rumbo_24h)}.` }),
      ` En el corredor viven ${fmtHab(e.pob_corredor_24h || 0)} personas a 24 h y ${fmtHab(e.pob_corredor_72h || 0)} a 72 h (WorldPop 2026).`,
      e.dias_secos ? ` Lleva ${e.dias_secos} días sin lluvia.` : " Llovió en las últimas 24 h."]
    : ["Con lluvia o humedad alta, el modelo no espera avance del frente en 72 h."];
  return el("div", { class: "rosa" }, svg.node(), el("p", {}, ...texto));
}
function dibujarSerieClima(s) {
  const cont = $("#g-clima-serie"); if (!cont) return;
  const { svg, iw, ih, m } = svgBase(cont, 190, { t: 10, r: 34, b: 24, l: 34 });
  svg.attr("aria-label", "Lluvia diaria e índice de Fosberg, siete días antes y siete después");
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const x = d3.scaleBand().domain(s.fecha).range([0, iw]).padding(0.25);
  const yL = d3.scaleLinear().domain([0, Math.max(10, d3.max(s.lluvia) || 0)]).nice().range([ih, 0]);
  const yF = d3.scaleLinear().domain([0, Math.max(40, d3.max(s.ffwi) || 0)]).nice().range([ih, 0]);
  const hoy = s.fecha.indexOf(D.clima.hoy);
  if (hoy >= 0) g.append("rect").attr("x", x(s.fecha[hoy]) - x.step() * x.paddingInner() / 2).attr("width", iw - x(s.fecha[hoy]) + x.step() * x.paddingInner() / 2)
    .attr("y", 0).attr("height", ih).attr("fill", token("--panel-2"));
  g.append("g").attr("class", "rejilla").call(d3.axisLeft(yF).ticks(4).tickSize(-iw).tickFormat("")).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").call(d3.axisLeft(yF).ticks(4)).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(${iw},0)`).call(d3.axisRight(yL).ticks(4).tickFormat(v => v + " mm")).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickValues(s.fecha.filter((_, i) => i % 3 === 0)).tickFormat(fechaCorta));
  g.selectAll("rect.ll").data(s.lluvia).join("rect").attr("class", "ll").attr("x", (_, i) => x(s.fecha[i])).attr("width", x.bandwidth())
    .attr("y", v => yL(v || 0)).attr("height", v => ih - yL(v || 0)).attr("rx", 2).attr("fill", token("--div-neg")).attr("opacity", 0.55);
  g.append("path").attr("d", d3.line().x((_, i) => x(s.fecha[i]) + x.bandwidth() / 2).y(v => yF(v))(s.ffwi)).attr("fill", "none")
    .attr("stroke", token("--fire-24")).attr("stroke-width", 2.2);
  g.selectAll("circle.cr").data(s.horas_criticas.map((v, i) => [v, i]).filter(d => d[0] > 0)).join("circle").attr("class", "cr")
    .attr("cx", d => x(s.fecha[d[1]]) + x.bandwidth() / 2).attr("cy", d => yF(s.ffwi[d[1]])).attr("r", 4.5).attr("fill", token("--crit"));
  const caja = cont.parentElement, t = tooltip(caja);
  g.selectAll("rect.hit").data(s.fecha).join("rect").attr("class", "hit").attr("x", f => x(f) - x.step() * x.paddingInner() / 2).attr("width", x.step())
    .attr("y", 0).attr("height", ih).attr("fill", "transparent")
    .on("pointermove", (ev, f) => { const i = s.fecha.indexOf(f), [cx, cy] = d3.pointer(ev, caja);
      ponerTip(t, caja, cx, cy, `<b>${fechaCorta(f)}</b>${i >= hoy ? " · pronóstico" : ""}<br>Lluvia ${fmt1.format(s.lluvia[i] || 0)} mm · humedad mín. ${fmt.format(s.hr_min[i])} %<br>Ráfaga ${fmt.format(s.racha[i])} km/h · T máx. ${fmt1.format(s.t_max[i])} °C<br>Fosberg ${fmt1.format(s.ffwi[i])}${s.horas_criticas[i] ? ` · ${s.horas_criticas[i]} h críticas` : ""}`); })
    .on("pointerleave", () => { t.hidden = true; });
}

/* ---------------------------------------------------------------- ¿a quién afecta? */
function pintarAfectados() {
  const x = D.expo;
  if (!x) { $("#afectados-intro").textContent = "La exposición no está disponible en esta actualización."; return; }
  const p = x.sensibilidad.probables, pa = x.sensibilidad.probables_activos, t = x.sensibilidad.todos;
  $("#afectados-intro").textContent = `${fmtHab(p["5km"])} personas viven a 5 km o menos de los ${fmt.format(p.incendios)} incendios de vegetación probables activos o en observación ` +
    `(${fmtHab(pa["5km"])} de los ${fmt.format(pa.incendios)} activos en las últimas 24 h). Si se contara cualquier foco, incluidas quemas urbanas y focos sueltos, la cifra subiría a ${fmtHab(t["5km"])}: ` +
    `por eso el tablero separa los incendios probables.`;
  const tile = (et, v, nota, cls) => el("div", { class: "cifra " + (cls || "") }, el("span", { class: "eyebrow", text: et }), el("span", { class: "valor", text: v }), el("span"), el("span", { class: "nota", text: nota }));
  $("#afectados-cifras").replaceChildren(
    tile("Personas a ≤ 1 km", fmtHab(p["1km"]), "riesgo directo: humo denso y fuego cerca de casas", "critico"),
    tile("Personas a ≤ 5 km", fmtHab(p["5km"]), `${fmtHab(p["2km"])} a ≤ 2 km; ${fmtHab(p["10km"])} a ≤ 10 km`),
    tile("Edificaciones a ≤ 1 km", fmtHab(x.edificaciones_1km), `${fmtHab(x.edificaciones_5km)} a ≤ 5 km (suma por incendio)`),
    tile("Establecimientos de salud a ≤ 5 km", fmt.format(x.salud_5km), "públicos, categoría I-1 a III (RENIPRESS)"),
    tile("Centros poblados a ≤ 5 km", fmt.format(x.ccpp_5km), `${fmt.format(x.ccpp_sin_4g_5km)} sin cobertura 4G garantizada (OSIPTEL)`),
    tile("Departamento más expuesto", x.departamentos[0] ? x.departamentos[0].departamento : "—",
      x.departamentos[0] ? `${fmtHab(x.departamentos[0].pob_5km)} personas, ${fmt1.format(x.departamentos[0].pct)} % de su población` : ""));
  // sensibilidad
  const defs = [["probables_activos", "Probables activos (24 h)"], ["probables", "Probables activos o en observación"], ["todos_3focos", "Cualquier incendio con 3 o más focos"], ["todos", "Cualquier foco, incluidas quemas urbanas"]];
  const radios = ["1km", "2km", "5km", "10km"];
  const max = d3.max(defs, ([k]) => x.sensibilidad[k]["10km"]);
  const color = d3.scaleSequentialLog([100, max], d3.interpolateRgb(token("--panel-2"), token("--fire-7")));
  const tb = encabezado($("#tabla-sens"), ["Qué se cuenta", "1 km", "2 km", "5 km", "10 km"]);
  for (const [k, nom] of defs) {
    const fila = x.sensibilidad[k];
    tb.append(el("tr", {}, el("td", {}, nom, el("br"), el("span", { class: "tenue", text: `${fmt.format(fila.incendios)} incendios` })),
      ...radios.map(r => { const c = color(Math.max(100, fila[r])); return el("td", { style: `background:${c};color:${d3.hsl(c).l > 0.55 ? "#0f1b26" : "#fff"}`, text: fmtHab(fila[r]) }); })));
  }
  $("#nota-sens").textContent = "El resto del tablero usa la segunda fila: incendios de vegetación probables, activos o en observación.";
  // tabla por incendio
  const lista = vivosProbables().filter(e => e.pob_1km != null).sort((a, b) => (b.poblacion_5km || 0) - (a.poblacion_5km || 0));
  const tb2 = encabezado($("#tabla-expo"), ["Incendio", "Estado", "Personas ≤ 1 km", "≤ 5 km", "Edificaciones ≤ 1 km", "≤ 5 km", "Salud ≤ 5 km", "Más cercano", "Centros poblados ≤ 5 km", "Sin 4G"]);
  $("#tabla-expo").classList.add("sel");
  for (const e of lista) {
    const cerca = (x.salud_cercanos[e.evento] || [])[0];
    tb2.append(filaTabla([lugar(e), pill(e.estado), td(fmt.format(e.pob_1km)), td(fmt.format(e.poblacion_5km || 0)),
      td(fmt.format(e.edif_1km || 0)), td(fmt.format(e.edif_5km || 0)), td(fmt.format(e.salud_5km || 0)),
      el("td", { class: "tenue", title: cerca ? `${cerca.nombre} (${cerca.categoria})` : "" }, cerca ? `${fmt1.format(cerca.km)} km · ${cerca.categoria}` : kmTxt(e.salud_mas_cercano_km)),
      td(fmt.format(e.ccpp_5km || 0)), td(fmt.format(e.ccpp_sin_4g_5km || 0), e.ccpp_sin_4g_5km ? "" : "cero")],
      { tabindex: "0", onclick: () => { seleccionarEvento(e.evento, true); desplazar("mapa-sec"); } }));
  }
  // alrededor del área quemada
  const q = (D.quemado?.filas || []).filter(f => f.exposicion);
  const tb3 = encabezado($("#tabla-expo-q"), ["Incendio", "Área quemada", "Edificaciones dentro", "≤ 100 m", "≤ 500 m", "≤ 1 km", "Personas dentro", "Personas ≤ 1 km"]);
  for (const f of q.sort((a, b) => b.exposicion.edif_1km - a.exposicion.edif_1km)) {
    const x2 = f.exposicion;
    tb3.append(filaTabla([el("span", { class: "lugar" }, f.distrito, el("small", { text: f.departamento })), td(`${fmt.format(f.total_ha)} ha`),
      td(fmt.format(x2.edif_dentro)), td(fmt.format(x2.edif_100m)), td(fmt.format(x2.edif_500m)), td(fmt.format(x2.edif_1km)),
      td(fmt.format(x2.pob_dentro)), td(fmt.format(x2.pob_1km))]));
  }
}
function dibujarDepExp() {
  if (!D.expo) return;
  const datos = D.expo.departamentos.slice(0, 12), cont = $("#g-depexp");
  const { svg, iw, ih, m } = svgBase(cont, datos.length * 26 + 30, { t: 6, r: 70, b: 20, l: 110 });
  svg.attr("aria-label", "Personas a 5 km de incendios probables por departamento");
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const y = d3.scaleBand().domain(datos.map(d => d.departamento)).range([0, ih]).padding(0.25);
  const x = d3.scaleLinear().domain([0, d3.max(datos, d => d.pob_5km) || 1]).nice().range([0, iw]);
  g.append("g").attr("class", "eje").call(d3.axisLeft(y).tickSize(0)).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).ticks(4).tickFormat(v => fmtHab(v)));
  g.selectAll("rect").data(datos).join("rect").attr("y", d => y(d.departamento)).attr("height", y.bandwidth()).attr("x", 0)
    .attr("width", d => Math.max(1, x(d.pob_5km))).attr("rx", 3).attr("fill", token("--pob"));
  g.selectAll("text.v").data(datos).join("text").attr("class", "etq-serie").attr("x", d => x(d.pob_5km) + 6).attr("y", d => y(d.departamento) + y.bandwidth() / 2 + 4)
    .attr("fill", token("--ink-2")).text(d => `${fmtHab(d.pob_5km)} · ${fmt1.format(d.pct)} %`);
}

/* ---------------------------------------------------------------- agua y ecosistemas */
function pintarAgua() {
  const h = D.historia;
  if (!h) { $("#agua-intro").textContent = "Sin datos históricos en esta actualización."; return; }
  const a = h.agua.por_anio, anios = Object.keys(a).sort(), base = anios.filter(x => x < "2026");
  const prom = k => d3.mean(base, y => a[y][k]);
  const a26 = a["2026"];
  $("#agua-intro").textContent = `Del 1 de julio al ${fechaCorta(h.hasta)}, ${fmt.format(a26.altoandino)} focos cayeron sobre 3,800 m, donde nacen los ríos ` +
    `(promedio 2012–2025: ${fmt.format(prom("altoandino"))}); ${fmt.format(a26.agua_alto)} estaban junto a lagunas o bofedales. ` +
    `Dentro de áreas protegidas hubo ${fmt.format(a26.anp)} focos (promedio ${fmt.format(prom("anp"))}). Las lagunas ` +
    `y bofedales salen de ESA WorldCover y son una aproximación.`;
  const tb = encabezado($("#tabla-anp-hist"), ["Área natural protegida", "2026", "Promedio 2012–2025", "Cambio"]);
  for (const r of h.agua.anp_2026) {
    const cambio = r.promedio >= 5 ? Math.round((r.anio_2026 / r.promedio - 1) * 100) : null;
    tb.append(filaTabla([el("span", { class: "lugar", text: r.anp }), td(fmt.format(r.anio_2026)), td(fmt1.format(r.promedio)),
      td(cambio == null ? "n. d." : signo(cambio) + " %", cambio > 0 ? "" : "tenue")]));
  }
  const mb = h.mapbiomas;
  if (mb) $("#nota-mapbiomas").textContent = `${mb.fuente} Total: ${fmt.format(mb.total_ha)} ha quemadas por primera vez en ${mb.periodo}. Por departamento, desde el ráster acumulado.`;
}
function serieAnual(cont, anios, valores, etiqueta, destacados = { "2026": "--y2026", "2024": "--y2024" }) {
  const { svg, iw, ih, m } = svgBase(cont, 220, { t: 14, r: 10, b: 24, l: 44 });
  svg.attr("aria-label", etiqueta + ": " + anios.map((a, i) => `${a} ${fmt.format(valores[i])}`).join(", "));
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const x = d3.scaleBand().domain(anios).range([0, iw]).padding(0.2);
  const y = d3.scaleLinear().domain([0, d3.max(valores) || 1]).nice().range([ih, 0]);
  g.append("g").attr("class", "rejilla").call(d3.axisLeft(y).ticks(4).tickSize(-iw).tickFormat("")).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").call(d3.axisLeft(y).ticks(4).tickFormat(v => (v >= 1000 ? fmt1.format(v / 1000) + " mil" : v))).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickValues(anios.filter((a, i) => i % 2 === 0 || a === "2026")).tickFormat(a => "’" + a.slice(2)));
  g.selectAll("rect").data(valores).join("rect").attr("x", (_, i) => x(anios[i])).attr("width", x.bandwidth())
    .attr("y", v => y(v)).attr("height", v => ih - y(v)).attr("rx", Math.min(3, x.bandwidth() / 2))
    .attr("fill", (_, i) => token(destacados[anios[i]] || "--hist-line"));
  const media = d3.mean(valores.filter((_, i) => anios[i] < "2026"));
  g.append("line").attr("x1", 0).attr("x2", iw).attr("y1", y(media)).attr("y2", y(media)).attr("stroke", token("--ink-3")).attr("stroke-dasharray", "4 3");
  g.append("text").attr("class", "etq-serie").attr("x", 4).attr("y", y(media) - 5).attr("fill", token("--ink-3")).text("promedio 2012–2025");
  const caja = cont.parentElement, t = tooltip(caja);
  g.selectAll("rect.hit").data(anios).join("rect").attr("class", "hit").attr("x", a => x(a)).attr("width", x.bandwidth()).attr("y", 0).attr("height", ih).attr("fill", "transparent")
    .on("pointermove", (ev, a) => { const [cx, cy] = d3.pointer(ev, caja); ponerTip(t, caja, cx, cy, `<b>${a}</b>: <span class="num">${fmt.format(valores[anios.indexOf(a)])}</span>`); })
    .on("pointerleave", () => { t.hidden = true; });
}
function dibujarAgua() {
  const h = D.historia; if (!h) return;
  const a = h.agua.por_anio, anios = Object.keys(a).sort();
  serieAnual($("#g-alto"), anios, anios.map(y => a[y].altoandino), "Focos sobre 3,800 m por año");
  $("#clave-alto").replaceChildren(el("span", {}, el("i", { class: "banda", style: `background:${token("--y2026")}` }), "2026"),
    el("span", {}, el("i", { class: "banda", style: `background:${token("--y2024")}` }), "2024"),
    el("span", {}, el("i", { style: `border-color:${token("--ink-3")};border-top-style:dashed` }), "Promedio 2012–2025"));
  serieAnual($("#g-anpser"), anios, anios.map(y => a[y].anp), "Focos dentro de áreas protegidas por año");
  const mb = h.mapbiomas; if (!mb) return;
  const datos = Object.entries(mb.departamentos).sort((x, y) => y[1] - x[1]).slice(0, 12);
  const cont = $("#g-mapbiomas");
  const { svg, iw, ih, m } = svgBase(cont, datos.length * 24 + 28, { t: 4, r: 64, b: 20, l: 110 });
  svg.attr("aria-label", "Área quemada 2013–2024 por departamento, MapBiomas");
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const y = d3.scaleBand().domain(datos.map(d => d[0])).range([0, ih]).padding(0.25);
  const x = d3.scaleLinear().domain([0, datos[0][1]]).nice().range([0, iw]);
  g.append("g").attr("class", "eje").call(d3.axisLeft(y).tickSize(0)).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).ticks(4).tickFormat(v => fmt.format(v / 1000) + " mil"));
  g.selectAll("rect").data(datos).join("rect").attr("y", d => y(d[0])).attr("height", y.bandwidth()).attr("x", 0).attr("width", d => x(d[1])).attr("rx", 3).attr("fill", token("--fire-old"));
  g.selectAll("text.v").data(datos).join("text").attr("class", "etq-serie").attr("x", d => x(d[1]) + 6).attr("y", d => y(d[0]) + y.bandwidth() / 2 + 4)
    .attr("fill", token("--ink-2")).text(d => `${fmt.format(d[1] / 1000)} mil ha`);
}

/* ---------------------------------------------------------------- incendios: área quemada medida */
function pintarQuemado() {
  const q = D.quemado; if (!q) return;
  const medidos = q.filas.filter(f => f.medido), sin = q.filas.filter(f => !f.medido);
  const total = d3.sum(medidos, f => f.total_ha);
  $("#quemado-intro").textContent = `Sentinel-2 midió ${fmt.format(total)} ha quemadas en ${medidos.length} de los ${q.filas.length} incendios con vista 3D` +
    (sin.length ? `; en ${sin.length} las nubes o la falta de una imagen posterior no lo permiten (${unir(sin.map(f => f.distrito))}).` : ".") +
    " Seleccione una fila para verla en el terreno.";
  const tb = encabezado($("#tabla-quemado"), ["Incendio", "Área quemada", "Con dNBR ≥ 0.27", "Sin dato", "Imágenes", "Qué se quemó", "Huella VIIRS"]);
  $("#tabla-quemado").classList.add("sel");
  for (const f of [...medidos.sort((a, b) => b.total_ha - a.total_ha), ...sin]) {
    const cob = f.cobertura?.length ? f.cobertura.slice(0, 2).map(c => `${c.clase} ${fmt.format(c.ha / f.total_ha * 100)} %`).join(", ") : "—";
    tb.append(filaTabla([
      el("span", { class: "lugar" }, f.distrito, el("small", { text: `${f.provincia} · ${f.departamento}` })),
      td(f.medido ? `${fmt.format(f.total_ha)} ha` : "no medible", f.medido ? "" : "tenue"),
      td(f.medido ? `${fmt.format(f.ha_027)} ha` : "—"),
      td(f.medido ? `${fmt.format(f.pct_sin_dato)} %` : "—", f.pct_sin_dato > 20 ? "" : "tenue"),
      td(f.sentinel.post ? `${fechaCorta(f.sentinel.pre || f.sentinel.post)} → ${fechaCorta(f.sentinel.post)}${f.focos_despues ? ` · ${fmt.format(f.focos_despues)} focos después` : ""}` : "sin imagen", "tenue"),
      td(cob), td(`${fmt.format(f.huella_ha)} ha`, "tenue"),
    ], { tabindex: "0", onclick: () => { seleccionarEvento(f.evento, false); $("#sel-evento").value = f.evento; desplazar("incendio"); } }));
  }
  $("#quemado-pie").textContent = "Área quemada: núcleo con dNBR ≥ 0.27 junto a los focos, más los píxeles contiguos con dNBR ≥ 0.10 y suelo carbonizado. «Con dNBR ≥ 0.27» es lo que daría un solo umbral: en la puna el pajonal arde con dNBR bajo y la diferencia es grande. «Sin dato»: entorno cubierto por nubes, sombra o nieve; si es alto, la cifra es un mínimo. «Focos después»: el fuego siguió tras la imagen y el área real puede ser mayor.";
}
const COLORES_COB = { "Pastizal": "#c9a227", "Bosque": "#2f7d4f", "Matorral": "#8f9a3a", "Cultivo": "#d77a3d", "Humedal herbáceo": "#3a8fa6", "Suelo desnudo": "#a89f91", "Otros": "#7c8792" };
function dibujarCobertura() {
  const q = D.quemado; if (!q) return;
  const filas = q.filas.filter(f => f.medido && f.cobertura?.length).sort((a, b) => b.total_ha - a.total_ha);
  const clases = ["Pastizal", "Bosque", "Matorral", "Cultivo", "Humedal herbáceo", "Suelo desnudo", "Otros"];
  const datos = filas.map(f => { const o = { distrito: f.distrito, total: f.total_ha };
    for (const c of clases) o[c] = 0;
    for (const c of f.cobertura) o[clases.includes(c.clase) ? c.clase : "Otros"] += c.ha;
    return o; });
  const cont = $("#g-cobertura");
  const { svg, iw, ih, m } = svgBase(cont, datos.length * 24 + 30, { t: 6, r: 60, b: 22, l: 110 });
  svg.attr("aria-label", "Cobertura dentro del área quemada por incendio");
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const y = d3.scaleBand().domain(datos.map(d => d.distrito)).range([0, ih]).padding(0.22);
  const x = d3.scaleLinear().domain([0, d3.max(datos, d => d.total) || 1]).nice().range([0, iw]);
  const pila = d3.stack().keys(clases)(datos);
  g.append("g").attr("class", "eje").call(d3.axisLeft(y).tickSize(0)).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).ticks(4).tickFormat(v => fmt.format(v) + " ha"));
  const caja = cont.parentElement, t = tooltip(caja);
  g.selectAll("g.s").data(pila).join("g").attr("class", "s").attr("fill", s => COLORES_COB[s.key])
    .selectAll("rect").data(s => s.map(v => ({ v, clase: s.key }))).join("rect")
    .attr("y", d => y(d.v.data.distrito)).attr("height", y.bandwidth()).attr("x", d => x(d.v[0])).attr("width", d => Math.max(0, x(d.v[1]) - x(d.v[0]) - (d.v[1] - d.v[0] > 0 ? 1 : 0)))
    .on("pointermove", (ev, d) => { const [cx, cy] = d3.pointer(ev, caja); ponerTip(t, caja, cx, cy, `<b>${d.v.data.distrito}</b><br>${d.clase}: <span class="num">${fmt.format(d.v[1] - d.v[0])} ha</span> (${fmt.format((d.v[1] - d.v[0]) / d.v.data.total * 100)} %)`); })
    .on("pointerleave", () => { t.hidden = true; });
  $("#clave-cobertura").replaceChildren(...clases.filter(c => d3.sum(datos, d => d[c]) > 0).map(c => el("span", {}, el("i", { class: "banda", style: `background:${COLORES_COB[c]}` }), c)));
  $("#nota-cobertura").textContent = "WorldCover casi no distingue chacras ni pastos cultivados: el 23 % de los focos cae en la Superficie Agrícola Nacional 2024 del MIDAGRI, pero solo el 1.9 % en «cultivo» de WorldCover. El fuego elige: en Chichas el pastizal es la mitad del entorno y casi tres cuartos de lo quemado.";
}

/* ---------------------------------------------------------------- temporada: récords y 2024 */
const RC = { ventana: "octubre" };
function pintarRecords() {
  const h = D.historia; if (!h) return;
  const seg = $("#ventana-rec");
  seg.replaceChildren(...Object.entries(h.records).map(([k, v]) => el("button", { type: "button", "aria-pressed": k === RC.ventana,
    text: { temporada: "Desde el 1 de julio", octubre: "Octubre", ultimos10: "Últimos 10 días" }[k] + ` (${v.etiqueta})`,
    onclick: () => { RC.ventana = k; pintarRecords(); dibujarStrip(); } })));
  const v = h.records[RC.ventana], peru = v.filas[0];
  const rec = v.filas.slice(1).filter(f => f.record && f.suficiente).map(f => f.departamento);
  const margen = peru.maximo_previo ? Math.round((peru.anio_2026 / peru.maximo_previo - 1) * 100) : null;
  $("#rec-resumen").textContent = (peru.record
    ? `Perú: récord, ${fmt.format(peru.anio_2026)} focos frente a ${fmt.format(peru.maximo_previo)} en ${peru.anio_maximo} (${signo(margen)} %). `
    : `Perú: puesto ${peru.puesto} de 15 (${fmt.format(peru.anio_2026)} focos; máximo ${fmt.format(peru.maximo_previo)} en ${peru.anio_maximo}). `) +
    (rec.length ? `Récord en ${rec.length} departamentos: ${unir(rec)}.` : "Ningún departamento marca récord en esta ventana.");
}
function dibujarStrip() {
  const h = D.historia; if (!h) return;
  const v = h.records[RC.ventana];
  const filas = [v.filas[0], ...v.filas.slice(1).filter(f => f.suficiente).sort((a, b) => (b.razon_mediana || 0) - (a.razon_mediana || 0))];
  const cont = $("#g-strip");
  const { svg, iw, ih, m } = svgBase(cont, filas.length * 22 + 34, { t: 6, r: 120, b: 26, l: 110 });
  svg.attr("aria-label", `Focos de cada año frente a la mediana 2012–2025, por departamento, ventana ${v.etiqueta}`);
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const y = d3.scaleBand().domain(filas.map(f => f.departamento)).range([0, ih]).padding(0.1);
  const lr = (f, a) => Math.log2(Math.max(0.0625, (f.por_anio[a] || 0) / Math.max(1, f.mediana)));
  const todos = filas.flatMap(f => Object.keys(f.por_anio).map(a => lr(f, a)));
  const x = d3.scaleLinear().domain([Math.max(-4, d3.min(todos)), Math.min(5, d3.max(todos))]).nice().range([0, iw]);
  g.append("g").attr("class", "rejilla").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).ticks(6).tickSize(-ih).tickFormat("")).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).ticks(6).tickFormat(t => (t >= 0 ? "×" + fmt1.format(2 ** t) : "÷" + fmt1.format(2 ** -t))));
  g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", 0).attr("y2", ih).attr("stroke", token("--ink-3")).attr("stroke-width", 1.2);
  g.append("g").attr("class", "eje").call(d3.axisLeft(y).tickSize(0)).call(a => a.select(".domain").remove()).selectAll("text").attr("font-weight", d => (d === "Perú" ? 700 : 400));
  const caja = cont.parentElement, t = tooltip(caja);
  for (const f of filas) {
    const cy = y(f.departamento) + y.bandwidth() / 2;
    const anios = Object.keys(f.por_anio).filter(a => a !== "2026");
    g.selectAll(null).data(anios).join("circle").attr("cx", a => x(lr(f, a))).attr("cy", cy).attr("r", 3.2).attr("fill", token("--hist-line")).attr("opacity", 0.75)
      .on("pointermove", (ev, a) => { const [px, py] = d3.pointer(ev, caja); ponerTip(t, caja, px, py, `<b>${f.departamento}, ${a}</b>: <span class="num">${fmt.format(f.por_anio[a])}</span> focos`); })
      .on("pointerleave", () => { t.hidden = true; });
    if (f.record) g.append("circle").attr("cx", x(lr(f, "2026"))).attr("cy", cy).attr("r", 8).attr("fill", "none").attr("stroke", token("--crit")).attr("stroke-width", 1.6);
    g.append("circle").attr("cx", x(lr(f, "2026"))).attr("cy", cy).attr("r", 5.5).attr("fill", token("--y2026")).attr("stroke", token("--panel")).attr("stroke-width", 1.5)
      .on("pointermove", ev => { const [px, py] = d3.pointer(ev, caja); ponerTip(t, caja, px, py, `<b>${f.departamento}, 2026</b>: <span class="num">${fmt.format(f.anio_2026)}</span> focos<br>Mediana 2012–2025: ${fmt.format(f.mediana)} · máximo ${fmt.format(f.maximo_previo)} (${f.anio_maximo})<br>Puesto ${f.puesto} de 15${f.record ? " · récord" : ""}`); })
      .on("pointerleave", () => { t.hidden = true; });
    g.append("text").attr("class", "etq-serie").attr("x", iw + 10).attr("y", cy + 4).attr("fill", f.record ? token("--crit") : token("--ink-2"))
      .text(`${f.razon_mediana != null ? "×" + fmt1.format(f.razon_mediana) : "—"}${f.record ? " · récord" : ` · ${f.puesto}.º`}`);
  }
}
function pintarComparacion() {
  const c = D.historia?.comparacion_2024; if (!c) return;
  const t24 = d3.sum(Object.values(c.meses["2024"])), t26 = d3.sum(Object.values(c.meses["2026"]));
  const sel = c.region.Selva || {};
  $("#comp-intro").textContent = `Con el mismo satélite y las mismas fechas (1 jul – ${fechaCorta(D.historia.hasta)}), 2024 tuvo ${fmt1.format(t24 / t26)} veces los focos de 2026. ` +
    `La diferencia está en la selva en setiembre, con la sequía amazónica de 2024: hubo ${fmt.format(sel["2024"] || 0)} focos en la selva frente a ${fmt.format(sel["2026"] || 0)}. ` +
    `2026 llegó tarde: su octubre supera al de 2024 y la temporada aún no termina.`;
  const panel = (titulo, sub, nodo) => el("div", { class: "panel grafico" }, el("h3", { text: titulo }), el("p", { class: "sub", text: sub }), nodo);
  const meses = ["7", "8", "9", "10"], nom = { 7: "jul", 8: "ago", 9: "set", 10: "oct" };
  const contM = el("div"), contR = el("div");
  const g3 = el("div", { class: "claves" },
    ...[["Incendios ≥ 1,000 ha", c.grandes["2024"].incendios_1000ha, c.grandes["2026"].incendios_1000ha],
      ["Día con más focos", c.pico["2024"].focos, c.pico["2026"].focos],
      ["Potencia radiativa, GW", c.frp_gw["2024"], c.frp_gw["2026"]],
      ["Mayor incendio, ha (huella)", c.grandes["2024"].mayor_ha, c.grandes["2026"].mayor_ha]].map(([k, a, b]) =>
      el("div", {}, el("span", { text: k }), el("b", {}, fmt.format(a), el("small", { text: `2024 · 2026: ${fmt.format(b)}` })))));
  $("#comp-paneles").replaceChildren(
    panel("Focos por mes", "S-NPP; octubre hasta el corte", contM),
    panel("Dónde", "Focos por región natural", contR),
    panel("Qué tan grandes", "Incendios agrupados con la misma regla (1 km, 48 h)", g3));
  barrasAgrupadas(contM, meses.map(mm => nom[mm]), [["2024", meses.map(mm => c.meses["2024"][mm] || 0), "--y2024"], ["2026", meses.map(mm => c.meses["2026"][mm] || 0), "--y2026"]],
    meses.map(mm => c.meses_promedio[mm] || 0));
  const regiones = ["Selva", "Sierra", "Costa"].filter(r => c.region[r]);
  barrasAgrupadas(contR, regiones, [["2024", regiones.map(r => c.region[r]["2024"] || 0), "--y2024"], ["2026", regiones.map(r => c.region[r]["2026"] || 0), "--y2026"]]);
}
function barrasAgrupadas(cont, cats, series, promedio) {
  const { svg, iw, ih, m } = svgBase(cont, 220, { t: 18, r: 8, b: 24, l: 44 });
  svg.attr("aria-label", series.map(s => `${s[0]}: ` + cats.map((c, i) => `${c} ${fmt.format(s[1][i])}`).join(", ")).join("; "));
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const x0 = d3.scaleBand().domain(cats).range([0, iw]).padding(0.25), x1 = d3.scaleBand().domain(series.map(s => s[0])).range([0, x0.bandwidth()]).padding(0.12);
  const y = d3.scaleLinear().domain([0, d3.max([...series.flatMap(s => s[1]), ...(promedio || [])])]).nice().range([ih, 0]);
  g.append("g").attr("class", "rejilla").call(d3.axisLeft(y).ticks(4).tickSize(-iw).tickFormat("")).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").call(d3.axisLeft(y).ticks(4).tickFormat(v => (v >= 1000 ? fmt.format(v / 1000) + " mil" : v))).call(a => a.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x0).tickSize(0));
  for (const [nombre, vals, color] of series)
    g.selectAll(null).data(vals).join("rect").attr("x", (_, i) => x0(cats[i]) + x1(nombre)).attr("width", x1.bandwidth())
      .attr("y", v => y(v)).attr("height", v => ih - y(v)).attr("rx", 2).attr("fill", token(color)).append("title").text((v, i) => `${nombre}, ${cats[i]}: ${fmt.format(v)}`);
  if (promedio) g.selectAll(null).data(promedio).join("line").attr("x1", (_, i) => x0(cats[i]) - 3).attr("x2", (_, i) => x0(cats[i]) + x0.bandwidth() + 3)
    .attr("y1", v => y(v)).attr("y2", v => y(v)).attr("stroke", token("--ink-3")).attr("stroke-dasharray", "3 2").attr("stroke-width", 1.5);
  const ley = g.append("g").attr("transform", "translate(0,-10)");
  [...series.map(s => [s[0], token(s[2])]), ...(promedio ? [["promedio 2012–2025", token("--ink-3")]] : [])].forEach(([t, c], i) => {
    ley.append("rect").attr("x", i * 74).attr("y", -7).attr("width", 9).attr("height", 9).attr("rx", 2).attr("fill", c);
    ley.append("text").attr("class", "etq-serie").attr("x", i * 74 + 13).attr("y", 1).attr("fill", token("--ink-2")).text(t);
  });
}

/* ---------------------------------------------------------------- respuesta: acciones y normas */
function pintarAcciones() {
  const a = D.contexto.acciones; if (!a?.length) return;
  $("#acciones-intro").textContent = `${a.length} acciones registradas por el COEN-INDECI en el incendio de la comunidad nativa Tsyapo, del inicio a la emergencia: ` +
    `${a.filter(x => x.nivel === "Nacional").length} del nivel nacional, ${a.filter(x => x.nivel === "Regional").length} regionales y ${a.filter(x => x.nivel === "Local").length} locales. ` +
    `Tomadas del Reporte complementario N.º 14680 (21 oct); cada fila se cotejó con el reporte.`;
  $("#lista-acciones").replaceChildren(...a.map(x => el("li", {},
    el("span", { class: "fecha", text: fechaCorta(x.fecha) }), el("span", { class: "nivel " + x.nivel, text: x.nivel }),
    el("span", { class: "txt" }, el("span", { class: "ent", text: x.entidad + ". " }), x.accion))));
  const f = a[0];
  $("#lista-acciones").after(el("p", { class: "nota-chica" }, "Fuente: ", el("a", { href: f.url, target: "_blank", rel: "noopener", text: f.fuente }), "."));
}
function dibujarAcciones() {
  const a = D.contexto.acciones; if (!a?.length) return;
  const cont = $("#g-acciones");
  const dias = d3.timeDays(new Date(a[0].fecha + "T00:00"), d3.timeDay.offset(new Date(a[a.length - 1].fecha + "T00:00"), 1)).map(d => d3.timeFormat("%Y-%m-%d")(d));
  // focos por día en el distrito de Río Tambo (los tres satélites)
  const idx = D.focos.distritos.findIndex(r => r[1] === "Río Tambo" && r[2] === "Satipo");
  const corte = new Date(D.resumen.corte_local.replace(" ", "T"));
  const cuenta = Object.fromEntries(dias.map(d => [d, 0]));
  if (idx >= 0) for (const f of D.focos) if (f.d === idx) { const t = d3.timeFormat("%Y-%m-%d")(new Date(corte.getTime() - f.h * 3600e3)); if (t in cuenta) cuenta[t]++; }
  const niveles = ["Nacional", "Regional", "Local"];
  const { svg, iw, ih, m } = svgBase(cont, 210, { t: 10, r: 10, b: 24, l: 70 });
  svg.attr("aria-label", "Focos por día en Río Tambo y acciones del Estado por nivel de gobierno");
  const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
  const x = d3.scaleBand().domain(dias).range([0, iw]).padding(0.2);
  const hb = ih * 0.42, yb = d3.scaleLinear().domain([0, d3.max(Object.values(cuenta)) || 1]).range([ih, ih - hb]);
  const yl = d3.scaleBand().domain(niveles).range([0, ih - hb - 10]).padding(0.2);
  g.selectAll("rect.f").data(dias).join("rect").attr("class", "f").attr("x", d => x(d)).attr("width", x.bandwidth())
    .attr("y", d => yb(cuenta[d])).attr("height", d => ih - yb(cuenta[d])).attr("rx", 2).attr("fill", token("--fire-old"))
    .append("title").text(d => `${fechaCorta(d)}: ${cuenta[d]} focos en Río Tambo`);
  g.append("text").attr("class", "etq-serie").attr("x", -8).attr("y", ih - hb / 2).attr("text-anchor", "end").attr("fill", token("--ink-3")).text("Focos");
  g.append("g").attr("class", "eje").call(d3.axisLeft(yl).tickSize(0)).call(s => s.select(".domain").remove());
  g.append("g").attr("class", "eje").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickValues(dias.filter((_, i) => i % 2 === 0)).tickFormat(fechaCorta));
  const color = { Nacional: token("--accent"), Regional: token("--warn"), Local: token("--anp") };
  const pila = {};
  const caja = cont.parentElement, t = tooltip(caja);
  g.selectAll("circle").data(a).join("circle")
    .attr("cx", d => { const k = d.fecha + d.nivel; pila[k] = (pila[k] || 0) + 1; return x(d.fecha) + x.bandwidth() / 2 + (pila[k] - 1) * 5 - 2; })
    .attr("cy", d => yl(d.nivel) + yl.bandwidth() / 2).attr("r", 5).attr("fill", d => color[d.nivel]).attr("stroke", token("--panel")).attr("stroke-width", 1.2)
    .on("pointermove", (ev, d) => { const [cx, cy] = d3.pointer(ev, caja); ponerTip(t, caja, cx, cy, `<b>${fechaCorta(d.fecha)} · ${d.entidad}</b><br>${d.accion}`); })
    .on("pointerleave", () => { t.hidden = true; });
  $("#clave-acciones").replaceChildren(...niveles.map(n => el("span", {}, el("i", { class: "banda", style: `background:${color[n]}` }), `Acción del nivel ${n.toLowerCase()}`)),
    el("span", {}, el("i", { class: "banda", style: `background:${token("--fire-old")}` }), "Focos por día en el distrito"));
}
function pintarNormas() {
  const n = D.contexto.normas; if (!n) return;
  $("#normas-intro").textContent = `Políticas, planes y leyes nacionales sobre incendios forestales, bosques y agricultura, revisadas el ${fechaCorta(n.revisado)} de 2026. La barra muestra los años desde la última actualización publicada.`;
  const hoy = new Date(n.revisado + "T00:00");
  const anios = s => (hoy - new Date((s.length === 4 ? s + "-07-01" : s.length === 7 ? s + "-15" : s) + "T00:00")) / (365.25 * 864e5);
  const tb = encabezado($("#tabla-normas"), ["Norma", "Entidad", "Aprobada", "Última actualización", "Estado", "Fuente"]);
  for (const r of n.normas) {
    const a = anios(r.actualizada);
    tb.append(filaTabla([
      el("span", {}, el("b", { text: r.norma }), el("br"), el("span", { class: "tenue", text: r.dispositivo }), el("br"), el("span", { class: "nota-chica", text: r.que_hace })),
      td(r.entidad), td(fechaNorma(r.aprobada)),
      el("span", {}, el("i", { class: "antig", style: `width:${Math.min(84, a * 6)}px` }), fechaNorma(r.actualizada), el("br"), el("span", { class: "tenue", text: a < 1 ? "hace meses" : `hace ${fmt.format(Math.floor(a))} ${Math.floor(a) === 1 ? "año" : "años"}` })),
      td(r.estado), el("span", {}, ...r.urls.flatMap((u, i) => [i ? " · " : null, el("a", { href: u, target: "_blank", rel: "noopener", text: new URL(u).hostname.replace("www.", "") })]),
        r.verificado ? null : el("span", { class: "verif" }, el("br"), "fuente secundaria o sin confirmar")),
    ].map(c => (c instanceof Node && c.tagName === "TD" ? c : el("td", { style: "white-space:normal;text-align:left;vertical-align:top" }, c)))));
  }
  $("#normas-pie").textContent = "Se excluyeron dos registros cuya fuente no se pudo confirmar. El estado de los proyectos de ley puede haber cambiado después de la fecha de revisión.";
}
function fechaNorma(s) {
  if (s.length === 4) return s;
  if (s.length === 7) return `${MESES[+s.slice(5, 7) - 1]} ${s.slice(0, 4)}`;
  return `${fechaCorta(s)} ${s.slice(0, 4)}`;
}

/* ---------------------------------------------------------------- créditos */
function pintarCreditos() {
  const c = D.contexto.creditos; if (!c) return;
  const al = [...c.alumnos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  $("#creditos-intro").replaceChildren(`Este tablero integra el trabajo de ${al.length} alumnas y alumnos del curso de Data Science con Python, que en la sesión 14 analizaron los incendios de 2026 desde distintas preguntas. `,
    el("a", { href: c.issue, target: "_blank", rel: "noopener", text: "Entregas en GitHub" }), ". Cada tarjeta dice qué parte de su trabajo quedó en el tablero.");
  $("#lista-creditos").replaceChildren(...al.map(a => el("li", {},
    el("span", { class: "reto", text: a.reto }), el("span", { class: "nombre", text: a.nombre }), el("span", { class: "aporte", text: a.aporte }),
    el("span", { class: "enlaces" },
      a.repo ? el("a", { href: a.repo, target: "_blank", rel: "noopener", text: "Repositorio" }) : el("span", { class: "tenue", text: "Repositorio privado" }),
      a.web ? el("a", { href: a.web, target: "_blank", rel: "noopener", text: "Su página" }) : null,
      el("a", { href: `https://github.com/${a.github}`, target: "_blank", rel: "noopener", text: "@" + a.github })))));
}
