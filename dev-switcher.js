/*
 * Dev mode: option switcher for comparing design options.
 *
 *   Turn on:   add ?dev to any page URL, e.g. http://localhost:8000/?dev
 *   Turn off:  click the × on the switcher, or add ?dev=off to the URL
 *
 * The on/off state is remembered in this browser (localStorage), so normal
 * visitors never see the switcher. To add or rename options, edit PAGES below.
 */
(function () {
  const PAGES = [
    { file: 'index.html',    label: 'Current' },
    { file: 'option-a.html', label: 'A' },
    { file: 'option-b.html', label: 'B' },
    { file: 'option-c.html', label: 'C' },
  ];
  const KEY = 'bimby-dev-mode';

  const store = {
    get() { try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; } },
    set(on) { try { on ? localStorage.setItem(KEY, '1') : localStorage.removeItem(KEY); } catch (e) {} },
  };

  const params = new URLSearchParams(location.search);
  if (params.has('dev')) store.set(!['off', '0', 'false'].includes(params.get('dev')));
  // Without storage the URL flag alone still works; links below carry ?dev along.
  const on = store.get() || (params.has('dev') && !['off', '0', 'false'].includes(params.get('dev')));
  if (!on) return;

  let current = location.pathname.split('/').pop() || 'index.html';
  if (!PAGES.some(p => p.file === current)) current = 'index.html';

  const css = `
    #devSwitch {
      position: fixed; top: 12px; right: 12px; z-index: 2000;
      display: flex; align-items: center; gap: 2px; padding: 4px;
      background: #22301b; border-radius: 999px; border: 1px dashed #e79a3c;
      box-shadow: 0 2px 10px rgba(0,0,0,0.3);
      font: 12px "Helvetica Neue", Helvetica, Arial, sans-serif; color: #f4f6f0;
    }
    #devSwitch .lbl { color: #e79a3c; padding: 0 8px 0 10px; text-transform: uppercase;
                      letter-spacing: 0.1em; font-size: 11px; font-weight: 700; }
    #devSwitch a { color: #f4f6f0; text-decoration: none; padding: 5px 12px; border-radius: 999px; }
    #devSwitch a:hover { background: rgba(255,255,255,0.18); }
    #devSwitch a.on { background: #e79a3c; color: #2b1d06; font-weight: 700; }
    #devSwitch button { background: none; border: none; color: rgba(244,246,240,0.6); cursor: pointer;
                        font-size: 15px; line-height: 1; padding: 4px 8px 4px 6px; }
    #devSwitch button:hover { color: #f4f6f0; }`;

  function mount() {
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    const nav = document.createElement('nav');
    nav.id = 'devSwitch';
    nav.innerHTML = '<span class="lbl">Dev</span>' +
      PAGES.map(p => `<a href="${p.file}?dev"${p.file === current ? ' class="on"' : ''}>${p.label}</a>`).join('') +
      '<button title="Exit dev mode">&times;</button>';
    nav.querySelector('button').addEventListener('click', () => {
      store.set(false);
      nav.remove();
      if (params.has('dev')) { params.delete('dev'); history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params : '')); }
    });
    document.body.appendChild(nav);
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', mount) : mount();
})();
