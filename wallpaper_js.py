"""JavaScript injected into the Windy page: autoplay + continuous looping."""
import json

_LOOP_JS = r"""
(function () {
  window.__windyOpts = __OPTS__;
  if (window.__windyLoopInstalled) return;
  window.__windyLoopInstalled = true;

  const RE = /(^|[^a-z])(play|pause)/i;
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  function findPlay() {
    const known = document.querySelector(
      '#playpause, #play-pause, .play-pause, [data-do="play"], [data-do="playpause"], [data-do="pause"]');
    if (known && vis(known)) return known;
    for (const n of document.querySelectorAll('[id],[class],[data-do],[aria-label],[title]')) {
      const s = [n.id, typeof n.className === 'string' ? n.className : '',
                 n.getAttribute('data-do'), n.getAttribute('aria-label'), n.getAttribute('title')].join(' ');
      if (RE.test(s) && vis(n)) return n;
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

  const changes = [];                       // times the page text changed (= animation frames)
  const recent = ms => { const now = Date.now(); while (changes.length && now - changes[0] > 20000) changes.shift();
                         return changes.filter(t => now - t <= ms).length; };
  let last = '', stalled = 0, wasPlaying = false, restartAt = 0, autoDone = false;
  const t0 = Date.now();

  setInterval(() => {
    const o = window.__windyOpts || {};
    if (document.hidden || window.__windyPaused) { stalled = 0; changes.length = 0; return; }
    const sig = document.body ? document.body.innerText : '';
    if (sig !== last) { last = sig; changes.push(Date.now()); stalled = 0; } else { stalled++; }
    const age = (Date.now() - t0) / 1000;

    if (stalled < 3 && recent(20000) >= 5 && age >= 15) { wasPlaying = true; restartAt = 0; }

    // Start the animation once, unless the page is already animating by itself.
    if (o.autoplay && !autoDone && age > 12) {
      autoDone = true;
      if (recent(6000) < 3) { const b = findPlay(); if (b) b.click(); }
    }

    // Loop: the cycle finished (animation was running, now nothing changes) -> play again.
    if (!o.loop || !wasPlaying || stalled < 8) return;
    if (!restartAt) { restartAt = Date.now(); const b = findPlay(); if (b) b.click(); return; }
    if (Date.now() - restartAt > 12000) safeReload();   // pressing play did nothing: reload the page
  }, 1000);
})();
"""


def build_loop_js(autoplay, loop):
    return _LOOP_JS.replace("__OPTS__", json.dumps({"autoplay": bool(autoplay), "loop": bool(loop)}))
