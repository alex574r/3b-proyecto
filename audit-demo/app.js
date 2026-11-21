const main = document.querySelector('main');
const menu = document.querySelector('#menu');
const dialog = document.querySelector('#dialogo');

const opcionesUrl = new URLSearchParams(location.search);
const demo = opcionesUrl.get('modo') === 'demo';
const integrado = location.pathname.startsWith('/portal/');
const api = new URL(integrado ? location.origin : 'https://api.jamp.digital');
const prueba = opcionesUrl.get('api');
if (prueba && !integrado) {
  const local = new URL(prueba);
  if (['localhost', '127.0.0.1'].includes(local.hostname) && local.protocol === 'http:') api.href = local.origin;
}
document.querySelector('#modo').textContent = demo ? 'Demostración' : 'API de capturas';
const enlaceModo = document.querySelector('#cambiar-modo');
const otroModo = new URL(location.href);
if (demo) otroModo.searchParams.delete('modo'); else otroModo.searchParams.set('modo', 'demo');
otroModo.hash = 'resumen';
enlaceModo.href = otroModo;
enlaceModo.textContent = demo ? 'Abrir operación' : 'Ver demo';
let credencial = '';
let errorApi = '';
let consultando = false;
let vistaCargada = null;
const fotosReales = new Map();

async function peticion(path, opciones = {}) {
  const r = await fetch(new URL(path, api), {
    ...opciones, cache: 'no-store', credentials: 'omit', redirect: 'error',
    headers: { 'X-Audit-Token': credencial, ...opciones.headers },
  });
  if (!r.ok) {
    const detalle = await r.json().catch(() => ({}));
    throw new Error(detalle.error || `HTTP ${r.status}`);
  }
  return r;
}

function limpiarFotos() {
  vistaCargada = null;
  for (const url of fotosReales.values()) URL.revokeObjectURL(url);
  fotosReales.clear();
}

async function cargarFotos(caso) {
  const version = caso.capture_id + caso.revision;
  if (vistaCargada === version) return;
  limpiarFotos();
  vistaCargada = version;
  for (const [clave, campo] of Object.entries({fachada:'facade', producto:'product', etiqueta:'shelf'})) {
    if (!caso[campo + '_file']) continue;
    try {
      const r = await peticion(`/auditoria/imagenes/${caso.capture_id}_${campo}.jpg`);
      const blob = await r.blob();
      if (vistaCargada !== version) return;
      fotosReales.set(clave, URL.createObjectURL(blob));
    } catch {
      if (vistaCargada !== version) return;
    }
  }
  if (vistaCargada === version) render();
}

function accesoHtml() {
  return `<section class="panel stack"><h1>Conectar con la API</h1>
    <p>Introduce la credencial de auditoría del equipo para consultar las capturas.</p>
    <form id="acceso" class="stack"><label class="field">Credencial de auditoría
      <input type="password" name="token" autocomplete="off" required></label>
      <button class="button primary">Conectar</button></form>
    <p role="status">${escapeHtml(errorApi)}</p></section>`;
}

const estados = {
  revision_manual: { plural: 'Revisión manual', singular: 'Revisión manual', tono: 'pending', icono: 'clock' },
  aprobada: { plural: 'Aprobadas', singular: 'Aprobada', tono: 'success', icono: 'check' },
  rechazada: { plural: 'No aprobadas', singular: 'Rechazada', tono: 'danger', icono: 'x' },
};
const evidencias = {
  fachada: { nombre: 'Fachada', icono: 'store' },
  producto: { nombre: 'Producto', icono: 'package' },
  etiqueta: { nombre: 'Etiqueta', icono: 'tag' },
};
const validaciones = {
  tienda_fachada: 'Fachada', producto: 'Producto', codigo_barras: 'Código de barras', evidencia_precio: 'Evidencia de precio',
};
const iconos = new Set(['clock', 'check', 'x', 'store', 'package', 'tag', 'chart', 'inbox', 'shield', 'alert', 'chevron']);
const motivosAuditoria = ['Evidencia no verificable', 'Producto no coincide', 'Fachada incorrecta', 'Precio no verificable', 'Otro'];
const defaultFilters = { query: '', cadena: '', motivo: '', desde: 0, hasta: 100 };
const storageKey = 'validat3b-auditoria-demo-v1';
const resumen = { total: 240, aprobada: 170, revision_manual: 32, rechazada: 38 };
const currency = new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' });
const hour = new Intl.DateTimeFormat('es-MX', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'America/Mexico_City' });

let casos = [];
let filtros = { ...defaultFilters };
let resoluciones = demo ? cargarResoluciones() : new Map();
let fotoActiva = 'etiqueta';
let zoomEnDetalle = false;
let carga = 'cargando';
let detalleAnterior = null;
let ultimaRuta = '';

function escapeHtml(value) {
  const chars = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(value ?? '').replace(/[&<>"']/g, char => chars[char]);
}

function icono(nombre) {
  return iconos.has(nombre) ? `<img class="icon" src="assets/${nombre}.svg" alt="">` : '';
}

function cargarResoluciones() {
  try {
    const data = JSON.parse(sessionStorage.getItem(storageKey)) ?? {};
    return new Map(Object.entries(data).filter(([id, decision]) =>
      /^CAP-[0-9]+$/.test(id) && ['aprobada', 'rechazada'].includes(decision?.estado) &&
      typeof decision.hora === 'string' && typeof decision.motivo === 'string' && typeof decision.nota === 'string'));
  } catch {
    return new Map();
  }
}

async function guardarResolucion(caso, decision) {
  if (estadoActual(caso) !== 'revision_manual') return;
  if (!demo) {
    const submit = dialog.querySelector('[type=submit]');
    if (submit.disabled) return;
    submit.disabled = true;
    try {
      const r = await peticion(`/auditoria/capturas/${caso.capture_id}/resolucion`, {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({...decision, revision:caso.revision})});
      resoluciones.set(caso.capture_id, await r.json());
      cerrarDialogo();
      render();
    } catch (e) {
      let aviso = dialog.querySelector('[role=alert]');
      if (!aviso) { aviso = document.createElement('p'); aviso.setAttribute('role','alert'); dialog.append(aviso); }
      aviso.textContent = e.message;
    } finally { submit.disabled = false; }
    return;
  }
  resoluciones.set(caso.capture_id, { ...decision, hora: hour.format(new Date()) });
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(Object.fromEntries(resoluciones)));
  } catch {
    // La navegación sigue funcionando cuando el navegador bloquea el almacenamiento.
  }
  cerrarDialogo();
  render();
  main.querySelector('.notice')?.focus();
}

function ruta() {
  const [pagina, valor] = location.hash.slice(1).split('/');
  if (pagina === 'bandeja') {
    return { pagina, estado: Object.hasOwn(estados, valor) ? valor : 'revision_manual' };
  }
  if (pagina === 'captura') return { pagina, id: valor };
  return { pagina: 'resumen' };
}

function estadoActual(caso) {
  return resoluciones.get(caso.capture_id)?.estado ?? caso.decision_esperada;
}

function motivoVisible(caso) {
  return resoluciones.get(caso.capture_id)?.motivo || caso.titulo;
}

function totales() {
  if (!demo) {
    const total = {total:casos.length, aprobada:0, rechazada:0, revision_manual:0};
    for (const caso of casos) total[estadoActual(caso)]++;
    return total;
  }
  const total = { ...resumen };
  for (const caso of casos) {
    const estado = estadoActual(caso);
    if (estado !== caso.decision_esperada) {
      total[caso.decision_esperada]--;
      total[estado]++;
    }
  }
  return total;
}

function normalizar(value) {
  return value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('es-MX').trim();
}

function aplicarFiltros(estado) {
  const query = normalizar(filtros.query);
  return casos.filter(caso => estadoActual(caso) === estado &&
    (!query || [caso.capture_id, caso.product_name].some(value => normalizar(value).includes(query))) &&
    (!filtros.cadena || filtros.cadena === caso.capture_store_name) &&
    (!filtros.motivo || filtros.motivo === motivoVisible(caso)) &&
    caso.confidence_score * 100 >= filtros.desde && caso.confidence_score * 100 <= filtros.hasta);
}

function rutaBandeja(estado) {
  return `#bandeja/${estado}`;
}

function enlaceNav(texto, hash, pictograma, actual, seccion = false) {
  return `<a href="${hash}" ${actual ? 'aria-current="page"' : seccion ? 'data-section="actual"' : ''}>${icono(pictograma)}${texto}</a>`;
}

function renderNav(destino, caso) {
  const estado = caso ? estadoActual(caso) : destino.estado;
  menu.innerHTML = `
    <div class="nav-group">
      <p class="micro">Operación</p>
      ${enlaceNav('Resumen', '#resumen', 'chart', destino.pagina === 'resumen')}
      ${enlaceNav('Bandeja', rutaBandeja('revision_manual'), 'inbox', false, destino.pagina !== 'resumen')}
    </div>
    <div class="nav-group">
      <p class="micro">Estados</p>
      ${Object.entries(estados).map(([clave, datos]) =>
        enlaceNav(datos.plural, rutaBandeja(clave), datos.icono, destino.pagina === 'bandeja' && estado === clave, estado === clave)).join('')}
    </div>`;
}

function badge(estado) {
  const vista = estados[estado];
  return `<span class="badge ${vista.tono}">${icono(vista.icono)} ${vista.singular}</span>`;
}

function resumenHtml() {
  const total = totales();
  const metrica = (nombre, cantidad, detalle) => `
    <div class="metric panel"><dt>${nombre}</dt><dd><strong>${cantidad}</strong><small>${detalle}</small></dd></div>`;
  const porcentaje = cantidad => `${(total.total ? cantidad * 100 / total.total : 0).toFixed(1)} % de las capturas`;
  return `<div class="stack">
    <section class="banner">
      <div class="banner-copy">
        <span class="badge">${demo ? 'Últimos 7 días' : 'Registros del servidor'}</span>
        <h1>Resumen</h1>
        <p>Capturas de precio y revisión de evidencias en tienda.</p>
      </div>
      <div class="banner-art" aria-hidden="true">
        <img class="halo" src="assets/halo.svg" alt=""><img class="aro" src="assets/aro.svg" alt="">
        <img class="marca" src="assets/logo.png" alt="">
      </div>
    </section>
    <dl class="metrics">
      ${metrica('Capturas totales', total.total, demo ? 'Periodo de demostración' : 'Capturas registradas')}
      ${Object.entries(estados).map(([clave, datos]) => metrica(datos.plural, total[clave], porcentaje(total[clave]))).join('')}
    </dl>
    <div class="summary-grid">
      <section class="panel">
        <div class="panel-header"><h2>Incidencias por categoría</h2>${icono('chart')}</div>
        <p class="muted">Una captura puede registrar más de una incidencia.</p>
        <div class="incidents">
          ${(demo ? [['Identidad',26],['Evidencia',41],['Precio',16]] :
            Object.entries(validaciones).map(([k,n]) => [n,casos.filter(c => c.validaciones[k]==='falla').length])).map(([nombre, valor]) =>
            `<div><span>${nombre}<span>${valor}</span></span><progress max="${demo ? 41 : Math.max(1,casos.length)}" value="${valor}" aria-label="${nombre}"></progress></div>`).join('')}
        </div>
      </section>
      <div class="stack">
        <section class="panel">
          <p class="micro eyebrow">${icono('shield')} Meta de calidad</p>
          <p class="goal">≥ 97 %</p>
          <h3>Precisión de las aprobaciones</h3>
          <small>Aprobaciones válidas sobre el total de aprobaciones auditadas.</small>
        </section>
        <section class="panel">
          <div class="panel-header"><h3>Confianza promedio del motor</h3><strong class="percent"> ${demo ? '88.4 %' : casos.length ? (casos.reduce((n,c) => n+c.confidence_score,0)*100/casos.length).toFixed(1)+' %' : '—'}</strong></div>
          <small>Promedio de confidence_score en el periodo.</small>
        </section>
      </div>
    </div>
    <section class="panel spaced list-foot">
      <div><h3>Capturas pendientes de revisión</h3><p class="muted">Consulta los motivos y abre la evidencia de cada captura.</p></div>
      <a class="button primary" href="${rutaBandeja('revision_manual')}">Abrir bandeja</a>
    </section>
  </div>`;
}

function campoBoton(etiqueta, valor, accion) {
  return `<button type="button" class="field" data-action="${accion}" aria-haspopup="dialog">
    <span class="micro">${etiqueta}</span><strong>${escapeHtml(valor)}</strong>
  </button>`;
}

function estadoBandeja(estado) {
  if (carga === 'cargando') {
    return `<section class="empty panel list" role="status" aria-label="Cargando capturas"><div class="loader" aria-hidden="true"></div><h2>Cargando capturas…</h2></section>`;
  }
  if (carga === 'error') {
    return `<section class="empty panel list" role="alert">${icono('alert')}<h2>No se pudo cargar la bandeja</h2>
      <p class="muted">Comprueba tu conexión y vuelve a intentarlo.</p>
      <button class="button primary" data-action="reintentar">Reintentar</button></section>`;
  }
  const visibles = aplicarFiltros(estado);
  const filas = visibles.map(caso => `<tr data-id="${caso.capture_id}">
    <td><a class="table-link mono nowrap" href="#captura/${caso.capture_id}">${caso.capture_id}</a></td>
    <td><strong>${escapeHtml(caso.product_name)}</strong></td>
    <td class="muted">${escapeHtml(caso.capture_store_name)}</td>
    <td><strong>${escapeHtml(motivoVisible(caso))}</strong></td>
    <td class="mono nowrap">${Math.round(caso.confidence_score * 100)} %</td>
    <td class="muted nowrap">${demo ? 'Hoy · ' : ''}${escapeHtml(caso.recibida)}</td><td>${icono('chevron')}</td>
  </tr>`).join('');
  const coincidencias = `${visibles.length} ${visibles.length === 1 ? 'captura' : 'capturas'} en vista`;
  return `<section class="panel list" aria-label="Resultados de búsqueda">
    <div class="toolbar">
      ${campoBoton('Buscar por captura o producto', filtros.query || 'ID de captura o producto', 'buscar')}
      ${campoBoton('Cadena', filtros.cadena || 'Todas ⌄', 'filtros')}
      ${campoBoton('Motivo', filtros.motivo || 'Todos ⌄', 'filtros')}
      ${campoBoton('Confianza', `${filtros.desde} % a ${filtros.hasta} % ⌄`, 'filtros')}
      <button class="button subtle" data-action="limpiar">Limpiar</button>
    </div>
    <div class="list-head spaced"><small role="status">${coincidencias}</small><span class="badge unknown">${demo ? 'Datos de demostración' : 'Datos de la API'}</span></div>
    ${filas ? `<div class="table-wrap"><table aria-label="Capturas">
      <thead><tr>${['Captura', 'Producto', 'Cadena', 'Motivo', 'Confianza', 'Recibida'].map(nombre => `<th scope="col">${nombre}</th>`).join('')}<th scope="col" aria-label="Abrir captura"></th></tr></thead>
      <tbody>${filas}</tbody></table></div>` : `<div class="empty">${icono('inbox')}<h2>Sin coincidencias</h2>
      <p class="muted">Prueba otra búsqueda o limpia los filtros.</p>
      <button class="button" data-action="limpiar">Limpiar filtros</button></div>`}
  </section>
  <div class="spaced list-foot"><small>Selecciona una fila para abrir el detalle.</small>
    <button class="button subtle" data-action="${demo ? 'simular-red' : 'reintentar'}">${demo ? 'Simular error de red' : 'Actualizar'}</button></div>`;
}

function bandejaHtml(estado) {
  const total = totales();
  return `<header class="page-header">
    <div><p class="micro eyebrow">Gestión y auditoría</p><h1>Bandeja de capturas</h1>
    <p class="muted">Revisa los resultados y abre una captura para inspeccionar su evidencia.</p></div>
    <a href="#resumen" class="button">Ver resumen</a>
  </header>
  <nav class="tabs" aria-label="Estado de la captura">
    ${Object.entries(estados).map(([clave, datos]) =>
      `<a class="button" href="${rutaBandeja(clave)}" ${estado === clave ? 'aria-current="page"' : ''}>${datos.plural} · ${total[clave]}</a>`).join('')}
  </nav>
  ${estadoBandeja(estado)}`;
}

function formatoPrecio(valor) {
  return valor == null ? '—' : currency.format(valor);
}

function marcado(caso, clave) {
  const { nombre } = evidencias[clave];
  if (!demo) {
    const url = fotosReales.get(clave);
    return url ? `<img src="${url}" alt="Foto de ${nombre.toLowerCase()}">` : '<span>Foto pendiente o no disponible</span>';
  }
  const reflejo = caso.reason_code === 'EVIDENCIA_AMBIGUA' && clave === 'etiqueta';
  return `<img class="${reflejo ? 'foto-con-reflejo' : ''}" src="demo-data/${clave}.png" alt="Foto de ${nombre.toLowerCase()}">
    ${reflejo ? '<span class="reflejo" aria-hidden="true"></span>' : ''}
    <span class="mark ${clave}" aria-hidden="true"></span>`;
}

function permiteZoomEnDetalle(caso) {
  return fotoActiva === 'etiqueta' && ['CAP-000145', 'CAP-000146'].includes(caso.capture_id);
}

function evidenciaHtml(caso) {
  const tipo = evidencias[fotoActiva];
  const inline = permiteZoomEnDetalle(caso);
  return `<section class="panel stack">
    <div class="panel-header">
      <div><h2>Evidencia de captura</h2><p class="muted">${demo ? 'Revisa el área marcada en la foto.' : 'Fotografías originales de esta captura.'}</p></div>
      ${inline
        ? `<button class="button" data-action="zoom-detalle" aria-pressed="${zoomEnDetalle}">${zoomEnDetalle ? 'Volver a 1×' : 'Ampliar 2×'}</button>`
        : `<button class="button" data-action="ampliar" aria-haspopup="dialog">Ampliar 2×</button>`}
    </div>
    <button type="button" class="photo ${zoomEnDetalle ? 'photo--zoom' : ''}" data-action="ampliar" aria-label="Ampliar 2× la foto de ${tipo.nombre.toLowerCase()}" aria-haspopup="dialog">
      ${marcado(caso, fotoActiva)}
    </button>
    <div class="thumbs" aria-label="Elegir evidencia">
      ${Object.entries(evidencias).map(([clave, { nombre, icono: pictograma }]) => `
        <button class="button thumbnail" data-photo="${clave}" aria-pressed="${clave === fotoActiva}">
          ${demo || fotosReales.has(clave) ? `<img src="${demo ? 'demo-data/'+clave+'.png' : fotosReales.get(clave)}" alt="">` : ''}<span>${icono(pictograma)}${nombre}</span>
        </button>`).join('')}
    </div>
    <dl class="facts">${[
      ['Producto esperado', caso.product_name], ['Marca', caso.capture_brand],
      ['Gramaje', `${caso.unit_quantity_product} ${caso.unit_product}`], ['Cadena', caso.capture_store_name],
    ].map(([titulo, valor]) => `<div><dt class="micro">${titulo}</dt><dd>${escapeHtml(valor)}</dd></div>`).join('')}</dl>
    <div class="comparison">
      <h3>Capturado vs. Detectado</h3>
      <table aria-label="Datos capturados y detectados">
        <thead><tr><th scope="col">Campo</th><th scope="col">Capturado</th><th scope="col">Detectado</th></tr></thead>
        <tbody>
          ${[['Precio (MXN)', formatoPrecio(caso.capture_price), formatoPrecio(caso.precio_detectado)],
            ['Código de barras', caso.capture_barcode, caso.codigo_barras_detectado ?? '—']].map(([campo, capturado, detectado]) =>
            `<tr><td><strong>${campo}</strong></td><td class="mono">${escapeHtml(capturado)}</td><td class="mono">${escapeHtml(detectado)}</td></tr>`).join('')}
        </tbody>
      </table>
      <small>Tipo de precio</small> <span class="badge ${caso.precio_detectado != null ? 'success' : 'unknown'}">${demo ? (caso.precio_detectado != null ? 'Regular' : 'No evaluable') : (caso.precio_descuento != null ? 'Promoción' : 'Sin promoción confirmada')}</span>
    </div>
  </section>`;
}

function dictamenHtml(caso) {
  const estado = estados[caso.decision_esperada];
  const chips = { ok: ['success', '✓ OK'], falla: ['danger', '× Falla'], no_evaluable: ['unknown', '— No evaluable'] };
  return `<section class="panel stack">
    <div class="panel-header"><h3>Dictamen original del motor</h3>${icono('shield')}</div>
    <div class="verdict-head">
      <div>${badge(caso.decision_esperada)}<p class="mono muted">${escapeHtml(caso.reason_code)}</p></div>
      <div><p class="micro">Confianza del motor</p><strong class="percent ${estado.tono}">${Math.round(caso.confidence_score * 100)} %</strong></div>
    </div>
    <dl class="validation">${Object.entries(validaciones).map(([clave, nombre]) => {
      const [tono, texto] = chips[caso.validaciones[clave]] ?? chips.no_evaluable;
      return `<div><dt>${nombre}</dt><dd class="badge ${tono}">${texto}</dd></div>`;
    }).join('')}</dl>
    <div><h3>Explicación</h3><p class="muted">${escapeHtml(caso.explicacion)}</p></div>
  </section>`;
}

function auditoriaHtml(caso) {
  const decision = resoluciones.get(caso.capture_id);
  const sePuedeResolver = estadoActual(caso) === 'revision_manual';
  return `<section class="panel stack">
    <div class="panel-header"><h3>Resolución de auditoría</h3>
      ${decision ? badge(decision.estado) : sePuedeResolver ? '<span class="badge pending">Pendiente</span>' : '<span class="badge unknown">Sin intervención</span>'}</div>
    <p class="muted">${decision
      ? decision.estado === 'aprobada' ? 'Confirmación registrada por Operaciones 3B.' : escapeHtml(`${decision.motivo} · ${decision.nota}`)
      : sePuedeResolver ? 'Registra el resultado de la inspección.' : 'El dictamen quedó registrado por el motor.'}</p>
    ${sePuedeResolver ? `<div class="split-buttons">
        <button class="button" data-action="rechazar" aria-haspopup="dialog">Rechazar</button>
        <button class="button primary" data-action="aprobar" aria-haspopup="dialog">Aprobar</button>
      </div>` : ''}
  </section>
  <section class="panel stack"><h3>Historial</h3><ol class="timeline">
    ${decision ? `<li>${icono(estados[decision.estado].icono)}<div>
      <div class="mono muted">${escapeHtml(decision.hora)} · Operaciones 3B</div>
      <div>${decision.estado === 'aprobada' ? 'Aprobó la captura' : `Rechazó la captura · ${escapeHtml(decision.motivo)}`}</div>
      ${decision.nota ? `<small>${escapeHtml(decision.nota)}</small>` : ''}
    </div></li>` : ''}
    <li>${icono('clock')}<div><p class="mono muted">${escapeHtml(caso.recibida)} · Motor Validat3B</p>
      <p>Dictamen original · ${estados[caso.decision_esperada].singular}</p><small class="mono">${escapeHtml(caso.reason_code)}</small></div></li>
  </ol></section>`;
}

function detalleHtml(caso) {
  if (!caso) {
    if (carga === 'cargando') return '<p role="status">Cargando captura…</p>';
    return `<section class="empty panel"><h1>Captura no disponible</h1>
      <a class="button" href="${rutaBandeja('revision_manual')}">Volver a la bandeja</a></section>`;
  }
  const estado = estadoActual(caso);
  const decision = resoluciones.get(caso.capture_id);
  const fecha = `${caso.capture_id} · ${caso.capture_store_name} · Recibida ${demo ? 'hoy, ' : ''}${caso.recibida}`;
  return `<header class="page-header">
    <div><p class="micro eyebrow">Detalle de captura</p><h1>${escapeHtml(caso.product_name)}</h1><p class="mono muted">${escapeHtml(fecha)}</p></div>
    <a class="button" href="${rutaBandeja(detalleAnterior ?? estado)}">Volver a la bandeja</a>
  </header>
  ${decision ? `<div class="notice ${estados[estado].tono}" tabindex="-1" role="status">
    <strong>${icono(estados[estado].icono)} ${estado === 'aprobada' ? 'Aprobación registrada' : 'Rechazo registrado'}</strong>
    <small>El historial de auditoría se actualizó.</small>
  </div>` : ''}
  <div class="details">
    ${evidenciaHtml(caso)}
    <div class="stack">${dictamenHtml(caso)}${auditoriaHtml(caso)}</div>
  </div>`;
}

function mostrarDialogo(contenido, size = '') {
  dialog.dataset.size = size;
  dialog.innerHTML = contenido;
  dialog.showModal();
}

function cerrarDialogo() {
  if (dialog.open) dialog.close();
}

function dialogFooter(texto, clase = 'primary') {
  return `<div class="dialog-foot spaced">
    <button type="button" class="button" data-action="cancelar">Cancelar</button>
    <button type="submit" class="button ${clase}">${texto}</button>
  </div>`;
}

function abrirBusqueda() {
  mostrarDialogo(`<form class="stack" data-form="buscar">
    <h2 id="dialog-title">Buscar captura o producto</h2>
    <p class="muted">Escribe el ID de la captura o el nombre del producto.</p>
    <label class="field"><span class="micro">ID de captura o producto</span>
      <input autofocus name="query" value="${escapeHtml(filtros.query)}" placeholder="CAP-000145 o Frijoles negros" type="search"></label>
    ${dialogFooter('Buscar')}
  </form>`, 'filter');
}

function opciones(values, selected) {
  return values.map(value => `<option ${value === selected ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
}

function abrirFiltros() {
  const cadenas = [...new Set(casos.map(caso => caso.capture_store_name))].sort();
  const motivos = [...new Set(casos.map(motivoVisible))].sort();
  mostrarDialogo(`<form class="stack" data-form="filtros">
    <h2 id="dialog-title">Filtros</h2><p class="muted">Selecciona los valores para acotar la bandeja.</p>
    <label class="field"><span class="micro">Cadena</span><select name="cadena"><option value="">Todas</option>${opciones(cadenas, filtros.cadena)}</select></label>
    <label class="field"><span class="micro">Motivo</span><select name="motivo"><option value="">Todos</option>${opciones(motivos, filtros.motivo)}</select></label>
    <div class="range">
      <label class="field"><span class="micro">Confianza desde (%)</span>
        <input type="number" min="0" max="100" step="1" name="desde" value="${filtros.desde}" required></label>
      <label class="field"><span class="micro">Confianza hasta (%)</span>
        <input type="number" min="0" max="100" step="1" name="hasta" value="${filtros.hasta}" required></label>
    </div>
    <p class="error" id="rango-error" role="alert" hidden>La confianza desde debe ser menor o igual que la confianza hasta.</p>
    ${dialogFooter('Aplicar filtros')}
  </form>`, 'filter');
}

function abrirZoom(caso) {
  const tipo = evidencias[fotoActiva];
  mostrarDialogo(`<div class="stack">
    <div class="panel-header"><div><h2 id="dialog-title">Inspección 2× · ${tipo.nombre}</h2>
      <p class="mono muted">${caso.capture_id}</p></div><button class="button" data-action="cancelar">Cerrar</button></div>
    <div class="zoom-view" tabindex="0" aria-label="Imagen ampliada desplazable"><div class="photo-frame">
      ${marcado(caso, fotoActiva)}</div></div>
  </div>`, 'zoom');
  const vista = dialog.querySelector('.zoom-view');
  vista.scrollLeft = (vista.scrollWidth - vista.clientWidth) / 2;
  vista.scrollTop = (vista.scrollHeight - vista.clientHeight) / 2;
}

function abrirResolucion(caso, tipo) {
  if (estadoActual(caso) !== 'revision_manual') return;
  const aprobacion = tipo === 'aprobar';
  mostrarDialogo(`<form class="stack" data-form="${tipo}" data-case="${caso.capture_id}" novalidate>
    <h2 id="dialog-title">¿${aprobacion ? 'Aprobar' : 'Rechazar'} captura?</h2>
    <p class="mono error">${caso.capture_id} · ${escapeHtml(caso.product_name)}</p>
    <p class="muted">${aprobacion ? 'La aprobación se guardará en el historial de auditoría.' : 'El motivo y la nota se guardarán en el historial de auditoría.'}</p>
    ${aprobacion ? '' : `<label class="field">
      <span class="micro">Motivo de rechazo · obligatorio</span>
      <select name="motivo" aria-describedby="motivo-error" required><option value="">Selecciona un motivo</option>
        ${opciones(motivosAuditoria, '')}</select>
      <span class="error" id="motivo-error" role="alert" hidden>Selecciona un motivo.</span>
    </label>
    <label class="field">
      <span class="micro">Nota de auditoría · obligatoria</span>
      <textarea name="nota" aria-describedby="nota-error" placeholder="Selecciona primero un motivo" rows="2" required disabled></textarea>
      <span class="error" id="nota-error" role="alert" hidden>Escribe una nota de auditoría.</span>
    </label>`}
    ${dialogFooter(aprobacion ? 'Confirmar aprobación' : 'Confirmar rechazo', aprobacion ? 'primary' : 'danger')}
  </form>`);
}

function render() {
  const destino = ruta();
  const caso = casos.find(item => item.capture_id === destino.id);
  if (!demo) {
    if (destino.pagina !== 'captura' && vistaCargada) limpiarFotos();
    if (!credencial || carga !== 'lista') {
      menu.innerHTML = '';
      main.innerHTML = !credencial || carga === 'error' ? accesoHtml() : '<p role="status">Consultando la API…</p>';
      main.setAttribute('aria-busy', String(!!credencial && carga === 'cargando'));
      return;
    }
    if (caso) cargarFotos(caso);
  }
  renderNav(destino, caso);
  if (destino.pagina === 'resumen') main.innerHTML = resumenHtml();
  else if (destino.pagina === 'bandeja') main.innerHTML = bandejaHtml(destino.estado);
  else main.innerHTML = detalleHtml(caso);
  main.setAttribute('aria-busy', String(carga === 'cargando' && destino.pagina !== 'resumen'));
}

async function cargarCasos(simularEspera = false) {
  if (!demo) {
    if (!credencial || consultando) return;
    consultando = true;
    try {
      const r = await peticion('/auditoria/capturas');
      const {casos: registros} = await r.json();
      const decisiones = new Map();
      casos = registros.filter(c => /^[A-Za-z0-9_-]{1,64}$/.test(c.capture_id) && Object.hasOwn(estados,c.decision_esperada)).map(c => {
        if (c.auditoria) decisiones.set(c.capture_id,c.auditoria);
        return {...c, product_name:c.product_name || 'Producto sin identificar', capture_store_name:c.capture_store_name || 'Sin cadena',
          titulo:c.motivo_rechazo || c.reason_code, validaciones:c.validaciones || {},
          recibida:new Date(c.recibida).toLocaleString('es-MX',{timeZone:'America/Mexico_City'})};
      });
      resoluciones = decisiones;
      carga = 'lista'; errorApi = '';
    } catch (e) {
      carga = 'error'; errorApi = 'No se pudo consultar la API. '+e.message;
      casos=[]; resoluciones.clear(); limpiarFotos(); credencial='';
    } finally { consultando = false; render(); }
    return;
  }
  if (simularEspera) {
    carga = 'cargando';
    render();
    await new Promise(resolve => setTimeout(resolve, 350));
  }
  try {
    const response = await fetch('demo-data/cases.json');
    if (!response.ok) throw new Error('No se pudieron cargar los casos');
    const { ejemplo, casos: lista } = await response.json();
    casos = lista.map(caso => ({ ...ejemplo, ...caso }));
    carga = 'lista';
  } catch {
    carga = 'error';
  }
  render();
  if (simularEspera && ruta().pagina === 'bandeja') main.focus();
}

function actualizarBandeja(accion) {
  render();
  main.querySelector(`[data-action="${accion}"]`)?.focus();
}

document.addEventListener('click', event => {
  const control = event.target.closest('[data-action], [data-photo], tr[data-id]');
  if (!control) return;
  const accion = control.dataset.action;
  const caso = casos.find(item => item.capture_id === ruta().id);
  if (accion === 'buscar') abrirBusqueda();
  if (accion === 'filtros') abrirFiltros();
  if (accion === 'limpiar') {
    filtros = { ...defaultFilters };
    actualizarBandeja('limpiar');
  }
  if (accion === 'simular-red') {
    carga = 'error';
    render();
    main.querySelector('[data-action="reintentar"]')?.focus();
  }
  if (accion === 'reintentar') cargarCasos(true);
  if (accion === 'cancelar') cerrarDialogo();
  if (accion === 'ampliar' && caso) abrirZoom(caso);
  if (accion === 'zoom-detalle' && caso) {
    zoomEnDetalle = !zoomEnDetalle;
    render();
    main.querySelector('[data-action="zoom-detalle"]')?.focus();
  }
  if (['aprobar', 'rechazar'].includes(accion) && caso) abrirResolucion(caso, accion);
  if (control.dataset.photo && caso) {
    fotoActiva = control.dataset.photo;
    zoomEnDetalle = false;
    render();
    main.querySelector(`[data-photo="${fotoActiva}"]`)?.focus();
  }
  if (control.dataset.id && !event.target.closest('a')) location.hash = `#captura/${control.dataset.id}`;
});

function mostrarError(input, id, visible) {
  input.setAttribute('aria-invalid', String(visible));
  dialog.querySelector(`#${id}`).hidden = !visible;
}

dialog.addEventListener('input', event => {
  const { target } = event;
  if (target.form?.dataset.form === 'rechazar' && target.name === 'nota' && target.value.trim()) {
    mostrarError(target, 'nota-error', false);
  }
});
dialog.addEventListener('change', event => {
  const form = event.target.form;
  if (form?.dataset.form !== 'rechazar' || event.target.name !== 'motivo') return;
  const nota = form.elements.nota;
  nota.disabled = !event.target.value;
  nota.placeholder = nota.disabled ? 'Selecciona primero un motivo' : 'Escribe una nota de auditoría';
  mostrarError(event.target, 'motivo-error', false);
});
dialog.addEventListener('submit', event => {
  event.preventDefault();
  const form = event.target;
  const data = new FormData(form);
  const accion = form.dataset.form;
  if (accion === 'buscar') {
    filtros.query = String(data.get('query')).trim();
    cerrarDialogo();
    actualizarBandeja('buscar');
  }
  if (accion === 'filtros') {
    const desde = Number(data.get('desde'));
    const hasta = Number(data.get('hasta'));
    mostrarError(form.elements.hasta, 'rango-error', desde > hasta);
    if (desde > hasta) {
      form.elements.hasta.focus();
      return;
    }
    filtros = { ...filtros, cadena: String(data.get('cadena')), motivo: String(data.get('motivo')), desde, hasta };
    cerrarDialogo();
    actualizarBandeja('filtros');
  }
  if (accion !== 'rechazar' && accion !== 'aprobar') return;
  const caso = casos.find(item => item.capture_id === form.dataset.case);
  if (!caso) return;
  const motivo = String(data.get('motivo') || '');
  const nota = String(data.get('nota') || '').trim();
  if (accion === 'rechazar') {
    mostrarError(form.elements.motivo, 'motivo-error', !motivo);
    mostrarError(form.elements.nota, 'nota-error', !nota);
    if (!motivo || !nota) {
      form.elements[motivo ? 'nota' : 'motivo'].focus();
      return;
    }
  }
  guardarResolucion(caso, { estado: accion === 'aprobar' ? 'aprobada' : 'rechazada', motivo, nota });
});

document.querySelector('.skip').addEventListener('click', event => {
  event.preventDefault();
  main.focus();
});

window.addEventListener('hashchange', () => {
  cerrarDialogo();
  const destino = ruta();
  if (destino.pagina === 'captura') {
    fotoActiva = 'etiqueta';
    zoomEnDetalle = false;
    const [paginaAnterior, estadoAnterior] = ultimaRuta.split('/');
    detalleAnterior = paginaAnterior === '#bandeja' && Object.hasOwn(estados, estadoAnterior) ? estadoAnterior : null;
  }
  ultimaRuta = location.hash;
  render();
  main.focus();
});

ultimaRuta = location.hash;
render();
cargarCasos();

document.addEventListener('submit', event => {
  if (event.target.id !== 'acceso') return;
  event.preventDefault();
  credencial = new FormData(event.target).get('token').trim();
  carga = 'cargando'; errorApi = ''; render(); cargarCasos();
});
if (!demo) setInterval(() => {
  if (credencial && !document.hidden && !dialog.open) cargarCasos();
}, 15000);
