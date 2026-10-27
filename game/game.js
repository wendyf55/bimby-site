/*
 * The guessing game behind game/index.html.
 * A random spot in BC is picked, and the butterflies recorded within 15 km of it in the
 * last 10 years are shown. The player clicks the map to guess the spot, then presses Reveal
 * to see how far off they were (distance to the edge of the 15 km circle).
 * Uses the same data files as the main map (../data/), both sources.
 */
const AREA_KM = 15;          // radius of the hidden area
const MIN_SPECIES = 5;       // an area needs at least this many species to be used
const YEARS_BACK = 10;       // only records from the last 10 years
const MIN_KM_FROM_LAST = 50; // a new area is never right next to the previous one
const MAX_TRIES = 400;
const SOURCES = ['../data/observations-sg.json', '../data/observations-inat.json'];

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => n.toLocaleString('en-CA');
const rand = n => Math.floor(Math.random() * n);
const TOUCH = window.matchMedia('(pointer: coarse)').matches;
const CUTOFF = (() => { const d = new Date(); d.setFullYear(d.getFullYear() - YEARS_BACK); return d.toISOString().slice(0, 10); })();

// Great-circle distance in km
function distKm(a, b) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

// Map (same limits as the main page)
const BC_BOUNDS = [[48.2, -139.1], [60.0, -114.0]];
const NA_BOUNDS = [[7.0, -170.0], [84.0, -50.0]];
const VIEW_BOUNDS = [[44.0, -152.0], [65.0, -100.0]];
const map = L.map('map', {
  zoomSnap: 0.25, maxBounds: VIEW_BOUNDS, maxBoundsViscosity: 1.0, worldCopyJump: false
}).fitBounds(BC_BOUNDS);
const lockZoomToBC = () => map.setMinZoom(Math.max(0, map.getBoundsZoom(BC_BOUNDS) - 0.5));
lockZoomToBC();
map.on('resize', lockZoomToBC);
window.addEventListener('resize', () => map.invalidateSize());
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, bounds: NA_BOUNDS, noWrap: true,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);
const guessIcon = L.divIcon({ className: '', html: '<div class="you-pin"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });

// Records: [{ lat, lng, sci, region }], last 10 years, exact locations only
let recs = [], byRegion = new Map(), commonNames = {};
let photos = {};   // scientific name -> { url, attribution, … } from ../data/species-info.json
const game = { centre: null, species: [], guess: null, revealed: false };
let guessMarker = null, answerLayer = null;

const content = document.getElementById('content');
const bar = document.getElementById('bar'), barMsg = document.getElementById('bar-msg'), barBtn = document.getElementById('bar-btn');
const announce = document.getElementById('announce');

const loadSource = file => fetch(file).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .catch(err => { console.warn(`${file} not loaded`, err); return null; });

// Photos: read species-info.json directly (not through species-info.js, which looks for
// data/ next to the page). If it fails, the cards just have no photos.
const loadPhotos = fetch('../data/species-info.json').then(r => (r.ok ? r.json() : {}))
  .then(d => { for (const [sci, e] of Object.entries(d.species || {})) { if (e.photo) photos[sci] = e.photo; if (e.commonName) commonNames[sci] ??= e.commonName; } })
  .catch(err => console.warn('photos not loaded', err));

Promise.all([...SOURCES.map(loadSource), loadPhotos]).then(results => {
  for (const d of results.slice(0, SOURCES.length).filter(Boolean)) {
    const f = Object.fromEntries(d.fields.map((k, i) => [k, i]));
    for (const r of d.rows) {
      if (r[f.flags] & 1) continue;                    // obscured iNat location (blurred ~20 km)
      if (!(r[f.date] >= CUTOFF)) continue;
      const [sci, common] = d.species[r[f.sp]];
      if (common) commonNames[sci] = common;
      const region = r[f.region] ?? 'none';
      if (!byRegion.has(region)) byRegion.set(region, []);
      byRegion.get(region).push(recs.length);
      recs.push({ lat: r[f.lat], lng: r[f.lng], sci, region });
    }
  }
  if (!recs.length) throw new Error('no observation data');
  newRound();
}).catch(err => {
  content.innerHTML = '<p class="sub">Sorry, the butterfly data could not be loaded.</p>';
  console.error(err);
});

// Species recorded within AREA_KM of a spot, most records first
function speciesNear(c) {
  const dLat = AREA_KM / 111.2, dLng = dLat / Math.cos(c.lat * Math.PI / 180);
  const counts = new Map();
  for (const r of recs) {
    if (Math.abs(r.lat - c.lat) > dLat || Math.abs(r.lng - c.lng) > dLng) continue;
    if (distKm(c, r) <= AREA_KM) counts.set(r.sci, (counts.get(r.sci) || 0) + 1);
  }
  return [...counts].map(([sci, n]) => ({ sci, n, common: commonNames[sci] || '' }))
    .sort((a, b) => b.n - a.n || (a.common || a.sci).localeCompare(b.common || b.sci));
}

// Pick an area: a random ecoregion first (so areas are spread across BC, not mostly
// around Vancouver and Victoria), then a random record in it as the centre.
// The area needs MIN_SPECIES species. Falls back to any record if that keeps failing.
function pickArea() {
  const regionKeys = [...byRegion.keys()], last = game.centre;
  for (let t = 0; t < MAX_TRIES * 2; t++) {
    const idx = t < MAX_TRIES ? (l => l[rand(l.length)])(byRegion.get(regionKeys[rand(regionKeys.length)])) : rand(recs.length);
    const r = recs[idx], centre = { lat: r.lat, lng: r.lng };
    if (last && distKm(last, centre) < MIN_KM_FROM_LAST) continue;
    const species = speciesNear(centre);
    if (species.length >= MIN_SPECIES) return { centre, species };
  }
  return null;
}

function newRound() {
  const area = pickArea();
  if (!area) { content.innerHTML = '<p class="sub">Sorry, no area with enough butterflies was found.</p>'; return; }
  Object.assign(game, area, { guess: null, revealed: false });
  if (guessMarker) { guessMarker.remove(); guessMarker = null; }
  if (answerLayer) { answerLayer.remove(); answerLayer = null; }
  map.fitBounds(BC_BOUNDS);
  map.getContainer().classList.add('guessing');
  renderPanel();
  renderBar();
  content.scrollTop = 0;
  window.scrollTo(0, 0);
  say(`New round: ${game.species.length} species to guess from.`);
}

// Photo credits in the data are HTML-escaped (e.g. "Libby &amp; Rick Avis"), so decode before re-escaping.
const unescapeHTML = s => { const t = document.createElement('textarea'); t.innerHTML = s; return t.value; };

// Short photo credit for under a card, e.g. "© Nick Block" (the full licence text is in its tooltip)
function photoCredit(p) {
  const a = unescapeHTML(p.attribution || '');
  let m = /^\(c\)\s*(?:\d{4}\s+)?([^,]+)/i.exec(a);
  if (m) return `© ${m[1].trim()}`;
  m = /uploaded by (.+)$/i.exec(a);                     // public-domain (CC0) iNaturalist photos
  return `Photo: ${(m ? m[1] : a.split(',')[0]).trim()}`;
}

function renderPanel() {
  const n = game.species.length;
  content.innerHTML = `
    <h2 class="lead">Where were these butterflies seen?</h2>
    <p class="sub">All ${n} species below were recorded within ${AREA_KM} km of one spot in British Columbia
      in the last ${YEARS_BACK} years. ${TOUCH ? 'Tap' : 'Click'} the map where you think that spot is, then press Reveal.</p>
    <ul class="g-list">${game.species.map(s => {
      const p = photos[s.sci];
      return `<li class="g-card">
        ${p ? `<img src="${esc(p.url)}" alt="" loading="lazy">` : '<span class="g-nophoto" aria-hidden="true"></span>'}
        <div class="g-name">${esc(s.common || s.sci)}</div>
        ${s.common ? `<div class="g-sci">${esc(s.sci)}</div>` : ''}
        <div class="g-credit" title="${esc(unescapeHTML(p?.attribution || ''))}">${p ? esc(photoCredit(p)) : '&nbsp;'}</div>
      </li>`;
    }).join('')}</ul>
    <p class="g-note">Records from Guppy &amp; Shepard and iNaturalist. Photos from iNaturalist.</p>`;
}

function renderBar() {
  bar.hidden = false;
  if (game.revealed) {
    const km = Math.max(0, distKm(game.guess, game.centre) - AREA_KM);
    barMsg.textContent = km === 0 ? 'Your guess is inside the area!'
      : km < 1 ? 'Your guess was less than 1 km from the area.'
        : `Your guess was ${fmt(Math.round(km))} km from the area.`;
    barBtn.textContent = 'Play again';
    barBtn.disabled = false;
  } else {
    const verb = TOUCH ? 'Tap' : 'Click';
    barMsg.textContent = game.guess ? `${verb} again to move your guess` : `${verb} the map to place your guess`;
    barBtn.textContent = 'Reveal';
    barBtn.disabled = !game.guess;
  }
}

function say(msg) { announce.textContent = ''; setTimeout(() => { announce.textContent = msg; }, 50); }

map.on('click', e => {
  if (!game.centre || game.revealed) return;
  game.guess = { lat: e.latlng.lat, lng: e.latlng.lng };
  if (guessMarker) guessMarker.setLatLng(e.latlng);
  else guessMarker = L.marker(e.latlng, { icon: guessIcon, keyboard: false, title: 'Your guess' }).addTo(map);
  renderBar();
});

barBtn.addEventListener('click', () => {
  if (game.revealed) { newRound(); return; }
  if (!game.guess) return;
  game.revealed = true;
  map.getContainer().classList.remove('guessing');
  const { centre, guess } = game, d = distKm(guess, centre);
  answerLayer = L.layerGroup().addTo(map);
  const circle = L.circle(centre, {
    radius: AREA_KM * 1000, color: '#c97a1c', weight: 3, fillColor: '#e79a3c', fillOpacity: 0.3, interactive: false
  }).addTo(answerLayer);
  if (d > AREA_KM) {
    // dashed line from the guess to the nearest point on the circle's edge
    const t = (d - AREA_KM) / d;
    const edge = [guess.lat + (centre.lat - guess.lat) * t, guess.lng + (centre.lng - guess.lng) * t];
    L.polyline([[guess.lat, guess.lng], edge], { color: '#22301b', weight: 3, dashArray: '6 8', interactive: false }).addTo(answerLayer);
  }
  renderBar();
  // keep the guess and the circle clear of the bar at the bottom of the map
  map.fitBounds(circle.getBounds().extend([guess.lat, guess.lng]),
    { paddingTopLeft: [50, 50], paddingBottomRight: [50, bar.offsetHeight + 60], maxZoom: 10 });
  say(barMsg.textContent);
  barBtn.focus();
});
