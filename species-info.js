/*
 * Species descriptions + photos, shared by all map pages.
 *
 * Data: data/species-info.json, built by scripts/build_species_info.py
 *   descriptions = first paragraph of the Wikipedia article (CC BY-SA 4.0)
 *   photos       = iNaturalist taxon photos (licence + credit per photo),
 *                  Wikimedia Commons as a fallback
 * If the file is missing, everything here quietly renders nothing.
 *
 * Usage in a page:
 *   <script src="species-info.js"></script>
 *   SpeciesInfo.load().then(() => rerender());
 *   SpeciesInfo.thumb('Danaus plexippus')             -> small square photo (or blank tile)
 *   SpeciesInfo.card('Danaus plexippus')              -> photo + description + credits
 *   SpeciesInfo.card(name, { layout: 'side' })        -> photo floated left of the text
 */
(function () {
  let info = {};
  let loading = null;

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Styles use currentColor / transparency so they suit both the dark sidebars
  // and the light popup card.
  const css = `
    .spi-thumb { width: 40px; height: 40px; border-radius: 8px; object-fit: cover; flex: 0 0 40px;
                 background: rgba(128,128,128,0.18); display: block; }
    .spi-thumb.sm { width: 32px; height: 32px; flex-basis: 32px; border-radius: 6px; }
    .spi-card { margin: 10px 0 14px; }
    .spi-card::after { content: ""; display: block; clear: both; }
    .spi-fig { margin: 0 0 10px; }
    .spi-fig img { display: block; width: 100%; aspect-ratio: 3 / 2; object-fit: cover; border-radius: 10px;
                   background: rgba(128,128,128,0.18); }
    .spi-card.side .spi-fig { float: left; width: 200px; margin: 2px 16px 8px 0; }
    .spi-cap { font-size: 11px; opacity: 0.65; line-height: 1.35; margin-top: 4px; }
    .spi-desc { font-size: 14px; line-height: 1.55; margin: 0; }
    .spi-desc.clamp { display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }
    .spi-more { background: none; border: 0; padding: 2px 0 0; font: inherit; font-size: 13px; color: inherit;
                opacity: 0.75; cursor: pointer; text-decoration: underline; }
    .spi-more:hover { opacity: 1; }
    .spi-src { font-size: 11px; opacity: 0.65; margin: 6px 0 0; }
    .spi-card a, .spi-cap a { color: inherit; text-decoration: underline; text-decoration-color: rgba(128,128,128,0.6); }
  `;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // "Show more" on long descriptions
  document.addEventListener('click', e => {
    const btn = e.target.closest && e.target.closest('.spi-more');
    if (!btn) return;
    e.stopPropagation();
    const desc = btn.previousElementSibling;
    const open = desc.classList.toggle('clamp');
    btn.textContent = open ? 'Show more' : 'Show less';
  });

  function load() {
    if (!loading) {
      loading = fetch('data/species-info.json')
        .then(r => (r.ok ? r.json() : { species: {} }))
        .then(d => { info = d.species || {}; })
        .catch(() => { info = {}; });
    }
    return loading;
  }

  const get = sci => info[sci] || null;

  function thumb(sci, opts = {}) {
    const p = get(sci)?.photo;
    const cls = 'spi-thumb' + (opts.small ? ' sm' : '');
    return p
      ? `<img class="${cls}" src="${esc(p.square || p.url)}" alt="" loading="lazy" title="${esc(p.attribution || '')}">`
      : `<span class="${cls}" aria-hidden="true"></span>`;
  }

  function card(sci, opts = {}) {
    const e = get(sci);
    if (!e || (!e.photo && !e.wikipedia)) return '';
    const name = e.commonName ? `${e.commonName} (${sci})` : sci;
    let html = `<div class="spi-card ${opts.layout === 'side' ? 'side' : ''}">`;
    if (e.photo) {
      const credit = esc(e.photo.attribution || '');
      html += `<figure class="spi-fig">
          <a href="${esc(e.photo.page || e.photo.url)}" target="_blank" rel="noopener"><img src="${esc(e.photo.url)}" alt="${esc(name)}" loading="lazy"></a>
          <figcaption class="spi-cap">Photo: ${credit}${e.photo.source ? ` · via <a href="${esc(e.photo.page || e.photo.url)}" target="_blank" rel="noopener">${esc(e.photo.source)}</a>` : ''}</figcaption>
        </figure>`;
    }
    if (e.wikipedia) {
      const long = e.wikipedia.extract.length > 420;
      html += `<p class="spi-desc ${long ? 'clamp' : ''}">${esc(e.wikipedia.extract)}</p>`;
      if (long) html += `<button class="spi-more" type="button">Show more</button>`;
      if (!e.wikipedia.custom) {
        html += `<p class="spi-src">From <a href="${esc(e.wikipedia.url)}" target="_blank" rel="noopener">Wikipedia</a>
          (<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>)</p>`;
      }
    }
    return html + '</div>';
  }

  window.SpeciesInfo = { load, get, thumb, card };
})();
