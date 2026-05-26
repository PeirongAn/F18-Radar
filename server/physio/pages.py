from __future__ import annotations


def check_page_html() -> str:
    return r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Physio Service Check</title>
  <style>
    :root { color-scheme: dark; --bg:#050806; --panel:#0b1510; --line:#214331; --ok:#35d07f; --warn:#f4bd50; --bad:#f06b6b; --muted:#8daf9a; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:#d9f5e4; font-family:"Segoe UI","Microsoft YaHei",sans-serif; letter-spacing:0; }
    main { max-width:1060px; margin:0 auto; padding:28px 22px 40px; }
    header { display:flex; align-items:end; justify-content:space-between; gap:16px; margin-bottom:18px; }
    h1 { margin:0; font-size:24px; font-weight:700; }
    .sub { color:var(--muted); margin-top:6px; font-size:13px; }
    .actions { display:flex; gap:10px; flex-wrap:wrap; }
    button, a.button { border:1px solid var(--line); background:#102216; color:#dff9e8; padding:9px 12px; border-radius:6px; text-decoration:none; cursor:pointer; font:inherit; }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:16px 0; }
    .card { border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:14px; min-height:92px; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; }
    .value { margin-top:8px; font-size:18px; font-weight:700; overflow-wrap:anywhere; }
    .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); }
    .wide { grid-column:1 / -1; }
    pre { white-space:pre-wrap; overflow-wrap:anywhere; color:#cdebd8; margin:8px 0 0; font-size:12px; }
    table { width:100%; border-collapse:collapse; margin-top:8px; }
    th, td { border-bottom:1px solid #173023; padding:9px 6px; text-align:left; font-size:13px; }
    th { color:var(--muted); font-weight:600; }
    @media (max-width:760px) { header { display:block; } .actions { margin-top:14px; } .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Physio Service Check</h1>
      <div class="sub">Use this page before starting the experiment. It is not part of the task flow.</div>
    </div>
    <div class="actions">
      <button type="button" onclick="loadStatus()">Refresh</button>
      <button type="button" onclick="exportData()">Export</button>
      <a class="button" href="/physio/dashboard" target="_blank" rel="noopener noreferrer">Open Dashboard</a>
    </div>
  </header>
  <div class="grid">
    <div class="card"><div class="label">Service</div><div class="value" id="service">Loading</div></div>
    <div class="card"><div class="label">Mode</div><div class="value" id="mode">-</div></div>
    <div class="card"><div class="label">Subject</div><div class="value" id="subject">-</div></div>
    <div class="card"><div class="label">Storage</div><div class="value" id="storage">-</div></div>
    <div class="card"><div class="label">Current Rows</div><div class="value" id="samples">0</div></div>
    <div class="card wide"><div class="label">Vendor CSV Session</div><div class="value" id="session">-</div></div>
    <div class="card wide"><div class="label">Current Raw Sample File</div><div class="value" id="rawFile">-</div></div>
    <div class="card wide">
      <div class="label">Streams</div>
      <table>
        <thead><tr><th>Stream</th><th>Hz</th><th>Latest value</th><th>Last seen</th></tr></thead>
        <tbody id="streams"></tbody>
      </table>
    </div>
    <div class="card wide"><div class="label">Warnings</div><pre id="warnings">-</pre></div>
    <div class="card wide"><div class="label">Export Result</div><pre id="exportResult">-</pre></div>
  </div>
</main>
<script>
const streamOrder = ["ppg","eda","acc","gyro","hr","skt","env","o2"];
function firstValue(values) {
  if (!values) return "-";
  const key = Object.keys(values)[0];
  const v = key ? values[key] : null;
  return typeof v === "number" ? v.toFixed(3) : (v ?? "-");
}
function ageText(ns) {
  if (!ns) return "-";
  const ms = Date.now() - Math.floor(ns / 1e6);
  if (ms < 0) return "now";
  if (ms < 1000) return `${ms} ms ago`;
  return `${Math.round(ms / 1000)} s ago`;
}
async function loadStatus() {
  try {
    const res = await fetch("/api/physio/status", {cache:"no-store"});
    const data = await res.json();
    const service = document.getElementById("service");
    if (!data.enabled) {
      service.textContent = "Disabled";
      service.className = "value warn";
    } else if (data.ok && data.running) {
      service.textContent = "Running";
      service.className = "value ok";
    } else {
      service.textContent = "Unavailable";
      service.className = "value bad";
    }
    const state = data.state || {};
    const collector = data.collector || {};
    const sampleFile = data.sample_file || {};
    document.getElementById("mode").textContent = state.mode || "-";
    document.getElementById("subject").textContent = state.subject_id || "-";
    document.getElementById("storage").textContent = data.sample_storage || "-";
    document.getElementById("samples").textContent = sampleFile.active_row_count ?? data.formal_sample_count ?? 0;
    document.getElementById("session").textContent = collector.source_session_path || "-";
    document.getElementById("rawFile").textContent = sampleFile.active_file_path || "-";
    const streams = collector.streams || {};
    document.getElementById("streams").innerHTML = streamOrder.map(name => {
      const item = streams[name] || {};
      return `<tr><td>${name.toUpperCase()}</td><td>${item.hz || 0}</td><td>${firstValue(item.last_value)}</td><td>${ageText(item.last_seen_ns)}</td></tr>`;
    }).join("");
    const warnings = [];
    if (data.error) warnings.push(data.error);
    warnings.push(...(collector.warnings || []));
    document.getElementById("warnings").textContent = warnings.length ? warnings.join("\n") : "-";
  } catch (err) {
    const service = document.getElementById("service");
    service.textContent = "Error";
    service.className = "value bad";
    document.getElementById("warnings").textContent = String(err);
  }
}
async function exportData() {
  const box = document.getElementById("exportResult");
  box.textContent = "Exporting...";
  try {
    const res = await fetch("/api/physio/export", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
    box.textContent = JSON.stringify(await res.json(), null, 2);
  } catch (err) {
    box.textContent = String(err);
  }
}
loadStatus();
setInterval(loadStatus, 1500);
</script>
</body>
</html>
"""


def dashboard_html() -> str:
    return r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Physio Dashboard</title>
  <style>
    :root { color-scheme:dark; --bg:#030604; --line:#193824; --ink:#e4f6ea; --muted:#85a891; --accent:#25c073; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font-family:"Segoe UI","Microsoft YaHei",sans-serif; letter-spacing:0; }
    header { padding:20px 24px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:16px; align-items:end; }
    h1 { margin:0; font-size:23px; } .sub { color:var(--muted); margin-top:6px; font-size:13px; overflow-wrap:anywhere; }
    a { color:#7fe6ad; }
    main { padding:18px 24px 28px; }
    .metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:14px; }
    .metric, .chart { border:1px solid var(--line); background:#07110b; border-radius:8px; padding:12px; }
    .metric span { color:var(--muted); font-size:12px; } .metric b { display:block; margin-top:5px; font-size:20px; }
    .charts { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .head { display:flex; justify-content:space-between; margin-bottom:8px; color:var(--muted); font-size:12px; }
    canvas { width:100%; height:170px; border:1px solid #102718; border-radius:6px; background:#030a05; }
    @media (max-width:860px) { .metrics, .charts { grid-template-columns:1fr; } header { display:block; } }
  </style>
</head>
<body>
<header>
  <div>
    <h1>Physio Dashboard</h1>
    <div class="sub" id="source">Loading</div>
  </div>
  <a href="/physio/check">Check Page</a>
</header>
<main>
  <div class="metrics" id="metrics"></div>
  <div class="charts" id="charts"></div>
</main>
<script>
const streams = ["ppg","eda","acc","gyro","hr","skt","env","o2"];
const colors = {ppg:"#25c073",eda:"#4da3ff",acc:"#f4bd50",gyro:"#c983ff",hr:"#ff6b6b",skt:"#7dd36f",env:"#94a3b8",o2:"#f59e0b"};
function firstValue(values) {
  if (!values) return null;
  const key = Object.keys(values)[0];
  return key ? Number(values[key]) : null;
}
function draw(canvas, points, color) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width = Math.max(1, canvas.clientWidth * devicePixelRatio);
  const h = canvas.height = Math.max(1, canvas.clientHeight * devicePixelRatio);
  ctx.scale(devicePixelRatio, devicePixelRatio);
  ctx.clearRect(0,0,w,h);
  const vals = (points || []).map(p => firstValue(p.values)).filter(Number.isFinite);
  if (vals.length < 2) return;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
  vals.forEach((v,i) => {
    const x = (i / (vals.length - 1)) * canvas.clientWidth;
    const y = canvas.clientHeight - ((v - min) / span) * (canvas.clientHeight - 18) - 9;
    if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();
}
async function tick() {
  const res = await fetch("/api/physio/status", {cache:"no-store"});
  const data = await res.json();
  const collector = data.collector || {};
  document.getElementById("source").textContent = collector.source_session_path || (data.enabled ? "No vendor CSV session" : "Physio disabled");
  const status = collector.streams || {};
  document.getElementById("metrics").innerHTML = streams.map(s => {
    const item = status[s] || {};
    const last = firstValue(item.last_value);
    return `<div class="metric"><span>${s.toUpperCase()} Hz</span><b>${item.hz || 0}</b><span>${last === null ? "-" : last.toFixed(3)}</span></div>`;
  }).join("");
  document.getElementById("charts").innerHTML = streams.map(s => {
    const item = status[s] || {};
    return `<section class="chart"><div class="head"><b>${s.toUpperCase()}</b><span>${item.hz || 0} Hz</span></div><canvas id="chart-${s}"></canvas></section>`;
  }).join("");
  requestAnimationFrame(() => streams.forEach(s => draw(document.getElementById(`chart-${s}`), (status[s] || {}).points || [], colors[s] || "#25c073")));
}
tick();
setInterval(tick, 1000);
</script>
</body>
</html>
"""
