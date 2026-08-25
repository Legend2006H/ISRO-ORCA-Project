const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : window.location.origin;
let location = { lat: 18.95, lon: 72.85 };
const sessionId = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
let latestResult = null;

const text = (id, value) => { document.getElementById(id).textContent = value; };
const percent = (id, value) => { document.getElementById(id).style.width = `${Math.max(0, Math.min(100, value))}%`; };
const format = (value, digits = 1) => Number(value).toFixed(digits);

function evidenceValue(item) {
  return typeof item.value === "number" ? `${format(item.value)} ${item.unit}` : item.value;
}

function render(result) {
  latestResult = result;
  const zone = result.recommendation;
  const safety = result.safety;
  const blocked = !safety.departure_allowed;
  text("zoneKicker", `PFZ · ${format(zone.distance_km)} km from Mumbai Harbour`);
  text("zoneTitle", zone.name);
  text("answer", result.answer);
  text("decisionStatus", blocked ? "DO NOT DEPART" : zone.decision_status);
  text("overallScore", format(zone.overall_score, 0));
  text("fishingScore", format(zone.fishing_score, 0));
  text("safetyScore", format(zone.safety_score, 0));
  text("dataScore", format(zone.data_quality_score, 0));
  percent("fishingBar", zone.fishing_score);
  percent("safetyBar", zone.safety_score);
  percent("dataBar", zone.data_quality_score);
  text("waveValue", `${format(safety.wave_height_m)} m`);
  const badge = document.getElementById("riskBadge");
  badge.textContent = blocked ? "HIGH RISK" : "LOW RISK";
  badge.className = `risk-badge ${blocked ? "high" : "low"}`;
  document.getElementById("hazardList").innerHTML = [
    `Wind: ${format(safety.wind_speed_ms)} m/s`,
    `Current: ${format(safety.current_speed_ms)} m/s`,
    `Swell: ${format(safety.swell_height_m)} m`,
    safety.reason,
  ].map((item, index) => `<li><span>${["↗", "◌", "≈", "!"][index]}</span>${item}</li>`).join("");
  document.querySelector(".source-line").textContent = `INCOIS cached evidence · ${result.freshness}`;
  document.querySelector(".sidebar-foot").firstChild.textContent = " CACHED MODE";
  document.getElementById("evidenceList").innerHTML = result.evidence.map((item) => `
    <div class="evidence-item"><span class="evidence-icon">◫</span><div><strong>${item.source}</strong>
    <p>${item.parameter} · <span class="status-chip">${item.source_mode}</span></p></div>
    <b class="evidence-value">${evidenceValue(item)}</b></div>`).join("");
  document.getElementById("traceList").innerHTML = result.trace.map((item) => `<li>${item}<span>validated cached-data step</span></li>`).join("");
  document.querySelector(".trace-status").textContent = `${result.trace.length}/${result.trace.length} COMPLETE`;
  document.querySelectorAll(".zone-node").forEach((node, index) => {
    const candidate = index === 0 ? zone : result.alternatives[index - 1];
    if (!candidate) return;
    node.dataset.zone = candidate.id;
    node.querySelector("b").textContent = index === 0 ? "Nearest PFZ" : `PFZ ${index + 1}`;
    node.querySelector("small").textContent = format(candidate.overall_score, 0);
  });
}

async function analyse() {
  const button = document.getElementById("askBtn");
  const message = document.getElementById("query").value.trim();
  if (!message) return;
  button.disabled = true;
  button.textContent = "Analyzing…";
  try {
    const response = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, location, language: document.getElementById("language").value, session_id: sessionId }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Analysis failed");
    render(result);
  } catch (error) {
    text("answer", `Could not contact the ORCA API: ${error.message}. Start it with: uvicorn api.main:app --reload`);
    text("decisionStatus", "API OFFLINE");
  } finally {
    button.disabled = false;
    button.innerHTML = "Analyze <span>→</span>";
  }
}

document.querySelectorAll(".quick-prompts button").forEach((button) => {
  button.addEventListener("click", () => { document.getElementById("query").value = button.dataset.query; analyse(); });
});
document.getElementById("askBtn").addEventListener("click", analyse);
document.getElementById("language").addEventListener("change", analyse);
document.querySelectorAll(".zone-node").forEach((node) => {
  node.addEventListener("click", () => {
    if (!latestResult) return;
    const selected = [latestResult.recommendation, ...latestResult.alternatives].find((item) => item.id === node.dataset.zone);
    if (!selected) return;
    render({ ...latestResult, recommendation: selected, answer: `${selected.name} is ${format(selected.distance_km)} km from your selected location. ${latestResult.safety.reason}` });
  });
});
document.getElementById("locateBtn").addEventListener("click", () => {
  const button = document.getElementById("locateBtn");
  if (!navigator.geolocation) {
    alert("Location is unavailable in this browser. Using Mumbai Harbour.");
    return;
  }
  button.textContent = "Locating…";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      location = { lat: position.coords.latitude, lon: position.coords.longitude };
      button.textContent = "Current location";
      analyse();
    },
    () => { button.textContent = "Mumbai Harbour"; alert("Location permission was not granted. Using Mumbai Harbour."); },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
  );
});
document.getElementById("evidenceBtn").addEventListener("click", () => alert("Every result shows its data source, timestamp, cache mode, and quality. Cached data is not a live operational advisory."));
analyse();
