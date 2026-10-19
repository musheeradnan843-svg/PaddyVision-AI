import * as THREE from "three";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js";

const container = document.getElementById("digital-twin-container");
const plants = [];
let paddyPlantsReady = false;
let latestPaddyMaskSource = null;
const healthDemoMeshes = [];
let activeHealthDemoZone = window.paddyHealthDemoZone ?? null;

function focusHealthDemoZone(zone) {
    activeHealthDemoZone = zone;
    for (const patch of healthDemoMeshes) {
        const selected = patch.zone === activeHealthDemoZone;
        if (patch.isFieldBase) {
            patch.fill.material.opacity = selected ? 0.32 : 0.12;
        } else {
            patch.fill.material.opacity = selected ? 0.72 : 0.38;
            patch.ring.material.opacity = selected ? 1 : 0.58;
            patch.ring.scale.set(
                patch.radiusX * (selected ? 1.12 : 1.02),
                patch.radiusZ * (selected ? 1.12 : 1.02),
                1
            );
        }
    }
}

document.addEventListener("paddy-health-demo-focus", event => {
    focusHealthDemoZone(event.detail?.zone ?? null);
});

if (!container) {
    throw new Error("Digital Twin container nahi mila. index.html check karo.");
}

// Register the prediction bridge before building the Three.js scene. This
// keeps an early U-Net result from being lost while the crop meshes initialize.
async function setPaddyMaskProjection(maskSource) {
    latestPaddyMaskSource = maskSource ?? null;
    const status = document.getElementById("segmentation-scene-status");

    if (!paddyPlantsReady) {
        if (status) status.textContent = maskSource
            ? "U-Net mask received · preparing the 3D crop projection…"
            : "Illustrative full-field default · run U-Net to update crop positions from its mask.";
        return true;
    }

    if (!maskSource) {
        for (const plant of plants) plant.visible = true;
        if (status) status.textContent = "Illustrative full-field default · run U-Net to update crop positions from its mask.";
        return true;
    }

    try {
        const maskImage = new Image();
        maskImage.src = maskSource;
        await maskImage.decode();

        const maskCanvas = document.createElement("canvas");
        maskCanvas.width = maskImage.naturalWidth;
        maskCanvas.height = maskImage.naturalHeight;
        const maskContext = maskCanvas.getContext("2d", { willReadFrequently: true });
        if (!maskContext || !maskCanvas.width || !maskCanvas.height) throw new Error("Empty mask image");
        maskContext.drawImage(maskImage, 0, 0);
        const pixels = maskContext.getImageData(0, 0, maskCanvas.width, maskCanvas.height).data;

        let visiblePlants = 0;
        for (const plant of plants) {
            const { u, v } = plant.userData.maskUv;
            const px = Math.min(maskCanvas.width - 1, Math.floor(u * maskCanvas.width));
            const py = Math.min(maskCanvas.height - 1, Math.floor(v * maskCanvas.height));
            const pixelIndex = (py * maskCanvas.width + px) * 4;
            plant.visible = pixels[pixelIndex] >= 128;
            if (plant.visible) visiblePlants++;
        }

        if (status) status.textContent = `U-Net mask applied · ${visiblePlants} of ${plants.length} rice positions shown. Illustrative mapping, not georeferenced.`;
        return true;
    } catch (error) {
        console.warn("Could not project U-Net mask onto the Three.js field:", error);
        if (status) status.textContent = "Prediction mask is available below the button, but could not be applied to the 3D field.";
        return false;
    }
}

document.addEventListener("paddy-mask-projection", event => {
    setPaddyMaskProjection(event.detail?.source ?? null);
});
window.applyPaddyMaskProjection = setPaddyMaskProjection;

// Scene
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a1711);
scene.fog = new THREE.Fog(0x0a1711, 38, 100);

// Camera
const camera = new THREE.PerspectiveCamera(
    48,
    container.clientWidth / container.clientHeight,
    0.1,
    200
);
camera.position.set(20.5, 17.5, 25);

// Renderer
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1));
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
scene.add(new THREE.HemisphereLight(0xdcebd5, 0x344027, 1.4));

const sun = new THREE.DirectionalLight(0xffe5b0, 3.7);
sun.position.set(-12, 25, 14);
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

    context.fillStyle = "#526047";
    context.fillRect(0, 0, size, size);

    const earthColors = ["#625640", "#71644a", "#46543b", "#68704d", "#596443"];

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
    texture.repeat.set(7, 7);
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);

    return texture;
}

// Surrounding ground
const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(100, 100),
    new THREE.MeshStandardMaterial({
        color: 0x9aa17a,
        map: createGroundTexture(),
        roughness: 1
    })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.24;
ground.receiveShadow = true;
scene.add(ground);

// Paddy field dimensions
const FIELD_WIDTH = 32;
const FIELD_DEPTH = 22;

function createSoilTexture() {
    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    context.fillStyle = "#705137";
    context.fillRect(0, 0, size, size);

    const soilColors = ["#4e3928", "#896a45", "#60452f", "#9a7950", "#756044"];
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
    texture.repeat.set(2, 2);
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
    return texture;
}

const soilTexture = createSoilTexture();

// Soil
const soil = new THREE.Mesh(
    new THREE.BoxGeometry(FIELD_WIDTH, 0.42, FIELD_DEPTH),
    new THREE.MeshStandardMaterial({
        color: 0xffffff,
        map: soilTexture,
        roughness: 0.96
    })
);
soil.position.y = -0.02;
soil.receiveShadow = true;
soil.castShadow = true;
scene.add(soil);

// Static, manually placed example zones for the clearly labeled UI demo.
// This green base plus red/amber patches are independent of U-Net masks and
// are not crop health results.
const healthFieldBase = new THREE.Mesh(
    new THREE.PlaneGeometry(FIELD_WIDTH - 0.55, FIELD_DEPTH - 0.55),
    new THREE.MeshBasicMaterial({
        color: 0x137a43,
        transparent: true,
        opacity: 0.12,
        depthWrite: false,
        side: THREE.DoubleSide
    })
);
healthFieldBase.rotation.x = -Math.PI / 2;
healthFieldBase.position.y = 0.197;
healthFieldBase.renderOrder = 1;
scene.add(healthFieldBase);
healthDemoMeshes.push({ zone: "healthy", fill: healthFieldBase, isFieldBase: true });

const healthZoneDefinitions = [
    { zone: "disease", x: 2.5, z: -1.5, radiusX: 2.05, radiusZ: 1.48, color: 0x9f2623 },
    { zone: "warning", x: -3.5, z: 5.2, radiusX: 1.65, radiusZ: 1.2, color: 0xa67513 },
    { zone: "warning", x: 5.5, z: -6.2, radiusX: 1.5, radiusZ: 1.05, color: 0xa67513 }
];

for (const definition of healthZoneDefinitions) {
    const fill = new THREE.Mesh(
        new THREE.CircleGeometry(1, 36),
        new THREE.MeshBasicMaterial({
            color: definition.color,
            transparent: true,
            opacity: 0.38,
            depthWrite: false,
            side: THREE.DoubleSide
        })
    );
    fill.rotation.x = -Math.PI / 2;
    fill.position.set(definition.x, 0.218, definition.z);
    fill.scale.set(definition.radiusX, definition.radiusZ, 1);
    fill.renderOrder = 2;
    scene.add(fill);

    const ring = new THREE.Mesh(
        new THREE.TorusGeometry(1, 0.028, 4, 36),
        new THREE.MeshBasicMaterial({
            color: definition.color,
            transparent: true,
            opacity: 0.58,
            depthWrite: false
        })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(definition.x, 0.224, definition.z);
    ring.scale.set(definition.radiusX * 1.02, definition.radiusZ * 1.02, 1);
    ring.renderOrder = 3;
    scene.add(ring);

    healthDemoMeshes.push({
        zone: definition.zone,
        fill,
        ring,
        radiusX: definition.radiusX,
        radiusZ: definition.radiusZ
    });
}
if (activeHealthDemoZone) focusHealthDemoZone(activeHealthDemoZone);

// Low-poly trees around the field
const treeSites = [
    [-29, -20], [-21, -23], [-11, -24], [1, -24], [14, -23], [25, -21],
    [-28, -11], [-29, 1], [-28, 13], [28, -12], [29, 0], [28, 12],
    [-25, 21], [-17, 24], [-7, 25], [5, 25], [17, 24], [26, 21]
];

function createBarkTexture() {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 256;
    const context = canvas.getContext("2d");
    context.fillStyle = "#62452e";
    context.fillRect(0, 0, canvas.width, canvas.height);

    for (let i = 0; i < 90; i++) {
        context.globalAlpha = 0.12 + Math.random() * 0.25;
        context.strokeStyle = i % 2 ? "#b18a59" : "#30251d";
        context.lineWidth = 1 + Math.random() * 3;
        const x = Math.random() * canvas.width;
        context.beginPath();
        context.moveTo(x, 0);
        context.lineTo(x + (Math.random() - 0.5) * 10, canvas.height);
        context.stroke();
    }

    context.globalAlpha = 1;
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    return texture;
}

function createFoliageTexture() {
    const size = 256;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    context.fillStyle = "#466c38";
    context.fillRect(0, 0, size, size);
    const leafColors = ["#315b30", "#3e6934", "#5b7b3d", "#708344", "#426633"];

    for (let i = 0; i < 1800; i++) {
        const x = Math.random() * size;
        const y = Math.random() * size;
        const length = 2 + Math.random() * 8;
        context.globalAlpha = 0.28 + Math.random() * 0.5;
        context.strokeStyle = leafColors[Math.floor(Math.random() * leafColors.length)];
        context.lineWidth = 1 + Math.random() * 2;
        context.beginPath();
        context.moveTo(x, y);
        context.quadraticCurveTo(x + length, y - length, x + length * 1.4, y + length * 0.3);
        context.stroke();
    }

    context.globalAlpha = 1;
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
    return texture;
}

const treeTrunkMaterial = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: createBarkTexture(),
    roughness: 0.96
});
const treeCanopyMaterial = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: createFoliageTexture(),
    roughness: 0.9
});
const trunkGeometry = new THREE.CylinderGeometry(0.15, 0.26, 2, 9, 3);
const branchGeometry = new THREE.CylinderGeometry(0.045, 0.09, 1.25, 6);
const treeTrunks = new THREE.InstancedMesh(trunkGeometry, treeTrunkMaterial, treeSites.length);
const treeBranches = new THREE.InstancedMesh(
    branchGeometry,
    treeTrunkMaterial,
    treeSites.length * 2
);
const canopyLayout = [
    [0, 2.15, 0, 1.02],
    [0.62, 1.75, 0, 0.84],
    [0.2, 1.72, 0.58, 0.86],
    [-0.48, 1.76, 0.43, 0.84],
    [-0.61, 1.72, -0.1, 0.86],
    [-0.1, 1.75, -0.61, 0.84],
    [0.42, 1.48, 0.36, 0.72]
];
const treeCanopies = new THREE.InstancedMesh(
    new THREE.SphereGeometry(0.82, 14, 10),
    treeCanopyMaterial,
    treeSites.length * canopyLayout.length
);
const treeTransform = new THREE.Object3D();
const treeColors = [0x93a979, 0x809969, 0xa1ad7e, 0x718c60];
const up = new THREE.Vector3(0, 1, 0);

treeSites.forEach(([x, z], index) => {
    const scale = 1.15 + Math.random() * 0.55;
    const baseY = -0.24;
    treeTransform.position.set(x, baseY + scale, z);
    treeTransform.rotation.y = Math.random() * Math.PI;
    treeTransform.scale.set(scale, scale, scale);
    treeTransform.updateMatrix();
    treeTrunks.setMatrixAt(index, treeTransform.matrix);

    for (let sideIndex = 0; sideIndex < 2; sideIndex++) {
        const side = sideIndex === 0 ? -1 : 1;
        const direction = new THREE.Vector3(side * 0.62, 0.78, side * 0.16).normalize();
        treeTransform.position.set(
            x + direction.x * 0.58 * scale,
            baseY + (0.62 + direction.y * 0.58) * scale,
            z + direction.z * 0.58 * scale
        );
        treeTransform.quaternion.setFromUnitVectors(up, direction);
        treeTransform.scale.setScalar(scale);
        treeTransform.updateMatrix();
        treeBranches.setMatrixAt(index * 2 + sideIndex, treeTransform.matrix);
    }

    canopyLayout.forEach(([offsetX, height, offsetZ, crownScale], cluster) => {
        treeTransform.position.set(
            x + offsetX * scale,
            baseY + height * scale,
            z + offsetZ * scale
        );
        treeTransform.rotation.set(
            (Math.random() - 0.5) * 0.18,
            Math.random() * Math.PI * 2,
            (Math.random() - 0.5) * 0.18
        );
        treeTransform.scale.set(
            crownScale * scale,
            crownScale * (0.84 + Math.random() * 0.2) * scale,
            crownScale * scale
        );
        treeTransform.updateMatrix();
        const instanceIndex = index * canopyLayout.length + cluster;
        treeCanopies.setMatrixAt(instanceIndex, treeTransform.matrix);
        treeCanopies.setColorAt(
            instanceIndex,
            new THREE.Color(treeColors[Math.floor(Math.random() * treeColors.length)])
        );
    });
});

for (const treeMesh of [treeTrunks, treeBranches, treeCanopies]) {
    treeMesh.instanceMatrix.needsUpdate = true;
    treeMesh.castShadow = true;
    treeMesh.receiveShadow = true;
}
if (treeCanopies.instanceColor) treeCanopies.instanceColor.needsUpdate = true;
scene.add(treeTrunks, treeBranches, treeCanopies);

// Instanced grass adds sparse detail to dry ground without thousands of draw calls.
const grassVertices = new Float32Array([
    -0.035, 0, 0,  0.035, 0, 0,  0.012, 0.58, 0,
    -0.035, 0, 0,  0.012, 0.58, 0, -0.012, 0.38, 0,
    0, 0, -0.035,  0, 0, 0.035,  0, 0.58, 0.012,
    0, 0, -0.035,  0, 0.58, 0.012,  0, 0.38, -0.012
]);
const grassGeometry = new THREE.BufferGeometry();
grassGeometry.setAttribute("position", new THREE.BufferAttribute(grassVertices, 3));
grassGeometry.computeVertexNormals();
const grassMaterial = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    side: THREE.DoubleSide,
    roughness: 0.92
});
const grassCount = 4200;
const grass = new THREE.InstancedMesh(grassGeometry, grassMaterial, grassCount);
const grassTransform = new THREE.Object3D();
const grassColors = [0x71834b, 0x89965a, 0x596d3e, 0x9a955e, 0x596141];
let grassIndex = 0;

while (grassIndex < grassCount) {
    const x = (Math.random() - 0.5) * 88;
    const z = (Math.random() - 0.5) * 88;
    const absX = Math.abs(x);
    const absZ = Math.abs(z);
    const insidePaddy = absX < FIELD_WIDTH / 2 + 0.7
        && absZ < FIELD_DEPTH / 2 + 0.7;
    if (insidePaddy) continue;

    const scale = 0.45 + Math.random() * 1.05;
    grassTransform.position.set(x, -0.235, z);
    grassTransform.rotation.y = Math.random() * Math.PI * 2;
    grassTransform.scale.set(scale, scale, scale);
    grassTransform.updateMatrix();
    grass.setMatrixAt(grassIndex, grassTransform.matrix);
    grass.setColorAt(
        grassIndex,
        new THREE.Color(grassColors[Math.floor(Math.random() * grassColors.length)])
    );
    grassIndex++;
}

grass.instanceMatrix.needsUpdate = true;
if (grass.instanceColor) grass.instanceColor.needsUpdate = true;
grass.castShadow = false;
grass.receiveShadow = false;
scene.add(grass);

// Field bunds
const bundMaterial = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    map: soilTexture,
    roughness: 0.98
});

const bunds = [
    new THREE.Mesh(
        new THREE.BoxGeometry(FIELD_WIDTH, 0.16, 0.42),
        bundMaterial
    ),
    new THREE.Mesh(
        new THREE.BoxGeometry(FIELD_WIDTH, 0.16, 0.42),
        bundMaterial
    ),
    new THREE.Mesh(
        new THREE.BoxGeometry(0.42, 0.16, FIELD_DEPTH),
        bundMaterial
    ),
    new THREE.Mesh(
        new THREE.BoxGeometry(0.42, 0.16, FIELD_DEPTH),
        bundMaterial
    )
];

bunds[0].position.set(0, 0.27, -FIELD_DEPTH / 2 + 0.21);
bunds[1].position.set(0, 0.27, FIELD_DEPTH / 2 - 0.21);
bunds[2].position.set(-FIELD_WIDTH / 2 + 0.21, 0.27, 0);
bunds[3].position.set(FIELD_WIDTH / 2 - 0.21, 0.27, 0);

for (const bund of bunds) {
    bund.castShadow = true;
    bund.receiveShadow = true;
    scene.add(bund);
}
// Field border
const border = new THREE.LineSegments(
    new THREE.EdgesGeometry(
        new THREE.BoxGeometry(FIELD_WIDTH, 0.42, FIELD_DEPTH)
    ),
    new THREE.LineBasicMaterial({ color: 0x9ab778 })
);
border.position.y = -0.02;
scene.add(border);

// Soil furrows between rice rows
const furrowMaterial = new THREE.MeshStandardMaterial({
    color: 0x302318,
    roughness: 1
});

for (let z = -9.5; z <= 9.5; z += 1.15) {
    const furrow = new THREE.Mesh(
        new THREE.BoxGeometry(FIELD_WIDTH - 1.8, 0.008, 0.08),
        furrowMaterial
    );
    furrow.position.set(0, 0.191, z);
    scene.add(furrow);
}

// Rice plant materials
const stemMaterial = new THREE.MeshStandardMaterial({
    color: 0x719345,
    roughness: 0.85
});

const leafMaterials = [
    new THREE.MeshStandardMaterial({
        color: 0x4f8039,
        side: THREE.DoubleSide,
        roughness: 0.8
    }),
    new THREE.MeshStandardMaterial({
        color: 0x78a94b,
        side: THREE.DoubleSide,
        roughness: 0.8
    }),
    new THREE.MeshStandardMaterial({
        color: 0x376b32,
        side: THREE.DoubleSide,
        roughness: 0.8
    })
];

// Curved rice leaves
function createLeafGeometry(length, width) {
    const shape = new THREE.Shape();

    shape.moveTo(0, 0);
    shape.quadraticCurveTo(
        width * 0.85, length * 0.28,
        width * 0.65, length * 0.58
    );
    shape.quadraticCurveTo(
        width * 0.4, length * 0.84,
        0, length
    );
    shape.quadraticCurveTo(
        -width * 0.22, length * 0.7,
        -width * 0.25, length * 0.42
    );
    shape.quadraticCurveTo(
        -width * 0.2, length * 0.15,
        0, 0
    );

    return new THREE.ShapeGeometry(shape, 8);
}

const leafGeometries = [
    createLeafGeometry(0.55, 0.13),
    createLeafGeometry(0.75, 0.15),
    createLeafGeometry(0.90, 0.17),
    createLeafGeometry(0.65, 0.11)
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
scene.add(plantGroup);

function createRicePlant(x, z) {
    const plant = new THREE.Group();
    plant.position.set(x, 0.22, z);
    // The uploaded mask is sampled in image space across this illustrative plot.
    // This is a visual projection only; the UAV patch has no field boundary tie.
    plant.userData.maskUv = {
        u: THREE.MathUtils.clamp((x + FIELD_WIDTH / 2) / FIELD_WIDTH, 0, 1),
        v: THREE.MathUtils.clamp(1 - (z + FIELD_DEPTH / 2) / FIELD_DEPTH, 0, 1)
    };

    const height = 0.88 + Math.random() * 0.45;

    const stem = new THREE.Mesh(
        new THREE.CylinderGeometry(0.018, 0.04, height, 6),
        stemMaterial
    );
    stem.position.y = height / 2;
    stem.castShadow = false;
    plant.add(stem);

    const leafCount = 6 + Math.floor(Math.random() * 3);

    for (let i = 0; i < leafCount; i++) {
        const leaf = new THREE.Mesh(
            leafGeometries[Math.floor(Math.random() * leafGeometries.length)],
            leafMaterials[Math.floor(Math.random() * leafMaterials.length)]
        );

        const angle = (i / leafCount) * Math.PI * 2
            + (Math.random() - 0.5) * 0.45;
        const leafHeight = height * (0.12 + Math.random() * 0.38);

        leaf.position.set(
            Math.cos(angle) * 0.035,
            leafHeight,
            Math.sin(angle) * 0.035
        );
        leaf.rotation.y = -angle;
        leaf.rotation.z = -0.25 + Math.random() * 0.5;
        leaf.rotation.x = -0.2 + Math.random() * 0.4;
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
const rowCount = 15;
const plantsPerRow = 24;
const rowSpacing = 1.15;
const plantSpacing = 1.15;

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

// Apply any output received before crop initialization finished.
paddyPlantsReady = true;
if (latestPaddyMaskSource) setPaddyMaskProjection(latestPaddyMaskSource);

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
    7: { name: "Mature crop", scale: 1.08, panicleScale: 1 }
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
    grainMaterial.color.setHex(Number(stageValue) >= 7 ? 0xd8bd68 : 0x9aaa55);
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

console.log("PaddyVision Digital Twin initialized.");
console.log(`Rice plants rendered: ${plants.length}`);





















