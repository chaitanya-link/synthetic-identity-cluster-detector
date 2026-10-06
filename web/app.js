(() => {
  "use strict";

  const FIELD_LABEL = { bank_account: "Bank account", device_id: "Device", phone: "Phone" };
  const FIELD_COLOR = { bank_account: "var(--c-bank)", device_id: "var(--c-device)", phone: "var(--c-phone)" };
  const WHY_WRONG = {
    "hard-slow-household-ring": "Fraud, approved: one reused surname spread over weeks looks like a household. A verified-address signal would expose it.",
    "hard-household-same-day": "Genuine, blocked: a real household with different surnames applying the same day. A shared verified address would clear it.",
    "hard-cyber-cafe": "Genuine, flagged: strangers sharing one cafe device. Device reputation over time would help.",
    "hard-invisible-ring": "Fraud, missed: nothing is shared, so there is nothing to link. Needs behavioural and device-intelligence signals.",
  };
  const FORM_FIELDS = ["name", "phone", "device_id", "bank_account", "ip", "loan_amount", "timestamp"];
  const reviewState = {};

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtTime = (iso) => String(iso || "").replace("T", " ").slice(0, 16);

  async function api(path, options) {
    const res = await fetch(path, options);
    let body = null;
    try { body = await res.json(); } catch (_) { /* not JSON */ }
    if (!res.ok) throw new Error(errorText(body) || `Request failed (${res.status})`);
    return body;
  }

  function errorText(body) {
    if (!body) return "";
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join("; ");
    return "";
  }

  // ---------- graph ----------
  function graphSvg(d) {
    const W = 560, H = 340, cx = W / 2, cy = H / 2;
    const n = d.nodes.length;
    const rx = n > 8 ? 215 : 185, ry = n > 8 ? 125 : 110;
    const nodeR = n > 14 ? 8 : 17;
    const showLabels = n <= 12;
    const pos = {};
    d.nodes.forEach((node, i) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
      pos[node.app_id] = n === 1 ? { x: cx, y: cy } : { x: cx + rx * Math.cos(angle), y: cy + ry * Math.sin(angle) };
    });

    const seen = {};
    const edges = d.edges.map((e) => {
      const key = [e.source, e.target].sort().join("|");
      seen[key] = (seen[key] === undefined ? -1 : seen[key]) + 1;
      const p = pos[e.source], q = pos[e.target];
      const len = Math.hypot(q.x - p.x, q.y - p.y) || 1;
      const off = seen[key] * 5;
      const ox = (-(q.y - p.y) / len) * off, oy = ((q.x - p.x) / len) * off;
      return `<line x1="${p.x + ox}" y1="${p.y + oy}" x2="${q.x + ox}" y2="${q.y + oy}" ` +
        `stroke="${FIELD_COLOR[e.field] || "var(--node-stroke)"}" stroke-width="2.5" stroke-linecap="round">` +
        `<title>${esc(FIELD_LABEL[e.field] || e.field)}: ${esc(e.value)}</title></line>`;
    }).join("");

    const nodes = d.nodes.map((node) => {
      const { x, y } = pos[node.app_id];
      const first = String(node.name || "").split(" ")[0];
      const halo = node.is_new ? `<circle class="halo" cx="${x}" cy="${y}" r="${nodeR + 6}"></circle>` : "";
      const tag = node.is_new ? `<text class="tag" x="${x}" y="${y + 3}">NEW</text>` : "";
      const labels = showLabels
        ? `<text x="${x}" y="${y + nodeR + 13}">${esc(first)}</text>` +
          `<text class="id" x="${x}" y="${y + nodeR + 25}">${esc(node.app_id)}</text>`
        : "";
      return `<g class="node${node.is_new ? " new" : ""}">${halo}` +
        `<circle class="core" cx="${x}" cy="${y}" r="${nodeR}"><title>${esc(node.name)} (${esc(node.app_id)})</title></circle>` +
        `${tag}${labels}</g>`;
    }).join("");

    return `<svg class="graph" viewBox="0 0 ${W} ${H}" role="img" aria-label="Graph of linked applications">${edges}${nodes}</svg>`;
  }

  function legendHtml(fields) {
    if (!fields.length) return "";
    return `<div class="legend">${fields.map((f) =>
      `<span><i style="background:${FIELD_COLOR[f] || "var(--node-stroke)"}"></i>${esc(FIELD_LABEL[f] || f)}</span>`).join("")}</div>`;
  }

  function reasonsHtml(d) {
    const rows = d.reasons.map((r) =>
      `<div class="reason"><span>${esc(r.text)}</span><span class="pts">+${esc(r.points)}</span>` +
      `<div class="bar"><span style="width:${Math.min(100, (r.points / 35) * 100)}%"></span></div></div>`).join("");
    return `<div class="reasons">${rows}` +
      `<div class="reason total"><span>Risk score</span><span class="pts">${esc(d.score)}</span></div></div>`;
  }

  function membersHtml(d) {
    const rows = d.nodes.map((n) =>
      `<tr><td class="mono">${esc(n.app_id)}</td><td>${esc(n.name)}</td><td class="mono">${esc(n.phone)}</td>` +
      `<td class="mono">${esc(n.device_id)}</td><td class="mono">${esc(n.bank_account)}</td><td>${esc(fmtTime(n.timestamp))}</td></tr>`).join("");
    return `<div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Phone</th><th>Device</th>` +
      `<th>Bank account</th><th>Submitted</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function detailHtml(d, { actions }) {
    const title = d.decision === "approve" ? "Why this was not flagged" : "Why this was flagged";
    const heading = d.cluster_id === "preview" ? "Why it scores this way" : title;
    const truth = d.truth.scenario
      ? `Synthetic ground truth: ${esc(d.truth.scenario)} (${esc(d.truth.label)})`
      : `Synthetic ground truth: ${esc(d.truth.label)}`;
    const reviewer = actions
      ? `<div class="actions" data-cluster="${esc(d.cluster_id)}">` +
        `<button data-act="escalate">Escalate</button><button data-act="dismiss">Dismiss</button>` +
        `<span class="review-state">${esc(reviewState[d.cluster_id] || "System recommends, a human confirms (demo only, not saved)")}</span></div>`
      : "";
    return `<div class="detail-head"><h2>${d.cluster_id === "preview" ? "Preview" : esc(d.cluster_id)}</h2>` +
      `<span class="pill ${esc(d.decision)}">${esc(d.decision)}</span><span class="score-big">${esc(d.score)}</span></div>` +
      `<div class="truth">${truth}</div>` +
      graphSvg(d) + legendHtml(d.link_fields) +
      `<h3>${esc(heading)}</h3>` + reasonsHtml(d) + reviewer +
      `<h3>Applications in this cluster</h3>` + membersHtml(d);
  }

  // ---------- clusters tab ----------
  function renderKpis(o) {
    const items = [
      ["Applications", o.applications], ["Clusters found", o.clusters], ["Flagged clusters", o.flagged_clusters],
      ["Blocked clusters", o.blocked_clusters], ["Flagged applications", o.flagged_applications],
      ["Shared IPs ignored", o.ignored_hubs],
    ];
    $("#kpis").innerHTML = items.map(([label, value]) =>
      `<div class="kpi"><div class="kpi-v">${esc(value)}</div><div class="kpi-l">${esc(label)}</div></div>`).join("");
  }

  function renderClusterList(rows) {
    $("#cluster-list").innerHTML = rows.map((r) =>
      `<button class="cl-item" data-id="${esc(r.cluster_id)}">` +
      `<span class="cl-top"><strong>${esc(r.cluster_id)}</strong><span class="pill ${esc(r.decision)}">${esc(r.decision)}</span>` +
      `<span class="cl-score">${esc(r.score)}</span></span>` +
      `<span class="cl-sub">${esc(r.size)} applications &middot; ${esc(r.headline)}</span></button>`).join("");
  }

  function renderHubs(hubs) {
    $("#hub-list").innerHTML = hubs.length
      ? hubs.map((h) => `<div class="hub">${esc(h.field.toUpperCase())} <span class="mono">${esc(h.value)}</span> &middot; ` +
          `${esc(h.count)} applications. Shared by design (offices, colleges), so never used to merge.</div>`).join("")
      : `<div class="hub">None</div>`;
  }

  async function selectCluster(id) {
    document.querySelectorAll(".cl-item").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
    try {
      const d = await api(`/api/clusters/${encodeURIComponent(id)}`);
      $("#detail").innerHTML = detailHtml(d, { actions: true });
    } catch (err) {
      $("#detail").innerHTML = `<div class="error">${esc(err.message)}</div>`;
    }
  }

  // ---------- try tab ----------
  function renderExamples(examples) {
    $("#examples").innerHTML = examples.map((e) =>
      `<button data-example="${esc(e.id)}">${esc(e.label)}</button>`).join("");
    $("#examples").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-example]");
      if (!button) return;
      const example = examples.find((e) => e.id === button.dataset.example);
      if (!example) return;
      FORM_FIELDS.forEach((f) => { $(`#f-${f}`).value = example.payload[f] ?? ""; });
      runScore();
    });
  }

  async function runScore() {
    const button = $("#score-btn");
    const payload = {};
    FORM_FIELDS.forEach((f) => {
      const value = $(`#f-${f}`).value.trim();
      if (value) payload[f] = value;
    });
    button.disabled = true;
    try {
      const r = await api("/api/score", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      $("#try-result").innerHTML = resultHtml(r);
    } catch (err) {
      $("#try-result").innerHTML = `<div class="error">${esc(err.message)}</div>`;
    } finally {
      button.disabled = false;
    }
  }

  function resultHtml(r) {
    const flip = r.linked
      ? `<span class="pill approve">On its own: ${esc(r.alone)}</span><span class="arrow">&rarr;</span>` +
        `<span class="pill ${esc(r.decision)}">With links: ${esc(r.decision)} &middot; score ${esc(r.score)}</span>`
      : `<span class="pill approve">No links found: ${esc(r.decision)}</span>`;
    const merged = r.merged.length
      ? `<p class="muted">Joins existing cluster${r.merged.length > 1 ? "s" : ""}: ` +
        r.merged.map((m) => `${esc(m.cluster_id)} (${esc(m.decision)}, ${esc(m.score)})`).join(", ") + `</p>`
      : "";
    const detail = r.cluster ? detailHtml(r.cluster, { actions: false }) : "";
    return `<div class="card"><div class="flip">${flip}</div><p>${esc(r.message)}</p>${merged}${detail}</div>`;
  }

  // ---------- evaluation tab ----------
  function evalCard(title, result, withWhy) {
    const m = result.metrics;
    const stat = (value, label) => `<div class="stat"><b>${esc(value)}</b><span>${esc(label)}</span></div>`;
    const rows = result.groups.map((g) =>
      `<tr><td>${esc(g.group)}</td><td>${esc(g.truth)}</td><td>${esc(g.size)}</td><td>${esc(g.decision)}</td>` +
      `<td><span class="pill ${g.correct ? "approve" : "block"}">${g.correct ? "ok" : "wrong"}</span></td>` +
      (withWhy ? `<td class="why">${esc(WHY_WRONG[g.group] || "")}</td>` : "") + `</tr>`).join("");
    return `<div class="card"><h2>${esc(title)}</h2>` +
      `<div class="stats">${stat(m.precision.toFixed(3), "precision")}${stat(m.recall.toFixed(3), "recall")}${stat(m.f1.toFixed(3), "F1")}` +
      `${stat(m.tp, "true positives")}${stat(m.fp, "false positives")}${stat(m.fn, "false negatives")}</div>` +
      `<div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Truth</th><th>Size</th><th>Decision</th><th>Result</th>` +
      `${withWhy ? "<th>Why</th>" : ""}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }

  function renderEvaluation(data) {
    const hardOnly = { metrics: data.hard.metrics, groups: data.hard.groups.filter((g) => g.group.startsWith("hard-") || !g.correct) };
    $("#eval").innerHTML =
      `<p class="muted">The easy set uses planted patterns that separate cleanly, so a perfect score there proves little. ` +
      `The hard set adds adversarial cases and shows where the detector fails.</p>` +
      `<div class="eval-grid">${evalCard("Easy set (planted patterns)", data.easy, false)}` +
      `${evalCard("Hard set (adversarial cases added)", hardOnly, true)}</div>`;
  }

  // ---------- wiring ----------
  function wireTabs() {
    document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", String(t === tab));
      });
      document.querySelectorAll(".tabpanel").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${tab.dataset.tab}`));
    }));
  }

  function wireClusters() {
    $("#cluster-list").addEventListener("click", (event) => {
      const button = event.target.closest(".cl-item");
      if (button) selectCluster(button.dataset.id);
    });
    $("#detail").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-act]");
      if (!button) return;
      const box = button.closest(".actions");
      const id = box.dataset.cluster;
      reviewState[id] = button.dataset.act === "escalate" ? "Reviewer: escalated (demo only, not saved)" : "Reviewer: dismissed (demo only, not saved)";
      $(".review-state", box).textContent = reviewState[id];
    });
  }

  async function init() {
    wireTabs();
    wireClusters();
    $("#score-btn").addEventListener("click", runScore);
    try {
      const [overview, clusters, hubs, examples, metrics] = await Promise.all([
        api("/api/overview"), api("/api/clusters"), api("/api/hubs"), api("/api/examples"), api("/api/metrics"),
      ]);
      renderKpis(overview);
      renderClusterList(clusters);
      renderHubs(hubs);
      renderExamples(examples);
      renderEvaluation(metrics);
      if (clusters.length) selectCluster(clusters[0].cluster_id);
    } catch (err) {
      $("#kpis").innerHTML = `<div class="error">Could not load data: ${esc(err.message)}</div>`;
    }
  }

  init();
})();