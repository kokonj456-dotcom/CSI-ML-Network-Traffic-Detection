
const $ = (id) => document.getElementById(id);

let experiments = [];
let currentExperimentId = null;

function fmt(value, digits = 4) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : Number(value).toFixed(digits);
}

function pct(value) {
  return value === null || value === undefined
    ? "—"
    : `${(Number(value) * 100).toFixed(2)}%`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

function statusBadge(status) {
  const labels = {
    completed: "สำเร็จ",
    failed: "ผิดพลาด",
    running: "กำลังทำงาน",
  };

  return `<span class="badge ${escapeHtml(status)}">${labels[status] || escapeHtml(status)}</span>`;
}

function showPage(name) {
  document.querySelectorAll(".page").forEach((p) => {
    p.classList.add("hidden");
  });

  $(`page-${name}`).classList.remove("hidden");

  document.querySelectorAll(".nav-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.page === name);
  });

  const titles = {
    dashboard: "ภาพรวมการทดลอง",
    new: "ทดลองโมเดล Autoencoder",
    history: "ประวัติการทดลอง",
    result: "ผลการทดลอง",
  };

  $("pageTitle").textContent = titles[name] || "Autoencoder Lab";

  if (name === "history") {
    renderHistory();
  }
}

document.querySelectorAll("[data-page]").forEach((b) => {
  b.addEventListener("click", () => showPage(b.dataset.page));
});

document.querySelectorAll("[data-go]").forEach((b) => {
  b.addEventListener("click", () => showPage(b.dataset.go));
});

$("refreshBtn").addEventListener("click", refreshAll);

$("threshold").addEventListener("input", (e) => {
  $("thresholdValue").textContent = e.target.value;
});

document.querySelectorAll("[data-threshold]").forEach((btn) => {
  btn.addEventListener("click", () => {
    $("threshold").value = btn.dataset.threshold;
    $("thresholdValue").textContent = btn.dataset.threshold;

    document.querySelectorAll("[data-threshold]").forEach((x) => {
      x.classList.toggle("active", x === btn);
    });
  });
});

$("threshold").addEventListener("input", (e) => {
  document.querySelectorAll("[data-threshold]").forEach((btn) => {
    btn.classList.toggle(
      "active",
      Number(btn.dataset.threshold) === Number(e.target.value)
    );
  });
});

function syncTrainingFields() {
  const enabled = $("modeSelect").value === "retrain";

  $("trainFields").classList.toggle("hidden", !enabled);

  $("trainFields").querySelectorAll("input, select, textarea").forEach((input) => {
    input.disabled = !enabled;
  });
}

$("modeSelect").addEventListener("change", syncTrainingFields);
syncTrainingFields();

$("searchHistory").addEventListener("input", renderHistory);

$("downloadDetails").addEventListener("click", () => {
  if (currentExperimentId) {
    window.location.href =
      `/api/experiments/${encodeURIComponent(currentExperimentId)}/files/record_details.csv`;
  }
});

$("checkBtn").addEventListener("click", checkReadiness);

// --------------------------------------------------
// เรียก API และแสดงรายละเอียด Error จาก Backend
// --------------------------------------------------

async function api(url, options) {
  const response = await fetch(url, options);
  let body = {};

  try {
    body = await response.json();
  } catch {
    body = {};
  }

  if (!response.ok) {
    const detail = body.detail;
    let message;

    if (Array.isArray(detail)) {
      message = detail.map((item) => {
        const field = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "ข้อมูล";

        return `${field}: ${item.msg || JSON.stringify(item)}`;
      }).join("\n");
    } else if (detail && typeof detail === "object") {
      message = JSON.stringify(detail, null, 2);
    } else {
      message = detail || `HTTP ${response.status}`;
    }

    throw new Error(message);
  }

  return body;
}

// --------------------------------------------------
// ตรวจสอบความพร้อมของระบบ
// --------------------------------------------------

async function checkHealth() {
  try {
    const h = await api("/api/health");
    const ready = h.dataset_directory_exists && h.model_exists;

    $("healthText").textContent = ready
      ? "ระบบพร้อมใช้งาน"
      : "ตรวจพบไฟล์ที่ยังขาด";

    document.querySelector(".status-dot").classList.toggle("ok", ready);
  } catch {
    $("healthText").textContent = "เชื่อมต่อ Backend ไม่ได้";
  }
}

async function refreshAll() {
  await checkHealth();

  try {
    experiments = await api("/api/experiments");
  } catch (e) {
    console.error(e);
    experiments = [];
  }

  renderDashboard();
  renderHistory();
}

// --------------------------------------------------
// Dashboard
// --------------------------------------------------

function renderDashboard() {
  const done = experiments.filter(
    (x) => x.status === "completed" && x.metrics
  );

  $("totalRuns").textContent = experiments.length;
  $("completedRuns").textContent = done.length;

  $("bestF1").textContent = done.length
    ? fmt(Math.max(...done.map((x) => x.metrics.f1)), 4)
    : "—";

  $("lastRun").textContent = experiments.length
    ? new Date(experiments[0].created_at).toLocaleString("th-TH", {
        dateStyle: "short",
        timeStyle: "short",
      })
    : "—";

  const rows = experiments.slice(0, 6);

  $("recentRows").innerHTML = rows.length
    ? rows.map((x) => `
      <tr class="clickable" data-open="${escapeHtml(x.id)}">
        <td>
          <div class="run-name">${escapeHtml(x.name)}</div>
          <div class="sub-id">${escapeHtml(x.id)}</div>
        </td>
        <td>${new Date(x.created_at).toLocaleString("th-TH")}</td>
        <td>${x.config?.threshold_percentile ?? "—"}%</td>
        <td>${x.metrics ? fmt(x.metrics.f1) : "—"}</td>
        <td>${statusBadge(x.status)}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="5" class="empty">ยังไม่มีการทดลอง เริ่มได้จากปุ่ม “สร้างการทดลอง”</td></tr>`;

  bindOpenRows();
}

// --------------------------------------------------
// ประวัติการทดลอง
// --------------------------------------------------

function renderHistory() {
  if (!$("historyRows")) return;

  const q = ($("searchHistory")?.value || "").toLowerCase();

  const filtered = experiments.filter((x) =>
    `${x.name} ${x.id}`.toLowerCase().includes(q)
  );

  $("historyRows").innerHTML = filtered.length
    ? filtered.map((x) => `
      <tr class="clickable" data-open="${escapeHtml(x.id)}">
        <td>
          <div class="run-name">${escapeHtml(x.name)}</div>
          <div class="sub-id">${escapeHtml(x.id)}</div>
        </td>
        <td>${new Date(x.created_at).toLocaleString("th-TH")}</td>
        <td>${x.config?.mode === "retrain" ? "ฝึกใหม่" : "โมเดลเดิม"}</td>
        <td>${x.config?.threshold_percentile ?? "—"}%</td>
        <td>${x.metrics ? fmt(x.metrics.f1) : "—"}</td>
        <td>${statusBadge(x.status)}</td>
        <td>
          <button class="button ghost small" data-open="${escapeHtml(x.id)}">
            เปิดผล
          </button>
        </td>
      </tr>
    `).join("")
    : `<tr><td colspan="7" class="empty">ไม่พบรายการทดลอง</td></tr>`;

  bindOpenRows();
}

function bindOpenRows() {
  document.querySelectorAll("[data-open]").forEach((el) => {
    el.onclick = () => openExperiment(el.dataset.open);
  });
}

// --------------------------------------------------
// Confusion Matrix
// --------------------------------------------------

function renderConfusion(m) {
  const a = m.matrix;

  $("confusionChart").innerHTML = `
    <div class="cm-label">ค่าจริง ↓<br>ทำนาย →</div>
    <div class="cm-label">Normal</div>
    <div class="cm-label">Attack</div>

    <div class="cm-label">Normal</div>
    <div class="cm-cell good">
      <strong>${a[0][0].toLocaleString()}</strong>
      <span>TN · Normal ถูก</span>
    </div>
    <div class="cm-cell bad">
      <strong>${a[0][1].toLocaleString()}</strong>
      <span>FP · False alarm</span>
    </div>

    <div class="cm-label">Attack</div>
    <div class="cm-cell bad">
      <strong>${a[1][0].toLocaleString()}</strong>
      <span>FN · พลาดการโจมตี</span>
    </div>
    <div class="cm-cell good">
      <strong>${a[1][1].toLocaleString()}</strong>
      <span>TP · ตรวจพบ</span>
    </div>
  `;
}

// --------------------------------------------------
// กราฟอัตราการตรวจพบ Attack แต่ละประเภท
// --------------------------------------------------

function renderBars(container, labels, values, maxRows = 30) {
  if (!labels?.length) {
    container.innerHTML = `<div class="empty">ไม่มีข้อมูลสำหรับแสดงกราฟ</div>`;
    return;
  }

  const ids = labels.map((l, i) => ({ l, v: values[i] })).slice(0, maxRows);

  container.innerHTML = ids.map(({ l, v }) => `
    <div class="bar-row">
      <div class="bar-name" title="${escapeHtml(l)}">${escapeHtml(l)}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${Math.max(0, Math.min(100, Number(v) * 100))}%"></div>
      </div>
      <div class="bar-value">${(Number(v) * 100).toFixed(1)}%</div>
    </div>
  `).join("");
}

// --------------------------------------------------
// กราฟ Training Loss
// --------------------------------------------------

function renderTraining(history) {
  if (!history?.length) {
    $("trainingPanel").classList.add("hidden");
    return;
  }

  $("trainingPanel").classList.remove("hidden");

  const max = Math.max(
    ...history.map((x) => x.validation_loss),
    ...history.map((x) => x.train_loss),
    0.000001
  );

  $("trainingChart").innerHTML = history.map((x) => `
    <div class="bar-row">
      <div class="bar-name">Epoch ${x.epoch}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${Math.min(100, x.validation_loss / max * 100)}%"></div>
      </div>
      <div class="bar-value">${fmt(x.validation_loss, 5)}</div>
    </div>
  `).join("");
}

// --------------------------------------------------
// เปิดดูผลการทดลอง
// --------------------------------------------------

async function openExperiment(id) {
  try {
    const x = await api(`/api/experiments/${encodeURIComponent(id)}`);

    currentExperimentId = id;

    const config = x.config || {};
    const metrics = x.metrics || {};

    $("resultName").textContent = x.name;
    $("resultMeta").textContent =
      `${x.id} · ${new Date(x.created_at).toLocaleString("th-TH")} · ${x.status}`;

    $("resultError").classList.toggle("hidden", !x.error);
    $("resultError").textContent = x.error || "";

    $("mAccuracy").textContent = pct(metrics.accuracy);
    $("mPrecision").textContent = pct(metrics.precision);
    $("mRecall").textContent = pct(metrics.recall);
    $("mF1").textContent = pct(metrics.f1);

    if (x.status === "completed" && x.metrics) {
      const cm = await api(
        `/api/experiments/${encodeURIComponent(id)}/files/confusion_matrix.json`
      );

      const attack = await api(
        `/api/experiments/${encodeURIComponent(id)}/files/detection_by_attack.json`
      );

      renderConfusion(cm);
      renderBars($("attackChart"), attack.labels, attack.rates);

      const items = [
        ["โหมด", config.mode === "retrain" ? "ฝึกโมเดลใหม่" : "ใช้โมเดลเดิม"],
        ["Dataset", config.dataset],
        ["Threshold percentile", `${config.threshold_percentile}%`],
        ["Threshold ที่คำนวณได้", fmt(metrics.threshold, 7)],
        ["จำนวน Features", metrics.feature_count],
        ["จำนวนข้อมูลทดสอบ", metrics.total_records],
        ["Epochs", config.epochs],
        ["Batch size", config.batch_size],
        ["Learning rate", config.learning_rate],
        ["False Positive Rate", pct(metrics.false_positive_rate)],
        ["TP / TN", `${metrics.tp} / ${metrics.tn}`],
        ["FP / FN", `${metrics.fp} / ${metrics.fn}`],
      ];

      $("configDetails").innerHTML = items.map(([k, v]) => `
        <div class="config-item">
          <span>${escapeHtml(k)}</span>
          <strong>${escapeHtml(v ?? "—")}</strong>
        </div>
      `).join("");

      $("resultStats").innerHTML = `
        <span>จำนวนข้อมูล <b>${metrics.total_records}</b></span>
        <span>Normal <b>${metrics.normal_count}</b></span>
        <span>Attack <b>${metrics.attack_count}</b></span>
        <span>ตรวจพบ Attack <b>${metrics.detected_attacks}</b></span>
        <span>พลาด Attack <b>${metrics.missed_attacks}</b></span>
      `;

      if (config.mode === "retrain") {
        try {
          const response = await fetch(
            `/api/experiments/${encodeURIComponent(id)}/files/training_history.csv`
          );

          if (!response.ok) {
            throw new Error("ไม่พบไฟล์ประวัติการเทรน");
          }

          const text = await response.text();

          const history = text.trim().split(/\r?\n/).slice(1).map((line) => {
            const [epoch, train_loss, validation_loss] = line.split(",").map(Number);
            return { epoch, train_loss, validation_loss };
          });

          renderTraining(history);

          $("downloadHistory").href =
            `/api/experiments/${encodeURIComponent(id)}/files/training_history.csv`;
        } catch {
          $("trainingPanel").classList.add("hidden");
        }
      } else {
        $("trainingPanel").classList.add("hidden");
      }
    } else {
      $("configDetails").innerHTML = `
        <div class="config-item">
          <span>สถานะ</span>
          <strong>${escapeHtml(x.status)}</strong>
        </div>
      `;

      $("confusionChart").innerHTML = "";
      $("attackChart").innerHTML = "";
      $("resultStats").innerHTML = "";
      $("trainingPanel").classList.add("hidden");
    }

    showPage("result");
  } catch (e) {
    alert(`เปิดผลการทดลองไม่ได้: ${e.message}`);
  }
}

// --------------------------------------------------
// ส่งคำขอเริ่มการทดลอง
// --------------------------------------------------

$("experimentForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  $("formError").classList.add("hidden");
  $("runProgress").classList.remove("hidden");
  $("runBtn").disabled = true;

  const fd = new FormData(e.target);
  const mode = fd.get("mode") || "existing";

  // กำหนดค่าเริ่มต้นให้ฟิลด์ที่ถูกปิดเมื่อเลือกโมเดลเดิม
  const payload = {
    name: (fd.get("name") || "Autoencoder experiment").trim(),
    dataset: fd.get("dataset") || "KDDTest",
    mode,
    threshold_percentile: Number(fd.get("threshold_percentile") || 95),
    epochs: Number(fd.get("epochs") || 20),
    batch_size: Number(fd.get("batch_size") || 256),
    learning_rate: Number(fd.get("learning_rate") || 0.001),
  };

  try {
    const result = await api("/api/experiments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    await refreshAll();
    await openExperiment(result.id);
  } catch (err) {
    $("formError").textContent = `ทดสอบไม่สำเร็จ: ${err.message}`;
    $("formError").classList.remove("hidden");

    await refreshAll();
  } finally {
    $("runProgress").classList.add("hidden");
    $("runBtn").disabled = false;
  }
});

// --------------------------------------------------
// ตรวจสอบไฟล์ที่จำเป็นก่อนใช้งาน
// --------------------------------------------------

async function checkReadiness() {
  $("preflight").textContent = "กำลังตรวจสอบ...";

  try {
    const h = await api("/api/health");

    const lines = [
      [
        h.dataset_directory_exists,
        `โฟลเดอร์ข้อมูล: ${h.dataset_directory_exists ? "พบ" : "ไม่พบ"}`,
      ],
      [
        h.model_exists,
        `ไฟล์โมเดล: ${h.model_exists ? "พบ" : "ไม่พบ"}`,
      ],
    ];

    $("preflight").innerHTML = lines.map(([ok, t]) => `
      <div class="${ok ? "ok" : "bad"}">${ok ? "✓" : "✕"} ${escapeHtml(t)}</div>
    `).join("") +
      `<div>ตำแหน่ง log: ${escapeHtml(h.backup_directory || h.database || "ไม่ระบุ")}</div>`;
  } catch (e) {
    $("preflight").textContent = e.message;
  }
}

refreshAll();
