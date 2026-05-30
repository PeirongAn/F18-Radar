"""Standalone Tobii test UI served by the backend."""


def tobii_test_ui_html() -> str:
    return r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tobii Gaze Test Console</title>
  <style>
    :root {
      --bg: #070907;
      --panel: #101510;
      --panel-2: #151814;
      --line: #2e3b31;
      --text: #d8dfd2;
      --muted: #7f8b7c;
      --green: #66d38b;
      --cyan: #57c7d4;
      --amber: #f0b84b;
      --red: #ff6b5f;
      --ink: #050705;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px),
        linear-gradient(0deg, rgba(255,255,255,0.018) 1px, transparent 1px),
        radial-gradient(circle at 70% 20%, rgba(87,199,212,0.09), transparent 30rem),
        var(--bg);
      background-size: 42px 42px, 42px 42px, auto, auto;
      color: var(--text);
      font-family: "Microsoft YaHei", "Noto Sans SC", "Segoe UI", sans-serif;
    }
    header {
      min-height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(8, 11, 8, 0.92);
    }
    h1 {
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    .status {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: var(--muted);
      white-space: nowrap;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--red);
      box-shadow: 0 0 12px rgba(255,107,95,0.6);
    }
    .dot.on {
      background: var(--green);
      box-shadow: 0 0 12px rgba(102,211,139,0.7);
    }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 420px) minmax(520px, 1fr) minmax(320px, 420px);
      gap: 14px;
      padding: 14px;
    }
    section {
      border: 1px solid var(--line);
      background: rgba(16, 21, 16, 0.92);
      border-radius: 6px;
      overflow: hidden;
    }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-2);
      font-size: 14px;
      font-weight: 700;
    }
    .section-body { padding: 14px; }
    label {
      display: block;
      margin: 10px 0 6px;
      color: var(--muted);
      font-size: 12px;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid #364438;
      border-radius: 4px;
      background: #080b08;
      color: var(--text);
      padding: 9px 10px;
      font: inherit;
      font-size: 13px;
      outline: none;
    }
    textarea {
      min-height: 86px;
      resize: vertical;
      font-family: "Cascadia Mono", Consolas, monospace;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--cyan);
      box-shadow: 0 0 0 2px rgba(87,199,212,0.13);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }
    button {
      min-height: 34px;
      border: 1px solid #456047;
      border-radius: 4px;
      background: #0c130d;
      color: var(--green);
      padding: 8px 12px;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }
    button:hover { border-color: var(--green); background: #102015; }
    button.warn { color: var(--amber); border-color: #6d5631; }
    button.danger { color: var(--red); border-color: #70403d; }
    button.cyan { color: var(--cyan); border-color: #33616a; }
    .stage {
      position: relative;
      min-height: 620px;
      border: 1px solid var(--line);
      background:
        linear-gradient(90deg, rgba(102,211,139,0.10) 1px, transparent 1px),
        linear-gradient(0deg, rgba(102,211,139,0.08) 1px, transparent 1px),
        #050805;
      background-size: 40px 40px;
      overflow: hidden;
    }
    .target {
      position: absolute;
      border: 2px solid var(--amber);
      background: rgba(240,184,75,0.10);
      box-shadow: 0 0 20px rgba(240,184,75,0.22);
      pointer-events: none;
    }
    .target.flash {
      animation: flash 0.32s alternate 10;
    }
    .gaze {
      position: absolute;
      width: 28px;
      height: 28px;
      border: 2px solid var(--red);
      border-radius: 50%;
      transform: translate(-50%, -50%);
      pointer-events: none;
      box-shadow: 0 0 18px rgba(255,107,95,0.7);
    }
    .gaze::before, .gaze::after {
      content: "";
      position: absolute;
      background: var(--amber);
      opacity: 0.95;
    }
    .gaze::before { width: 44px; height: 1px; left: -10px; top: 12px; }
    .gaze::after { width: 1px; height: 44px; left: 12px; top: -10px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 9px;
      background: rgba(0,0,0,0.18);
      min-height: 58px;
    }
    .metric b {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
      margin-bottom: 4px;
    }
    .metric span {
      color: var(--text);
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 13px;
    }
    .log {
      height: 520px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #050705;
      padding: 10px;
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 12px;
      line-height: 1.5;
    }
    .entry {
      padding: 5px 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .entry .time { color: var(--muted); }
    .entry.ok { color: var(--green); }
    .entry.err { color: var(--red); }
    .entry.info { color: var(--cyan); }
    @keyframes flash {
      from { background: rgba(240,184,75,0.08); box-shadow: 0 0 16px rgba(240,184,75,0.28); }
      to { background: rgba(255,107,95,0.38); box-shadow: 0 0 30px rgba(255,107,95,0.75); }
    }
    @media (max-width: 1180px) {
      main { grid-template-columns: 1fr; }
      .stage { min-height: 520px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Tobii 眼动单测控制台</h1>
      <div class="sub">注视点追踪、目标区域、marker、真实 attention_feedback 联调</div>
    </div>
    <div class="status"><span id="wsDot" class="dot"></span><span id="wsText">WS 未连接</span></div>
  </header>

  <main>
    <section>
      <div class="section-head">连接与目标区域</div>
      <div class="section-body">
        <label>HTTP Base</label>
        <input id="httpBase" />
        <label>WebSocket URL</label>
        <input id="wsUrl" />
        <div class="actions">
          <button class="cyan" id="connectWs">连接 WS</button>
          <button id="pollToggle">开始轮询</button>
        </div>

        <div class="row">
          <div>
            <label>task_id</label>
            <input id="taskId" placeholder="可为空，使用当前 active task" />
          </div>
          <div>
            <label>user_id</label>
            <input id="userId" value="test_operator" />
          </div>
        </div>
        <label>坐标空间</label>
        <select id="coordinateSpace">
          <option value="display_area_normalized">display_area_normalized</option>
          <option value="physical_pixel">physical_pixel</option>
        </select>
        <div class="row">
          <div><label>left</label><input id="left" value="0.35" /></div>
          <div><label>top</label><input id="top" value="0.30" /></div>
          <div><label>right</label><input id="right" value="0.65" /></div>
          <div><label>bottom</label><input id="bottom" value="0.55" /></div>
        </div>
        <label>screen_data，仅 physical_pixel 需要</label>
        <input id="screenData" value="1920,1080" />
        <div class="actions">
          <button id="setRegion">设置目标区域</button>
          <button class="warn" id="clearRegion">清除目标区域</button>
          <button class="cyan" id="getGazeData">查询 gaze_data</button>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">注视点追踪画布</div>
      <div class="section-body">
        <div class="metrics">
          <div class="metric"><b>active_task_id</b><span id="activeTask">--</span></div>
          <div class="metric"><b>gaze</b><span id="gazeText">--</span></div>
          <div class="metric"><b>window_count</b><span id="windowCount">--</span></div>
        </div>
        <div id="stage" class="stage">
          <div id="target" class="target" hidden></div>
          <div id="gaze" class="gaze" hidden></div>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">Marker 与反馈日志</div>
      <div class="section-body">
        <label>marker name</label>
        <input id="markerName" value="manual_marker" />
        <label>marker payload JSON</label>
        <textarea id="markerPayload">{"note":"gaze test marker"}</textarea>
        <div class="actions">
          <button id="sendMarker">POST marker</button>
          <button class="cyan" id="sendWsMarker">WS marker</button>
          <button class="danger" id="clearLog">清空日志</button>
        </div>
        <label>请求与反馈日志</label>
        <div id="log" class="log"></div>
      </div>
    </section>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    const state = { ws: null, polling: false, pollId: null, target: null };
    const isStandaloneHttp = location.port === "8081";
    $("httpBase").value = location.origin;
    $("wsUrl").value = isStandaloneHttp
      ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.hostname}:8082`
      : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

    function log(kind, message, data) {
      const el = document.createElement("div");
      el.className = `entry ${kind || "info"}`;
      const text = data === undefined ? message : `${message}\n${JSON.stringify(data, null, 2)}`;
      el.innerHTML = `<span class="time">${new Date().toLocaleTimeString()}</span> ${escapeHtml(text)}`;
      $("log").prepend(el);
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }
    function apiUrl(path) {
      return `${$("httpBase").value.replace(/\/$/, "")}${path}`;
    }
    function parseJsonTextarea() {
      const text = $("markerPayload").value.trim();
      if (!text) return {};
      return JSON.parse(text);
    }
    function currentRegion() {
      const left = Number($("left").value);
      const top = Number($("top").value);
      const right = Number($("right").value);
      const bottom = Number($("bottom").value);
      return { shape: "rect", id: "test_region", left, top, right, bottom };
    }
    function requestBase() {
      const taskId = $("taskId").value.trim();
      return {
        task_id: taskId || undefined,
        user_id: $("userId").value.trim(),
        task_source: "tobii_test_ui",
        task_name: "manual_gaze_test"
      };
    }
    function screenData() {
      const parts = $("screenData").value.split(",").map((v) => Number(v.trim()));
      return parts.length >= 2 && parts.every(Number.isFinite) ? parts.slice(0, 2) : undefined;
    }
    async function postJson(path, body) {
      log("info", `POST ${path}`, body);
      const response = await fetch(apiUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await response.json().catch(() => ({}));
      log(response.ok && data.ok !== false ? "ok" : "err", `RESP ${response.status}`, data);
      return data;
    }
    async function getJson(path) {
      const response = await fetch(apiUrl(path), { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      updateGaze(data);
      return data;
    }
    function updateTarget() {
      const region = currentRegion();
      state.target = region;
      const stage = $("stage").getBoundingClientRect();
      const target = $("target");
      const space = $("coordinateSpace").value;
      const size = screenData() || [stage.width, stage.height];
      const left = space === "physical_pixel" ? region.left / size[0] : region.left;
      const top = space === "physical_pixel" ? region.top / size[1] : region.top;
      const right = space === "physical_pixel" ? region.right / size[0] : region.right;
      const bottom = space === "physical_pixel" ? region.bottom / size[1] : region.bottom;
      target.hidden = false;
      target.style.left = `${Math.min(left, right) * stage.width}px`;
      target.style.top = `${Math.min(top, bottom) * stage.height}px`;
      target.style.width = `${Math.abs(right - left) * stage.width}px`;
      target.style.height = `${Math.abs(bottom - top) * stage.height}px`;
    }
    function updateGaze(data) {
      $("activeTask").textContent = data.active_task_id || data.task_id || "--";
      $("windowCount").textContent = data.window_count ?? "--";
      if (Array.isArray(data.gaze_point)) {
        const [x, y] = data.gaze_point.map(Number);
        $("gazeText").textContent = `${x.toFixed(4)}, ${y.toFixed(4)}`;
        const stage = $("stage").getBoundingClientRect();
        const gaze = $("gaze");
        gaze.hidden = false;
        gaze.style.left = `${x * stage.width}px`;
        gaze.style.top = `${y * stage.height}px`;
      } else {
        $("gazeText").textContent = "--";
        $("gaze").hidden = true;
      }
    }
    function flashTarget(payload) {
      const target = $("target");
      target.hidden = false;
      target.classList.remove("flash");
      void target.offsetWidth;
      target.classList.add("flash");
      window.setTimeout(() => target.classList.remove("flash"), Number(payload.duration_ms || 3000));
    }
    function setWsStatus(on, text) {
      $("wsDot").classList.toggle("on", on);
      $("wsText").textContent = text;
    }
    $("connectWs").onclick = () => {
      if (state.ws) state.ws.close();
      const ws = new WebSocket($("wsUrl").value);
      state.ws = ws;
      setWsStatus(false, "WS 连接中");
      ws.onopen = () => setWsStatus(true, "WS 已连接");
      ws.onclose = () => setWsStatus(false, "WS 已断开");
      ws.onerror = () => setWsStatus(false, "WS 错误");
      ws.onmessage = (event) => {
        let data = {};
        try { data = JSON.parse(event.data); } catch { data = { raw: event.data }; }
        if (data.type === "attention_feedback") {
          log("ok", "attention_feedback", data);
          flashTarget(data);
        } else {
          log("info", "WS message", data);
        }
      };
    };
    $("pollToggle").onclick = () => {
      state.polling = !state.polling;
      $("pollToggle").textContent = state.polling ? "停止轮询" : "开始轮询";
      if (state.polling) {
        state.pollId = window.setInterval(() => getJson("/tobii/gaze_data?limit=20").catch((e) => log("err", e.message)), 150);
      } else {
        window.clearInterval(state.pollId);
      }
    };
    $("setRegion").onclick = async () => {
      updateTarget();
      const region = currentRegion();
      const body = {
        ...requestBase(),
        box_visible: true,
        coordinate_space: $("coordinateSpace").value,
        regions: [region],
        bbox: [[region.left, region.top, region.right, region.bottom]]
      };
      if ($("coordinateSpace").value === "physical_pixel") body.screen_data = screenData();
      const data = await postJson("/tobii/hand", body);
      if (data.task_id) $("taskId").value = data.task_id;
    };
    $("clearRegion").onclick = async () => {
      $("target").hidden = true;
      await postJson("/tobii/hand", { ...requestBase(), box_visible: false });
    };
    $("getGazeData").onclick = () => getJson("/tobii/gaze_data?limit=20").then((data) => log("ok", "GET gaze_data", data)).catch((e) => log("err", e.message));
    $("sendMarker").onclick = async () => {
      try {
        await postJson("/tobii/marker", {
          ...requestBase(),
          name: $("markerName").value,
          payload: parseJsonTextarea()
        });
      } catch (e) {
        log("err", e.message);
      }
    };
    $("sendWsMarker").onclick = () => {
      if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
        log("err", "WS is not open");
        return;
      }
      const body = { type: "tobii_marker", ...requestBase(), name: $("markerName").value, payload: parseJsonTextarea() };
      state.ws.send(JSON.stringify(body));
      log("info", "WS marker sent", body);
    };
    $("clearLog").onclick = () => { $("log").innerHTML = ""; };
    window.addEventListener("resize", () => {
      if (!$("target").hidden) updateTarget();
    });
    log("info", "页面已加载，先连接 WS，再设置目标区域或发送 marker。");
  </script>
</body>
</html>"""
