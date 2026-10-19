"""Settings window (HTML UI) + city search for Windy Live Wallpaper."""
import json
import urllib.parse
import urllib.request


def search_city(query, count=8):
    q = (query or "").strip()
    if len(q) < 2:
        return {"ok": True, "results": []}
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": q, "count": count, "language": "en", "format": "json"}
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WindyLiveWallpaper/1.1"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    results = []
    for x in data.get("results", []) or []:
        label = ", ".join(p for p in (x.get("name"), x.get("admin1"), x.get("country")) if p)
        results.append({"label": label, "name": x.get("name", ""),
                        "lat": x["latitude"], "lon": x["longitude"]})
    return {"ok": True, "results": results}


class SettingsApi:
    """Exposed to the settings page as window.pywebview.api (underscore attrs stay private)."""

    def __init__(self, app):
        self._app = app

    def get_state(self):
        return self._app.get_state()

    def search_city(self, query):
        return search_city(query)

    def apply(self, data):
        return self._app.update_settings(data)

    def add_place(self, name, lat, lon, zoom):
        return self._app.add_place(name, lat, lon, zoom)

    def remove_place(self, index):
        return self._app.remove_place(index)

    def go_to_place(self, index):
        return self._app.go_to_place(index)

    def set_autostart(self, enable):
        self._app.set_autostart(bool(enable))
        return self._app.get_state()

    def close(self):
        self._app.close_settings()


SETTINGS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Settings</title>
<style>
:root{color-scheme:dark;--bg:#0f1b2d;--card:#172640;--line:#27395a;--fg:#e8eefb;--mut:#8fa3c7;--acc:#4da3ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px "Segoe UI",system-ui,sans-serif;padding:16px 16px 0}
h1{font-size:18px;margin:0 0 12px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:12px}
h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:0 0 8px}
label{display:block;margin:8px 0 4px;color:var(--mut);font-size:12px}
input[type=text],input[type=number],select{width:100%;padding:7px 9px;border-radius:7px;border:1px solid var(--line);background:#0d1829;color:var(--fg)}
input[type=range]{width:100%}
.row{display:flex;gap:8px;align-items:center}
.row>*{flex:1}
.check{display:flex;align-items:center;gap:8px;margin:6px 0}
button{background:var(--acc);color:#04111f;border:0;border-radius:7px;padding:7px 12px;font-weight:600;cursor:pointer}
button.sec{background:#243a5e;color:var(--fg)}
.res,.place{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--line);border-radius:7px;margin-top:6px}
.res{cursor:pointer}.res:hover{border-color:var(--acc)}
.mut{color:var(--mut);font-size:12px}
.bar{position:sticky;bottom:0;display:flex;gap:8px;justify-content:flex-end;background:var(--bg);padding:10px 0}
#status{align-self:center;color:#6fdc8c;margin-right:auto}
</style></head><body>
<h1>Windy Live Wallpaper</h1>

<section><h2>Location</h2>
  <input type="text" id="q" placeholder="Search a city, e.g. Bloemfontein" autocomplete="off">
  <div id="results"></div>
  <div class="row"><div><label>Latitude</label><input type="number" id="lat" step="0.001"></div>
  <div><label>Longitude</label><input type="number" id="lon" step="0.001"></div></div>
  <label>Zoom: <span id="zoomv"></span></label><input type="range" id="zoom" min="3" max="12">
</section>

<section><h2>Map</h2>
  <div class="row"><div><label>Overlay</label><select id="overlay"></select></div>
  <div><label>Forecast model</label><select id="product"></select></div></div>
  <label>Refresh every <span id="refreshv"></span> min</label><input type="range" id="refresh" min="5" max="240" step="5">
  <div class="check"><input type="checkbox" id="pressure_isolines"><span>Show pressure lines</span></div>
  <div class="check"><input type="checkbox" id="autoplay"><span>Auto-play the animation</span></div>
</section>

<section><h2>Smart pause</h2>
  <div class="mut" id="pausedNote"></div>
  <div class="check"><input type="checkbox" id="pause_fullscreen"><span>Pause when a fullscreen app or game is running</span></div>
  <div class="check"><input type="checkbox" id="pause_locked"><span>Pause when the screen is locked</span></div>
  <div class="check"><input type="checkbox" id="pause_battery_saver"><span>Pause when Battery Saver is on</span></div>
  <div class="check"><input type="checkbox" id="pause_on_battery"><span>Pause whenever running on battery</span></div>
</section>

<section><h2>Saved places</h2>
  <div class="row"><input type="text" id="placename" placeholder="Name for current location"><button class="sec" id="addplace" style="flex:0 0 auto">Save place</button></div>
  <div id="places"></div>
</section>

<section><h2>General</h2>
  <div class="check"><input type="checkbox" id="autostart"><span>Start with Windows</span></div>
  <label>Custom Windy URL (advanced, overrides the options above)</label>
  <input type="text" id="custom_url" placeholder="leave empty to use the options above">
</section>

<div class="bar"><span id="status"></span><button class="sec" id="close">Close</button><button id="save">Save &amp; apply</button></div>

<script>
const $ = id => document.getElementById(id);
const BOOLS = ['pressure_isolines','autoplay','pause_fullscreen','pause_locked','pause_battery_saver','pause_on_battery'];
let S = null, timer = null, flashTimer = null;
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function flash(msg){ $('status').textContent = msg; clearTimeout(flashTimer); flashTimer = setTimeout(() => $('status').textContent = '', 3000); }

function fill(){
  const c = S.config;
  $('lat').value = c.lat; $('lon').value = c.lon;
  $('zoom').value = c.zoom; $('zoomv').textContent = c.zoom;
  $('refresh').value = c.refresh_minutes; $('refreshv').textContent = c.refresh_minutes;
  const ov = $('overlay'); ov.innerHTML = '';
  for (const [k, v] of Object.entries(S.overlays)) ov.add(new Option(k, v));
  ov.value = c.overlay;
  const pr = $('product'); pr.innerHTML = '';
  S.products.forEach(p => pr.add(new Option(p, p)));
  pr.value = c.product;
  BOOLS.forEach(id => $(id).checked = !!c[id]);
  $('custom_url').value = c.custom_url || '';
  $('autostart').checked = !!S.autostart;
  $('pausedNote').textContent = S.paused ? ('Currently paused: ' + S.paused) : '';
  renderPlaces();
}

function collect(){
  const o = {
    lat: parseFloat($('lat').value), lon: parseFloat($('lon').value),
    zoom: parseInt($('zoom').value), overlay: $('overlay').value, product: $('product').value,
    refresh_minutes: parseInt($('refresh').value), custom_url: $('custom_url').value.trim()
  };
  BOOLS.forEach(id => o[id] = $(id).checked);
  return o;
}

function renderPlaces(){
  const box = $('places'); box.innerHTML = '';
  const ps = S.config.places || [];
  if (!ps.length){ box.innerHTML = '<div class="mut" style="margin-top:6px">No saved places yet.</div>'; return; }
  ps.forEach((p, i) => {
    const d = document.createElement('div'); d.className = 'place';
    d.innerHTML = '<span>' + esc(p.name) + ' <span class="mut">' + p.lat + ', ' + p.lon + '</span></span>';
    const b = document.createElement('span');
    const go = document.createElement('button'); go.className = 'sec'; go.textContent = 'Show';
    go.onclick = async () => { S = await pywebview.api.go_to_place(i); fill(); flash('Switched to ' + p.name); };
    const rm = document.createElement('button'); rm.className = 'sec'; rm.textContent = 'Remove';
    rm.onclick = async () => { S = await pywebview.api.remove_place(i); fill(); };
    b.append(go, ' ', rm); d.appendChild(b); box.appendChild(d);
  });
}

async function search(){
  const q = $('q').value.trim(), box = $('results'); box.innerHTML = '';
  if (q.length < 2) return;
  const r = await pywebview.api.search_city(q);
  if (!r.ok){ box.innerHTML = '<div class="mut">Search failed: ' + esc(r.error) + '</div>'; return; }
  if (!r.results.length){ box.innerHTML = '<div class="mut">No matches</div>'; return; }
  r.results.forEach(x => {
    const d = document.createElement('div'); d.className = 'res';
    d.innerHTML = '<span>' + esc(x.label) + '</span><span class="mut">' + x.lat.toFixed(2) + ', ' + x.lon.toFixed(2) + '</span>';
    d.onclick = () => {
      $('lat').value = x.lat; $('lon').value = x.lon; $('placename').value = x.name;
      box.innerHTML = '<div class="mut" style="margin-top:6px">Selected ' + esc(x.label) + ' - press Save &amp; apply</div>';
    };
    box.appendChild(d);
  });
}

$('q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 400); });
$('zoom').oninput = () => $('zoomv').textContent = $('zoom').value;
$('refresh').oninput = () => $('refreshv').textContent = $('refresh').value;
$('addplace').onclick = async () => {
  const lat = parseFloat($('lat').value), lon = parseFloat($('lon').value);
  if (isNaN(lat) || isNaN(lon)) return flash('Enter a location first');
  S = await pywebview.api.add_place($('placename').value || '', lat, lon, parseInt($('zoom').value));
  fill(); flash('Place saved');
};
$('save').onclick = async () => {
  await pywebview.api.set_autostart($('autostart').checked);
  S = await pywebview.api.apply(collect());
  fill(); flash('Saved and applied');
};
$('close').onclick = () => pywebview.api.close();
window.addEventListener('pywebviewready', async () => { S = await pywebview.api.get_state(); fill(); });
</script></body></html>
"""
