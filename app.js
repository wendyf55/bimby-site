/*
 * the app behind index.html (map, place search, butterfly lists, charts).
 * Styles are in styles.css; species photos/descriptions come from species-info.js.
 * Data files are built by the scripts in scripts/ (see README.md).
 */
// constants and helpers
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const THIS_MONTH = new Date().getMonth();
const RADII = [5, 15, 30, 50];
const INAT_PROJECT = 'https://www.inaturalist.org/projects/2026-butterflies-in-my-backyard-bimby-project';
const GEOCODER = 'https://nominatim.openstreetmap.org';   // OpenStreetMap place search (light use only)

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => n.toLocaleString('en-CA');
const plural = (n, one, many = one + 's') => `${fmt(n)} ${n === 1 ? one : many}`;
const fmtDate = d => { const [y, m, dd] = d.split('-'); return `${MONTHS[+m - 1]} ${+dd}, ${y}`; };
const ICON = {
  pin: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  locate: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>',
  search: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4-4"/></svg>',
  bars: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h16M7 16v-5M12 16V6M17 16v-8"/></svg>',
};

// Data sources (one file each, built by scripts/build_*.py)
const SOURCES = [
  { key: 'sg', file: 'data/observations-sg.json', label: 'Guppy & Shepard', short: 'G&S' },
  { key: 'inat', file: 'data/observations-inat.json', label: 'iNaturalist', short: 'iNat' },
];
const NEAR_MIN_KM_OBSCURED = 30;   // obscured iNat locations (blurred ~20 km) only count from this distance up
let allObs = [], loaded = [], srcMeta = {};                // loaded = keys of sources that loaded

// State
let observations = [], plantIndex = {}, regions = [], allYears = [];
const state = {
  point: null, place: '', radiusKm: 15, region: null,   // region = GeoJSON feature or null
  scope: 'near',                                          // 'near' | 'region'
  q: '', month: '', sort: 'count', year: '',
  open: null, plantCat: 'host', listId: null,             // expanded card
  mapped: null,                                           // species shown as dots
  matches: null, message: '', showEcoInfo: false, placeQ: '',   // placeQ = text in the place search box
  trends: null,                                           // 'near' | 'region' when the trends drawer is open
  secOpen: { months: true, years: true },                 // collapsible sections in a butterfly's detail
  sources: null,                                          // keys of sources shown (null = all loaded)
};
let YEARS = [];                                           // every year from first to last record (no gaps)
let scopeCache = null;
let refocusPlace = false;                                 // put the cursor back in the place search after a search re-renders

// Map
const BC_BOUNDS = [[48.2, -139.1], [60.0, -114.0]];   // British Columbia
const NA_BOUNDS = [[7.0, -170.0], [84.0, -50.0]];      // North America: only these map tiles are drawn
const VIEW_BOUNDS = [[44.0, -152.0], [65.0, -100.0]];  // BC plus a margin: how far the map can be panned
const map = L.map('map', {
  zoomSnap: 0.25, maxBounds: VIEW_BOUNDS, maxBoundsViscosity: 1.0, worldCopyJump: false
}).fitBounds(BC_BOUNDS);
// Don't let people zoom out past "all of BC" (re-checked when the map changes size)
function lockZoomToBC() {
  map.setMinZoom(Math.max(0, map.getBoundsZoom(BC_BOUNDS) - 0.5));
}
lockZoomToBC();
map.on('resize', lockZoomToBC);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, bounds: NA_BOUNDS, noWrap: true,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    + ' | Ecoregions: <a href="https://sis.agr.gc.ca/cansis/nsdb/ecostrat/" target="_blank" rel="noopener">AAFC</a>'
}).addTo(map);
// Resizable panel (desktop)
(function () {
  const KEY = 'bimby-panel-w', root = document.documentElement, handle = document.getElementById('resizer');
  const MIN = 360, MAP_MIN = 320;
  const clamp = w => Math.round(Math.max(MIN, Math.min(w, window.innerWidth - MAP_MIN)));
  const set = (w, save) => {
    if (w == null) root.style.removeProperty('--panel-w');
    else root.style.setProperty('--panel-w', clamp(w) + 'px');
    handle.setAttribute('aria-valuenow', Math.round(document.getElementById('panel').getBoundingClientRect().width));
    map.invalidateSize();
    if (save !== undefined) { try { w == null ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, clamp(w)); } catch (e) { } }
  };
  try { const w = +localStorage.getItem(KEY); if (w) set(w); } catch (e) { }
  handle.addEventListener('pointerdown', e => {
    e.preventDefault(); handle.setPointerCapture(e.pointerId);
    handle.classList.add('dragging'); document.body.classList.add('resizing');
    const move = ev => set(ev.clientX);
    const up = ev => {
      handle.releasePointerCapture(ev.pointerId); handle.classList.remove('dragging'); document.body.classList.remove('resizing');
      handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up);
      set(ev.clientX, true);
    };
    handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up);
  });
  handle.addEventListener('dblclick', () => set(null, true));
  handle.addEventListener('keydown', e => {
    const cur = document.getElementById('panel').getBoundingClientRect().width;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); set(cur + (e.key === 'ArrowRight' ? 40 : -40), true); }
    if (e.key === 'Home' || e.key === 'Escape') { e.preventDefault(); set(null, true); }
  });
  window.addEventListener('resize', () => { const w = root.style.getPropertyValue('--panel-w'); if (w) set(parseFloat(w)); else map.invalidateSize(); });
})();
const youIcon = L.divIcon({ className: '', html: '<div class="you-pin"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
let youMarker = null, radiusCircle = null, regionLayer = null, dotLayer = null, postalLayer = null;
const dotRenderer = L.canvas({ padding: 0.5 });

const hint = L.control({ position: 'topright' });
hint.onAdd = () => { const d = L.DomUtil.create('div', 'map-hint'); d.textContent = 'Click the map to choose a spot'; return d; };
hint.addTo(map);
const banner = L.control({ position: 'topright' });
banner.onAdd = () => { const d = L.DomUtil.create('div', 'map-banner'); L.DomEvent.disableClickPropagation(d); return d; };

map.on('click', e => setPoint(e.latlng, null, true));

// Load data
// First and last year among a source's record dates, e.g. ['1950', '2025']
const yearRange = dates => {
  let lo = '', hi = '';
  for (const x of dates) if (x) { if (!lo || x < lo) lo = x; if (x > hi) hi = x; }
  return hi ? [lo.slice(0, 4), hi.slice(0, 4)] : null;
};
// A source that fails to load is simply left out (e.g. a copy of the site without it).
const loadSource = src => fetch(src.file).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(d => ({ src, d }), err => { console.warn(`${src.label} data not loaded`, err); return null; });
Promise.all([
  Promise.all(SOURCES.map(loadSource)),
  fetch('data/plant-lists.json').then(r => r.json()),
  fetch('data/ecoregions.geojson').then(r => r.json()),
  SpeciesInfo.load(),
]).then(([sources, lists, geo]) => {
  for (const s of sources.filter(Boolean)) {
    const { src, d } = s, f = Object.fromEntries(d.fields.map((k, i) => [k, i]));
    srcMeta[src.key] = { asOf: d.asOf || d.built, count: d.rows.length, years: yearRange(d.rows.map(r => r[f.date])) };
    loaded.push(src.key);
    for (const r of d.rows) {
      const [sci, common] = d.species[r[f.sp]], date = r[f.date];
      allObs.push({
        id: `${src.key}-${r[f.id]}`, rid: r[f.id], source: src.key, scientificName: sci, commonName: common,
        lat: r[f.lat], lng: r[f.lng], observedOn: date, obscured: !!(r[f.flags] & 1),
        _region: r[f.region], _year: date.slice(0, 4), _month: +date.slice(5, 7) - 1,
      });
    }
  }
  if (!allObs.length) throw new Error('no observation data');
  for (const l of lists) (plantIndex[l.butterfly.scientificName] ??= []).push(l);
  regions = geo.features.map(f => ({ f, bbox: bboxOf(f.geometry) }));
  applySources();
  if (!restoreFromHash()) render();
}).catch(err => {
  document.getElementById('content').innerHTML = '<p class="empty">Sorry, the butterfly data could not be loaded.</p>';
  console.error(err);
});

// Which sources are shown
const activeSources = () => state.sources ? loaded.filter(k => state.sources.includes(k)) : loaded;
const srcInfo = key => SOURCES.find(s => s.key === key);
function applySources() {
  const on = new Set(activeSources());
  observations = on.size === loaded.length ? allObs : allObs.filter(o => on.has(o.source));
  allYears = [...new Set(observations.map(o => o._year).filter(Boolean))].sort();
  YEARS = [];
  for (let y = +allYears[0]; y <= +allYears[allYears.length - 1]; y++) YEARS.push(String(y));
  if (state.year && !allYears.includes(state.year)) state.year = '';
  scopeCache = null;
}
function setSources(key) {
  state.sources = key === 'all' ? null : [key];
  state.open = null;
  applySources(); render(); drawSpeciesDots(false);
}
function sourceHTML() {
  if (loaded.length < 2) return '';
  const cur = state.sources ? state.sources[0] : 'all';
  const btn = (k, label) => `<button type="button" data-src="${k}" aria-pressed="${cur === k}">${label}</button>`;
  return `<div class="src-pick"><span>Data:</span>
    <div class="seg" role="group" aria-label="Data source">${btn('all', 'Both')}${loaded.map(k => btn(k, esc(srcInfo(k).label))).join('')}</div>
    ${loaded.includes('inat') && (!state.sources || state.sources.includes('inat')) && srcMeta.inat.asOf
      ? `<small>iNaturalist updated ${fmtDate(srcMeta.inat.asOf.slice(0, 10))}</small>` : ''}</div>`;
}
// Obscured iNat locations are blurred by ~20 km, so they don't belong in small "near you" circles.
const nearOK = o => !o.obscured || state.radiusKm >= NEAR_MIN_KM_OBSCURED;

// Which ecoregion is a point in? (ray casting on the outlines)
function bboxOf(g) {
  let b = [Infinity, Infinity, -Infinity, -Infinity];
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
  for (const poly of polys) for (const [x, y] of poly[0]) {
    if (x < b[0]) b[0] = x; if (y < b[1]) b[1] = y; if (x > b[2]) b[2] = x; if (y > b[3]) b[3] = y;
  }
  return b;
}
function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function regionAt(latlng) {
  const x = latlng.lng, y = latlng.lat;
  for (const { f, bbox } of regions) {
    if (x < bbox[0] || x > bbox[2] || y < bbox[1] || y > bbox[3]) continue;
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    for (const poly of polys) {
      if (inRing(x, y, poly[0]) && !poly.slice(1).some(h => inRing(x, y, h))) return f;
    }
  }
  return nearestRegion(x, y);
}

// Same rule as scripts/source_files.py: a spot outside every outline (just off the coast,
// or in a gap between simplified borders) counts in the nearest ecoregion within 0.05° (~5 km).
const NEAREST_MAX_DEG = 0.05;
function nearestRegion(x, y) {
  const d = NEAREST_MAX_DEG;
  let best = null, bestD2 = d * d;
  for (const { f, bbox } of regions) {
    if (x < bbox[0] - d || x > bbox[2] + d || y < bbox[1] - d || y > bbox[3] + d) continue;
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    for (const poly of polys) for (const ring of poly) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const d2 = segDist2(x, y, ring[j], ring[i]);
        if (d2 < bestD2) { bestD2 = d2; best = f; }
      }
    }
  }
  return best;
}
// Squared distance (in degrees, like shapely) from (x, y) to the segment a–b
function segDist2(x, y, [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2)) : 0;
  const px = ax + t * dx - x, py = ay + t * dy - y;
  return px * px + py * py;
}

// Choosing a spot
function setPoint(latlng, label, fromMapClick) {
  state.point = L.latLng(latlng);
  state.place = label || '';
  state.region = regionAt(state.point);
  state.open = null; state.matches = null; state.message = ''; state.q = ''; state.placeQ = ''; refocusPlace = false;
  if (!state.region && state.scope === 'region') state.scope = 'near';
  scopeCache = null;
  drawPlace(!fromMapClick);
  render();
  if (!label) reverseGeocode(state.point);
}

function drawPlace(zoom) {
  postalLayer?.remove(); postalLayer = null;
  hint.remove();
  youMarker?.remove(); radiusCircle?.remove(); regionLayer?.remove();
  if (!state.point) { hint.addTo(map); return; }
  if (state.region) {
    regionLayer = L.geoJSON(state.region, {
      interactive: false,
      style: { color: '#33472a', weight: 1.5, dashArray: '5 4', fillColor: '#33472a', fillOpacity: state.scope === 'region' ? 0.08 : 0.03 },
    }).addTo(map);
  }
  radiusCircle = L.circle(state.point, {
    radius: state.radiusKm * 1000, color: '#e79a3c', weight: 2, fillColor: '#e79a3c',
    fillOpacity: state.scope === 'near' ? 0.12 : 0.04, interactive: false,
  }).addTo(map);
  youMarker = L.marker(state.point, { icon: youIcon, keyboard: false, interactive: false }).addTo(map);
  if (zoom) fitScope();
}
function fitScope() {
  if (!state.point) return;
  const b = state.scope === 'region' && regionLayer ? regionLayer.getBounds() : radiusCircle.getBounds();
  map.fitBounds(b, { padding: [70, 70], maxZoom: 11 });   // leave some surroundings visible
}

// Postal codes
// Only the first three characters (the "forward sortation area", e.g. V6T) are used:
// data/postal-fsa.json is built from Statistics Canada's FSA boundaries
// (scripts/build_postal.py). Loaded on the first postal code search.
const PROVINCE_BY_LETTER = {
  A: 'Newfoundland and Labrador', B: 'Nova Scotia', C: 'Prince Edward Island', E: 'New Brunswick',
  G: 'Quebec', H: 'Quebec', J: 'Quebec', K: 'Ontario', L: 'Ontario', M: 'Ontario', N: 'Ontario', P: 'Ontario',
  R: 'Manitoba', S: 'Saskatchewan', T: 'Alberta', X: 'Northwest Territories or Nunavut', Y: 'Yukon',
};
let postalData = null;
const loadPostal = () => postalData ??= fetch('data/postal-fsa.json')
  .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(d => d.fsa)
  .catch(err => { postalData = null; throw err; });

// "v6t 1z4", "V6T1Z4", "V6T" → { fsa: 'V6T', code: 'V6T 1Z4' }. A letter O typed for
// a zero (common: "VOH") is accepted, since O never appears in Canadian postal codes.
function parsePostal(q) {
  const c = q.toUpperCase().replace(/[\s-]/g, '');
  if (!/^[A-Z][0-9O][A-Z]([0-9O][A-Z][0-9O])?$/.test(c)) return null;
  const fix = c.split('').map((ch, i) => (i % 2 === 1 && ch === 'O') ? '0' : ch).join('');
  return { fsa: fix.slice(0, 3), code: fix.length === 6 ? `${fix.slice(0, 3)} ${fix.slice(3)}` : fix };
}

function searchPostal(pc) {
  if (pc.fsa[0] !== 'V') {
    const prov = PROVINCE_BY_LETTER[pc.fsa[0]];
    state.message = prov
      ? `${pc.code} is a postal code in ${prov}. This map covers British Columbia only — BC postal codes start with V.`
      : `${pc.code} isn’t a Canadian postal code we recognise. BC postal codes start with V.`;
    render(); return;
  }
  state.message = 'Searching…'; state.matches = null; render();
  loadPostal().then(fsas => {
    const f = fsas[pc.fsa];
    if (!f) {
      state.message = `We couldn’t find the postal area ${pc.fsa}. Check the code, or search for your town instead.`;
      render(); return;
    }
    if (!f.wide) {
      setPoint({ lat: f.pt[0], lng: f.pt[1] }, `${pc.fsa} area`, false);
      reverseGeocode(state.point, pc.fsa);
      return;
    }
    // A rural or very large postal area: a pin in the middle could be far from the visitor,
    // so show the area and let them click their spot.
    state.message = `${pc.code} covers a large area (about ${fmt(f.km2)} km²), so we can’t tell where in it you are. ` +
      `Click your spot inside the outlined area on the map, or search for your town.`;
    render();
    postalLayer?.remove();
    postalLayer = L.geoJSON(f.outline, {
      interactive: false,
      style: { color: '#e79a3c', weight: 2, dashArray: '6 4', fillColor: '#e79a3c', fillOpacity: 0.08 },
    }).addTo(map);
    map.fitBounds(postalLayer.getBounds(), { padding: [40, 40] });
  }).catch(() => searchByName(pc.code));   // lookup file missing: fall back to the place search
}

function searchPlace(q) {
  q = q.trim();
  state.placeQ = q; refocusPlace = true;
  if (!q) return;
  postalLayer?.remove(); postalLayer = null;
  const pc = parsePostal(q);
  if (pc) searchPostal(pc); else searchByName(q);
}

// Town/place search with OpenStreetMap's Nominatim. The viewbox is a rectangle around BC
// that also takes in part of Alberta, so results are filtered to BC by their address.
const inBC = p => p.address && (p.address['ISO3166-2-lvl4'] === 'CA-BC' || p.address.state === 'British Columbia');
function searchByName(q) {
  state.message = 'Searching…'; state.matches = null; render();
  fetch(`${GEOCODER}/search?format=jsonv2&addressdetails=1&countrycodes=ca&viewbox=-139.1,60.0,-114.0,48.2&bounded=1&limit=8&q=${encodeURIComponent(q)}`)
    .then(r => r.json())
    .then(found => {
      const list = found.filter(inBC).slice(0, 5);
      state.message = list.length ? ''
        : found.length ? `We found “${shortPlace(found[0].display_name)}”, but it’s outside British Columbia. This map covers BC only.`
          : `No places in British Columbia found for “${q}”. Check the spelling, try a nearby town, or click the map.`;
      state.matches = list.map(p => ({ lat: +p.lat, lng: +p.lon, name: p.display_name }));
      if (state.matches.length === 1) pickMatch(0); else render();
    })
    .catch(() => { state.message = 'Place search is not available right now. You can click the map instead.'; render(); });
}
function pickMatch(i) {
  const m = state.matches[i];
  setPoint({ lat: m.lat, lng: m.lng }, shortPlace(m.name), false);
}
const shortPlace = name => name.split(',').slice(0, 2).join(',').trim();

function reverseGeocode(latlng, suffix) {
  const at = latlng;
  // Only the town is needed, so send coordinates rounded to ~1 km (2 decimals), never the exact spot.
  fetch(`${GEOCODER}/reverse?format=jsonv2&zoom=12&lat=${at.lat.toFixed(2)}&lon=${at.lng.toFixed(2)}`)
    .then(r => r.json())
    .then(p => {
      if (state.point !== at || !p || !p.address) return;
      const a = p.address;
      const town = a.city || a.town || a.village || a.hamlet || a.municipality || a.county || '';
      state.place = [town, a.state].filter(Boolean).join(', ');
      if (state.place && suffix) state.place += ` (${suffix})`;
      if (state.place) renderPlaceName();
    })
    .catch(() => { });
}

function useMyLocation() {
  if (!navigator.geolocation) { state.message = 'Your browser can’t share its location. Try searching instead.'; render(); return; }
  state.message = 'Finding your location…'; render();
  navigator.geolocation.getCurrentPosition(
    pos => setPoint({ lat: pos.coords.latitude, lng: pos.coords.longitude }, null, false),
    () => { state.message = 'We couldn’t get your location. Try searching or click the map.'; render(); },
    { enableHighAccuracy: false, timeout: 10000 }
  );
}

function resetPlace() {
  state.point = null; state.region = null; state.open = null; state.place = '';
  showSpeciesOnMap(null);
  drawPlace(false);
  render();
}

// Butterflies in the current scope
function scopeObservations() {
  if (scopeCache) return scopeCache;
  const inYear = o => !state.year || o._year === state.year;
  let obs;
  if (state.scope === 'region') {
    const id = state.region?.properties.id;
    obs = observations.filter(o => o._region === id && inYear(o));
  } else {
    const r = state.radiusKm * 1000, p = state.point;
    // quick box check first, then exact distance
    const dLat = state.radiusKm / 111, dLng = dLat / Math.max(0.2, Math.cos(p.lat * Math.PI / 180));
    obs = observations.filter(o => inYear(o) && nearOK(o) && Math.abs(o.lat - p.lat) <= dLat && Math.abs(o.lng - p.lng) <= dLng
      && map.distance(p, [o.lat, o.lng]) <= r);
  }
  const species = new Map();
  for (const o of obs) {
    let s = species.get(o.scientificName);
    if (!s) species.set(o.scientificName, s = { sci: o.scientificName, common: o.commonName, count: 0, bySrc: {}, months: new Array(12).fill(0), first: o.observedOn, last: o.observedOn });
    s.count++; s.months[o._month]++; s.bySrc[o.source] = (s.bySrc[o.source] || 0) + 1;
    if (o.observedOn < s.first) s.first = o.observedOn;
    if (o.observedOn > s.last) s.last = o.observedOn;
  }
  return (scopeCache = { obs, species });
}
// Records in a scope across ALL years (the year charts ignore the year filter)
function scopeAllYears(scope) {
  if (scope === 'region') {
    const id = state.region?.properties.id;
    return id == null ? [] : observations.filter(o => o._region === id);
  }
  const r = state.radiusKm * 1000, p = state.point;
  const dLat = state.radiusKm / 111, dLng = dLat / Math.max(0.2, Math.cos(p.lat * Math.PI / 180));
  return observations.filter(o => nearOK(o) && Math.abs(o.lat - p.lat) <= dLat && Math.abs(o.lng - p.lng) <= dLng
    && map.distance(p, [o.lat, o.lng]) <= r);
}
function yearly(obs) {
  const idx = new Map(YEARS.map((y, i) => [y, i]));
  const recs = new Array(YEARS.length).fill(0), sp = YEARS.map(() => new Set());
  for (const o of obs) {
    const i = idx.get(o._year);
    if (i !== undefined) { recs[i]++; sp[i].add(o.scientificName); }
  }
  return { recs, species: sp.map(x => x.size) };
}
function scopeLabel(scope) {
  return scope === 'region' ? `${esc(state.region.properties.name)} ecoregion`
    : `Within ${state.radiusKm} km of ${esc(state.place || 'your spot')}`;
}

function statsFor(scope) {
  const saved = [state.scope, scopeCache];
  state.scope = scope; scopeCache = null;
  const s = scopeObservations();
  const out = { obs: s.obs.length, species: s.species.size };
  [state.scope, scopeCache] = saved;
  return out;
}

function visibleSpecies() {
  let rows = [...scopeObservations().species.values()];
  const q = state.q.trim().toLowerCase();
  if (q) rows = rows.filter(s => (s.sci + ' ' + (s.common || '')).toLowerCase().includes(q));
  if (state.month !== '') rows = rows.filter(s => s.months[+state.month] > 0);
  const name = s => s.common || s.sci;
  const sorts = {
    count: (a, b) => b.count - a.count || name(a).localeCompare(name(b)),
    rare: (a, b) => a.count - b.count || name(a).localeCompare(name(b)),
    az: (a, b) => name(a).localeCompare(name(b)),
  };
  return rows.sort(sorts[state.sort]);
}

// Render
function render() {
  updateHash();
  const box = document.getElementById('content');
  box.innerHTML = state.point ? resultsHTML() : startHTML();
  wire(box);
  if (!state.point && refocusPlace) {
    const inp = document.getElementById('placeInput');
    inp?.focus({ preventScroll: true }); inp?.setSelectionRange(inp.value.length, inp.value.length);
  }
  announce();
  renderTrends();
}

// Only the butterfly list, so typing in its search box doesn't rebuild the whole panel
function renderList() {
  const el = document.getElementById('list');
  if (!el) return render();
  el.innerHTML = listHTML();
  wire(el);
  announce();
}

// Screen readers hear the message or the count line (one small live region, not the whole panel)
let announceTimer = null, lastAnnounced = '';
function announce() {
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => {
    const t = state.message || document.querySelector('#list .count-line')?.textContent.trim() || '';
    if (t && t !== lastAnnounced) document.getElementById('announce').textContent = lastAnnounced = t;
  }, 500);
}

function startHTML() {
  const total = observations.length, sp = new Set(observations.map(o => o.scientificName)).size;
  return `
    <h2 class="lead">Where is your backyard?</h2>
    <p class="sub">Find out which butterflies have been seen near you, when they fly, and which plants help them.</p>
    <form class="search" id="placeForm" role="search">
      <label class="sr-only" for="placeInput">Town, city or postal code</label>
      <input id="placeInput" type="search" placeholder="Town, city or postal code" autocomplete="off" value="${esc(state.placeQ)}">
      <button class="btn primary" type="submit">${ICON.search}<span>Search</span></button>
    </form>
    ${state.matches && state.matches.length > 1 ? `<ul class="matches" aria-label="Places found">${state.matches.map((m, i) =>
    `<li><button type="button" data-match="${i}">${esc(shortPlace(m.name))}<small>${esc(m.name)}</small></button></li>`).join('')}</ul>` : ''}
    ${state.message ? `<p class="msg">${esc(state.message)}</p>` : ''}
    <div class="or">or</div>
    <button class="btn secondary full" type="button" id="locateBtn">${ICON.locate}<span>Use my location</span></button>
    <p class="hint">You can also click anywhere on the map.</p>
    ${total ? `<div class="canada">${sourceHTML()}<p style="margin:0">The map holds <b>${fmt(total)}</b> records of <b>${sp}</b> butterfly species from British Columbia
      (${activeSources().map(k => k === 'sg' ? 'Guppy &amp; Shepard, 2001' : 'iNaturalist observers').join(' and ')}).
      Seen a butterfly? <a href="${INAT_PROJECT}" target="_blank" rel="noopener" style="color:var(--link)">Join the BIMBY project on iNaturalist</a>.</p></div>` : ''}`;
}

function resultsHTML() {
  const near = statsFor('near'), reg = state.region ? statsFor('region') : null;
  const where = state.scope === 'near' ? `within ${state.radiusKm} km` : `in ${esc(state.region.properties.name)}`;
  let html = `
    <div class="place">
      ${ICON.pin}<span class="name" id="placeName">${esc(state.place || 'Your spot')}</span>
      <button class="link-btn" type="button" id="changeBtn">Change</button>
    </div>
    ${sourceHTML()}
    <div class="scope" role="group" aria-label="Show butterflies">
      <div class="tile" role="button" tabindex="0" data-scope="near" aria-pressed="${state.scope === 'near'}">
        <div class="k">Near you</div>
        <div class="t">Within <select id="radiusSel" aria-label="Distance">${RADII.map(r => `<option value="${r}" ${r === state.radiusKm ? 'selected' : ''}>${r} km</option>`).join('')}</select></div>
        <div class="n">${near.species} <small>species</small></div>
        <div class="s">${plural(near.obs, 'sighting')}</div>
        <button class="trend-btn" type="button" data-trends="near" aria-expanded="${state.trends === 'near'}" aria-controls="trends">${ICON.bars}Trends by year</button>
      </div>
      <div class="tile" role="button" tabindex="${reg ? 0 : -1}" data-scope="region" aria-pressed="${state.scope === 'region'}" aria-disabled="${!reg}">
        <div class="k">Your ecoregion</div>
        <div class="t">${reg ? esc(state.region.properties.name) : 'Not in a mapped ecoregion'}</div>
        ${reg ? `<div class="n">${reg.species} <small>species</small></div><div class="s">${plural(reg.obs, 'sighting')}</div>
        <button class="trend-btn" type="button" data-trends="region" aria-expanded="${state.trends === 'region'}" aria-controls="trends">${ICON.bars}Trends by year</button>` : ''}
      </div>
    </div>
    <button class="link-btn" type="button" id="ecoInfo" aria-expanded="${state.showEcoInfo}" style="font-size:13px;margin-bottom:6px">What’s an ecoregion?</button>
    ${state.showEcoInfo ? `<p class="explain">An <b>ecoregion</b> is a natural area with similar climate, landforms, plants and wildlife.
      Canada has 194 of them${state.region ? `; yours is part of the <b>${esc(state.region.properties.zoneName)}</b> ecozone` : ''}.
      It shows which butterflies live in your wider area, not just close by.</p>` : ''}
    <div class="filters">
      <label class="sr-only" for="qInput">Search butterflies</label>
      <input id="qInput" type="search" placeholder="Search butterflies" value="${esc(state.q)}">
      <label class="sr-only" for="monthSel">Flying in month</label>
      <select id="monthSel" class="${state.month !== '' ? 'active' : ''}">
        <option value="">Flying any month</option>
        ${MONTHS_LONG.map((m, i) => `<option value="${i}" ${String(i) === state.month ? 'selected' : ''}>Flying in ${m}${i === THIS_MONTH ? ' (now)' : ''}</option>`).join('')}
      </select>
      <label class="sr-only" for="sortSel">Sort</label>
      <select id="sortSel">
        <option value="count" ${state.sort === 'count' ? 'selected' : ''}>Most seen</option>
        <option value="rare" ${state.sort === 'rare' ? 'selected' : ''}>Rarest</option>
        <option value="az" ${state.sort === 'az' ? 'selected' : ''}>A–Z</option>
      </select>
      ${allYears.length > 1 ? `<select id="yearSel" aria-label="Year"><option value="">All years</option>${allYears.slice().reverse().map(y =>
    `<option ${y === state.year ? 'selected' : ''}>${y}</option>`).join('')}</select>` : ''}
    </div>
    <div id="list">${listHTML()}</div>`;

  html += `
    <details class="about">
      <summary>About this data</summary>
      <p>Butterfly records (${srcMeta.sg?.years ? srcMeta.sg.years.join('&ndash;') + ', ' : ''}British Columbia) come from the occurrence data compiled for
        Guppy, C., &amp; Shepard, J. (2001). <i>Butterflies of British Columbia: Including Western Alberta, Southern Yukon, the Alaska Panhandle, Washington, Northern Oregon, Northern Idaho, and Northwestern Montana</i>. UBC Press.
        A butterfly missing from the list may simply not have been recorded here yet.</p>
      ${loaded.includes('inat') ? `<p>iNaturalist records are research-grade butterfly observations in British Columbia
        (identifications agreed by the community), refreshed weekly${srcMeta.inat.asOf ? `; last updated ${fmtDate(srcMeta.inat.asOf.slice(0, 10))}` : ''}.
        Observations are &copy; their observers, used under the licence each observer chose
        (<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener" style="color:var(--link)">CC0</a>,
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener" style="color:var(--link)">CC BY</a> or
        <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener" style="color:var(--link)">CC BY-NC</a>;
        records under other licences are not shown); each map dot links to its observation, with the observer's name and licence.
        Thanks to the iNaturalist observers who shared them. Subspecies are counted under their species, and a few split species are
        grouped to match Guppy &amp; Shepard (e.g. iNaturalist's two Arctic Skippers count as one). Where an observer hid their exact location
        (blurred by about 20 km), the sighting counts towards your ecoregion and the ${NEAR_MIN_KM_OBSCURED} km and ${RADII[RADII.length - 1]} km circles only.</p>` : ''}
      <p>Descriptions come from Wikipedia and photos from iNaturalist photographers (credited on each butterfly).
        Plant lists come from the Xerces Society. Ecoregions: Agriculture and Agri-Food Canada.</p>
    </details>`;
  return html;
}

// The butterfly list (count line + cards). Re-rendered on its own while typing in the search box.
function listHTML() {
  const rows = visibleSpecies();
  const where = state.scope === 'near' ? `within ${state.radiusKm} km` : `in ${esc(state.region.properties.name)}`;
  let html = `<div class="count-line">${plural(rows.length, 'butterfly species', 'butterfly species')} ${where}${state.month !== '' ? `, seen in ${MONTHS_LONG[+state.month]}` : ''}</div>`;

  if (!rows.length) {
    const nothing = scopeObservations().species.size === 0;
    html += `<div class="empty">${nothing
      ? `No butterfly records ${where} yet. Try a bigger distance, switch to your ecoregion, or be the first:
         <a href="${INAT_PROJECT}" target="_blank" rel="noopener" style="color:var(--link)">add a sighting on iNaturalist</a>.`
      : state.month !== '' ? `None of these butterflies have been recorded ${where} in ${MONTHS_LONG[+state.month]} yet.
         <button class="link-btn" type="button" id="clearFly">Show all months</button>`
        : `No butterflies match “${esc(state.q)}”.`}</div>`;
  } else {
    html += `<div class="grid">${rows.map(s => s.sci === state.open ? detailHTML(s) : cardHTML(s)).join('')}</div>`;
  }
  return html;
}

function cardHTML(s) {
  const p = SpeciesInfo.get(s.sci)?.photo;
  return `
    <button class="card" type="button" data-sci="${esc(s.sci)}" aria-expanded="false">
      <div class="ph">${p ? `<img src="${esc(p.url || p.square)}" alt="" loading="lazy">` : 'No photo yet'}</div>
      <div class="meta">
        <div class="cn">${esc(s.common || s.sci)}</div>
        <div class="sn">${esc(s.sci)}</div>
        <div class="ct">${plural(s.count, 'sighting')}</div>
      </div>
    </button>`;
}

function detailHTML(s) {
  const lists = plantIndex[s.sci] || [];
  const list = lists.find(l => l.id === state.listId) || lists[0];
  const plants = list ? list.plants.filter(p => (state.plantCat === 'host') === !!p.isHost) : [];
  const where = state.scope === 'near' ? `within ${state.radiusKm} km` : `in ${esc(state.region.properties.name)}`;
  const total = observations.filter(o => o.scientificName === s.sci).length;
  const peak = s.months.indexOf(Math.max(...s.months));
  return `
    <article class="detail" id="detail" aria-label="${esc(s.common || s.sci)}">
      <div class="detail-head">
        <div class="names"><h3>${esc(s.common || s.sci)}</h3><div class="sn">${esc(s.sci)}</div></div>
        <button class="close-btn" type="button" id="closeDetail">Close</button>
      </div>
      <div class="facts">
        <span><b>${plural(s.count, 'sighting')}</b> ${where}${activeSources().length > 1
      ? ` <small>(${activeSources().map(k => `${fmt(s.bySrc[k] || 0)} ${srcInfo(k).short}`).join(', ')})</small>` : ''}</span>
        <span>Most seen in <b>${MONTHS_LONG[peak]}</b></span>
        <span>Last seen <b>${fmtDate(s.last)}</b></span>
      </div>
      ${SpeciesInfo.card(s.sci)}

      <details class="sec" data-sec="months" ${state.secOpen.months ? 'open' : ''}>
        <summary>When it flies here <span class="hint-r">by month</span></summary>
        <p class="chart-sub">Sightings by month ${where}${state.year ? ', ' + state.year : ''}</p>
        <div class="chart">${monthChart(s.months)}</div>
      </details>

      ${speciesYearsHTML(s)}

      <h4 style="margin-top:22px">Plants for your garden</h4>
      <div class="seg" role="group" aria-label="Plant type">
        <button type="button" data-cat="host" aria-pressed="${state.plantCat === 'host'}">Caterpillar food (host)</button>
        <button type="button" data-cat="nectar" aria-pressed="${state.plantCat === 'nectar'}">Adult food (nectar)</button>
      </div>
      ${!list ? `<p class="note">We don’t have a plant list for this butterfly yet.</p>` : `
        ${lists.length > 1 ? `<select class="list-select" id="listSel" aria-label="Plant list">${lists.map(l =>
        `<option value="${esc(l.id)}" ${l === list ? 'selected' : ''}>${esc(l.region)} — ${esc(shortSource(l.source.org))} (${l.source.year})</option>`).join('')}</select>`
        : `<p class="note" style="margin-bottom:6px">List for: ${esc(list.region)}</p>`}
        ${plants.length ? `<ul class="plants">${plants.map(p => `<li><span>${esc(p.commonName)} <i>${esc(p.scientificName)}</i></span>${p.bloom ? `<span class="bloom">Blooms ${esc(p.bloom)}</span>` : ''}</li>`).join('')}</ul>`
        : `<p class="note">None listed as ${state.plantCat === 'host' ? 'host' : 'nectar'} plants in this list.</p>`}
        <p class="cite">Source: <a href="${esc(list.source.url)}" target="_blank" rel="noopener">${esc(list.source.title)}</a>, ${esc(shortSource(list.source.org))} (${list.source.year}).</p>`}

      <div class="map-row">
        <button class="btn ${state.mapped === s.sci ? 'secondary' : 'primary'}" type="button" id="mapBtn">
          ${state.mapped === s.sci ? 'Stop showing on map' : 'Show where it’s been seen'}</button>
        <span class="s">${plural(total, 'sighting')} across BC</span>
      </div>
    </article>`;
}
function shortSource(org) { return /xerces/i.test(org) ? 'Xerces Society' : org; }

function monthChart(months) {
  const W = 400, H = 110, padL = 30, padB = 20, padT = 8, iw = W - padL - 4, ih = H - padB - padT;
  const max = Math.max(1, ...months), step = iw / 12, bw = step * 0.66;
  const top = max <= 5 ? max : Math.ceil(max / 5) * 5;
  let g = `<line x1="${padL}" x2="${W - 4}" y1="${padT + ih}" y2="${padT + ih}" stroke="#e4e1d6"/>` +
    `<text x="${padL - 5}" y="${padT + 8}" text-anchor="end">${fmt(top)}</text>` +
    `<text x="${padL - 5}" y="${padT + ih}" text-anchor="end">0</text>`;
  months.forEach((v, i) => {
    const h = ih * v / top, x = padL + step * i + (step - bw) / 2, y = padT + ih - h, r = Math.min(3, h);
    g += `<g><title>${MONTHS_LONG[i]}: ${plural(v, 'sighting')}</title>` +
      `<rect x="${padL + step * i}" y="${padT}" width="${step}" height="${ih}" fill="transparent"/>` +
      (h > 0 ? `<path class="bar ${i === THIS_MONTH ? 'now' : ''}" d="M${x},${padT + ih} V${y + r} Q${x},${y} ${x + r},${y} H${x + bw - r} Q${x + bw},${y} ${x + bw},${y + r} V${padT + ih} Z"/>` : '') +
      `<text x="${padL + step * i + step / 2}" y="${H - 5}" text-anchor="middle" ${i === THIS_MONTH ? 'style="fill:#1f261b;font-weight:700"' : ''}>${MONTHS[i][0]}</text></g>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Sightings by month">${g}</svg>`;
}

// One butterfly's sightings by year in the current scope (all years)
function speciesYearsHTML(s) {
  const where = state.scope === 'near' ? `within ${state.radiusKm} km` : `in ${esc(state.region.properties.name)}`;
  const recs = yearly(scopeAllYears(state.scope).filter(o => o.scientificName === s.sci)).recs;
  const yrs = recs.filter(v => v > 0).length;
  return `
      <details class="sec" data-sec="years" ${state.secOpen.years ? 'open' : ''}>
        <summary>Sightings by year <span class="hint-r">${plural(yrs, 'year')} with records</span></summary>
        <p class="chart-sub">Records per year ${where}, ${YEARS[0]}–${YEARS[YEARS.length - 1]}${state.year ? ` (${state.year} highlighted)` : ''}</p>
        <div class="chart">${yearChart(recs, 'sighting')}</div>
      </details>`;
}

// Vertical bars, one per year; decade labels so 70+ years stay readable
function yearChart(values, unit) {
  const W = 520, H = 130, padL = 34, padB = 20, padT = 8, iw = W - padL - 4, ih = H - padB - padT;
  const max = Math.max(1, ...values), step = iw / values.length, bw = Math.max(1, step * 0.72);
  const top = max <= 5 ? max : niceMax(max);
  let g = `<line x1="${padL}" x2="${W - 4}" y1="${padT + ih}" y2="${padT + ih}" stroke="#e4e1d6"/>` +
    `<line x1="${padL}" x2="${W - 4}" y1="${padT + ih / 2}" y2="${padT + ih / 2}" stroke="#efece3"/>` +
    `<text x="${padL - 5}" y="${padT + 8}" text-anchor="end">${fmt(top)}</text>` +
    `<text x="${padL - 5}" y="${padT + ih / 2 + 4}" text-anchor="end">${fmt(Math.round(top / 2))}</text>` +
    `<text x="${padL - 5}" y="${padT + ih}" text-anchor="end">0</text>`;
  values.forEach((v, i) => {
    const yr = YEARS[i], h = ih * v / top, x = padL + step * i + (step - bw) / 2, y = padT + ih - h, r = Math.min(2, h, bw / 2);
    g += `<g><title>${yr}: ${plural(v, unit)}</title>` +
      `<rect x="${padL + step * i}" y="${padT}" width="${step}" height="${ih}" fill="transparent"/>` +
      (h > 0 ? `<path class="bar ${yr === state.year ? 'now' : ''}" d="M${x},${padT + ih} V${y + r} Q${x},${y} ${x + r},${y} H${x + bw - r} Q${x + bw},${y} ${x + bw},${y + r} V${padT + ih} Z"/>` : '') +
      (+yr % 10 === 0 ? `<line x1="${padL + step * i + step / 2}" x2="${padL + step * i + step / 2}" y1="${padT + ih}" y2="${padT + ih + 4}" stroke="#cfcabc"/>` +
        `<text x="${padL + step * i + step / 2}" y="${H - 4}" text-anchor="middle">${yr}</text>` : '') + `</g>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${unit === 'species' ? 'Species' : 'Sightings'} by year">${g}</svg>`;
}
function niceMax(v) {
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

// Trends drawer: sightings + species by year for Near you / Your ecoregion
function renderTrends() {
  const el = document.getElementById('trends');
  if (state.trends === 'region' && !state.region) state.trends = null;
  if (!state.point) state.trends = null;
  const open = !!state.trends;
  el.classList.toggle('open', open);
  el.setAttribute('aria-hidden', String(!open));
  document.querySelectorAll('.trend-btn').forEach(b => b.setAttribute('aria-expanded', String(b.dataset.trends === state.trends)));
  if (!open) return;
  const sc = state.trends, obs = scopeAllYears(sc), y = yearly(obs);
  const ys = y.recs.map((v, i) => v ? YEARS[i] : null).filter(Boolean);
  const span = ys.length ? `${ys[0]}–${ys[ys.length - 1]}` : '—';
  const peakI = arr => arr.indexOf(Math.max(...arr));
  const pr = peakI(y.recs), ps = peakI(y.species);
  el.innerHTML = `
    <header class="tr-head">
      <div class="ttl"><h2>Trends by year</h2><div class="where">${scopeLabel(sc)}</div></div>
      <button class="close-btn" type="button" id="closeTrends">Close</button>
    </header>
    <div class="tr-body">
      ${state.region ? `<div class="seg" role="group" aria-label="Area">
        <button type="button" data-tscope="near" aria-pressed="${sc === 'near'}">Near you (${state.radiusKm} km)</button>
        <button type="button" data-tscope="region" aria-pressed="${sc === 'region'}">Your ecoregion</button>
      </div>` : ''}
      ${!obs.length ? `<p class="note">No butterfly records here yet.</p>` : `
      <div class="tr-stats">
        <div><b>${fmt(obs.length)}</b><span>sightings, ${span}</span></div>
        <div><b>${YEARS[pr]}</b><span>most sightings (${fmt(y.recs[pr])})</span></div>
        <div><b>${YEARS[ps]}</b><span>most species (${y.species[ps]})</span></div>
      </div>
      <div class="tr-chart">
        <h3>Sightings by year</h3>
        <p class="chart-sub">Butterfly records logged each year, all species. Hover a bar for the number.</p>
        <div class="chart">${yearChart(y.recs, 'sighting')}</div>
      </div>
      <div class="tr-chart">
        <h3>Species by year</h3>
        <p class="chart-sub">How many different butterfly species were recorded each year.</p>
        <div class="chart">${yearChart(y.species, 'species')}</div>
      </div>
      <p class="note">Ups and downs partly reflect how much searching and recording happened each year,
        not only how many butterflies there were.</p>`}
    </div>`;
  el.querySelector('#closeTrends').addEventListener('click', closeTrends);
  el.querySelectorAll('[data-tscope]').forEach(b => b.addEventListener('click', () => { state.trends = b.dataset.tscope; renderTrends(); }));
}
// On phones the map area is a small sticky strip, so the drawer becomes a full-screen sheet on <body>
(function () {
  const mq = window.matchMedia('(max-width: 800px)');
  const place = () => {
    const el = document.getElementById('trends');
    const home = mq.matches ? document.body : document.getElementById('mapwrap');
    if (el.parentNode !== home) home.prepend(el);
  };
  place(); mq.addEventListener('change', place);
})();
function closeTrends() {
  const was = state.trends; state.trends = null; renderTrends();
  document.querySelector(`.trend-btn[data-trends="${was}"]`)?.focus();
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && state.trends) closeTrends(); });

function renderPlaceName() {
  const el = document.getElementById('placeName');
  if (el) el.textContent = state.place || 'Your spot';
}

// Events
function wire(box) {
  const on = (sel, ev, fn) => box.querySelector(sel)?.addEventListener(ev, fn);

  on('#placeForm', 'submit', e => { e.preventDefault(); searchPlace(box.querySelector('#placeInput').value); });
  box.querySelectorAll('[data-match]').forEach(b => b.addEventListener('click', () => pickMatch(+b.dataset.match)));
  on('#locateBtn', 'click', useMyLocation);
  on('#changeBtn', 'click', resetPlace);

  const pickScope = t => {
    if (t.getAttribute('aria-disabled') === 'true' || state.scope === t.dataset.scope) return;
    state.scope = t.dataset.scope; state.open = null; scopeCache = null;
    drawPlace(false); fitScope(); render();
  };
  box.querySelectorAll('.tile').forEach(t => {
    t.addEventListener('click', e => { if (!e.target.closest('select, .trend-btn')) pickScope(t); });
    t.addEventListener('keydown', e => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target === t) { e.preventDefault(); pickScope(t); }
    });
  });
  on('#radiusSel', 'change', e => {
    state.radiusKm = +e.target.value; state.scope = 'near'; state.open = null; scopeCache = null;
    drawPlace(false); fitScope(); render();
  });
  on('#ecoInfo', 'click', () => { state.showEcoInfo = !state.showEcoInfo; render(); });
  box.querySelectorAll('.trend-btn').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation();
    state.trends = state.trends === b.dataset.trends ? null : b.dataset.trends;
    renderTrends();
    if (state.trends) document.getElementById('closeTrends')?.focus({ preventScroll: true });
  }));
  box.querySelectorAll('details.sec').forEach(d => d.addEventListener('toggle', () => { state.secOpen[d.dataset.sec] = d.open; }));

  const q = box.querySelector('#qInput');
  q?.addEventListener('input', () => { state.q = q.value; renderList(); });
  on('#monthSel', 'change', e => { state.month = e.target.value; render(); });
  on('#clearFly', 'click', () => { state.month = ''; render(); });
  on('#sortSel', 'change', e => { state.sort = e.target.value; render(); });
  on('#yearSel', 'change', e => { state.year = e.target.value; scopeCache = null; state.open = null; render(); drawSpeciesDots(false); });

  box.querySelectorAll('.card').forEach(c => c.addEventListener('click', () => {
    state.open = c.dataset.sci; state.listId = null;
    if (state.mapped && state.mapped !== state.open) { state.mapped = null; drawSpeciesDots(false); }   // clear the previous butterfly's dots
    render();
    const d = document.getElementById('detail');
    d?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    document.getElementById('closeDetail')?.focus({ preventScroll: true });
  }));
  on('#closeDetail', 'click', () => {
    const sci = state.open; state.open = null; render();
    document.querySelector(`.card[data-sci="${CSS.escape(sci)}"]`)?.focus();
  });
  box.querySelectorAll('.seg button[data-cat]').forEach(b => b.addEventListener('click', () => { state.plantCat = b.dataset.cat; render(); }));
  box.querySelectorAll('[data-src]').forEach(b => b.addEventListener('click', () => setSources(b.dataset.src)));
  on('#listSel', 'change', e => { state.listId = e.target.value; render(); });
  on('#mapBtn', 'click', () => showSpeciesOnMap(state.mapped === state.open ? null : state.open));
}

// One butterfly's sightings as dots
function showSpeciesOnMap(sci) {
  state.mapped = sci;
  drawSpeciesDots(true);
  if (state.point) render();
}
function drawSpeciesDots(zoom) {
  dotLayer?.remove(); dotLayer = null;
  if (!state.mapped) { banner.remove(); return; }
  const pts = observations.filter(o => o.scientificName === state.mapped && (!state.year || o._year === state.year));
  const name = pts[0]?.commonName || state.mapped;
  dotLayer = L.layerGroup(pts.map(o => {
    const m = L.circleMarker([o.lat, o.lng], {
      renderer: dotRenderer, radius: 4, weight: 1, color: '#ffffff', fillColor: o.source === 'inat' ? '#3f7cac' : '#e79a3c', fillOpacity: 0.9,
      bubblingMouseEvents: o.source !== 'inat',   // iNat dots open a popup instead of moving your spot
    }).bindTooltip(`${esc(name)} · ${fmtDate(o.observedOn)} · ${srcInfo(o.source).short}`);
    if (o.source === 'inat') m.bindPopup(`${esc(name)}<br>${fmtDate(o.observedOn)}${o.obscured ? ' <small>(location blurred)</small>' : ''}<br>
      <a href="https://www.inaturalist.org/observations/${o.rid}" target="_blank" rel="noopener">View on iNaturalist</a>`);
    return m;
  })).addTo(map);
  if (zoom && pts.length) map.fitBounds(L.latLngBounds(pts.map(o => [o.lat, o.lng])), { padding: [30, 30], maxZoom: 9 });
  if (!banner.getContainer() || !banner.getContainer().parentNode) banner.addTo(map);
  const d = banner.getContainer();
  const srcs = activeSources(), n = k => pts.filter(o => o.source === k).length;
  d.innerHTML = srcs.length > 1
    ? `<span>Showing <b>${esc(name)}</b>:</span>${srcs.map(k => `<span class="key"><span class="dot ${k}"></span>${fmt(n(k))} ${srcInfo(k).short}</span>`).join('')}<button type="button">Clear</button>`
    : `<span class="dot ${srcs[0]}"></span><span>Showing <b>${esc(name)}</b> · ${plural(pts.length, 'sighting')}</span><button type="button">Clear</button>`;
  d.querySelector('button').addEventListener('click', () => showSpeciesOnMap(null));
}

// Shareable link: #at=lat,lng&r=15&view=region&year=2023&month=6&sp=Papilio+rutulus&src=inat
function updateHash() {
  const parts = [];
  if (state.point) {
    // ~100 m: close enough to show the same results, without pinpointing someone's house
    parts.push(`at=${state.point.lat.toFixed(3)},${state.point.lng.toFixed(3)}`);
    if (state.radiusKm !== 15) parts.push(`r=${state.radiusKm}`);
    if (state.scope === 'region') parts.push('view=region');
    if (state.year) parts.push(`year=${state.year}`);
    if (state.month !== '') parts.push(`month=${+state.month + 1}`);   // 1 = January
    if (state.open) parts.push(`sp=${encodeURIComponent(state.open).replace(/%20/g, '+')}`);
  }
  if (state.sources) parts.push(`src=${state.sources.join(',')}`);
  const s = parts.join('&');
  history.replaceState(null, '', location.pathname + location.search + (s ? '#' + s : ''));
}
function restoreFromHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const src = (h.get('src') || '').split(',').filter(k => loaded.includes(k));
  if (src.length && src.length < loaded.length) { state.sources = src; applySources(); }
  const at = (h.get('at') || '').split(',').map(Number);
  if (at.length !== 2 || at.some(isNaN)) return false;
  if (RADII.includes(+h.get('r'))) state.radiusKm = +h.get('r');
  if (h.get('view') === 'region') state.scope = 'region';
  if (allYears.includes(h.get('year'))) state.year = h.get('year');
  const m = +h.get('month');
  if (m >= 1 && m <= 12) state.month = String(m - 1);
  setPoint({ lat: at[0], lng: at[1] }, null, false);
  const sp = h.get('sp');
  if (sp && scopeObservations().species.has(sp)) {
    state.open = sp; render();
    document.getElementById('detail')?.scrollIntoView({ block: 'start' });
  }
  return true;
}
