"use strict";

// Iconos sencillos (trazos de 24x24). Se eligen con la etiqueta wallo.icono.
const ICONOS = {
  rayo: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  casa: '<path d="M3 11 12 3l9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
  grafica: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  nube: '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
  archivo: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/>',
  herramienta: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  camara: '<path d="M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="4"/>',
  musica: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  libro: '<path d="M4 4h6a3 3 0 0 1 3 3v14a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v14a2 2 0 0 1 2-2h7z"/>',
  servidor: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 7h.01M7 18h.01"/>',
  euro: '<path d="M18 6a7 7 0 1 0 0 12M4 10h10M4 14h10"/>',
  calendario: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
};

const ESTADOS = { activa: "Activa", despertando: "Despertando", arrancando: "Arrancando", dormida: "Dormida" };

const $ = (s, el = document) => el.querySelector(s);

function tam(bytes) {
  if (bytes == null) return "—";
  if (bytes === 0) return "0 MB";
  return `${(bytes / 1048576).toLocaleString("es-ES", { maximumFractionDigits: bytes < 10485760 ? 1 : 0 })} MB`;
}

function textoDormir(h) {
  if (h.dormir_tras === 0) return "Nunca";
  if (h.estado === "dormida") return `Tras ${h.dormir_tras} min`;
  const faltan = Math.max(0, h.dormir_tras - (h.minutos_inactiva ?? 0));
  return faltan < 1 ? "En < 1 min" : `En ${Math.ceil(faltan)} min`;
}

function urlHerramienta(h) {
  // Mismo nombre o IP con el que se ha abierto el portal, en el puerto de la herramienta
  return `${location.protocol}//${location.hostname}:${h.puerto}/`;
}

// ---------------------------------------------------------------- tema
function aplicarTema(t) {
  if (t === "claro" || t === "oscuro") document.documentElement.dataset.tema = t;
  else delete document.documentElement.dataset.tema;
  document.querySelectorAll(".tema button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tema === t)));
  try { localStorage.setItem("wallo-tema", t); } catch (_) {}
}
let temaGuardado = "sistema";
try { temaGuardado = localStorage.getItem("wallo-tema") || "sistema"; } catch (_) {}
aplicarTema(temaGuardado);
document.querySelectorAll(".tema button").forEach((b) => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));

// --------------------------------------------------------------- datos
let temporizador;

async function cargar() {
  clearTimeout(temporizador);
  let datos;
  try {
    const r = await fetch("api/herramientas", { cache: "no-store" });
    if (!r.ok) throw new Error(`Error ${r.status}`);
    datos = await r.json();
    $("#aviso").hidden = true;
  } catch (e) {
    $("#aviso").textContent = `No se puede conectar con el portal (${e.message}). Reintentando…`;
    $("#aviso").hidden = false;
    temporizador = setTimeout(cargar, 5000);
    return;
  }
  pintar(datos);
  const algunaCambiando = datos.herramientas.some((h) => h.estado === "despertando" || h.estado === "arrancando");
  // Solo se consulta a menudo mientras algo está despertando; si no, cada 30 s y solo con la pestaña visible
  temporizador = setTimeout(cargar, algunaCambiando ? 1500 : 30000);
}

function pintar({ portal, herramientas }) {
  const despiertas = herramientas.filter((h) => h.estado !== "dormida");
  const memoria = herramientas.reduce((a, h) => a + (h.memoria || 0), 0) + (portal.memoria || 0);
  $("#resumen").textContent = herramientas.length
    ? `${herramientas.length} herramienta${herramientas.length === 1 ? "" : "s"} · ${despiertas.length} despierta${despiertas.length === 1 ? "" : "s"} · ${tam(memoria)} en uso`
    : "Sin herramientas";
  $("#memoria-portal").textContent = `Wall-O v${portal.version} · ${tam(portal.memoria)}`;
  $("#vacio").hidden = herramientas.length > 0;

  const lista = $("#lista");
  const vistas = new Set();
  for (const h of herramientas) {
    vistas.add(h.contenedor);
    let el = lista.querySelector(`[data-contenedor="${CSS.escape(h.contenedor)}"]`);
    if (!el) {
      el = $("#plantilla").content.firstElementChild.cloneNode(true);
      el.dataset.contenedor = h.contenedor;
      $(".conmutar", el).addEventListener("click", () => conmutar(el));
      lista.appendChild(el);
    }
    el._h = h;
    const icono = ICONOS[h.icono];
    $(".icono", el).innerHTML = icono ? `<svg viewBox="0 0 24 24">${icono}</svg>` : "";
    if (!icono) $(".icono", el).textContent = (h.icono || h.nombre).slice(0, 1).toUpperCase();
    $(".nombre", el).textContent = h.nombre;
    $(".version", el).textContent = h.version ? `v${h.version}` : "";
    $(".descripcion", el).textContent = h.descripcion;
    $(".descripcion", el).hidden = !h.descripcion;
    $(".estado", el).dataset.estado = h.estado;
    $(".estado span", el).textContent = ESTADOS[h.estado] || h.estado;
    $(".memoria", el).textContent = h.estado === "dormida" ? "0 MB" : tam(h.memoria);
    $(".dormir", el).textContent = textoDormir(h);
    $(".puerto", el).textContent = h.puerto;
    $(".error", el).textContent = h.error || "";
    $(".error", el).hidden = !h.error;
    const abrir = $(".abrir", el);
    abrir.href = urlHerramienta(h);
    abrir.title = h.estado === "dormida" ? "Se despierta sola al abrirla" : "";
    const boton = $(".conmutar", el);
    boton.textContent = h.estado === "dormida" ? "Despertar" : "Dormir";
    boton.disabled = h.estado === "despertando" || h.estado === "arrancando";
  }
  lista.querySelectorAll("[data-contenedor]").forEach((el) => vistas.has(el.dataset.contenedor) || el.remove());
}

async function conmutar(el) {
  const h = el._h;
  const accion = h.estado === "dormida" ? "despertar" : "dormir";
  const boton = $(".conmutar", el);
  boton.disabled = true;
  boton.textContent = accion === "dormir" ? "Durmiendo…" : "Despertando…";
  try {
    await fetch(`api/herramientas/${encodeURIComponent(h.contenedor)}/${accion}`, { method: "POST" });
  } finally {
    cargar();
  }
}

document.addEventListener("visibilitychange", () => { if (!document.hidden) cargar(); else clearTimeout(temporizador); });
cargar();
