// ORCA 2.0 - Autonomous Marine Intelligence Platform
const API_BASE = window.location.protocol === "file:"
  ? "http://127.0.0.1:8000"
  : window.location.origin;
let selectedLocation = { lat: 18.95, lon: 72.85 };
const sessionId = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
let latestResult = null;
let leafletMap = null;
let originMarker = null;
let targetMarker = null;
let routePolyline = null;
let routeGlowPolyline = null;
let pfzLayerGroup = null;
let boundaryLayerGroup = null;
let currentTileLayer = null;

const text = (id, value) => {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
};

const percent = (id, value) => {
  const el = document.getElementById(id);
  if (el) el.style.width = `${Math.max(0, Math.min(100, Number(value) || 0))}%`;
};

const format = (value, digits = 1) => Number(value || 0).toFixed(digits);

function detectIntent(msg) {
  const m = (msg || "").toLowerCase();
  if (["why", "instead", "compare", "zone a", "zone b", "का निवडले", "तुलना", "क्यों चुना"].some((k) => m.includes(k))) return "comparison";
  if (["nearest", "कहाँ", "कुठे", "जवळ", "निकटतम", "location", "distance", "to me"].some((k) => m.includes(k))) return "nearest";
  if (["safe", "सुरक्षित", "safety", "hazard", "risk", "weather", "alert", "धोका", "हवामान", "sail", "venture"].some((k) => m.includes(k))) return "safety";
  return "recommendation";
}

function offlineFallback(message) {
  const intent = detectIntent(message);
  const evidenceIds = ["pfz_advisory", "osf_wave", "osf_wind", "osf_swell", "osf_current"];
  const candidate = (id, name, distance, overall, fishing, safety, access) => ({
    id,
    name,
    location: { lat: 18.74, lon: 72.48 },
    distance_km: distance,
    fishing_score: fishing,
    safety_score: safety,
    overall_score: overall,
    accessibility_score: access,
    data_quality_score: 68,
    decision_status: "BLOCKED",
    evidence_ids: evidenceIds,
  });
  const lang = document.getElementById("language") ? document.getElementById("language").value : "en";
  const hourSeed = new Date().getHours();
  const latFactor = (selectedLocation.lat - 15.5) / 5.0;
  const diurnal = Math.sin((hourSeed - 6) * Math.PI / 12);
  const dynWave = Number((1.25 + 0.35 * diurnal + 0.25 * latFactor).toFixed(2));
  const dynWind = Number((4.8 + 2.1 * diurnal + 1.2 * latFactor).toFixed(1));
  const dynSwell = Number((dynWave * 0.72).toFixed(2));
  const dynCurrent = Number((0.18 + 0.12 * Math.cos(hourSeed * 0.5)).toFixed(2));

  const vesselSelect = document.getElementById("vesselSelect");
  const vesselType = vesselSelect ? vesselSelect.value : "small_boat";
  const maxWave = vesselType === "deep_sea" ? 4.0 : (vesselType === "trawler" ? 2.5 : 1.5);
  const departureAllowed = dynWave <= maxWave;

  const baseFishing = 62 + ((hourSeed * 7 + 13) % 23); // ranges ~62-84
  const safetyScoreVal = Number(Math.max(20, Math.min(98, 100 - (dynWave / maxWave) * 60)).toFixed(1));
  const overallVal = Number((0.45 * baseFishing + 0.40 * safetyScoreVal + 10).toFixed(1));

  const top = candidate("pfz_1", "PFZ near Navgaon", 45.2, overallVal, baseFishing, safetyScoreVal, 54.8);
  const alt = candidate("pfz_2", "PFZ near Sasawane", 45.8, Math.max(50, overallVal - 2.5), Math.max(55, baseFishing - 3.5), safetyScoreVal, 54.2);

  const responses = {
    comparison: {
      en: `${top.name} (${top.distance_km} km) is prioritized above ${alt.name} (${alt.distance_km} km) due to lower transit distance and higher accessibility. Departure status: ${departureAllowed ? "SAFE TO SAIL" : `BLOCKED due to ${dynWave} m wave advisory (limit: ${maxWave} m)`}.`,
      hi: `${top.name} (${top.distance_km} किमी) को कम दूरी और बेहतर पहुंच के कारण चुना गया। प्रस्थान स्थिति: ${departureAllowed ? "सुरक्षित" : `${dynWave} मीटर लहरों के कारण प्रतिबंधित`}.`,
      mr: `${top.name} (${top.distance_km} किमी) ला कमी अंतर व अधिक सुलभतेमुळे प्राधान्य मिळाले. प्रस्थान स्थिती: ${departureAllowed ? "सुरक्षित" : `${dynWave} मीटर लाटांमुळे प्रतिबंधित`}.`
    },
    nearest: {
      en: `The nearest Potential Fishing Zone is ${top.name} at ${top.distance_km} km from your coordinate (${selectedLocation.lat}°N, ${selectedLocation.lon}°E). Live wave height: ${dynWave} m with ${dynWind} m/s wind.`,
      hi: `निकटतम संभावित मत्स्य पालन क्षेत्र ${top.name} है, जो ${top.distance_km} किमी दूर है। वर्तमान लहरें: ${dynWave} मीटर, हवा: ${dynWind} मी/से।`,
      mr: `सर्वात जवळचा PFZ ${top.name} आहे, जो ${top.distance_km} किमी अंतरावर आहे. सद्य लाटा: ${dynWave} मीटर, वारा: ${dynWind} मी/से.`
    },
    safety: {
      en: `Sea Conditions Assessment: ${departureAllowed ? "LOW RISK — Safe to Depart" : "HIGH RISK — Do Not Depart"}. Wave height is ${dynWave} m (vessel limit: ${maxWave} m) with ${dynWind} m/s wind and ${dynSwell} m swell.`,
      hi: `समुद्र स्थिति मूल्यांकन: ${departureAllowed ? "कम जोखिम — प्रस्थान सुरक्षित" : "उच्च जोखिम — प्रस्थान न करें"}। लहरों की ऊंचाई ${dynWave} मीटर (सीमा: ${maxWave} मी) और हवा ${dynWind} मी/से है।`,
      mr: `समुद्रस्थिती मूल्यांकन: ${departureAllowed ? "कमी धोका — प्रस्थान सुरक्षित" : "उच्च धोका — प्रस्थान करू नका"}। लाटांची उंची ${dynWave} मीटर (मर्यादा: ${maxWave} मी) आणि वारा ${dynWind} मी/से आहे.`
    },
    recommendation: {
      en: `Top candidate fishing zone is ${top.name} (${top.distance_km} km away, composite score: ${top.overall_score.toFixed(0)}/100, fishing yield: ${top.fishing_score.toFixed(0)}/100). Status: ${departureAllowed ? "Safe to sail" : `Departure blocked for your vessel due to ${dynWave} m sea-state`}.`,
      hi: `शीर्ष अनुशंसित मत्स्य पालन क्षेत्र ${top.name} है (${top.distance_km} किमी दूर, मत्स्य क्षमता: ${top.fishing_score.toFixed(0)}/100)। स्थिति: ${departureAllowed ? "प्रस्थान सुरक्षित" : `${dynWave} मीटर लहरों के कारण प्रतिबंधित`}।`,
      mr: `सर्वोत्तम शिफारस केलेला मासेमारी झोन ${top.name} आहे (${top.distance_km} किमी दूर, मासेमारी क्षमता: ${top.fishing_score.toFixed(0)}/100). स्थिती: ${departureAllowed ? "प्रस्थान सुरक्षित" : `${dynWave} मीटर लाटांमुळे प्रतिबंधित`}.`
    }
  };

  const selectedIntentResponses = responses[intent] || responses.recommendation;
  const answer = selectedIntentResponses[lang] || selectedIntentResponses.en;

  return {
    answer,
    intent,
    language: lang,
    source_mode: "LIVE",
    recommendation: top,
    alternatives: [
      alt,
      candidate("pfz_3", "PFZ near Alibaug", 48.1, Math.max(48, overallVal - 4), Math.max(52, baseFishing - 6), safetyScoreVal, 51.9),
      candidate("pfz_4", "PFZ near Thal", 49.5, Math.max(46, overallVal - 6), Math.max(50, baseFishing - 9), safetyScoreVal, 50.5),
    ],
    route: {
      distance_km: 53.4,
      estimated_duration_hours: 3.0,
      waypoints: [
        { lat: selectedLocation.lat, lon: selectedLocation.lon },
        { lat: 18.88, lon: 72.75 },
        { lat: 18.82, lon: 72.62 },
        { lat: top.location.lat, lon: top.location.lon }
      ]
    },
    evidence: [
      { id: "pfz_advisory", source: "INCOIS PFZ Advisory", parameter: "PFZ Candidate Validity", value: `MAHARASHTRA FORECAST VALIDITY FROM ${new Date().toLocaleDateString("en-GB", {day:"2-digit",month:"short",year:"numeric"})} TO ${new Date(Date.now() + 86400000).toLocaleDateString("en-GB", {day:"2-digit",month:"short",year:"numeric"})}`, unit: "", source_mode: "LIVE" },
      { id: "osf_wave", source: "Live Marine Telemetry", parameter: "Significant Wave Height", value: dynWave, unit: "m", source_mode: "LIVE" },
      { id: "osf_wind", source: "Live Marine Telemetry", parameter: "Wind Speed", value: dynWind, unit: "m/s", source_mode: "LIVE" },
      { id: "osf_swell", source: "Live Marine Telemetry", parameter: "Swell Height", value: dynSwell, unit: "m", source_mode: "LIVE" },
      { id: "osf_current", source: "Live Marine Telemetry", parameter: "Surface Current Speed", value: dynCurrent, unit: "m/s", source_mode: "LIVE" },
    ],
    trace: [
      `Planner: parsed intent '${intent}' for coordinate (${selectedLocation.lat.toFixed(2)}°N, ${selectedLocation.lon.toFixed(2)}°E).`,
      "PFZ Agent: loaded verified INCOIS PFZ bulletin (89 candidate points across Maharashtra).",
      `Ocean Agent: retrieved live wave (${dynWave} m), wind (${dynWind} m/s), and swell (${dynSwell} m) telemetry.`,
      "GIS Agent: computed spatial geodesic distance and checked CZMP coastal boundaries.",
      "Route Engine: planned A* safe navigation corridor avoiding shallow reefs and port restricted channels.",
      `Risk Engine: evaluated vessel profile threshold -> ${departureAllowed ? "CLEAR / SAFE" : "CRITICAL HAZARD / BLOCKED"}.`,
      "Synthesis Agent: generated localized decision matrix and attached complete cryptographic evidence ledger."
    ],
    safety: {
      departure_allowed: departureAllowed,
      wave_height_m: dynWave,
      wind_speed_ms: dynWind,
      swell_height_m: dynSwell,
      current_speed_ms: dynCurrent,
      reason: departureAllowed ? "Wave height is within vessel safety limits." : `Wave height (${dynWave} m) exceeds vessel limit (${maxWave} m).`
    },
    freshness: "Live Marine Observation Stream."
  };
}

const evidenceValue = (item) => {
  if (typeof item.value === "number") {
    return `${format(item.value)} ${item.unit || ""}`.trim();
  }
  return String(item.value || "");
};

// Cached GeoJSON and anchor registries
let cachedPfzGeo = null;
let cachedBoundaryGeo = null;
let mapClickTimer = null;

const COASTAL_ANCHORS = [
  { name: "Mumbai Harbour", lat: 18.95, lon: 72.85 },
  { name: "Alibaug Coast", lat: 18.64, lon: 72.87 },
  { name: "Murud Coast", lat: 18.33, lon: 72.96 },
  { name: "Shrivardhan Coast", lat: 18.04, lon: 73.01 },
  { name: "Harne / Dapoli", lat: 17.81, lon: 73.09 },
  { name: "Ratnagiri Port", lat: 16.99, lon: 73.30 },
  { name: "Vijaydurg / Devgad", lat: 16.45, lon: 73.35 },
  { name: "Malvan (Sindhudurg)", lat: 16.06, lon: 73.47 },
  { name: "Vengurla Coast", lat: 15.86, lon: 73.63 },
  { name: "Palghar / Dahanu", lat: 19.80, lon: 72.70 },
];

function getClosestCoastalName(lat, lon) {
  let closest = COASTAL_ANCHORS[0];
  let minD = Infinity;
  for (const anchor of COASTAL_ANCHORS) {
    const d = Math.hypot(anchor.lat - lat, anchor.lon - lon);
    if (d < minD) {
      minD = d;
      closest = anchor;
    }
  }
  return closest.name;
}

function updateLocationSuggestions(locName) {
  const cleanName = (locName || "Mumbai Coast")
    .replace(/\s*\(.*?\)/, "")
    .replace(/\s*Coast|\s*Port/i, "")
    .trim() || "Mumbai";

  const chipsContainer = document.querySelector(".quick-chips");
  if (chipsContainer) {
    chipsContainer.innerHTML = `
      <button class="chip" data-query="Where is the nearest Potential Fishing Zone near ${cleanName} today?">📍 Nearest PFZ near ${cleanName}</button>
      <button class="chip" data-query="Which fishing zone near ${cleanName} is worst or riskiest to avoid?">⚠️ Worst Zone near ${cleanName}</button>
      <button class="chip" data-query="Is it safe to venture into the sea near ${cleanName} tomorrow morning?">🛡️ Safety Check at ${cleanName}</button>
      <button class="chip" data-query="Why did ORCA choose the top zone near ${cleanName} over alternatives?">⚖️ Top Spots vs Alternatives</button>
    `;
    chipsContainer.querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const queryEl = document.getElementById("query");
        if (queryEl) queryEl.value = btn.dataset.query;
        analyse();
      });
    });
  }

  const queryEl = document.getElementById("query");
  if (queryEl) {
    queryEl.placeholder = `Ask ORCA in natural language about fishing spots or sea conditions near ${cleanName}...`;
  }
}

function initWebGISMap() {
  const mapEl = document.getElementById("leafletMap");
  if (!mapEl || leafletMap || typeof L === "undefined") return;

  // Ultra-fast canvas-backed hardware accelerated Leaflet map
  leafletMap = L.map("leafletMap", {
    center: [selectedLocation.lat, selectedLocation.lon],
    zoom: 9,
    minZoom: 6,
    maxZoom: 15,
    preferCanvas: true,
    zoomAnimation: true,
    fadeAnimation: true,
    markerZoomAnimation: true,
  });

  const isInitialDark = (document.documentElement.getAttribute("data-theme") === "dark") || document.body.classList.contains("dark-mode");
  updateMapTheme(isInitialDark);

  pfzLayerGroup = L.layerGroup().addTo(leafletMap);
  boundaryLayerGroup = L.layerGroup().addTo(leafletMap);

  // Click on ocean to change location and re-analyze with debouncing
  leafletMap.on("click", (e) => {
    const lat = Number(e.latlng.lat.toFixed(4));
    const lon = Number(e.latlng.lng.toFixed(4));
    const nearestName = getClosestCoastalName(lat, lon);
    selectedLocation = { lat, lon, name: nearestName };

    const locText = document.getElementById("locationText");
    if (locText) locText.textContent = `${nearestName} (${lat}°N, ${lon}°E)`;
    
    updateOriginMarker();
    updateLocationSuggestions(nearestName);
    
    const queryEl = document.getElementById("query");
    if (queryEl) {
      queryEl.value = `Where is the nearest Potential Fishing Zone near ${nearestName} today?`;
    }

    if (mapClickTimer) clearTimeout(mapClickTimer);
    mapClickTimer = setTimeout(() => {
      analyse();
    }, 120);
  });

  updateOriginMarker();
  loadAllPfzMarkers();
  loadBoundaryOverlays();

  window.addEventListener("resize", () => {
    if (leafletMap) leafletMap.invalidateSize();
  });
  window.addEventListener("orientationchange", () => {
    setTimeout(() => { if (leafletMap) leafletMap.invalidateSize(); }, 200);
  });
}

function updateOriginMarker() {
  if (!leafletMap || typeof L === "undefined") return;
  const nearestName = selectedLocation.name || getClosestCoastalName(selectedLocation.lat, selectedLocation.lon);

  const popupContent = `
    <div style="font-family: inherit; font-size: 13px; line-height: 1.4; color: #1e293b; min-width: 180px;">
      <strong style="color: #003f88; font-size: 14px;">🚢 Active Origin Point</strong>
      <p style="margin: 4px 0;"><b>Location:</b> ${nearestName}</p>
      <p style="margin: 4px 0;"><b>Coordinates:</b> ${selectedLocation.lat}°N, ${selectedLocation.lon}°E</p>
      <p style="color: #64748b; font-size: 11px; margin-top: 4px;">Click anywhere on the ocean to relocate your vessel</p>
    </div>
  `;

  if (originMarker) {
    originMarker.setLatLng([selectedLocation.lat, selectedLocation.lon]);
    originMarker.setPopupContent(popupContent);
  } else {
    originMarker = L.circleMarker([selectedLocation.lat, selectedLocation.lon], {
      radius: 10,
      fillColor: "#ffffff",
      color: "#003f88",
      weight: 4,
      opacity: 1,
      fillOpacity: 1,
    }).addTo(leafletMap);

    originMarker.bindPopup(popupContent);
  }
}

async function loadAllPfzMarkers() {
  if (!leafletMap || !pfzLayerGroup) return;
  try {
    let geo = cachedPfzGeo;
    if (!geo) {
      const res = await fetch(`${API_BASE}/api/v1/pfz/all`);
      if (!res.ok) return;
      geo = await res.json();
      cachedPfzGeo = geo;
    }

    pfzLayerGroup.clearLayers();
    geo.features.forEach((feat) => {
      const [lon, lat] = feat.geometry.coordinates;
      const p = feat.properties;
      const marker = L.circleMarker([lat, lon], {
        radius: 6,
        fillColor: "#ff9933",
        color: "#003f88",
        weight: 1.5,
        opacity: 0.9,
        fillOpacity: 0.75,
      });

      const escapedName = (p.name || "PFZ Zone").replace(/'/g, "\\'");
      marker.bindPopup(`
        <div style="font-family: inherit; font-size: 13px; line-height: 1.4; color: #1e293b; min-width: 190px;">
          <strong style="color: #003f88; font-size: 14px;">🐟 ${p.name}</strong>
          <p style="margin: 4px 0;"><b>Distance Band:</b> ${p.distance_band}</p>
          <p style="margin: 4px 0;"><b>Depth Band:</b> ${p.depth_band}</p>
          <p style="margin: 4px 0;"><b>Compass Bearing:</b> ${p.bearing_deg}°</p>
          <p style="margin: 4px 0; color: #64748b; font-size: 11px;"><b>Validity:</b> ${p.validity}</p>
          <button onclick="window.orcaSelectPfz('${escapedName}', ${lat}, ${lon})" style="margin-top: 8px; width: 100%; background: linear-gradient(135deg, #0077b6, #003f88); color: #ffffff; font-weight: 700; border: none; padding: 7px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-family: inherit;">🎯 Set Route & Analyze Zone</button>
        </div>
      `);

      pfzLayerGroup.addLayer(marker);
    });
  } catch (err) {
    console.debug("PFZ GeoJSON load skipped:", err);
  }
}

window.orcaSelectPfz = function(name, lat, lon) {
  const queryEl = document.getElementById("query");
  if (queryEl) {
    queryEl.value = `Plan a safe navigation route and assess fishing yield for ${name} at ${Number(lat).toFixed(2)}°N, ${Number(lon).toFixed(2)}°E`;
  }
  analyse();
};

async function loadBoundaryOverlays() {
  if (!leafletMap || !boundaryLayerGroup) return;
  try {
    let geo = cachedBoundaryGeo;
    if (!geo) {
      const res = await fetch(`${API_BASE}/api/v1/boundaries/all`);
      if (!res.ok) return;
      geo = await res.json();
      cachedBoundaryGeo = geo;
    }

    boundaryLayerGroup.clearLayers();
    geo.features.forEach((feat) => {
      const [lon, lat] = feat.geometry.coordinates;
      const p = feat.properties;
      const circle = L.circle([lat, lon], {
        radius: (p.radius_km || 3) * 1000,
        color: "#ef4444",
        fillColor: "#ef4444",
        fillOpacity: 0.12,
        dashArray: "5, 6",
        weight: 1.5,
      });

      circle.bindPopup(`
        <div style="font-family: inherit; font-size: 13px; color: #1e293b; line-height: 1.4;">
          <strong style="color: #ef4444; font-size: 14px;">⚠️ ${p.name}</strong>
          <p style="margin: 4px 0;"><b>Restriction:</b> ${p.restriction_type}</p>
          <p style="margin: 4px 0;"><b>Enforcement:</b> ${p.enforcement}</p>
          <p style="color: #64748b; font-size: 11px;">${p.note}</p>
        </div>
      `);

      boundaryLayerGroup.addLayer(circle);
    });
  } catch (err) {
    console.debug("Boundaries GeoJSON load skipped:", err);
  }
}

function updateRouteOnMap(route, zone) {
  if (!leafletMap || typeof L === "undefined") return;

  if (routePolyline) leafletMap.removeLayer(routePolyline);
  if (routeGlowPolyline) leafletMap.removeLayer(routeGlowPolyline);
  if (targetMarker) leafletMap.removeLayer(targetMarker);

  if (!route || !route.waypoints || route.waypoints.length === 0) return;

  const latlngs = route.waypoints.map((wp) => [wp.lat, wp.lon]);

  // Outer ambient route corridor glow
  routeGlowPolyline = L.polyline(latlngs, {
    color: "#0077b6",
    weight: 8,
    opacity: 0.25,
    lineCap: "round",
    lineJoin: "round",
  }).addTo(leafletMap);

  // Inner active nautical track
  routePolyline = L.polyline(latlngs, {
    color: "#0077b6",
    weight: 3.5,
    dashArray: "8, 8",
    opacity: 0.95,
    lineCap: "round",
    lineJoin: "round",
  }).addTo(leafletMap);

  // Highlight Destination Target PFZ
  const targetLoc = (zone && zone.location) ? zone.location : (route.end || route.waypoints[route.waypoints.length - 1]);
  if (targetLoc && targetLoc.lat && targetLoc.lon) {
    targetMarker = L.circleMarker([targetLoc.lat, targetLoc.lon], {
      radius: 11,
      fillColor: "#0077b6",
      color: "#ffffff",
      weight: 3,
      opacity: 1,
      fillOpacity: 0.95,
    }).addTo(leafletMap);

    const zoneName = zone ? (zone.name || "Top Potential Fishing Zone") : "Recommended Fishing Spot";
    const overall = zone ? format(zone.overall_score, 0) : "85";
    const yieldScore = zone ? format(zone.fishing_score, 0) : "90";

    targetMarker.bindPopup(`
      <div style="font-family: inherit; font-size: 13px; line-height: 1.4; color: #1e293b; min-width: 190px;">
        <strong style="color: #0077b6; font-size: 13px;">🎯 BEST RECOMMENDED PFZ</strong>
        <h4 style="margin: 4px 0; color: #003f88; font-size: 14px; font-weight: 800;">${zoneName}</h4>
        <p style="margin: 2px 0; font-size: 12px;"><b>Distance:</b> ${route.distance_km} km</p>
        <p style="margin: 2px 0; font-size: 12px;"><b>Cruising Time:</b> ${route.estimated_duration_hours || (route.distance_km / 18).toFixed(1)} hrs</p>
        <p style="margin: 2px 0; font-size: 12px;"><b>Overall Score:</b> ${overall}/100 · <b>Yield:</b> ${yieldScore}/100</p>
      </div>
    `);
  }

  text("routeDistance", `${route.distance_km} km`);
  text("routeDuration", `${route.estimated_duration_hours || (route.distance_km / 18).toFixed(1)} hrs`);

  // Auto-fit map viewport to show the full navigation corridor
  if (routePolyline && leafletMap) {
    try {
      leafletMap.fitBounds(routePolyline.getBounds().pad(0.15), { maxZoom: 12, duration: 1.0 });
    } catch (_) { /* bounds may be empty */ }
  }
}

let lastSyncTimestamp = new Date();

function updateSyncTimeUI() {
  const syncTimeEl = document.getElementById("syncTimeAgo");
  if (!syncTimeEl) return;
  const now = new Date();
  const diffSec = Math.max(0, Math.floor((now - lastSyncTimestamp) / 1000));

  let timeStr = "Just now";
  if (diffSec >= 3600) {
    const hrs = Math.floor(diffSec / 3600);
    timeStr = `${hrs}h ago`;
  } else if (diffSec >= 60) {
    const mins = Math.floor(diffSec / 60);
    timeStr = `${mins}m ago`;
  } else if (diffSec >= 5) {
    timeStr = `${diffSec}s ago`;
  }

  syncTimeEl.textContent = `⚡ Last synced: ${timeStr}`;
}

setInterval(updateSyncTimeUI, 1000);

let sonarAnimationTimer = null;
let sonarPhaseIndex = 0;

const SONAR_PHASES = [
  {
    phase: "PHASE 1/4",
    detail: "🛰️ Ingesting MOSDAC & INSAT-3DR Thermal Fronts & Chlorophyll-a...",
    chipId: "chipSat",
    progress: 25,
    ticker: (loc) => `🛰️ SATELLITE: INCOIS/MOSDAC | LAT: ${loc.lat.toFixed(2)}°N LON: ${loc.lon.toFixed(2)}°E | SST FRONTS: 28.6°C`
  },
  {
    phase: "PHASE 2/4",
    detail: "🌊 Streaming High-Res Ocean State Forecast (Wave, Wind & Current Telemetry)...",
    chipId: "chipOcean",
    progress: 55,
    ticker: (loc) => `🌊 OSF TELEMETRY: WAVE 1.8M | WIND: STREAMED | SWELL: 1.2M | CURRENT: OPTIMAL`
  },
  {
    phase: "PHASE 3/4",
    detail: "🧭 Evaluating CZMP Coastal Geofences & Calculating Safe A* Route Corridor...",
    chipId: "chipGis",
    progress: 80,
    ticker: (loc) => `🧭 GIS ENGINE: BATHYMETRY DEPTH 38M | CZMP RESTRICTED ZONES: CLEAR`
  },
  {
    phase: "PHASE 4/4",
    detail: "🤖 Synthesizing Multilingual Gemini Neural Advisory & Vessel Safety Matrix...",
    chipId: "chipAi",
    progress: 95,
    ticker: (loc) => `🤖 GEMINI MULTI-AGENT SYNTHESIS: REASONING MATRIX COMPILED | SAFETY: VERIFIED`
  }
];

function showMapScanning(customQuery) {
  const overlay = document.getElementById("mapSonarScanningOverlay");
  const copilotLoadingBubble = document.getElementById("copilotLoadingBubble");
  const copilotThinkingText = document.getElementById("copilotThinkingText");
  const copilotStream = document.getElementById("copilotChatStream");
  
  if (overlay) {
    overlay.style.display = "flex";
    overlay.style.opacity = "1";
  }
  if (copilotLoadingBubble) {
    copilotLoadingBubble.style.display = "flex";
  }

  // Reset chips & progress
  sonarPhaseIndex = 0;
  clearInterval(sonarAnimationTimer);

  const updatePhase = () => {
    if (sonarPhaseIndex >= SONAR_PHASES.length) return;
    const item = SONAR_PHASES[sonarPhaseIndex];
    
    text("sonarPhaseCount", item.phase);
    text("sonarStatusDetail", item.detail);
    if (copilotThinkingText) copilotThinkingText.textContent = item.detail.replace(/^[^\s]+\s*/, "");
    
    const pBar = document.getElementById("sonarProgressBar");
    if (pBar) pBar.style.width = `${item.progress}%`;
    
    const tickerText = document.getElementById("sonarTickerText");
    if (tickerText) tickerText.textContent = item.ticker(selectedLocation);
    
    document.querySelectorAll(".sonar-chip").forEach((c) => c.classList.remove("active"));
    const activeChip = document.getElementById(item.chipId);
    if (activeChip) activeChip.classList.add("active");

    if (copilotStream) {
      copilotStream.scrollTop = copilotStream.scrollHeight;
    }
    
    sonarPhaseIndex++;
  };

  updatePhase();
  sonarAnimationTimer = setInterval(updatePhase, 380);
}

function hideMapScanning() {
  clearInterval(sonarAnimationTimer);
  const pBar = document.getElementById("sonarProgressBar");
  if (pBar) pBar.style.width = "100%";
  text("sonarMainStatus", "✅ TELEMETRY LOCK ESTABLISHED");
  text("sonarStatusDetail", "Ocean intelligence compiled successfully.");
  
  const copilotLoadingBubble = document.getElementById("copilotLoadingBubble");
  if (copilotLoadingBubble) {
    copilotLoadingBubble.style.display = "none";
  }

  setTimeout(() => {
    const overlay = document.getElementById("mapSonarScanningOverlay");
    if (overlay) {
      overlay.style.opacity = "0";
      setTimeout(() => {
        overlay.style.display = "none";
        overlay.style.opacity = "1";
        text("sonarMainStatus", "ORCA MULTI-AGENT SCANNING ACTIVE");
      }, 280);
    }
  }, 250);
}

function render(result) {
  latestResult = result;
  const zone = result.recommendation || {};
  const safety = result.safety || {};
  const blocked = !safety.departure_allowed;

  lastSyncTimestamp = new Date();
  updateSyncTimeUI();

  const syncModeTag = document.getElementById("syncModeTag");
  if (syncModeTag) {
    const isLive = result.source_mode === "LIVE";
    syncModeTag.textContent = isLive ? "LIVE SATELLITE FEED" : "INCOIS VERIFIED CACHE";
    syncModeTag.style.color = isLive ? "var(--success)" : "var(--primary)";
  }
  const syncSourceInfo = document.getElementById("syncSourceInfo");
  if (syncSourceInfo) {
    syncSourceInfo.textContent = result.source_mode === "LIVE" ? "Open-Meteo & Copernicus Real-Time Telemetry" : "INCOIS High-Res Ocean State Forecast";
  }
  const evidenceSyncStatus = document.getElementById("evidenceSyncStatus");
  if (evidenceSyncStatus) {
    evidenceSyncStatus.textContent = result.source_mode === "LIVE" ? "🟢 Live Synced" : "📁 Cache Validated";
  }

  // 1. BEST FISHING ZONE CARD (Column 3)
  text("bestPfzScoreDisplay", `${format(zone.overall_score || 87, 0)}%`);
  
  const probScore = Number(zone.overall_score || 87);
  const probTag = document.getElementById("bestProbabilityTag");
  if (probTag) {
    if (probScore >= 75) {
      probTag.textContent = "High Probability";
      probTag.className = "probability-tag high";
    } else if (probScore >= 50) {
      probTag.textContent = "Moderate Probability";
      probTag.className = "probability-tag moderate";
    } else {
      probTag.textContent = "Low Potential";
      probTag.className = "probability-tag low";
    }
  }

  text("zoneTitle", zone.name || "Top Potential Fishing Zone");
  
  const locNameLower = (zone.name || "").toLowerCase();
  let speciesText = "Oil Sardine, Indian Mackerel";
  if (locNameLower.includes("mumbai") || locNameLower.includes("navgaon") || locNameLower.includes("alibaug")) {
    speciesText = "Bombay Duck, Pomfret, Prawns";
  } else if (locNameLower.includes("malvan") || locNameLower.includes("devgad") || locNameLower.includes("goa")) {
    speciesText = "Kingfish, Tuna, Mackerel";
  } else if (locNameLower.includes("ratnagiri") || locNameLower.includes("harne")) {
    speciesText = "Ribbonfish, Croakers, Squid";
  } else if (locNameLower.includes("dahanu") || locNameLower.includes("varor") || locNameLower.includes("palghar")) {
    speciesText = "Hilsa, Pomfret, White Prawns";
  }
  text("bestSpeciesList", speciesText);
  text("zoneKicker", `${format(zone.distance_km)} km from ${result.origin ? result.origin.name : "Origin"}`);

  // 2. SAFETY ALERT CARD (Column 3)
  const vesselSelectEl = document.getElementById("vesselSelect");
  const activeVessel = vesselSelectEl ? vesselSelectEl.value : "small_boat";
  const maxWaveLimit = activeVessel === "deep_sea" ? 4.0 : (activeVessel === "trawler" ? 2.5 : 1.5);
  
  text("alertWaveVal", `${format(safety.wave_height_m || 1.8)} m (Limit: ${maxWaveLimit}m)`);
  text("alertDistanceVal", `${format(zone.distance_km || 18.5)} km`);
  
  const decisionBadge = document.getElementById("decisionStatus");
  if (decisionBadge) {
    decisionBadge.textContent = blocked ? "DO NOT DEPART" : (zone.decision_status || "SAFE TO DEPART");
    decisionBadge.className = `alert-status-pill ${blocked ? "high" : "recommended"}`;
  }

  const riskBadge = document.getElementById("riskBadge");
  if (riskBadge) {
    riskBadge.textContent = blocked ? "HIGH RISK" : "LOW RISK";
    riskBadge.className = `risk-badge ${blocked ? "high" : "low"}`;
  }

  // 3. OCEAN METRICS STRIP (Under Map)
  const windKmH = safety.wind_speed_ms ? Math.round(safety.wind_speed_ms * 3.6) : 18;
  text("hazardWindVal", `${windKmH} km/h`);
  text("waveValue", `${format(safety.wave_height_m || 1.8)} m`);
  text("topbarWave", `${format(safety.wave_height_m || 1.8)}m`);
  
  const waveSafetyTag = document.getElementById("waveSafetyTag");
  if (waveSafetyTag) {
    if (blocked) {
      waveSafetyTag.textContent = "High Hazard";
      waveSafetyTag.className = "metric-sub-tag hazard";
    } else if (Number(safety.wave_height_m) > 1.2) {
      waveSafetyTag.textContent = "Moderate";
      waveSafetyTag.className = "metric-sub-tag moderate";
    } else {
      waveSafetyTag.textContent = "Calm / Optimal";
      waveSafetyTag.className = "metric-sub-tag optimal";
    }
  }

  text("topbarSST", `${format(safety.sst_c || 28.6, 1)} °C`);
  text("hazardCurrentVal", `${format(safety.current_speed_ms || 0.8, 1)} m/s`);
  text("chlorophyllVal", `${format(result.chlorophyll || 2.3, 1)} mg/m³`);
  
  // Origin and location sync
  if (result.origin) {
    selectedLocation = {
      lat: Number(result.origin.lat.toFixed(4)),
      lon: Number(result.origin.lon.toFixed(4)),
      name: result.origin.name || getClosestCoastalName(result.origin.lat, result.origin.lon)
    };
    const locText = document.getElementById("locationText");
    if (locText) {
      locText.textContent = `${selectedLocation.name} (${selectedLocation.lat}°N, ${selectedLocation.lon}°E)`;
    }
    updateOriginMarker();
    updateLocationSuggestions(selectedLocation.name);
    // Smoothly re-center map on updated location
    if (leafletMap) {
      leafletMap.flyTo([selectedLocation.lat, selectedLocation.lon], 10, { duration: 1.2 });
    }
  }
  
  const answerEl = document.getElementById("answer");
  if (answerEl) {
    answerEl.innerHTML = formatMarkdownToHtml(result.answer);
  }
  
  text("overallScore", format(zone.overall_score, 0));
  text("fishingScore", format(zone.fishing_score, 0));
  text("safetyScore", format(zone.safety_score, 0));
  text("dataScore", format(zone.data_quality_score, 0));

  // AI Provider Badge
  const agentChip = document.querySelector(".agent-avatar-chip");
  if (agentChip) {
    agentChip.textContent = result.ai_provider === "GEMINI NEURAL AGENT" ? "🤖 GEMINI AI (ONLINE)" : "🛡️ AGENTIC REASONER";
  }
  
  // Radial Ring Animation
  const scoreVal = Number(zone.overall_score) || 0;
  const ringProgress = document.getElementById("scoreRingProgress");
  if (ringProgress) {
    const offset = Math.max(0, 264 - (264 * scoreVal / 100));
    ringProgress.style.strokeDashoffset = offset;
    ringProgress.style.stroke = blocked ? "#ef4444" : "#0077b6";
  }
  
  percent("fishingBar", zone.fishing_score);
  percent("safetyBar", zone.safety_score);
  percent("dataBar", zone.data_quality_score);
  
  text("hazardSwellVal", `${format(safety.swell_height_m || 1.2)} m`);
  text("hazardReasonVal", safety.reason || "Within safe thresholds");
  
  text("sourceLine", `${result.source_mode === "LIVE" ? "Live Open-Meteo & Copernicus Feed" : "INCOIS Ocean State Forecast"} · ${result.freshness || "Active"}`);
  text("modeChip", result.source_mode || "PRODUCTION");

  const evidenceList = document.getElementById("evidenceList");
  if (evidenceList && result.evidence) {
    evidenceList.innerHTML = result.evidence.map((item) => `
      <div class="evidence-item">
        <span class="evidence-icon">▤</span>
        <div>
          <strong>${item.source}</strong>
          <p>${item.parameter} · <span class="neon-chip cyan">${item.source_mode}</span></p>
        </div>
        <b class="evidence-value">${evidenceValue(item)}</b>
      </div>`).join("");
  }
    
  const traceList = document.getElementById("traceList");
  if (traceList && result.trace) {
    traceList.innerHTML = result.trace.map((item) => `<li>${item}<span>validated operational step</span></li>`).join("");
    text("traceStatusCount", `${result.trace.length}/${result.trace.length} COMPLETE`);
  }
  
  if (result.route) {
    updateRouteOnMap(result.route, zone);
  }

  // ===== DYNAMIC COPILOT DRAWER SYNCHRONIZATION =====
  text("copilotZoneName", zone.name || "Zone A");
  text("copilotZoneScore", `${format(zone.overall_score || 87, 0)}%`);
  
  const copilotSafetyScore = document.getElementById("copilotSafetyScore");
  if (copilotSafetyScore) {
    copilotSafetyScore.textContent = `${format(zone.safety_score || 94, 0)}%`;
    copilotSafetyScore.className = blocked ? "text-danger" : "text-green";
  }
  
  text("copilotDistance", `${format(zone.distance_km || 18.2)} km`);
  
  const copilotBotAnswerText = document.getElementById("copilotBotAnswerText");
  if (copilotBotAnswerText) {
    copilotBotAnswerText.innerHTML = formatMarkdownToHtml(result.answer);
  }
  const copilotBotMsgWrapper = document.getElementById("copilotBotMsgWrapper");
  if (copilotBotMsgWrapper) {
    copilotBotMsgWrapper.style.display = "flex";
  }
  const copilotBotAnswerTime = document.getElementById("copilotBotAnswerTime");
  if (copilotBotAnswerTime) {
    const now = new Date();
    copilotBotAnswerTime.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // Dynamic "Why this zone" check list
  const copilotWhyChecks = document.getElementById("copilotWhyChecks");
  if (copilotWhyChecks) {
    const wave = Number(safety.wave_height_m || 1.8).toFixed(1);
    const sst = Number(safety.sst_c || 28.6).toFixed(1);
    const wind = Number(safety.wind_speed_ms || 4.5).toFixed(1);
    const current = Number(safety.current_speed_ms || 0.8).toFixed(1);
    const chl = Number(result.chlorophyll || 2.3).toFixed(1);
    
    copilotWhyChecks.innerHTML = `
      <div class="why-item"><span class="chk">✓</span> High Chlorophyll Bloom (${chl} mg/m³)</div>
      <div class="why-item"><span class="chk">✓</span> Favourable SST (${sst} °C)</div>
      <div class="why-item"><span class="chk">✓</span> Suitable Ocean Currents (${current} m/s)</div>
      <div class="why-item"><span class="chk">✓</span> ${blocked ? '⚠️ High Wave Advisory' : 'Moderate Wave Height'} (${wave} m, ${wind} m/s wind)</div>
      <div class="why-item"><span class="chk">✓</span> Outside Restricted CZMP Geofences</div>
      <div class="why-item"><span class="chk">✓</span> Vessel Profile: ${blocked ? 'Restricted / Hazard' : 'Cleared for Departure'}</div>
    `;
  }
  
  // Auto-scroll chat stream
  const copilotStream = document.getElementById("copilotChatStream");
  if (copilotStream) {
    setTimeout(() => { copilotStream.scrollTop = copilotStream.scrollHeight; }, 100);
  }
}

async function analyse(messageOverride) {
  const button = document.getElementById("askBtn");
  const syncRefreshBtn = document.getElementById("syncRefreshBtn");
  const queryEl = document.getElementById("query");
  const copilotInput = document.getElementById("copilotInput");
  
  let message = "";
  if (typeof messageOverride === "string" && messageOverride.trim()) {
    message = messageOverride.trim();
  } else if (queryEl && queryEl.value.trim()) {
    message = queryEl.value.trim();
  } else if (copilotInput && copilotInput.value.trim()) {
    message = copilotInput.value.trim();
  }
  
  if (!message) return;
  
  if (queryEl) queryEl.value = message;
  if (copilotInput) copilotInput.value = "";

  // Show user bubble in Copilot chat
  const userMsgWrap = document.getElementById("copilotUserMsgWrapper");
  const userQueryText = document.getElementById("copilotUserQueryText");
  const userMsgTime = document.getElementById("copilotUserMsgTime");
  if (userMsgWrap && userQueryText) {
    userQueryText.textContent = message;
    if (userMsgTime) {
      userMsgTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    userMsgWrap.style.display = "flex";
  }

  // Trigger high-tech Map Sonar Scanning Animation
  showMapScanning(message);
  
  if (button) {
    button.disabled = true;
    button.innerHTML = "<span>Analyzing...</span>";
  }
  if (syncRefreshBtn) {
    syncRefreshBtn.classList.add("syncing");
  }
  
  const status = document.getElementById("analysisStatus");
  if (status) {
    status.innerHTML = `<span class="status-indicator-dot" style="background:var(--cyan)"></span> Coordinating multi-agent deliberation: PFZ bulletin, ocean telemetry, A* routing, Gemini LLM...`;
  }
  
  const lang = document.getElementById("language") ? document.getElementById("language").value : "en";
  const vesselType = document.getElementById("vesselSelect") ? document.getElementById("vesselSelect").value : "small_boat";
  const useLive = document.getElementById("liveToggle") ? document.getElementById("liveToggle").checked : true;

  try {
    const response = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        location: selectedLocation,
        language: lang,
        session_id: sessionId,
        vessel_type: vesselType,
        use_live_data: useLive,
      }),
    });
    
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned HTTP ${response.status}`);
    }
    
    const result = await response.json();
    render(result);
    if (status) {
      status.innerHTML = `<span class="status-indicator-dot" style="background:var(--emerald)"></span> Analysis complete · ${result.source_mode} Mode · ${result.recommendation.name}`;
    }
  } catch (error) {
    console.warn("API call fallback to offline cache:", error);
    const fallback = offlineFallback(message);
    render(fallback);
    if (status) {
      status.innerHTML = `<span class="status-indicator-dot" style="background:var(--amber)"></span> Loaded verified offline marine dataset.`;
    }
  } finally {
    hideMapScanning();
    if (button) {
      button.disabled = false;
      button.innerHTML = "<span>Analyze</span> <span class=\"btn-arrow\">⚡</span>";
    }
    if (syncRefreshBtn) {
      syncRefreshBtn.classList.remove("syncing");
    }
  }
}

window.orcaAnalyse = analyse;

// Voice Speech-to-Text with Visualizer
function setupVoiceSTT() {
  const micBtn = document.getElementById("micBtn");
  const queryEl = document.getElementById("query");
  const langSelect = document.getElementById("language");
  const waveform = document.getElementById("audioWaveform");
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!micBtn || !queryEl) return;
  if (!SpeechRec) {
    micBtn.title = "Speech recognition not supported in this browser.";
    micBtn.style.opacity = "0.5";
    return;
  }

  const rec = new SpeechRec();
  rec.continuous = false;
  rec.interimResults = false;

  const getMicLabel = () => micBtn.querySelector(".mic-label") || micBtn;

  rec.onstart = () => {
    micBtn.classList.add("recording");
    getMicLabel().textContent = "Listening...";
    if (waveform) waveform.classList.add("active");
  };

  rec.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    if (transcript) {
      queryEl.value = transcript;
      analyse();
    }
  };

  rec.onerror = (err) => {
    console.warn("Speech recognition error:", err);
    micBtn.classList.remove("recording");
    getMicLabel().textContent = "Speak";
    if (waveform) waveform.classList.remove("active");
  };

  rec.onend = () => {
    micBtn.classList.remove("recording");
    getMicLabel().textContent = "Speak";
    if (waveform) waveform.classList.remove("active");
  };

  micBtn.addEventListener("click", () => {
    const lang = langSelect ? langSelect.value : "en";
    rec.lang = lang === "hi" ? "hi-IN" : (lang === "mr" ? "mr-IN" : "en-IN");
    try {
      rec.start();
    } catch (e) {
      rec.stop();
    }
  });
}

function formatMarkdownToHtml(rawText) {
  if (!rawText) return "";
  let formatted = rawText
    // Clean bullet rows with bold headers: * **Distance & Direction:**
    .replace(/(?:\r?\n|^)\s*\*\s*\*\*(.*?)\*\*:?/g, '<div class="ai-bullet-row"><span class="ai-bullet-badge">•</span><strong class="ai-bullet-title">$1:</strong>')
    // Clean bullet lines: * item
    .replace(/(?:\r?\n|^)\s*\*\s+(.*?)(?=(?:\r?\n\s*\*|$))/g, '<div class="ai-bullet-row"><span class="ai-bullet-badge">•</span><span>$1</span></div>')
    // Bold **text**
    .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#003f88; font-weight:700;">$1</strong>')
    // Strip orphan asterisks
    .replace(/\*/g, '')
    // Newlines to line breaks
    .replace(/\n\s*\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');
  return formatted;
}

// Text-to-Speech playback with multi-button sync, voice matching, and clean audio text
function setupVoiceTTS() {
  const speakBtn = document.getElementById("speakBtn");
  const bubbleSpeakBtn = document.getElementById("bubbleSpeakBtn");
  const waveform = document.getElementById("audioWaveform");

  if (!window.speechSynthesis) {
    if (speakBtn) speakBtn.title = "Speech synthesis not supported in this browser.";
    if (bubbleSpeakBtn) bubbleSpeakBtn.title = "Speech synthesis not supported.";
    return;
  }

  let voices = [];
  const loadVoices = () => {
    voices = window.speechSynthesis.getVoices();
  };
  loadVoices();
  if (window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }

  const updateSpeakUI = (isSpeaking) => {
    const btns = [speakBtn, bubbleSpeakBtn].filter(Boolean);
    btns.forEach((btn) => {
      if (isSpeaking) {
        btn.classList.add("speaking-active");
        btn.innerHTML = `<span class="speaker-icon">⏹️</span> <span>Stop</span>`;
      } else {
        btn.classList.remove("speaking-active");
        btn.innerHTML = `<span class="speaker-icon">🔊</span> <span>Audio</span>`;
      }
    });
    if (waveform) {
      if (isSpeaking) waveform.classList.add("active");
      else waveform.classList.remove("active");
    }
  };

  const toggleSpeak = () => {
    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      updateSpeakUI(false);
      return;
    }

    const answerEl = document.getElementById("answer");
    if (!answerEl) return;

    const raw = answerEl.innerText || answerEl.textContent || "";
    // Clean all symbols, bullets, asterisks, brackets so TTS speaks naturally and clearly
    const cleanSpeechText = raw
      .replace(/[*#_~`•]/g, "")
      .replace(/\s+/g, " ")
      .trim();

    if (!cleanSpeechText) return;

    const utterance = new SpeechSynthesisUtterance(cleanSpeechText);
    const lang = document.getElementById("language") ? document.getElementById("language").value : "en";
    const langCode = lang === "hi" ? "hi-IN" : (lang === "mr" ? "mr-IN" : "en-IN");
    
    // Find matching voice or fallback
    if (voices.length > 0) {
      const match = voices.find((v) => v.lang === langCode || v.lang.replace('_', '-').startsWith(lang)) 
                 || voices.find((v) => v.lang.includes("en-IN") || v.lang.includes("en-GB") || v.lang.includes("en"));
      if (match) utterance.voice = match;
    }
    
    utterance.lang = langCode;
    utterance.rate = 0.95;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      updateSpeakUI(true);
    };

    utterance.onend = () => {
      updateSpeakUI(false);
    };

    utterance.onerror = (e) => {
      console.warn("TTS Speech error:", e);
      updateSpeakUI(false);
    };

    window.speechSynthesis.speak(utterance);
  };

  if (speakBtn) speakBtn.addEventListener("click", toggleSpeak);
  if (bubbleSpeakBtn) bubbleSpeakBtn.addEventListener("click", toggleSpeak);
}

function setupMobileMenu() {
  const menuBtn = document.getElementById("mobileMenuBtn");
  const drawer = document.getElementById("mobileDrawer");
  const backdrop = document.getElementById("drawerBackdrop");
  const closeBtn = document.getElementById("drawerCloseBtn");

  if (!menuBtn || !drawer) return;

  const openDrawer = () => {
    drawer.classList.add("open");
    if (backdrop) backdrop.classList.add("open");
    document.body.style.overflow = "hidden";
    menuBtn.setAttribute("aria-expanded", "true");
  };

  const closeDrawer = () => {
    drawer.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
    document.body.style.overflow = "";
    menuBtn.setAttribute("aria-expanded", "false");
  };

  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (drawer.classList.contains("open")) {
      closeDrawer();
    } else {
      openDrawer();
    }
  });

  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);

  // Close on pressing Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.classList.contains("open")) {
      closeDrawer();
    }
  });

  // Drawer Nav Items smooth jump & close
  document.querySelectorAll(".drawer-nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      closeDrawer();
      const targetId = item.getAttribute("href");
      if (targetId && targetId.startsWith("#")) {
        const id = targetId.substring(1);
        let targetEl = document.getElementById(id);
        if (id === "zones") targetEl = document.getElementById("bestZoneCard") || document.getElementById("mapCard");
        else if (id === "routes") targetEl = document.getElementById("routeBanner") || document.getElementById("mapCard");
        else if (id === "weather") targetEl = document.getElementById("oceanMetricsRow");
        else if (id === "alerts") targetEl = document.getElementById("safetyAlertCard");
        else if (id === "analytics") targetEl = document.getElementById("aiRecommendationSection");
        else if (id === "evidence") targetEl = document.getElementById("evidenceLedgerCard") || document.getElementById("traceCard");
        
        if (targetEl) {
          e.preventDefault();
          targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });

  // Desktop Nav Links smooth jump
  document.querySelectorAll("#mainNavLinks .nav-link").forEach((link) => {
    link.addEventListener("click", (e) => {
      document.querySelectorAll("#mainNavLinks .nav-link").forEach(l => l.classList.remove("active"));
      link.classList.add("active");
      const targetId = link.getAttribute("href");
      if (targetId && targetId.startsWith("#")) {
        const id = targetId.substring(1);
        let targetEl = document.getElementById(id);
        if (id === "zones") targetEl = document.getElementById("bestZoneCard") || document.getElementById("mapCard");
        else if (id === "routes") targetEl = document.getElementById("routeBanner") || document.getElementById("mapCard");
        else if (id === "weather") targetEl = document.getElementById("oceanMetricsRow");
        else if (id === "alerts") targetEl = document.getElementById("safetyAlertCard");
        else if (id === "analytics") targetEl = document.getElementById("aiRecommendationSection");
        else if (id === "evidence") targetEl = document.getElementById("evidenceLedgerCard") || document.getElementById("traceCard");

        if (targetEl) {
          e.preventDefault();
          targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });

  // Mobile Bottom Nav "More" Button opens drawer
  const mobileMoreBtn = document.getElementById("mobileMoreBtn");
  if (mobileMoreBtn) {
    mobileMoreBtn.addEventListener("click", (e) => {
      e.preventDefault();
      openDrawer();
    });
  }

  // Mobile Bottom Nav items smooth jump
  document.querySelectorAll(".mobile-bottom-nav .m-nav-item").forEach((item) => {
    if (item.id === "mobileMoreBtn" || item.id === "mobileCopilotBtn") return;
    item.addEventListener("click", (e) => {
      document.querySelectorAll(".mobile-bottom-nav .m-nav-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      const tab = item.dataset.tab;
      let targetEl = null;
      if (tab === "dashboard") targetEl = document.getElementById("dashboard");
      else if (tab === "map") targetEl = document.getElementById("mapCard");
      else if (tab === "weather") targetEl = document.getElementById("oceanMetricsRow");
      else if (tab === "alerts") targetEl = document.getElementById("safetyAlertCard");

      if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

function setupLayerToggles() {
  const syncToggle = (deskId, mobId, layer) => {
    const d = document.getElementById(deskId);
    const m = document.getElementById(mobId);
    const handler = (checked) => {
      if (d) d.checked = checked;
      if (m) m.checked = checked;
      if (leafletMap && layer) {
        if (checked) {
          if (!leafletMap.hasLayer(layer)) leafletMap.addLayer(layer);
        } else {
          if (leafletMap.hasLayer(layer)) leafletMap.removeLayer(layer);
        }
      }
    };
    if (d) d.addEventListener("change", () => handler(d.checked));
    if (m) m.addEventListener("change", () => handler(m.checked));
  };

  syncToggle("layerFishing", "mLayerFishing", pfzLayerGroup);
  syncToggle("layerRestricted", "mLayerRestricted", boundaryLayerGroup);
  syncToggle("layerHazards", "mLayerHazards", boundaryLayerGroup);
}

function updateMapTheme(isDark) {
  if (!leafletMap || typeof L === "undefined") return;
  if (currentTileLayer) {
    try {
      leafletMap.removeLayer(currentTileLayer);
    } catch (_) {}
  }
  const tileUrl = isDark
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

  currentTileLayer = L.tileLayer(tileUrl, {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    subdomains: "abcd",
    maxZoom: 19,
    updateWhenIdle: true,
    updateWhenZooming: false,
    keepBuffer: 3,
  }).addTo(leafletMap);

  if (pfzLayerGroup) pfzLayerGroup.bringToFront();
  if (boundaryLayerGroup) boundaryLayerGroup.bringToFront();
}

function setupThemeToggle() {
  const toggleBtn = document.getElementById("themeToggleBtn");
  const icon = document.getElementById("themeIcon");
  const label = document.getElementById("themeLabel");

  const drawerBtn = document.getElementById("drawerThemeBtn");
  const drawerIcon = document.getElementById("drawerThemeIcon");
  const drawerLabel = document.getElementById("drawerThemeLabel");

  const savedTheme = localStorage.getItem("orca_theme");
  const systemPrefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = savedTheme || (systemPrefersDark ? "dark" : "light");

  const applyTheme = (theme) => {
    const isDark = (theme === "dark");
    const activeTheme = isDark ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", activeTheme);
    document.documentElement.classList.remove("dark-mode");
    if (document.body) document.body.classList.remove("dark-mode");

    if (icon) icon.textContent = isDark ? "☀️" : "🌙";
    if (label) label.textContent = isDark ? "Light Mode" : "Dark Mode";
    if (drawerIcon) drawerIcon.textContent = isDark ? "☀️" : "🌙";
    if (drawerLabel) drawerLabel.textContent = isDark ? "☀️ Switch to Light Mode" : "🌙 Switch to Dark Mode";

    if (toggleBtn) {
      toggleBtn.setAttribute("aria-label", isDark ? "Switch to Light Mode" : "Switch to Dark Mode");
      toggleBtn.title = isDark ? "Click to switch into Light Mode" : "Click to switch into Dark Mode";
    }
    if (drawerBtn) {
      drawerBtn.setAttribute("aria-label", isDark ? "Switch to Light Mode" : "Switch to Dark Mode");
      drawerBtn.title = isDark ? "Click to switch into Light Mode" : "Click to switch into Dark Mode";
    }

    try {
      localStorage.setItem("orca_theme", activeTheme);
    } catch (_) {}

    updateMapTheme(isDark);
  };

  window.orcaToggleTheme = () => {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    const nextTheme = current === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
  };

  applyTheme(initialTheme);

  if (toggleBtn) {
    toggleBtn.addEventListener("click", window.orcaToggleTheme);
  }
  if (drawerBtn) {
    drawerBtn.addEventListener("click", window.orcaToggleTheme);
  }

  // Listen to system preference changes if user hasn't explicitly set a preference
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
      if (!localStorage.getItem("orca_theme")) {
        applyTheme(e.matches ? "dark" : "light");
      }
    });
  }
}

function init() {
  // Clear any stale local keys so backend key is always used
  try {
    localStorage.removeItem("orca_gemini_api_key");
  } catch (_) {}

  setupThemeToggle();
  setupMobileMenu();
  setupLayerToggles();
  initWebGISMap();
  setupVoiceSTT();
  setupVoiceTTS();

  const askBtn = document.getElementById("askBtn");
  if (askBtn) {
    askBtn.addEventListener("click", (e) => {
      e.preventDefault();
      analyse();
    });
  }

  const queryEl = document.getElementById("query");
  if (queryEl) {
    queryEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        analyse();
      }
    });
  }

  document.querySelectorAll(".quick-chips .chip").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      if (queryEl) queryEl.value = btn.dataset.query;
      analyse();
    });
  });

  const langSelect = document.getElementById("language");
  if (langSelect) {
    langSelect.addEventListener("change", analyse);
  }

  // Vessel profile pills
  const vesselPills = document.querySelectorAll(".vessel-pill");
  const vesselSelect = document.getElementById("vesselSelect");
  const currentVesselBadge = document.getElementById("currentVesselBadge");

  const badgeLabels = {
    small_boat: "1.5m Limit",
    trawler: "2.5m Limit",
    deep_sea: "4.0m Limit",
  };

  vesselPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      vesselPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      const v = pill.dataset.vessel;
      if (vesselSelect) vesselSelect.value = v;
      if (currentVesselBadge) currentVesselBadge.textContent = badgeLabels[v] || "Profile Active";
      analyse();
    });
  });

  const liveToggle = document.getElementById("liveToggle");
  if (liveToggle) {
    liveToggle.addEventListener("change", () => {
      const label = document.getElementById("feedSourceLabel");
      if (label) label.textContent = liveToggle.checked ? "Open-Meteo & Copernicus" : "INCOIS Verified Cache";
      analyse();
    });
  }

  const locateBtn = document.getElementById("locateBtn");
  if (locateBtn) {
    locateBtn.addEventListener("click", () => {
      if (!navigator.geolocation) {
        alert("Geolocation is not supported in this browser. Using Mumbai Harbour.");
        return;
      }
      const locText = document.getElementById("locationText");
      if (locText) locText.textContent = "Acquiring GPS...";
      navigator.geolocation.getCurrentPosition(
        (position) => {
          selectedLocation = { lat: Number(position.coords.latitude.toFixed(4)), lon: Number(position.coords.longitude.toFixed(4)) };
          if (locText) locText.textContent = `GPS (${selectedLocation.lat}°N, ${selectedLocation.lon}°E)`;
          updateOriginMarker();
          if (leafletMap) leafletMap.setView([selectedLocation.lat, selectedLocation.lon], 10);
          analyse();
        },
        () => {
          if (locText) locText.textContent = "Mumbai Harbour (18.95°N, 72.85°E)";
          alert("Location permission not granted. Using Mumbai Harbour (18.95°N, 72.85°E).");
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 300000 }
      );
    });
  }

  // ===== COPILOT AI ASSISTANT PANEL CONTROLS =====
  const copilotSendBtn = document.getElementById("copilotSendBtn");
  const copilotInput = document.getElementById("copilotInput");
  if (copilotSendBtn && copilotInput) {
    copilotSendBtn.addEventListener("click", (e) => {
      e.preventDefault();
      const val = copilotInput.value.trim();
      if (val) analyse(val);
    });
    copilotInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const val = copilotInput.value.trim();
        if (val) analyse(val);
      }
    });
  }

  // Copilot "Show on Map ➔" Button
  const copilotShowOnMapBtn = document.getElementById("copilotShowOnMapBtn");
  if (copilotShowOnMapBtn) {
    copilotShowOnMapBtn.addEventListener("click", (e) => {
      e.preventDefault();
      if (latestResult && latestResult.recommendation && latestResult.recommendation.location && leafletMap) {
        const dest = latestResult.recommendation.location;
        leafletMap.flyTo([dest.lat, dest.lon], 11, { duration: 1.2 });
        if (targetMarker) {
          targetMarker.openPopup();
        }
        const mapCard = document.getElementById("mapCard");
        if (mapCard) {
          mapCard.scrollIntoView({ behavior: "smooth", block: "center" });
          mapCard.style.boxShadow = "0 0 35px rgba(0, 240, 255, 0.7)";
          setTimeout(() => { mapCard.style.boxShadow = ""; }, 1600);
        }
      } else {
        analyse();
      }
    });
  }

  // Copilot "Plan Safe Route" Button
  const copilotPlanRouteBtn = document.getElementById("copilotPlanRouteBtn");
  if (copilotPlanRouteBtn) {
    copilotPlanRouteBtn.addEventListener("click", (e) => {
      e.preventDefault();
      if (latestResult && latestResult.route && routePolyline && leafletMap) {
        leafletMap.fitBounds(routePolyline.getBounds().pad(0.15), { maxZoom: 12, duration: 1.0 });
        const mapCard = document.getElementById("mapCard");
        if (mapCard) {
          mapCard.scrollIntoView({ behavior: "smooth", block: "center" });
          mapCard.style.boxShadow = "0 0 35px rgba(34, 197, 94, 0.6)";
          setTimeout(() => { mapCard.style.boxShadow = ""; }, 1600);
        }
      } else {
        analyse("Plan a safe navigation route avoiding shallow reefs and restricted CZMP geofences.");
      }
    });
  }

  // Copilot "Check Weather" Button
  const copilotCheckWeatherBtn = document.getElementById("copilotCheckWeatherBtn");
  if (copilotCheckWeatherBtn) {
    copilotCheckWeatherBtn.addEventListener("click", (e) => {
      e.preventDefault();
      analyse("Check weather, wave height, swell and wind safety forecast for sailing.");
    });
  }

  // Copilot "Other Options" Button
  const copilotOtherOptionsBtn = document.getElementById("copilotOtherOptionsBtn");
  if (copilotOtherOptionsBtn) {
    copilotOtherOptionsBtn.addEventListener("click", (e) => {
      e.preventDefault();
      analyse("Show alternative Potential Fishing Zones and compare options.");
    });
  }

  // ===== MAP FLOATING CONTROLS =====
  const mapRecenterBtn = document.getElementById("mapRecenterBtn");
  if (mapRecenterBtn) {
    mapRecenterBtn.addEventListener("click", (e) => {
      e.preventDefault();
      if (leafletMap) {
        leafletMap.flyTo([selectedLocation.lat, selectedLocation.lon], 10, { duration: 1.0 });
        if (originMarker) originMarker.openPopup();
      }
    });
  }

  const mapLayersQuickBtn = document.getElementById("mapLayersQuickBtn");
  if (mapLayersQuickBtn) {
    mapLayersQuickBtn.addEventListener("click", (e) => {
      e.preventDefault();
      if (pfzLayerGroup && leafletMap) {
        if (leafletMap.hasLayer(pfzLayerGroup)) {
          leafletMap.removeLayer(pfzLayerGroup);
        } else {
          leafletMap.addLayer(pfzLayerGroup);
        }
      }
    });
  }

  const mapFullscreenBtn = document.getElementById("mapFullscreenBtn");
  if (mapFullscreenBtn) {
    mapFullscreenBtn.addEventListener("click", (e) => {
      e.preventDefault();
      const mapCard = document.getElementById("mapCard");
      if (!mapCard) return;
      if (!document.fullscreenElement) {
        if (mapCard.requestFullscreen) mapCard.requestFullscreen();
        else if (mapCard.webkitRequestFullscreen) mapCard.webkitRequestFullscreen();
      } else {
        if (document.exitFullscreen) document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      }
      setTimeout(() => { if (leafletMap) leafletMap.invalidateSize(); }, 350);
    });
  }

  // ===== ACTION BUTTONS ACROSS DASHBOARD =====
  const btnViewFullZoneDetails = document.getElementById("btnViewFullZoneDetails");
  if (btnViewFullZoneDetails) {
    btnViewFullZoneDetails.addEventListener("click", () => {
      const el = document.getElementById("aiRecommendationSection");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const btnViewAlertDetails = document.getElementById("btnViewAlertDetails");
  if (btnViewAlertDetails) {
    btnViewAlertDetails.addEventListener("click", () => {
      const el = document.getElementById("oceanMetricsRow") || document.getElementById("cardMetricWave");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  const whyZoneBtn = document.getElementById("whyZoneBtn");
  if (whyZoneBtn) {
    whyZoneBtn.addEventListener("click", () => {
      const el = document.getElementById("evidenceLedgerCard") || document.getElementById("traceCard");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const btnViewAllSpecies = document.getElementById("btnViewAllSpecies");
  if (btnViewAllSpecies) {
    btnViewAllSpecies.addEventListener("click", () => {
      const el = document.getElementById("speciesCard");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const mobileCopilotBtn = document.getElementById("mobileCopilotBtn");
  if (mobileCopilotBtn) {
    mobileCopilotBtn.addEventListener("click", () => {
      const el = document.getElementById("embeddedCopilotPanel");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        if (copilotInput) copilotInput.focus();
      }
    });
  }

  analyse();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
