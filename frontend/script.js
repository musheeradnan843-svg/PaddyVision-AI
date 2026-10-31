import * as THREE from "three";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js";

const container = document.getElementById("digital-twin-container");
const plants = [];

if (!container) {
    throw new Error("Digital Twin container nahi mila. index.html check karo.");
}

// Scene
const scene = new THREE.Scene();
const fieldRoot = new THREE.Group();
fieldRoot.rotation.y = -2.55; // Approximate major-axis orientation until the AOI geometry is returned.
scene.add(fieldRoot);
scene.background = new THREE.Color(0x718276);
scene.fog = new THREE.Fog(0x718276, 48, 112);

// Camera
const camera = new THREE.PerspectiveCamera(
    43,
    container.clientWidth / container.clientHeight,
    0.1,
    200
);
camera.position.set(-20, 36, -27);

// Renderer
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.2));
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.domElement.style.display = "block";
renderer.domElement.style.width = "100%";
renderer.domElement.style.height = "100%";
container.replaceChildren(renderer.domElement);

// Camera controls
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0.4, 0);
controls.minDistance = 12;
controls.maxDistance = 55;
controls.maxPolarAngle = Math.PI * 0.48;

// Lighting
scene.add(new THREE.HemisphereLight(0xe6eee2, 0x25372b, 1.65));

const sun = new THREE.DirectionalLight(0xffedcf, 3.1);
sun.position.set(-18, 30, 12);
sun.castShadow = true;
sun.shadow.mapSize.set(1536, 1536);
sun.shadow.camera.left = -35;
sun.shadow.camera.right = 35;
sun.shadow.camera.top = 35;
sun.shadow.camera.bottom = -35;
sun.shadow.bias = -0.00015;
sun.shadow.normalBias = 0.025;
scene.add(sun);

// Procedural earth-and-grass texture for the surrounding ground
function createGroundTexture() {
    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");

    context.fillStyle = "#39473a";
    context.fillRect(0, 0, size, size);

    const earthColors = ["#625c46", "#71684f", "#3e5140", "#59624a", "#4c5942"];

    for (let i = 0; i < 2400; i++) {
        const x = Math.random() * size;
        const y = Math.random() * size;
        const radius = 1 + Math.random() * 4;

        context.globalAlpha = 0.12 + Math.random() * 0.2;
        context.fillStyle = earthColors[
            Math.floor(Math.random() * earthColors.length)
        ];
        context.beginPath();
        context.ellipse(
            x,
            y,
            radius * 1.8,
            radius,
            Math.random() * Math.PI,
            0,
            Math.PI * 2
        );
        context.fill();
    }

    context.globalAlpha = 1;

    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(35, 35);
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);

    return texture;
}

// Surrounding ground
const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(500, 500),
    new THREE.MeshStandardMaterial({
        color: 0x737c69,
        map: createGroundTexture(),
        roughness: 1
    })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.24;
ground.receiveShadow = true;
scene.add(ground);

// Paddy field dimensions
const FIELD_WIDTH = 50;
const FIELD_DEPTH = 13.2;

function createSoilTexture() {
    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    context.fillStyle = "#554632";
    context.fillRect(0, 0, size, size);

    const soilColors = ["#3d382b", "#776044", "#514330", "#88704d", "#68583e"];
    for (let i = 0; i < 4200; i++) {
        const x = Math.random() * size;
        const y = Math.random() * size;
        const radius = 0.5 + Math.random() * 3.2;
        context.globalAlpha = 0.15 + Math.random() * 0.28;
        context.fillStyle = soilColors[Math.floor(Math.random() * soilColors.length)];
        context.beginPath();
        context.ellipse(x, y, radius * 2, radius, Math.random() * Math.PI, 0, Math.PI * 2);
        context.fill();
    }

    context.globalAlpha = 1;
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(3, 1.4);
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
    return texture;
}

const soilTexture = createSoilTexture();

// Actual Sekinchan satellite observations are rendered as a bounded surface
// overlay. Crop meshes and the hand-placed health zones remain illustrative.
let satelliteLayerMesh = null;
let currentSatelliteLayer = null;
let soilLayerMesh = null;
let currentSoilLayer = null;
let missionOverlay = null;
let missionRouteLocal = [];
let missionSegmentLengths = [];
let missionRouteTotal = 0;
let missionAnimationStartedAt = 0;
let missionAnimationPlaying = false;
const satellite3dToggle = document.getElementById("satellite-3d-toggle");
const satellite3dStatus = document.getElementById("satellite-3d-status");
const soil3dToggle = document.getElementById("soil-3d-toggle");
const soil3dStatus = document.getElementById("soil-3d-status");
const twinLayerPill = document.getElementById("twin-layer-pill");
const cellInspector = document.getElementById("twin-cell-inspector");
const cellInspectorStatus = document.getElementById("twin-cell-inspector-status");
const cellInspectorGrid = document.getElementById("twin-cell-inspector-grid");
const cellInspectorClear = document.getElementById("twin-cell-inspector-clear");
let inspectorPinned = false;
const inspectorMarker = new THREE.Group();
inspectorMarker.visible = false;
const inspectorRing = new THREE.Mesh(
    new THREE.RingGeometry(0.22, 0.32, 36),
    new THREE.MeshBasicMaterial({ color: 0xffe17a, side: THREE.DoubleSide, transparent: true, opacity: 0.98, depthTest: false })
);
inspectorRing.rotation.x = -Math.PI / 2;
inspectorRing.renderOrder = 30;
inspectorMarker.add(inspectorRing);
const inspectorCenter = new THREE.Mesh(
    new THREE.CircleGeometry(0.095, 24),
    new THREE.MeshBasicMaterial({ color: 0xfff5c2, side: THREE.DoubleSide, depthTest: false })
);
inspectorCenter.rotation.x = -Math.PI / 2;
inspectorCenter.renderOrder = 31;
inspectorMarker.add(inspectorCenter);
fieldRoot.add(inspectorMarker);

function setTwinLayerPill(text) {
    if (twinLayerPill) twinLayerPill.textContent = text;
}

function clearCellInspector(message = "Hover over or click a coloured satellite/soil cell to inspect it. Coordinates come from the nearest source cell.") {
    inspectorPinned = false;
    if (cellInspectorGrid) cellInspectorGrid.hidden = true;
    if (cellInspectorStatus) cellInspectorStatus.textContent = message;
    if (inspectorMarker) inspectorMarker.visible = false;
}

cellInspectorClear?.addEventListener("click", () => clearCellInspector());

const twinLayerLegend = document.getElementById("twin-layer-legend");
const twinOverlayOpacity = document.getElementById("twin-overlay-opacity");
const twinOverlayOpacityValue = document.getElementById("twin-overlay-opacity-value");
const SATELLITE_COLOR_SCALES = {
    NDVI: { min: -0.2, max: 0.9, unit: "unitless", colors: [[117, 70, 56], [198, 139, 76], [226, 208, 107], [141, 208, 104], [24, 119, 68]] },
    NDMI: { min: -1, max: 1, unit: "unitless", colors: [[157, 85, 71], [225, 199, 116], [103, 167, 196], [53, 111, 161]] },
    NDWI: { min: -1, max: 1, unit: "unitless", colors: [[157, 85, 71], [225, 199, 116], [103, 167, 196], [53, 111, 161]] },
    S1_VV: { min: -30, max: 0, unit: "dB", colors: [[57, 45, 105], [65, 125, 165], [120, 200, 181], [230, 216, 118]] },
    S1_VH: { min: -35, max: -5, unit: "dB", colors: [[57, 45, 105], [65, 125, 165], [120, 200, 181], [230, 216, 118]] },
    elevation_m: { min: 1.5, max: 4, unit: "m", colors: [[49, 95, 114], [113, 167, 128], [215, 199, 122], [154, 107, 67]] },
    gsw_occurrence: { min: 0, max: 5, unit: "source value", colors: [[240, 230, 178], [148, 201, 194], [67, 140, 163], [35, 74, 117]] },
    gsw_seasonality: { min: 0, max: 3, unit: "source value", colors: [[240, 230, 178], [148, 201, 194], [67, 140, 163], [35, 74, 117]] }
};
const SOIL_COLOR_SCALE = [[64, 93, 122], [199, 181, 121], [112, 151, 91]];

function setTwinLayerLegend(title, kind, min, max, unit, colors, detail) {
    if (!twinLayerLegend) return;
    const active = Boolean(title);
    twinLayerLegend.hidden = !active;
    if (!active) return;
    document.getElementById("twin-legend-title").textContent = title;
    document.getElementById("twin-legend-kind").textContent = kind;
    document.getElementById("twin-legend-gradient").style.background = "linear-gradient(90deg, " + colors.map(color => "rgb(" + color.join(",") + ")").join(", ") + ")";
    document.getElementById("twin-legend-min").textContent = Number(min).toFixed(2) + " " + unit;
    document.getElementById("twin-legend-max").textContent = Number(max).toFixed(2) + " " + unit;
    document.getElementById("twin-legend-detail").textContent = detail;
}

function renderTwinSatelliteLegend(data) {
    if (!data || !satellite3dToggle?.checked) return;
    const scale = SATELLITE_COLOR_SCALES[data.metric] || SATELLITE_COLOR_SCALES.NDVI;
    const observedMin = data.summary?.min ?? scale.min;
    const observedMax = data.summary?.max ?? scale.max;
    const count = data.points?.length ?? 0;
    const isStatic = data.layer_kind === "satellite_static";
    const unit = data.unit || scale.unit;
    const displayMin = isStatic ? observedMin : scale.min;
    const displayMax = isStatic ? observedMax : scale.max;
    const period = isStatic ? "Static layer" : data.window_start + " to " + data.window_end;
    const detail = isStatic
        ? data.scale_note + " " + count + " AOI grid locations; displayed range " + Number(observedMin).toFixed(3) + " to " + Number(observedMax).toFixed(3) + "."
        : "Observed " + Number(observedMin).toFixed(3) + " to " + Number(observedMax).toFixed(3) + "; " + count + " valid cells, " + period + ". Colors use the fixed display scale.";
    setTwinLayerLegend((data.label || data.metric) + " satellite layer", isStatic ? "STATIC SATELLITE · " + unit : "SATELLITE · " + unit, displayMin, displayMax, unit, scale.colors, detail);
}

function renderTwinSoilLegend(data) {
    if (!data || !soil3dToggle?.checked) return;
    const property = data.property.replaceAll("_", " ");
    const min = Number(data.min ?? 0);
    const max = Number(data.max ?? 1);
    setTwinLayerLegend(property + " · " + data.depth_cm + " cm", "SOIL REFERENCE · " + data.unit, min, max, data.unit, SOIL_COLOR_SCALE,
        Number(data.pixel_count ?? 0) + " coarse cells · approx. " + data.resolution_m_approx + " m · " + data.source + ". Reference estimate, not a local soil test.");
}

function applyTwinOverlayOpacity(value) {
    const opacity = Number(value) / 100;
    if (satelliteLayerMesh) satelliteLayerMesh.material.opacity = opacity;
    if (soilLayerMesh) soilLayerMesh.material.opacity = opacity;
    if (twinOverlayOpacityValue) twinOverlayOpacityValue.textContent = Math.round(Number(value)) + "%";
}

twinOverlayOpacity?.addEventListener("input", () => applyTwinOverlayOpacity(twinOverlayOpacity.value));
applyTwinOverlayOpacity(twinOverlayOpacity?.value ?? 82);

function satelliteRamp(value, metric, data) {
    const scale = SATELLITE_COLOR_SCALES[metric] || SATELLITE_COLOR_SCALES.NDVI;
    const min = data?.layer_kind === "satellite_static" ? (data.summary?.min ?? scale.min) : scale.min;
    const max = data?.layer_kind === "satellite_static" ? (data.summary?.max ?? scale.max) : scale.max;
    const t = THREE.MathUtils.clamp((value - min) / (max - min || 1), 0, 1);
    const position = t * (scale.colors.length - 1);
    const index = Math.min(scale.colors.length - 2, Math.floor(position));
    const mix = position - index;
    return scale.colors[index].map((channel, i) => Math.round(channel + (scale.colors[index + 1][i] - channel) * mix));
}

function soilRamp(value, data) {
    const min = Number(data.min);
    const max = Number(data.max);
    const t = THREE.MathUtils.clamp((value - min) / (max - min || 1), 0, 1);
    const colors = SOIL_COLOR_SCALE;
    const position = t * (colors.length - 1);
    const index = Math.min(colors.length - 2, Math.floor(position));
    const mix = position - index;
    return colors[index].map((channel, i) => Math.round(channel + (colors[index + 1][i] - channel) * mix));
}

function makeSatelliteTexture(data) {
    const size = 1024;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    const ring = data?.boundary?.coordinates?.[0];
    if (!ctx || !ring?.length || ring.length < 4) return null;

    const vertices = ring.slice(0, -1);
    const meanLat = vertices.reduce((sum, point) => sum + point[1], 0) / vertices.length;
    const centerLon = vertices.reduce((sum, point) => sum + point[0], 0) / vertices.length;
    const centerLat = meanLat;
    const project = ([lon, lat]) => [
        (lon - centerLon) * 111320 * Math.cos(meanLat * Math.PI / 180),
        (lat - centerLat) * 110574
    ];
    const projected = vertices.map(project);
    let major = null;
    for (let i = 0; i < projected.length; i++) {
        const a = projected[i];
        const b = projected[(i + 1) % projected.length];
        const dx = b[0] - a[0], dy = b[1] - a[1];
        const length = Math.hypot(dx, dy);
        if (!major || length > major.length) major = { dx, dy, length };
    }
    if (!major?.length) return null;
    const ux = major.dx / major.length;
    const uy = major.dy / major.length;
    const angle = Math.atan2(uy, ux);
    const local = ([lon, lat]) => {
        const [east, north] = project([lon, lat]);
        return [east * ux + north * uy, -east * uy + north * ux];
    };
    const boundaryLocal = ring.map(local);
    const minX = Math.min(...boundaryLocal.map(point => point[0]));
    const maxX = Math.max(...boundaryLocal.map(point => point[0]));
    const minY = Math.min(...boundaryLocal.map(point => point[1]));
    const maxY = Math.max(...boundaryLocal.map(point => point[1]));
    const spanX = maxX - minX, spanY = maxY - minY;
    if (!(spanX > 0 && spanY > 0)) return null;
    const padding = 8;
    const px = point => {
        const [x, y] = local(point);
        return [padding + (x - minX) / spanX * (size - 2 * padding),
            size - padding - (y - minY) / spanY * (size - 2 * padding)];
    };
    const projection = {
        lonLatToLocal: point => local(point),
        spanX,
        spanY,
        localToPlane: point => {
            const u = (padding + (point[0] - minX) / spanX * (size - 2 * padding)) / size;
            const v = (padding + (point[1] - minY) / spanY * (size - 2 * padding)) / size;
            return [
                (u - 0.5) * (FIELD_WIDTH - 0.12),
                (0.5 - v) * (FIELD_DEPTH - 0.12)
            ];
        },
        uvToLocal: uv => {
            // CanvasTexture flips the canvas vertically for WebGL. Reverse the same
            // padding/normalization used by px() to recover the map-local metres.
            const canvasX = uv.x * size;
            const canvasY = (1 - uv.y) * size;
            return [
                minX + ((canvasX - padding) / (size - 2 * padding)) * spanX,
                minY + ((size - padding - canvasY) / (size - 2 * padding)) * spanY
            ];
        },
        cellSizeMeters: data.cell_size_m ?? { width: 9.7, height: 9.7 }
    };

    ctx.clearRect(0, 0, size, size);
    ctx.beginPath();
    ring.forEach((point, index) => {
        const [x, y] = px(point);
        if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.save();
    ctx.clip();
    ctx.fillStyle = "#173b2a";
    ctx.fillRect(0, 0, size, size);
    const cellWidth = Math.max(1, (data.cell_size_m?.width ?? 9.7) / spanX * (size - 2 * padding));
    const cellHeight = Math.max(1, (data.cell_size_m?.height ?? 9.7) / spanY * (size - 2 * padding));
    for (const point of data.points ?? []) {
        const [x, y] = px([point.longitude, point.latitude]);
        const [r, g, b] = data.layer_kind === "soil_reference"
            ? soilRamp(point.value, data)
            : satelliteRamp(point.value, data.metric, data);
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x - cellWidth / 2, y - cellHeight / 2, cellWidth + 0.5, cellHeight + 0.5);
    }
    ctx.restore();
    ctx.beginPath();
    ring.forEach((point, index) => {
        const [x, y] = px(point);
        if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = "#fff3b0";
    ctx.lineWidth = 3;
    ctx.stroke();
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
    return { texture, angle, projection };
}

function prepareInspectorPoints(data, projection) {
    return (data?.points ?? []).map(point => ({
        point,
        local: projection.lonLatToLocal([point.longitude, point.latitude])
    }));
}

function activeInspectorTarget() {
    if (soil3dToggle?.checked && soilLayerMesh?.visible && currentSoilLayer) {
        return { mesh: soilLayerMesh, data: currentSoilLayer, kind: "soil_reference" };
    }
    if (satellite3dToggle?.checked && satelliteLayerMesh?.visible && currentSatelliteLayer) {
        return { mesh: satelliteLayerMesh, data: currentSatelliteLayer, kind: currentSatelliteLayer.layer_kind || "satellite" };
    }
    return null;
}

function flagDescription(value, flag) {
    if (value == null) return `${flag}: missing / not applicable`;
    return `${flag}: ${Number(value) === 0 ? "0 (clear in source flag)" : Number(value) === 1 ? "1 (flagged in source)" : value}`;
}

function inspectCell(event, pinned = false) {
    if (pinned) inspectorPinned = false;
    const target = activeInspectorTarget();
    if (!target) {
        inspectorPinned = false;
        if (cellInspectorGrid) cellInspectorGrid.hidden = true;
        if (cellInspectorStatus) cellInspectorStatus.textContent = "Turn on the satellite history or soil reference overlay to inspect its cells.";
        inspectorMarker.visible = false;
        return false;
    }
    const bounds = renderer.domElement.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return false;
    const pointer = new THREE.Vector2(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1
    );
    const raycaster = inspectCell.raycaster || (inspectCell.raycaster = new THREE.Raycaster());
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObject(target.mesh, false)[0];
    if (!hit?.uv) {
        if (cellInspectorGrid) cellInspectorGrid.hidden = true;
        if (cellInspectorStatus) cellInspectorStatus.textContent = "No mapped surface under the pointer.";
        inspectorMarker.visible = false;
        return false;
    }
    const clickedLocal = target.mesh.userData.projection.uvToLocal(hit.uv);
    const indexedPoints = target.mesh.userData.inspectorPoints || [];
    let nearest = null;
    for (const candidate of indexedPoints) {
        const distance = Math.hypot(candidate.local[0] - clickedLocal[0], candidate.local[1] - clickedLocal[1]);
        if (!nearest || distance < nearest.distance) nearest = { ...candidate, distance };
    }
    const cellSize = target.mesh.userData.projection.cellSizeMeters;
    const maxDistance = Math.hypot(cellSize.width, cellSize.height) * 0.55;
    if (!nearest || nearest.distance > maxDistance) {
        if (cellInspectorGrid) cellInspectorGrid.hidden = true;
        if (cellInspectorStatus) cellInspectorStatus.textContent = "No valid source cell within this pixel footprint; this location may be nodata or outside mapped coverage.";
        inspectorMarker.visible = false;
        return false;
    }

    const point = nearest.point;
    const data = target.data;
    const soilReference = target.kind === "soil_reference";
    const isStatic = data.layer_kind === "satellite_static";
    const metric = soilReference ? `${data.property} · ${data.depth_cm} cm` : (data.metric || data.label || "Satellite layer");
    const numericValue = Number(point.value);
    const valueText = `${metric} · ${Number.isFinite(numericValue) ? numericValue.toFixed(4) : "unavailable"} ${data.unit || ""}`.trim();
    let sourceText;
    let fillText;
    let qualityText;
    if (soilReference) {
        sourceText = `${data.source} · approx. ${data.resolution_m_approx} m source cell`;
        fillText = "Not applicable · soil reference raster";
        qualityText = `${data.confidence || "Confidence not specified"} · coarse reference cell; not a local lab result`;
    } else if (isStatic) {
        sourceText = `${data.source} · static layer; period not documented`;
        fillText = "Not applicable · static layer";
        qualityText = data.scale_note || "Static source values; consult the source scale note.";
    } else {
        const dateRange = `${data.window_start} to ${data.window_end}`;
        if (String(data.metric).startsWith("S1_")) {
            sourceText = `Sentinel-1 observation · ${dateRange} · radar gaps are not filled`;
            fillText = "Not applicable · Sentinel-1 is not monthly-filled";
        } else {
            const source = point.s2_source;
            const sourceLabel = source === "v3_10day"
                ? "v3_10day · direct 10-day Sentinel-2"
                : source === "v2_monthly_fill"
                    ? "v2_monthly_fill · same-month value reused in a ten-day slot"
                    : "Sentinel-2 source unavailable";
            sourceText = `${sourceLabel} · ${dateRange}`;
            fillText = source === "v2_monthly_fill"
                ? `Monthly-fill confidence: ${point.s2_fill_confidence || "not specified"}`
                : "No monthly fill for this selected cell";
        }
        qualityText = `${flagDescription(point.bright_flag, "bright_flag")} · ${flagDescription(point.s1_outlier_flag, "s1_outlier_flag")}`;
        if (data.summary?.window_summary?.usable_s2_or_s1 === false) {
            qualityText += " · source window summary marks this slot unusable; inspect the availability warning";
        }
    }

    const setValue = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    };
    setValue("twin-cell-coordinates", `${Number(point.latitude).toFixed(6)}, ${Number(point.longitude).toFixed(6)} · EPSG:4326`);
    setValue("twin-cell-value", valueText);
    setValue("twin-cell-source", sourceText);
    setValue("twin-cell-fill-confidence", fillText);
    setValue("twin-cell-quality", qualityText);
    setValue("twin-cell-evidence", data.evidence_class || "Evidence class unavailable");
    if (cellInspectorGrid) cellInspectorGrid.hidden = false;
    if (cellInspectorStatus) {
        cellInspectorStatus.textContent = `Nearest source-cell centre · ${nearest.distance.toFixed(1)} m from the picked surface point${pinned ? " · pinned by click" : " · preview"}.`;
    }

    const projection = target.mesh.userData.projection;
    const markerPlanePosition = projection.localToPlane(nearest.local);
    inspectorMarker.position.set(markerPlanePosition[0], target.mesh.position.y + 0.045, markerPlanePosition[1]);
    const paddedWidth = FIELD_WIDTH - 0.12;
    const paddedDepth = FIELD_DEPTH - 0.12;
    const mapFraction = (1024 - 16) / 1024;
    const worldCellWidth = (cellSize.width / projection.spanX) * paddedWidth * mapFraction;
    const worldCellDepth = (cellSize.height / projection.spanY) * paddedDepth * mapFraction;
    const markerRadius = Math.max(0.22, Math.min(0.9, Math.min(worldCellWidth, worldCellDepth) * 0.42));
    inspectorMarker.scale.setScalar(markerRadius / 0.32);
    inspectorMarker.visible = true;
    inspectorPinned = pinned;
    return true;
}

let inspectorPointerDown = null;
renderer.domElement.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    inspectorPointerDown = { id: event.pointerId, x: event.clientX, y: event.clientY, dragged: false };
});
renderer.domElement.addEventListener("pointermove", event => {
    if (inspectorPointerDown?.id === event.pointerId) {
        const deltaX = event.clientX - inspectorPointerDown.x;
        const deltaY = event.clientY - inspectorPointerDown.y;
        if (Math.hypot(deltaX, deltaY) > 5) inspectorPointerDown.dragged = true;
        return;
    }
    if (event.pointerType === "mouse" && !inspectorPinned) inspectCell(event, false);
});
renderer.domElement.addEventListener("pointerup", event => {
    if (!inspectorPointerDown || inspectorPointerDown.id !== event.pointerId) return;
    const isClick = !inspectorPointerDown.dragged;
    inspectorPointerDown = null;
    if (isClick) inspectCell(event, true);
});
renderer.domElement.addEventListener("pointercancel", () => { inspectorPointerDown = null; });
renderer.domElement.addEventListener("pointerleave", () => {
    if (!inspectorPinned) clearCellInspector("Hover over or click a coloured satellite/soil cell to inspect it.");
});

function updateSatelliteLayer(data) {
    clearCellInspector("Satellite overlay updated. Hover over or click a coloured satellite/soil cell to inspect it.");
    currentSatelliteLayer = data;
    if (satelliteLayerMesh) {
        fieldRoot.remove(satelliteLayerMesh);
        satelliteLayerMesh.geometry.dispose();
        satelliteLayerMesh.material.map?.dispose();
        satelliteLayerMesh.material.dispose();
        satelliteLayerMesh = null;
    }
    if (!data?.boundary?.coordinates?.[0]) {
        if (satellite3dStatus) satellite3dStatus.textContent = "Sekinchan satellite data unavailable; the AOI-shaped field remains visible.";
        if (!soil3dToggle?.checked) setTwinLayerLegend("", "", 0, 0, "", [], "");
        return;
    }
    if (soilLayerMesh && soil3dToggle?.checked) {
        soil3dToggle.checked = false;
        soilLayerMesh.visible = false;
    }
    if (satellite3dToggle) satellite3dToggle.checked = true;
    const result = makeSatelliteTexture(data);
    if (!result) return;
    fieldRoot.rotation.y = result.angle;
    satelliteLayerMesh = new THREE.Mesh(
        new THREE.PlaneGeometry(FIELD_WIDTH - 0.12, FIELD_DEPTH - 0.12),
        new THREE.MeshBasicMaterial({ map: result.texture, transparent: true, opacity: Number(twinOverlayOpacity?.value ?? 82) / 100, depthWrite: false, side: THREE.DoubleSide })
    );
    satelliteLayerMesh.rotation.x = -Math.PI / 2;
    satelliteLayerMesh.position.y = 0.235;
    satelliteLayerMesh.renderOrder = 5;
    satelliteLayerMesh.visible = satellite3dToggle?.checked ?? true;
    satelliteLayerMesh.userData.projection = result.projection;
    satelliteLayerMesh.userData.inspectorPoints = prepareInspectorPoints(data, result.projection);
    fieldRoot.add(satelliteLayerMesh);
    const isStatic = data.layer_kind === "satellite_static";
    const label = isStatic
        ? `${data.label} · static layer · ${data.points?.length ?? 0} AOI grid locations`
        : `${data.metric} · ${data.window_start} to ${data.window_end} · ${data.points?.length ?? 0} valid pixels`;
    if (satellite3dStatus) satellite3dStatus.textContent = `${label} · AOI-clipped texture overlay; crop growth is illustrative.${isStatic ? " " + data.scale_note : ""}`;
    setTwinLayerPill(isStatic
        ? `STATIC SATELLITE · ${data.label} · ${data.points?.length ?? 0} locations`
        : `SATELLITE · ${data.metric} · ${data.window_start} — ${data.window_end} · ${data.points?.length ?? 0} pixels`);
    if (satellite3dToggle?.checked) renderTwinSatelliteLegend(data);
}

function updateSoilLayer(data) {
    clearCellInspector("Soil reference updated. Hover over or click a coloured satellite/soil cell to inspect it.");
    currentSoilLayer = data;
    if (soilLayerMesh) {
        fieldRoot.remove(soilLayerMesh);
        soilLayerMesh.geometry.dispose();
        soilLayerMesh.material.map?.dispose();
        soilLayerMesh.material.dispose();
        soilLayerMesh = null;
    }
    if (!data?.points?.length || !currentSatelliteLayer?.boundary?.coordinates?.[0]) {
        if (soil3dStatus) soil3dStatus.textContent = "Soil reference raster cells are unavailable for this AOI.";
        return;
    }
    const result = makeSatelliteTexture({ ...data, boundary: currentSatelliteLayer.boundary });
    if (!result) return;
    fieldRoot.rotation.y = result.angle;
    soilLayerMesh = new THREE.Mesh(
        new THREE.PlaneGeometry(FIELD_WIDTH - 0.12, FIELD_DEPTH - 0.12),
        new THREE.MeshBasicMaterial({ map: result.texture, transparent: true, opacity: Number(twinOverlayOpacity?.value ?? 82) / 100, depthWrite: false, side: THREE.DoubleSide })
    );
    soilLayerMesh.rotation.x = -Math.PI / 2;
    soilLayerMesh.position.y = 0.236;
    soilLayerMesh.renderOrder = 6;
    soilLayerMesh.visible = soil3dToggle?.checked ?? false;
    soilLayerMesh.userData.projection = result.projection;
    soilLayerMesh.userData.inspectorPoints = prepareInspectorPoints(data, result.projection);
    fieldRoot.add(soilLayerMesh);
    const range = data.min == null || data.max == null ? "range unavailable" : `${Number(data.min).toFixed(2)}–${Number(data.max).toFixed(2)} ${data.unit}`;
    if (soil3dStatus) soil3dStatus.textContent = `${data.property.replaceAll("_", " ")} · ${data.depth_cm} cm · ${range} · ${data.pixel_count} coarse cells · ${data.resolution_m_approx} m · ${data.source} · reference only.`;
    setTwinLayerPill(`SOIL REFERENCE · ${data.property.replaceAll("_", " ")} · ${data.depth_cm} cm · ${range}`);
    if (soil3dToggle?.checked) renderTwinSoilLegend(data);
}

function clearIllustrativeMission() {
    missionAnimationPlaying = false;
    if (missionOverlay) {
        fieldRoot.remove(missionOverlay);
        missionOverlay.traverse(object => {
            object.geometry?.dispose();
            if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
            else object.material?.dispose();
        });
        missionOverlay = null;
    }
    missionRouteLocal = [];
    missionSegmentLengths = [];
    missionRouteTotal = 0;
}

function showIllustrativeMission(plan) {
    clearIllustrativeMission();
    const projection = satelliteLayerMesh?.userData?.projection || soilLayerMesh?.userData?.projection;
    if (!projection || !plan?.route?.length) throw new Error("Load the satellite boundary before drawing the illustrative route.");
    missionOverlay = new THREE.Group();
    missionOverlay.name = "Synthetic illustrative UAV mission";
    missionOverlay.userData.evidenceClass = "SYNTHETIC";

    for (const footprint of plan.footprints || []) {
        const planePoints = footprint.corners.map(corner => projection.localToPlane(
            projection.lonLatToLocal([corner.longitude, corner.latitude])
        ));
        if (planePoints.length < 3) continue;
        const shape = new THREE.Shape();
        shape.moveTo(planePoints[0][0], -planePoints[0][1]);
        planePoints.slice(1).forEach(point => shape.lineTo(point[0], -point[1]));
        shape.closePath();
        const fill = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({
            color: 0x70d8a0, transparent: true, opacity: 0.32, depthWrite: false, side: THREE.DoubleSide
        }));
        fill.rotation.x = -Math.PI / 2;
        fill.position.y = 0.248;
        fill.renderOrder = 12;
        missionOverlay.add(fill);
        const outlinePoints = planePoints.map(point => new THREE.Vector3(point[0], 0.27, point[1]));
        outlinePoints.push(outlinePoints[0].clone());
        const outline = new THREE.Line(new THREE.BufferGeometry().setFromPoints(outlinePoints), new THREE.LineBasicMaterial({ color: 0x9af0c0, transparent: true, opacity: 0.95, depthTest: false }));
        outline.renderOrder = 13;
        missionOverlay.add(outline);
    }

    missionRouteLocal = plan.route.map(point => projection.localToPlane(
        projection.lonLatToLocal([point.longitude, point.latitude])
    ));
    missionSegmentLengths = missionRouteLocal.slice(1).map((point, index) => Math.hypot(
        point[0] - missionRouteLocal[index][0], point[1] - missionRouteLocal[index][1]
    ));
    missionRouteTotal = missionSegmentLengths.reduce((sum, length) => sum + length, 0);
    const routePoints = missionRouteLocal.map(point => new THREE.Vector3(point[0], 0.29, point[1]));
    const routeLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(routePoints), new THREE.LineBasicMaterial({ color: 0xffd36d, depthTest: false }));
    routeLine.renderOrder = 14;
    missionOverlay.add(routeLine);

    const marker = new THREE.Mesh(new THREE.SphereGeometry(0.16, 14, 10), new THREE.MeshBasicMaterial({ color: 0xff6d48, depthTest: false }));
    marker.name = "Illustrative UAV marker";
    marker.position.set(routePoints[0].x, 0.43, routePoints[0].z);
    marker.renderOrder = 15;
    missionOverlay.add(marker);
    missionOverlay.userData.marker = marker;
    fieldRoot.add(missionOverlay);
    missionAnimationPlaying = false;
    const clearButton = document.getElementById("mission-clear");
    const playButton = document.getElementById("mission-play");
    if (clearButton) clearButton.disabled = false;
    if (playButton) { playButton.disabled = missionRouteLocal.length < 2; playButton.textContent = "Play route"; }
}

document.addEventListener("paddy-satellite-layer", event => updateSatelliteLayer(event.detail));
document.addEventListener("paddy-soil-layer", event => updateSoilLayer(event.detail));
document.addEventListener("paddy-illustrative-mission", event => {
    try { showIllustrativeMission(event.detail); }
    catch (error) { document.getElementById("mission-status").textContent = error.message; }
});
document.getElementById("mission-clear")?.addEventListener("click", () => {
    clearIllustrativeMission();
    document.getElementById("mission-clear").disabled = true;
    document.getElementById("mission-play").disabled = true;
    document.getElementById("mission-play").textContent = "Play route";
    document.getElementById("mission-status").textContent = "Illustrative mission cleared from the 3D view.";
});
document.getElementById("mission-play")?.addEventListener("click", event => {
    missionAnimationPlaying = !missionAnimationPlaying;
    if (missionAnimationPlaying) missionAnimationStartedAt = clock.getElapsedTime();
    event.currentTarget.textContent = missionAnimationPlaying ? "Pause route" : "Play route";
});
satellite3dToggle?.addEventListener("change", () => {
    clearCellInspector("Overlay selection changed. Hover over or click a coloured satellite/soil cell to inspect it.");
    if (satellite3dToggle.checked && soilLayerMesh) {
        if (soil3dToggle) soil3dToggle.checked = false;
        soilLayerMesh.visible = false;
    }
    if (satelliteLayerMesh) satelliteLayerMesh.visible = satellite3dToggle.checked;
    if (satellite3dToggle.checked && currentSatelliteLayer) renderTwinSatelliteLegend(currentSatelliteLayer);
    else if (!soil3dToggle?.checked) setTwinLayerLegend("", "", 0, 0, "", [], "");
    if (satellite3dStatus && currentSatelliteLayer) {
        satellite3dStatus.textContent = satellite3dToggle.checked
            ? currentSatelliteLayer.layer_kind === "satellite_static"
                ? `${currentSatelliteLayer.label} · static AOI layer shown; crop geometry remains illustrative. ${currentSatelliteLayer.scale_note}`
                : `${currentSatelliteLayer.metric} · ${currentSatelliteLayer.window_start} to ${currentSatelliteLayer.window_end} · satellite layer shown on AOI; crop geometry remains illustrative.`
            : "Satellite layer hidden · illustrative 3D crop scene shown.";
    }
    if (!satellite3dToggle.checked && !soil3dToggle?.checked) setTwinLayerPill("NO DATA OVERLAY · illustrative 3D field only");
    else if (satellite3dToggle.checked && currentSatelliteLayer) setTwinLayerPill(currentSatelliteLayer.layer_kind === "satellite_static"
        ? `STATIC SATELLITE · ${currentSatelliteLayer.label} · ${currentSatelliteLayer.points?.length ?? 0} locations`
        : `SATELLITE · ${currentSatelliteLayer.metric} · ${currentSatelliteLayer.window_start} — ${currentSatelliteLayer.window_end} · ${currentSatelliteLayer.points?.length ?? 0} pixels`);
});
soil3dToggle?.addEventListener("change", () => {
    clearCellInspector("Overlay selection changed. Hover over or click a coloured satellite/soil cell to inspect it.");
    if (soil3dToggle.checked) {
        if (satellite3dToggle) satellite3dToggle.checked = false;
        if (satelliteLayerMesh) satelliteLayerMesh.visible = false;
        if (soilLayerMesh) soilLayerMesh.visible = true;
        if (satellite3dStatus) satellite3dStatus.textContent = "Satellite overlay hidden while the coarse soil reference layer is selected.";
        if (currentSoilLayer) renderTwinSoilLegend(currentSoilLayer);
    } else if (soilLayerMesh) {
        soilLayerMesh.visible = false;
        if (!satellite3dToggle?.checked) setTwinLayerLegend("", "", 0, 0, "", [], "");
    }
    if (!soil3dToggle.checked && !satellite3dToggle?.checked) setTwinLayerPill("NO DATA OVERLAY · illustrative 3D field only");
    else if (!soil3dToggle.checked && satellite3dToggle?.checked && currentSatelliteLayer) setTwinLayerPill(currentSatelliteLayer.layer_kind === "satellite_static"
        ? `STATIC SATELLITE · ${currentSatelliteLayer.label} · ${currentSatelliteLayer.points?.length ?? 0} locations`
        : `SATELLITE · ${currentSatelliteLayer.metric} · ${currentSatelliteLayer.window_start} — ${currentSatelliteLayer.window_end} · ${currentSatelliteLayer.points?.length ?? 0} pixels`);
});

// Soil
const soil = new THREE.Mesh(
    new THREE.BoxGeometry(FIELD_WIDTH, 0.26, FIELD_DEPTH),
    new THREE.MeshStandardMaterial({
        color: 0xffffff,
        map: soilTexture,
        roughness: 0.96
    })
);
soil.position.y = 0.06;
soil.receiveShadow = true;
soil.castShadow = true;
fieldRoot.add(soil);

// A restrained shallow-water sheen gives the paddy a wet, planted surface
// while keeping the soil texture visible through it.
const fieldWater = new THREE.Mesh(
    new THREE.PlaneGeometry(FIELD_WIDTH - 0.9, FIELD_DEPTH - 0.9),
    new THREE.MeshPhysicalMaterial({
        color: 0x87917a,
        roughness: 0.34,
        metalness: 0.04,
        clearcoat: 0.38,
        clearcoatRoughness: 0.32,
        transparent: true,
        opacity: 0.22,
        depthWrite: false
    })
);
fieldWater.rotation.x = -Math.PI / 2;
fieldWater.position.y = 0.196;
fieldWater.renderOrder = 1;
fieldRoot.add(fieldWater);

// Keep the selected study field as the only raised plot in the scene. The
// softly lit ground and fog give it depth without adding unrelated demo plots.

// Field bunds
const bundMaterial = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: soilTexture,
    roughness: 0.98
});

const bunds = [
    new THREE.Mesh(
        new THREE.BoxGeometry(FIELD_WIDTH, 0.12, 0.28),
        bundMaterial
    ),
    new THREE.Mesh(
        new THREE.BoxGeometry(FIELD_WIDTH, 0.12, 0.28),
        bundMaterial
    ),
    new THREE.Mesh(
        new THREE.BoxGeometry(0.28, 0.12, FIELD_DEPTH),
        bundMaterial
    ),
    new THREE.Mesh(
        new THREE.BoxGeometry(0.28, 0.12, FIELD_DEPTH),
        bundMaterial
    )
];

bunds[0].position.set(0, 0.25, -FIELD_DEPTH / 2 + 0.14);
bunds[1].position.set(0, 0.25, FIELD_DEPTH / 2 - 0.14);
bunds[2].position.set(-FIELD_WIDTH / 2 + 0.14, 0.25, 0);
bunds[3].position.set(FIELD_WIDTH / 2 - 0.14, 0.25, 0);

for (const bund of bunds) {
    bund.castShadow = true;
    bund.receiveShadow = true;
    fieldRoot.add(bund);
}
// Soil furrows between rice rows
const furrowMaterial = new THREE.MeshStandardMaterial({
    color: 0x302318,
    roughness: 1
});

for (let z = -FIELD_DEPTH / 2 + 0.8; z <= FIELD_DEPTH / 2 - 0.8; z += 1.35) {
    const furrow = new THREE.Mesh(
        new THREE.BoxGeometry(FIELD_WIDTH - 1.8, 0.008, 0.08),
        furrowMaterial
    );
    furrow.position.set(0, 0.191, z);
    fieldRoot.add(furrow);
}

// Rice plant materials
const stemMaterial = new THREE.MeshStandardMaterial({
    color: 0x657b3d,
    roughness: 0.85
});

const leafMaterials = [
    new THREE.MeshStandardMaterial({
        color: 0x416b37,
        side: THREE.DoubleSide,
        roughness: 0.8
    }),
    new THREE.MeshStandardMaterial({
        color: 0x638a41,
        side: THREE.DoubleSide,
        roughness: 0.8
    }),
    new THREE.MeshStandardMaterial({
        color: 0x315b30,
        side: THREE.DoubleSide,
        roughness: 0.8
    })
];

// Narrow, tapered leaves with a gentle 3D curl; broad flat blades made the crop
// read as a decorative low-poly model instead of a rice canopy.
function createLeafGeometry(length, width) {
    const segments = 10;
    const vertices = [];
    const indices = [];
    for (let row = 0; row <= segments; row++) {
        const t = row / segments;
        const taper = Math.pow(Math.sin(Math.PI * t), 0.72);
        const halfWidth = Math.max(0.002, width * 0.5 * taper);
        const sweep = width * 0.55 * t * t;
        for (const side of [-1, 0, 1]) {
            vertices.push(
                sweep + side * halfWidth,
                length * t,
                (1 - Math.abs(side)) * width * 0.11 * Math.sin(Math.PI * t)
            );
        }
    }
    for (let row = 0; row < segments; row++) {
        const current = row * 3;
        const next = current + 3;
        for (let col = 0; col < 2; col++) {
            const a = current + col, b = a + 1, c = next + col, d = c + 1;
            indices.push(a, c, b, b, c, d);
        }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return geometry;
}

const leafGeometries = [
    createLeafGeometry(0.78, 0.09),
    createLeafGeometry(0.96, 0.105),
    createLeafGeometry(1.12, 0.115),
    createLeafGeometry(0.88, 0.082)
];

// Mature rice grain heads
const grainGeometry = new THREE.SphereGeometry(0.075, 7, 6);
const grainMaterial = new THREE.MeshStandardMaterial({
    color: 0xd8bd68,
    roughness: 0.82
});
const panicleMaterial = new THREE.MeshStandardMaterial({
    color: 0x9b8748,
    roughness: 0.9
});

// Rice plants
const plantGroup = new THREE.Group();
fieldRoot.add(plantGroup);

function createRicePlant(x, z) {
    const plant = new THREE.Group();
    plant.position.set(x, 0.22, z);
    const height = 0.88 + Math.random() * 0.45;

    // Rice grows as a small clump of tillers rather than a single upright stalk.
    const culmOffsets = [[-0.045, -0.02], [0, 0], [0.045, 0.025]];
    const culmHeights = [height * 0.78, height, height * 0.88];
    for (let culmIndex = 0; culmIndex < culmOffsets.length; culmIndex++) {
        const culm = new THREE.Mesh(
            new THREE.CylinderGeometry(0.012, 0.026, culmHeights[culmIndex], 5),
            stemMaterial
        );
        culm.position.set(culmOffsets[culmIndex][0], culmHeights[culmIndex] / 2, culmOffsets[culmIndex][1]);
        culm.castShadow = false;
        plant.add(culm);
    }

    const leafCount = 10 + Math.floor(Math.random() * 3);

    for (let i = 0; i < leafCount; i++) {
        const leaf = new THREE.Mesh(
            leafGeometries[Math.floor(Math.random() * leafGeometries.length)],
            leafMaterials[Math.floor(Math.random() * leafMaterials.length)]
        );

        const angle = (i / leafCount) * Math.PI * 2
            + (Math.random() - 0.5) * 0.45;
        const culmIndex = i % culmOffsets.length;
        const culmHeight = culmHeights[culmIndex];
        const leafHeight = culmHeight * (0.1 + Math.random() * 0.45);
        const offset = culmOffsets[culmIndex];

        leaf.position.set(
            offset[0] + Math.cos(angle) * 0.035,
            leafHeight,
            offset[1] + Math.sin(angle) * 0.035
        );
        leaf.rotation.y = -angle;
        leaf.rotation.z = -0.66 + Math.random() * 1.32;
        leaf.rotation.x = -0.66 + Math.random() * 1.32;
        leaf.castShadow = false;
        plant.add(leaf);
    }

    // Grain heads appear only in heading and mature stages
    const panicle = new THREE.Group();
    panicle.position.set(0, height * 0.78, 0);
    panicle.rotation.y = Math.random() * Math.PI * 2;
    panicle.visible = false;

    const panicleCurve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0.04, 0.2, 0),
        new THREE.Vector3(0.1, 0.34, 0),
        new THREE.Vector3(0.2, 0.39, 0)
    ]);

    panicle.add(new THREE.Mesh(
        new THREE.TubeGeometry(panicleCurve, 6, 0.012, 4, false),
        panicleMaterial
    ));

    const branchVertices = [];
    const grainInstances = new THREE.InstancedMesh(
        grainGeometry,
        grainMaterial,
        9
    );
    const grainTransform = new THREE.Object3D();

    for (let grainIndex = 0; grainIndex < 9; grainIndex++) {
        const t = 0.18 + grainIndex * 0.085;
        const point = panicleCurve.getPoint(t);
        const side = grainIndex % 2 === 0 ? -1 : 1;
        const branchEnd = point.clone().add(
            new THREE.Vector3(side * 0.12, -0.12, 0)
        );

        branchVertices.push(
            point.x, point.y, point.z,
            branchEnd.x, branchEnd.y, branchEnd.z
        );

        grainTransform.position.copy(branchEnd);
        grainTransform.position.y -= 0.035;
        grainTransform.rotation.z = side * -0.35;
        grainTransform.scale.set(0.72, 1.45, 0.72);
        grainTransform.updateMatrix();
        grainInstances.setMatrixAt(grainIndex, grainTransform.matrix);
    }

    const branchGeometry = new THREE.BufferGeometry();
    branchGeometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(branchVertices, 3)
    );
    panicle.add(new THREE.LineSegments(branchGeometry, panicleMaterial));

    grainInstances.castShadow = false;
    panicle.add(grainInstances);

    plant.add(panicle);
    plant.userData.panicle = panicle;
    plant.userData.windOffset = Math.random() * Math.PI * 2;
    plant.userData.windStrength = 0.07 + Math.random() * 0.06;

    plantGroup.add(plant);
    plants.push(plant);
}

// Arrange rice plants in rows
const rowCount = 16;
const plantsPerRow = 52;
const rowSpacing = (FIELD_DEPTH - 2) / (rowCount - 1);
const plantSpacing = (FIELD_WIDTH - 3) / (plantsPerRow - 1);

for (let row = 0; row < rowCount; row++) {
    const z = (row - (rowCount - 1) / 2) * rowSpacing;

    for (let i = 0; i < plantsPerRow; i++) {
        const x = (i - (plantsPerRow - 1) / 2) * plantSpacing;

        createRicePlant(
            x + (Math.random() - 0.5) * 0.12,
            z + (Math.random() - 0.5) * 0.12
        );
    }
}

// Growth and wind controls
const growthSlider = document.getElementById("growth-slider");
const growthLabel = document.getElementById("growth-stage-label");
const windToggle = document.getElementById("wind-toggle");

document.getElementById("reset-camera")?.addEventListener("click", () => {
    controls.reset();
});

// Illustrative crop growth stages
const growthStages = {
    1: { name: "Seedling", scale: 0.30, panicleScale: 0 },
    2: { name: "Early vegetative", scale: 0.42, panicleScale: 0 },
    3: { name: "Tillering", scale: 0.56, panicleScale: 0 },
    4: { name: "Stem elongation", scale: 0.72, panicleScale: 0 },
    5: { name: "Booting", scale: 0.84, panicleScale: 0 },
    6: { name: "Heading & grain fill", scale: 0.94, panicleScale: 0.72 },
    7: { name: "Ripening & mature crop", scale: 1.08, panicleScale: 1 },
    8: { name: "Harvested field · stubble", scale: 0.22, panicleScale: 0 }
};

function applyGrowthStage(stageValue) {
    const stage = growthStages[stageValue];
    if (!stage) return;

    for (const plant of plants) {
        plant.scale.setScalar(stage.scale);
        plant.userData.panicle.visible = stage.panicleScale > 0;
        plant.userData.panicle.scale.setScalar(stage.panicleScale);
    }

    growthLabel.textContent = stage.name;
    const harvested = Number(stageValue) === 8;
    const baseLeafColors = [0x4f8039, 0x78a94b, 0x376b32];
    const harvestLeafColors = [0x9b8844, 0xb09a53, 0x88763c];
    leafMaterials.forEach((material, index) => material.color.setHex(harvested ? harvestLeafColors[index] : baseLeafColors[index]));
    stemMaterial.color.setHex(harvested ? 0x88763c : 0x719345);
    grainMaterial.color.setHex(Number(stageValue) >= 7 && !harvested ? 0xd8bd68 : 0x9aaa55);
}

if (growthSlider && growthLabel) {
    growthSlider.addEventListener("input", () => {
        applyGrowthStage(Number(growthSlider.value));
    });

    applyGrowthStage(Number(growthSlider.value));
}

// Resize renderer with the dashboard container
function resizeRenderer() {
    const width = container.clientWidth;
    const height = container.clientHeight;

    if (!width || !height) return;

    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
}

const resizeObserver = new ResizeObserver(resizeRenderer);
resizeObserver.observe(container);

// Gentle crop breeze; the soil and background scenery remain still
const clock = new THREE.Clock();

renderer.setAnimationLoop(() => {
    const time = clock.getElapsedTime();
    const windEnabled = windToggle?.checked ?? true;

    if (missionAnimationPlaying && missionOverlay?.userData?.marker && missionRouteTotal > 0) {
        const progressDistance = ((time - missionAnimationStartedAt) % 24) / 24 * missionRouteTotal;
        let remaining = progressDistance;
        let segment = 0;
        while (segment < missionSegmentLengths.length - 1 && remaining > missionSegmentLengths[segment]) {
            remaining -= missionSegmentLengths[segment];
            segment += 1;
        }
        const start = missionRouteLocal[segment];
        const end = missionRouteLocal[segment + 1];
        const fraction = missionSegmentLengths[segment] ? remaining / missionSegmentLengths[segment] : 0;
        const marker = missionOverlay.userData.marker;
        marker.position.set(start[0] + (end[0] - start[0]) * fraction, 0.43, start[1] + (end[1] - start[1]) * fraction);
    }

    for (const plant of plants) {
        plant.rotation.z = windEnabled
            ? Math.sin(time * 1.8 + plant.userData.windOffset)
                * plant.userData.windStrength
            : 0;

        plant.rotation.x = windEnabled
            ? Math.sin(time * 1.5 + plant.userData.windOffset)
                * plant.userData.windStrength * 0.55
            : 0;
    }

    controls.update();
    renderer.render(scene, camera);
});

if (window.latestSekinchanSatelliteLayer) updateSatelliteLayer(window.latestSekinchanSatelliteLayer);



console.log("PaddyVision Digital Twin initialized.");
console.log(`Rice plants rendered: ${plants.length}`);





















