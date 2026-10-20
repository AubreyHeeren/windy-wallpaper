"""JavaScript injected into the Windy page: autoplay + looping, frame-rate cap, weather panel."""
import json

_LOOP_JS = r"""
(function () {
  window.__windyOpts = __OPTS__;
  if (window.__windyLoopInstalled) return;
  window.__windyLoopInstalled = true;

  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };

  // Windy marks its play/pause button with a data-ref="play" attribute.
  function findPlay() {
    for (const n of document.querySelectorAll(
      '[data-ref="play"], [data-ref="playpause"], #playpause, #play-pause, .play-pause, [data-do="play"], [data-do="playpause"]')) {
      if (vis(n)) return n;
    }
    for (const n of document.querySelectorAll('*')) {
      for (const a of n.attributes) {
        if (a.name.indexOf('data-ref') === 0 && a.value === 'play' && vis(n)) return n;
      }
    }
    const re = /(^|[^a-z])(play|pause)/i;
    for (const n of document.querySelectorAll('[id],[class],[aria-label],[title]')) {
      const s = [n.id, typeof n.className === 'string' ? n.className : '',
                 n.getAttribute('aria-label'), n.getAttribute('title')].join(' ');
      if (re.test(s) && vis(n)) return n;
    }
    return null;
  }

  function safeReload() {
    if (window.__windyOffline || navigator.onLine === false) return;   // never swap the map for an error page
    try {
      const k = '__windyReloadAt', t = +sessionStorage.getItem(k) || 0;
      if (Date.now() - t < 60000) return;
      sessionStorage.setItem(k, String(Date.now()));
    } catch (e) {}
    location.reload();
  }

  // What is the animation doing right now? Prefer Windy's own timeline timestamp; otherwise
  // fall back to a fingerprint of the page text and inline styles (the progress marker moves).
  // Our own weather panel (it has a ticking clock) is excluded from the fingerprint.
  function sample() {
    let ts = null;
    try { if (window.W && window.W.store && typeof window.W.store.get === 'function') ts = window.W.store.get('timestamp'); } catch (e) {}
    if (typeof ts === 'number' && isFinite(ts)) return { ts: ts, key: 'ts:' + ts };
    const panel = document.getElementById('windy-wp-panel');
    const texts = [];
    Array.prototype.forEach.call(document.body ? document.body.children : [], n => { if (n !== panel) texts.push(n.innerText || ''); });
    const styles = [];
    document.querySelectorAll('[style]').forEach((n, i) => {
      if (i < 600 && !(panel && (n === panel || panel.contains(n)))) styles.push(n.getAttribute('style'));
    });
    return { ts: null, key: texts.join('|') + '|' + styles.join(';') };
  }

  const changes = [];                                  // times the animation advanced
  const recent = ms => { const now = Date.now(); while (changes.length && now - changes[0] > 20000) changes.shift();
                         return changes.filter(t => now - t <= ms).length; };
  let lastKey = null, lastTs = null, stalled = 0, rewound = false, wasPlaying = false;
  let autoDone = false, clickedAt = 0, attempts = 0;
  const t0 = Date.now();
  const press = () => { const b = findPlay(); if (b) b.click(); clickedAt = Date.now(); return !!b; };

  setInterval(() => {
    const o = window.__windyOpts || {};
    if (document.hidden || window.__windyPaused) { stalled = 0; changes.length = 0; return; }

    const s = sample();
    if (s.key !== lastKey) {
      if (s.ts !== null && lastTs !== null && s.ts < lastTs) rewound = true;   // jumped back to the start: cycle over
      lastKey = s.key; if (s.ts !== null) lastTs = s.ts;
      changes.push(Date.now()); stalled = 0;
    } else { stalled++; }
    const age = (Date.now() - t0) / 1000;

    if (stalled < 3 && recent(20000) >= 5) {           // clearly animating
      attempts = 0; rewound = false;
      if (age >= 15) wasPlaying = true;
    }

    // Start the animation once, unless the page is already animating by itself.
    if (o.autoplay && !autoDone && age > 12) {
      autoDone = true;
      if (recent(6000) < 3) press();
    }

    if (!o.loop || age < 15) return;

    // Loop: the animation is not advancing any more -> press play again (twice at most),
    // and if it was running before and still won't start, reload the page.
    const tsMode = s.ts !== null;
    const ended = tsMode ? stalled >= (rewound ? 2 : 6) : (wasPlaying && stalled >= 8);
    if (!ended || Date.now() - clickedAt < 10000) return;
    if (attempts < 2) { attempts++; press(); return; }
    if (wasPlaying) safeReload();
  }, 1000);
})();
"""

# Caps requestAnimationFrame to window.__windyFps (0 = uncapped) to save GPU/CPU.
_PERF_JS = r"""
(function () {
  if (window.__windyRafPatched) return;
  window.__windyRafPatched = true;
  const origRaf = window.requestAnimationFrame.bind(window);
  const origCancel = window.cancelAnimationFrame.bind(window);
  const live = new Map(), lastByCb = new WeakMap();
  let nextId = 1;
  window.requestAnimationFrame = function (cb) {
    const id = nextId++;
    const step = ts => {
      if (!live.has(id)) return;
      const fps = window.__windyFps || 0;
      const last = lastByCb.get(cb) || 0;
      if (fps && ts - last < 1000 / fps - 2) { live.set(id, origRaf(step)); return; }
      live.delete(id); lastByCb.set(cb, ts); cb(ts);
    };
    live.set(id, origRaf(step));
    return id;
  };
  window.cancelAnimationFrame = function (id) {
    const h = live.get(id);
    if (h !== undefined) origCancel(h);
    live.delete(id);
  };
})();
"""

# Weather panel drawn on top of the map. Config via __CFG__, data via window.__windyPanelUpdate(data).
_PANEL_JS = r"""
(function () {
  window.__windyPanelCfg = __CFG__;
  if (!window.__windyPanelInstalled) {
    window.__windyPanelInstalled = true;
    window.__windyPanelData = null;
    const el = document.createElement('div');
    el.id = 'windy-wp-panel';
    document.body.appendChild(el);

    window.__windyPanelRender = function () {
      const c = window.__windyPanelCfg, d = window.__windyPanelData, p = document.getElementById('windy-wp-panel');
      if (!p) return;
      if (!c.enabled) { p.style.display = 'none'; return; }
      const sc = c.scale, dpr = window.devicePixelRatio || 1;
      Object.assign(p.style, {
        display: 'block', position: 'fixed', zIndex: '2147483647', pointerEvents: 'none', color: '#fff',
        fontFamily: '"Segoe UI", system-ui, sans-serif', background: 'rgba(10,20,35,' + c.opacity + ')',
        borderRadius: (14 * sc) + 'px', padding: (12 * sc) + 'px ' + (16 * sc) + 'px', minWidth: (190 * sc) + 'px',
        boxShadow: '0 4px 18px rgba(0,0,0,.35)', fontSize: (14 * sc) + 'px', lineHeight: '1.35', left: '0px', top: '0px'
      });
      while (p.firstChild) p.removeChild(p.firstChild);
      const add = (text, css) => { const n = document.createElement('div'); n.textContent = text; if (css) Object.assign(n.style, css); p.appendChild(n); };

      if (c.clock !== 'off') {
        const now = new Date();
        add(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: c.clock === '12h' }),
            { fontSize: (30 * sc) + 'px', fontWeight: '600', lineHeight: '1.1' });
        add(now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' }),
            { opacity: '0.75', marginBottom: (8 * sc) + 'px' });
      }
      if (!d) {
        add('Loading weather...', { opacity: '0.75' });
      } else {
        if (d.place) add(d.place, { textTransform: 'uppercase', letterSpacing: '.08em', fontSize: (11 * sc) + 'px', opacity: '0.7' });
        add(d.temp + '  ' + d.cond, { fontSize: (20 * sc) + 'px', fontWeight: '600' });
        add('Rain ' + d.rain + '   Wind ' + d.wind, { opacity: '0.85' });
        add(d.storm, { marginTop: (4 * sc) + 'px', color: d.alert ? '#ffcf5a' : '#9fe0a8', fontWeight: '600' });
        if (d.offline) add('Offline - showing last data', { opacity: '0.6', fontSize: (11 * sc) + 'px' });
      }

      const a = c.anchor || [0, 0, window.innerWidth * dpr, window.innerHeight * dpr];
      const ax = a[0] / dpr, ay = a[1] / dpr, aw = a[2] / dpr, ah = a[3] / dpr, m = 16 * sc;
      const pw = p.offsetWidth, ph = p.offsetHeight;
      p.style.left = (c.corner.indexOf('right') >= 0 ? ax + aw - pw - m : ax + m) + 'px';
      p.style.top = (c.corner.indexOf('bottom') >= 0 ? ay + ah - ph - m : ay + m) + 'px';
    };
    window.__windyPanelUpdate = function (data) { window.__windyPanelData = data; window.__windyPanelRender(); };
    setInterval(window.__windyPanelRender, 1000);
  }
  window.__windyPanelRender();
})();
"""


def build_loop_js(autoplay, loop):
    return _LOOP_JS.replace("__OPTS__", json.dumps({"autoplay": bool(autoplay), "loop": bool(loop)}))


def build_perf_js():
    return _PERF_JS


def build_panel_js(cfg):
    return _PANEL_JS.replace("__CFG__", json.dumps(cfg))
