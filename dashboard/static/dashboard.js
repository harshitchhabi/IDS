"use strict";
const $ = (id) => document.getElementById(id);
const fmtPct = (v) => (v === null || v === undefined ? "—" : (100 * v).toFixed(1) + "%");
const fmtN = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString());
const RED = "#f85149", GREEN = "#3fb950", BLUE = "#58a6ff", ORANGE = "#d29922", GREY = "#8b98a8";
Chart.defaults.color = "#8b98a8";
Chart.defaults.borderColor = "#262d38";
Chart.defaults.animation = false;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.plugins.legend.labels.boxWidth = 10;

const traffic = new Chart($("c-traffic"), {
  data: { labels: [], datasets: [
    { type: "bar", label: "benign", data: [], backgroundColor: "#2d6a4f", stack: "s", order: 2 },
    { type: "bar", label: "attack", data: [], backgroundColor: RED, stack: "s", order: 2 },
    { type: "line", label: "alerts", data: [], borderColor: ORANGE, borderWidth: 2, pointRadius: 0, order: 1 } ] },
  options: { scales: { x: { stacked: true, ticks: { maxTicksLimit: 8 } }, y: { stacked: true, beginAtZero: true } } },
});

function roundChart(id, keyFixed, keyRecal, max) {
  return new Chart($(id), {
    type: "line",
    data: { labels: [], datasets: [
      { label: "fixed threshold", data: [], borderColor: RED, backgroundColor: RED, borderWidth: 2, pointRadius: 3, tension: 0.15 },
      { label: "recalibrated", data: [], borderColor: BLUE, backgroundColor: BLUE, borderWidth: 2, borderDash: [5, 3], pointRadius: 2, tension: 0.15 } ] },
    options: { scales: { y: { min: 0, max, ticks: { callback: (v) => (100 * v).toFixed(0) + "%" } }, x: { title: { display: true, text: "round (dot: green = S0 feed, red = A1 feed)" }, ticks: { maxTicksLimit: 16, maxRotation: 0 } } },
               plugins: { tooltip: { callbacks: { title: (i) => "round " + i[0].label, label: (c) => `${c.dataset.label}: ${(100 * c.parsed.y).toFixed(1)}%` } } } },
  });
}
const cFpr = roundChart("c-fpr"), cTpr = roundChart("c-tpr", null, null, 1);
cFpr.options.scales.y.max = undefined; cFpr.options.scales.y.suggestedMax = 0.1;

const classes = new Chart($("c-classes"), {
  type: "bar",
  data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
  options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => (100 * c.parsed.x).toFixed(1) + "% alerted" } } },
             scales: { x: { min: 0, max: 1, ticks: { callback: (v) => 100 * v + "%" } } } },
});

const feedName = { s0: "S0 (clean)", a1: "A1 (poison)", none: "—", off: "—" };
const defName = { off: "off", sharecap: "ShareCap", d1: "D1", knn: "kNN" };

function renderTraffic(s) {
  const t = s.traffic.slice(0, -1);   // the newest bucket is still filling
  traffic.data.labels = t.map((b) => new Date(b.t * 1000).toLocaleTimeString());
  traffic.data.datasets[0].data = t.map((b) => b.benign);
  traffic.data.datasets[1].data = t.map((b) => b.attack);
  traffic.data.datasets[2].data = t.map((b) => b.alerts);
  traffic.update();
}

function renderAlerts(s) {
  $("alerts").innerHTML = s.alerts.map((a) =>
    `<tr class="${a.injected ? "inj" : ""}"><td>${new Date(a.ts * 1000).toLocaleTimeString()}</td>` +
    `<td class="bad">${a.predicted}</td><td class="${a.true_attack ? "" : "bad"}">${a.true_attack ? a.family : "BENIGN (false alarm)"}</td>` +
    `<td>${a.score.toFixed(2)}</td></tr>`).join("");
}

function renderRounds(s) {
  const r = s.rounds;
  const lab = r.map((x) => x.round);
  for (const [chart, kf, kr] of [[cFpr, "fixed_fpr", "recal_fpr"], [cTpr, "fixed_tpr", "recal_tpr"]]) {
    chart.data.labels = lab;
    chart.data.datasets[0].data = r.map((x) => x[kf]);
    chart.data.datasets[1].data = r.map((x) => x[kr]);
    chart.data.datasets[0].pointBackgroundColor = r.map((x) => (x.scenario === "a1" ? RED : x.scenario === "s0" ? GREEN : GREY));
    chart.update();
  }
  $("defs").innerHTML = s.defenses.map((d) =>
    `<tr><td><b>${defName[d.defense]}</b></td><td>${d.rounds}</td><td>${fmtPct(d.last_fpr)}</td><td>${fmtPct(d.last_tpr)}</td>` +
    `<td>${fmtPct(d.last_recal_tpr)}</td><td>${fmtPct(d.last_eff)}</td><td>${d.ms_per_round < 1 ? d.ms_per_round.toFixed(2) : d.ms_per_round.toFixed(0)} ms</td></tr>`).join("");
  const dd = Object.fromEntries(s.defenses.map((d) => [d.defense, d]));
  $("defs-note").textContent = (dd.knn && dd.sharecap)
    ? `kNN costs ${(dd.knn.ms_per_round / Math.max(dd.sharecap.ms_per_round, 0.001)).toFixed(0)}× ShareCap per round; the cap needs no reference data, no cost model, and does not know the poison ratio.`
    : "Switch each defense on in turn (with A1 still arriving) to fill this table.";
}

function renderModels(s) {
  $("models").innerHTML = s.models.slice().reverse().map((m) =>
    `<tr><td>v${m.version}</td><td>${m.round}</td><td>${feedName[m.scenario]}</td><td>${defName[m.defense]}</td>` +
    `<td>${fmtPct(m.poison)}</td><td>${fmtPct(m.eff)}</td><td class="${m.fixed_fpr > 0.05 ? "bad" : ""}">${fmtPct(m.fixed_fpr)}</td>` +
    `<td>${fmtPct(m.fixed_tpr)}</td><td>${fmtPct(m.recal_fpr)}</td><td>${fmtPct(m.recal_tpr)}</td></tr>`).join("");
}

function renderClasses(s) {
  const rows = Object.entries(s.classes).map(([f, v]) => [f, v.flows ? v.alerted / v.flows : 0, v.flows]);
  rows.sort((a, b) => (a[0] === "BENIGN") - (b[0] === "BENIGN") || b[1] - a[1]);
  classes.data.labels = rows.map((r) => `${r[0]} (${fmtN(r[2])})`);
  classes.data.datasets[0].data = rows.map((r) => r[1]);
  classes.data.datasets[0].backgroundColor = rows.map((r) => (r[0] === "BENIGN" ? RED : GREEN));
  classes.update();
}

function renderControl(s) {
  const c = s.control;
  document.querySelectorAll("button.feed").forEach((b) => b.classList.toggle("active", b.dataset.feed === c.feed));
  document.querySelectorAll("button.def").forEach((b) => b.classList.toggle("active", b.dataset.def === c.defense));
  document.querySelectorAll("#mode-seg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === s.detector.mode));
  const last = s.rounds[s.rounds.length - 1];
  $("loop-status").innerHTML = `round <b>${c.round}</b> · feed <b>${feedName[c.feed]}</b> · defense <b>${defName[c.defense]}</b>` +
    (c.busy ? ` · <span class="good">retraining…</span>` : "") +
    (last ? `<br>honeypot share of training set: <b>${fmtPct(last.poison_ratio)}</b> → effective <b>${fmtPct(last.hp_effective_ratio)}</b>` : "") +
    (s.recorded ? `<br><b>recorded</b>` : "");
  $("b-version").textContent = `model v${s.detector.version}`;
  $("k-thr").textContent = s.detector.threshold === null ? "—" : s.detector.threshold.toFixed(3);
  if (document.activeElement !== $("rate")) { $("rate").value = c.rate; $("rate-v").textContent = c.rate; }
}

function renderHoneypot(s) {
  const h = s.honeypot;
  if (!h || !h.enabled) return;
  const top = (arr, k) => arr.slice(0, 8).map((x) => `<tr><td>${x[0]}</td><td>${x[1]}</td></tr>`).join("");
  const sess = h.sessions.map((x) =>
    `<tr><td>${x.session.slice(0, 8)}</td><td>${x.src_ip || ""}</td><td>${x.logins}</td><td>${x.commands}</td><td>${fmtN(x.bytes)}</td><td>${x.duration.toFixed(1)}s</td>` +
    `<td><b>${x.effort.toFixed(1)}</b> <span class="mut">${x.active ? "active" : ""}</span></td></tr>`).join("");
  $("hp-body").innerHTML =
    `<div class="hpgrid"><div class="kpi"><div class="k">sessions</div><div class="v">${h.totals.sessions}</div></div>` +
    `<div class="kpi"><div class="k">login attempts</div><div class="v">${h.totals.logins}</div></div>` +
    `<div class="kpi"><div class="k">successful logins</div><div class="v">${h.totals.login_success}</div></div>` +
    `<div class="kpi"><div class="k">commands run</div><div class="v">${h.totals.commands}</div></div>` +
    `<div class="kpi"><div class="k">distinct credentials</div><div class="v">${h.totals.distinct_credentials}</div></div></div>` +
    `<div class="rounds"><div><h3>Sessions <small>effort = ∏(1+x/r)^¼ − 1 over auth attempts, commands, bytes, duration</small></h3><div class="scroll"><table class="mini"><thead><tr><th>session</th><th>src</th><th>logins</th><th>cmds</th><th>bytes</th><th>time</th><th>effort</th></tr></thead><tbody>${sess}</tbody></table></div></div>` +
    `<div><h3>Credentials tried</h3><table class="mini"><thead><tr><th>user / password</th><th>n</th></tr></thead><tbody>${top(h.credentials)}</tbody></table></div>` +
    `<div><h3>Commands run</h3><table class="mini"><thead><tr><th>command</th><th>n</th></tr></thead><tbody>${top(h.commands)}</tbody></table></div></div>`;
}

let last = null;
function render(s) {
  last = s;
  $("k-rate").textContent = fmtN(s.rate_now);
  $("k-flows").textContent = fmtN(s.totals.flows);
  $("k-alerts").textContent = fmtN(s.totals.alerts);
  $("k-fpr").textContent = fmtPct(s.live.fpr);
  $("k-fpr").className = "v " + (s.live.fpr > 0.05 ? "bad" : "good");
  $("k-tpr").textContent = fmtPct(s.live.tpr);
  renderTraffic(s); renderAlerts(s); renderRounds(s); renderModels(s); renderClasses(s); renderControl(s); renderHoneypot(s);
}

function connect() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => { $("b-conn").textContent = "connected"; $("b-conn").style.color = GREEN; setInterval(() => ws.readyState === 1 && ws.send("."), 15000); };
  ws.onmessage = (e) => render(JSON.parse(e.data));
  ws.onclose = () => { $("b-conn").textContent = "reconnecting…"; $("b-conn").style.color = ORANGE; setTimeout(connect, 1000); };
}
connect();

$("rate").addEventListener("input", (e) => { $("rate-v").textContent = e.target.value; });
$("rate").addEventListener("change", (e) => fetch("/api/rate/" + e.target.value, { method: "POST" }));
$("btn-attack").addEventListener("click", () => fetch("/api/attack/" + $("atk-family").value, { method: "POST" }));
$("btn-reset").addEventListener("click", () => fetch("/api/reset", { method: "POST" }));
