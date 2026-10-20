"""JavaScript injected into the Windy page: autoplay + continuous looping."""
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
    try {
      const k = '__windyReloadAt', t = +sessionStorage.getItem(k) || 0;
      if (Date.now() - t < 60000) return;
      sessionStorage.setItem(k, String(Date.now()));
    } catch (e) {}
    location.reload();
  }

  // What is the animation doing right now? Prefer Windy's own timeline timestamp; otherwise
  // fall back to a fingerprint of the page text and inline styles (the progress marker moves).
  function sample() {
    let ts = null;
    try { if (window.W && window.W.store && typeof window.W.store.get === 'function') ts = window.W.store.get('timestamp'); } catch (e) {}
    if (typeof ts === 'number' && isFinite(ts)) return { ts: ts, key: 'ts:' + ts };
    const styles = [];
    document.querySelectorAll('[style]').forEach((n, i) => { if (i < 600) styles.push(n.getAttribute('style')); });
    return { ts: null, key: (document.body ? document.body.innerText : '') + '|' + styles.join(';') };
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


def build_loop_js(autoplay, loop):
    return _LOOP_JS.replace("__OPTS__", json.dumps({"autoplay": bool(autoplay), "loop": bool(loop)}))
