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

    def check_update(self):
        return self._app.check_updates_now()

    def install_update(self):
        return self._app.install_update()

    def restart(self):
        self._app.restart_app()

    def close(self):
        self._app.close_settings()


SETTINGS_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Settings</title>
<style>
:root{color-scheme:dark;--bg:#0f1b2d;--card:#172640;--line:#27395a;--fg:#e8eefb;--mut:#8fa3c7;--acc:#4da3ff}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;display:flex;flex-direction:column;overflow:hidden;background:var(--bg);color:var(--fg);font:14px "Segoe UI",system-ui,sans-serif}
main{flex:1;overflow-y:auto;padding:16px 16px 4px}
h1{font-size:18px;margin:0 0 12px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:12px}
h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:0 0 8px}
label{display:block;margin:8px 0 4px;color:var(--mut);font-size:12px}
input[type=text],input[type=number],input[type=time],select{width:100%;padding:7px 9px;border-radius:7px;border:1px solid var(--line);background:#0d1829;color:var(--fg)}
input[type=range]{width:100%}
.row{display:flex;gap:8px;align-items:center}
.row>*{flex:1}
.check{display:flex;align-items:center;gap:8px;margin:6px 0}
button{background:var(--acc);color:#04111f;border:0;border-radius:7px;padding:7px 12px;font-weight:600;cursor:pointer}
button.sec{background:#243a5e;color:var(--fg)}
.res,.place{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--line);border-radius:7px;margin-top:6px}
.res{cursor:pointer}.res:hover{border-color:var(--acc)}
.mut{color:var(--mut);font-size:12px}
.bar{flex:none;display:flex;gap:8px;justify-content:flex-end;background:#0b1524;border-top:1px solid var(--line);padding:10px 16px}
#status{align-self:center;color:#6fdc8c;margin-right:auto}
</style></head><body>
<main>
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
  <div class="check"><input type="checkbox" id="loop_animation"><span>Loop the animation continuously</span></div>
</section>

<section><h2>Smart pause</h2>
  <div class="mut" id="pausedNote"></div>
  <div class="check"><input type="checkbox" id="pause_fullscreen"><span>Pause when a fullscreen app or game is running</span></div>
  <div class="check"><input type="checkbox" id="pause_locked"><span>Pause when the screen is locked</span></div>
  <div class="check"><input type="checkbox" id="pause_battery_saver"><span>Pause when Battery Saver is on</span></div>
  <div class="check"><input type="checkbox" id="pause_on_battery"><span>Pause whenever running on battery</span></div>
</section>

<section><h2>Storm alerts</h2>
  <div class="check"><input type="checkbox" id="alerts_enabled"><span>Notify me about storms and heavy rain</span></div>
  <div class="check"><input type="checkbox" id="alert_thunder"><span>Thunderstorms</span></div>
  <div class="check"><input type="checkbox" id="alert_rain"><span>Heavy rain</span></div>
  <div class="row"><div><label>Warn me this far ahead</label><select id="alert_lead_minutes">
    <option value="30">30 minutes</option><option value="60">1 hour</option><option value="120">2 hours</option><option value="180">3 hours</option><option value="360">6 hours</option></select></div>
  <div><label>Heavy rain means at least</label><select id="alert_rain_mm">
    <option value="2">2 mm/h (moderate)</option><option value="5">5 mm/h (heavy)</option><option value="10">10 mm/h (very heavy)</option></select></div></div>
  <div class="check"><input type="checkbox" id="alert_watch_places"><span>Also watch my saved places</span></div>
  <div class="check"><input type="checkbox" id="auto_switch_overlay"><span>Switch the map to Thunderstorms while a storm is near</span></div>
  <div class="check"><input type="checkbox" id="alert_quiet_hours"><span>Quiet hours (no notifications)</span></div>
  <div class="row"><div><label>From</label><input type="time" id="alert_quiet_start"></div><div><label>Until</label><input type="time" id="alert_quiet_end"></div></div>
</section>

<section><h2>Weather panel</h2>
  <div class="check"><input type="checkbox" id="panel_enabled"><span>Show a weather panel on the wallpaper</span></div>
  <input type="text" id="place_label" placeholder="Name shown on the panel, e.g. Home">
  <div class="row"><div><label>Corner</label><select id="panel_corner">
    <option value="top-right">Top right</option><option value="top-left">Top left</option><option value="bottom-right">Bottom right</option><option value="bottom-left">Bottom left</option></select></div>
  <div><label>Size</label><select id="panel_size"><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></div></div>
  <div class="row"><div><label>Units</label><select id="units"><option value="metric">Metric (&deg;C, km/h)</option><option value="imperial">Imperial (&deg;F, mph)</option></select></div>
  <div><label>Clock</label><select id="panel_clock"><option value="24h">24-hour</option><option value="12h">12-hour</option><option value="off">Hidden</option></select></div></div>
  <label>Opacity: <span id="panel_opacityv"></span>%</label><input type="range" id="panel_opacity" min="30" max="100">
</section>

<section><h2>Performance</h2>
  <label>Animation quality</label>
  <select id="performance"><option value="full">Full (smoothest)</option><option value="balanced">Balanced (30 fps)</option><option value="eco">Eco (15 fps)</option><option value="minimal">Minimal (10 fps, no wind particles)</option></select>
  <div class="check"><input type="checkbox" id="eco_on_battery"><span>Use at least Eco quality when on battery</span></div>
</section>

<section id="monsec" style="display:none"><h2>Monitors</h2>
  <div class="check"><input type="checkbox" id="per_monitor"><span>Different location / overlay on each monitor</span></div>
  <div id="monlist"></div>
  <div id="restartrow" style="display:none;margin-top:8px"><div class="mut">Restart the wallpaper to apply the new monitor layout.</div>
    <button class="sec" id="restartbtn" style="margin-top:6px">Restart now</button></div>
</section>

<section><h2>Saved places</h2>
  <div class="row"><input type="text" id="placename" placeholder="Name for current location"><button class="sec" id="addplace" style="flex:0 0 auto">Save place</button></div>
  <div id="places"></div>
</section>

<section><h2>Updates</h2>
  <div class="mut" id="verline"></div>
  <div class="check"><input type="checkbox" id="check_updates"><span>Check for updates automatically</span></div>
  <div class="row"><button class="sec" id="checknow" style="flex:0 0 auto">Check now</button><button id="installupd" style="display:none;flex:0 0 auto">Install update</button></div>
  <div class="mut" id="updmsg" style="margin-top:6px"></div>
</section>

<section><h2>General</h2>
  <div class="check"><input type="checkbox" id="autostart"><span>Start with Windows</span></div>
  <label>Custom Windy URL (advanced, overrides the options above)</label>
  <input type="text" id="custom_url" placeholder="leave empty to use the options above">
</section>

</main>
<div class="bar"><span id="status"></span><button class="sec" id="close">Close</button><button id="save">Save &amp; apply</button></div>

<script>
const $ = id => document.getElementById(id);
const BOOLS = ['pressure_isolines','autoplay','loop_animation','check_updates','pause_fullscreen','pause_locked','pause_battery_saver','pause_on_battery',
  'alerts_enabled','alert_thunder','alert_rain','alert_watch_places','auto_switch_overlay','alert_quiet_hours','panel_enabled','eco_on_battery','per_monitor'];
const VALUES = ['alert_lead_minutes','alert_rain_mm','alert_quiet_start','alert_quiet_end','panel_corner','panel_size','panel_clock','units','performance','place_label'];
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
  VALUES.forEach(id => $(id).value = String(c[id] == null ? '' : c[id]));
  $('panel_opacity').value = Math.round(c.panel_opacity * 100); $('panel_opacityv').textContent = $('panel_opacity').value;
  $('custom_url').value = c.custom_url || '';
  $('autostart').checked = !!S.autostart;
  $('pausedNote').textContent = S.paused ? ('Currently paused: ' + S.paused) : '';
  renderUpdates();
  renderMonitors();
  renderPlaces();
}

function renderUpdates(){
  $('verline').textContent = 'Version ' + S.version;
  const msgs = { current: "You're up to date.", dev: 'Development build: update checks are disabled.',
                 error: "Couldn't reach GitHub. Try again later." };
  const btn = $('installupd');
  if (S.update){
    $('updmsg').textContent = 'Version ' + S.update.version + ' is available.';
    btn.style.display = ''; btn.textContent = S.can_auto_install ? 'Install update' : 'Open download page';
  } else {
    btn.style.display = 'none'; $('updmsg').textContent = msgs[S.update_status] || '';
  }
}

function renderMonitors(){
  const mons = S.monitors || [], sec = $('monsec');
  sec.style.display = mons.length > 1 ? '' : 'none';
  if (mons.length <= 1) return;
  const box = $('monlist'); box.innerHTML = '';
  const views = S.config.monitor_views || {}, places = S.config.places || [];
  mons.forEach(m => {
    const v = views[m.index] || {};
    const wrap = document.createElement('div');
    wrap.innerHTML = '<label>Monitor ' + (m.index + 1) + (m.primary ? ' (main)' : '') + ' - ' + m.width + 'x' + m.height + '</label>';
    const row = document.createElement('div'); row.className = 'row';
    const pl = document.createElement('select'); pl.id = 'mon_place_' + m.index;
    pl.add(new Option('Main location', ''));
    places.forEach(p => pl.add(new Option(p.name, p.name)));
    pl.value = v.place || '';
    const ov = document.createElement('select'); ov.id = 'mon_overlay_' + m.index;
    ov.add(new Option('Same overlay as main', ''));
    for (const [k, val] of Object.entries(S.overlays)) ov.add(new Option(k, val));
    ov.value = v.overlay || '';
    [pl, ov].forEach(el => el.addEventListener('change', queueSave));
    row.append(pl, ov); wrap.appendChild(row); box.appendChild(wrap);
  });
  updateRestart();
}
function updateRestart(){
  $('restartrow').style.display = (!!S.config.per_monitor !== !!S.per_monitor_active) ? '' : 'none';
}

function collect(){
  const o = {
    lat: parseFloat($('lat').value), lon: parseFloat($('lon').value),
    zoom: parseInt($('zoom').value), overlay: $('overlay').value, product: $('product').value,
    refresh_minutes: parseInt($('refresh').value), custom_url: $('custom_url').value.trim()
  };
  BOOLS.forEach(id => o[id] = $(id).checked);
  VALUES.forEach(id => o[id] = $(id).value);
  o.panel_opacity = parseInt($('panel_opacity').value) / 100;
  o.monitor_views = {};
  (S.monitors || []).forEach(m => {
    const pl = $('mon_place_' + m.index), ov = $('mon_overlay_' + m.index);
    if (pl && ov) o.monitor_views[m.index] = { place: pl.value, overlay: ov.value };
  });
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
      $('lat').value = x.lat; $('lon').value = x.lon; $('placename').value = x.name; $('place_label').value = x.name;
      box.innerHTML = '<div class="mut" style="margin-top:6px">Selected ' + esc(x.label) + '</div>';
      save();
    };
    box.appendChild(d);
  });
}

$('q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 400); });
$('zoom').oninput = () => $('zoomv').textContent = $('zoom').value;
$('refresh').oninput = () => $('refreshv').textContent = $('refresh').value;
$('panel_opacity').oninput = () => $('panel_opacityv').textContent = $('panel_opacity').value;
$('restartbtn').onclick = () => pywebview.api.restart();
$('addplace').onclick = async () => {
  const lat = parseFloat($('lat').value), lon = parseFloat($('lon').value);
  if (isNaN(lat) || isNaN(lon)) return flash('Enter a location first');
  S = await pywebview.api.add_place($('placename').value || '', lat, lon, parseInt($('zoom').value));
  fill(); flash('Place saved');
};
let saveTimer = null, saving = false;
function queueSave(){ clearTimeout(saveTimer); $('status').textContent = 'Saving...'; saveTimer = setTimeout(save, 700); }
function syncFields(){
  const c = S.config;
  [['lat','lat'],['lon','lon'],['zoom','zoom'],['refresh','refresh_minutes']].forEach(([id, key]) => {
    if (document.activeElement !== $(id)) $(id).value = c[key];
  });
  $('zoomv').textContent = $('zoom').value; $('refreshv').textContent = $('refresh').value;
  $('pausedNote').textContent = S.paused ? ('Currently paused: ' + S.paused) : '';
  if ((S.monitors || []).length > 1) updateRestart();
  renderPlaces();
}
async function save(){
  clearTimeout(saveTimer);
  if (saving){ queueSave(); return; }
  saving = true;
  try {
    if ($('autostart').checked !== !!S.autostart) await pywebview.api.set_autostart($('autostart').checked);
    S = await pywebview.api.apply(collect());
    syncFields(); flash('Saved and applied');
  } finally { saving = false; }
}
$('save').onclick = save;
$('checknow').onclick = async () => { $('updmsg').textContent = 'Checking...'; S = await pywebview.api.check_update(); renderUpdates(); };
$('installupd').onclick = async () => {
  S = await pywebview.api.install_update();
  if (S.can_auto_install) $('updmsg').textContent = 'Downloading... the wallpaper will restart when done.';
};
document.querySelectorAll('main input, main select').forEach(el => {
  if (el.id !== 'q' && el.id !== 'placename') el.addEventListener('change', queueSave);
});
$('close').onclick = () => pywebview.api.close();
window.addEventListener('pywebviewready', async () => { S = await pywebview.api.get_state(); fill(); });
</script></body></html>
"""
