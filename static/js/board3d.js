// 3D Pylos board (Three.js).
// Exposes (via globals):
//   window.boardReady()   - (re)init the scene if needed
//   window.boardRender()  - sync to latest server state

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const PLAYER_COLOR_DARK  = 0x6a4527;   // opponent (or player-1 marbles)
const PLAYER_COLOR_LIGHT = 0xf0e3c1;   // you (or player-0 marbles)
const HIGHLIGHT_COLOR    = 0x4c7cff;
const RETRIEVE_COLOR     = 0xffd166;
const SOURCE_COLOR       = 0xff5d6c;

let renderer, scene, camera, controls;
let baseGroup, marbleGroup, slotGroup;
let raycaster, pointer;
let canvas, canvasWrap;
let resizeObserver;

// Track current valid-action slots: { mesh -> {type, lv, r, c, ...} }
const actionSlots = new Map();
// Track marbles on board: key 'lv,r,c' -> mesh
const placedMarbles = new Map();
let hovered = null;
let lastHoverWasMarble = false;

const SHARED = {
  marbleGeom: null,
  slotDiscGeom: null,
  slotHitGeom: null,
};

function ensureGeoms() {
  if (!SHARED.marbleGeom) {
    SHARED.marbleGeom = new THREE.SphereGeometry(MARBLE_RADIUS, 32, 24);
  }
  if (!SHARED.slotDiscGeom) {
    // Visible glow disc — full marble-sized so it's easy to tap on mobile.
    SHARED.slotDiscGeom = new THREE.CircleGeometry(MARBLE_RADIUS * 1.05, 36);
  }
  if (!SHARED.slotHitGeom) {
    // Invisible larger hit target for fingers (1.4x marble radius).
    SHARED.slotHitGeom = new THREE.CircleGeometry(MARBLE_RADIUS * 1.4, 24);
  }
}

function init3D() {
  canvas = document.getElementById('board-canvas');
  canvasWrap = document.getElementById('canvas-wrap');
  if (!canvas || renderer) return;

  ensureGeoms();

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;

  scene = new THREE.Scene();
  scene.background = null;

  camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.set(6, 6.5, 7.5);

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.set(0, 1.5, 0);
  controls.minDistance = 4.5;
  controls.maxDistance = 16;
  controls.maxPolarAngle = Math.PI * 0.49;

  // Lights
  const hemi = new THREE.HemisphereLight(0xb1c0ff, 0x1a1430, 0.55);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xffffff, 1.1);
  sun.position.set(6, 12, 4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = -8;
  sun.shadow.camera.right = 8;
  sun.shadow.camera.top = 8;
  sun.shadow.camera.bottom = -8;
  scene.add(sun);
  const accent = new THREE.PointLight(0x4c7cff, 0.6, 18);
  accent.position.set(-4, 4, -3);
  scene.add(accent);

  // Base plate
  baseGroup = new THREE.Group();
  scene.add(baseGroup);
  buildBase();

  // Marble + slot groups
  marbleGroup = new THREE.Group();
  scene.add(marbleGroup);
  slotGroup = new THREE.Group();
  scene.add(slotGroup);

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();

  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointerup', onPointerUp);
  document.getElementById('cancel-lift-btn').addEventListener('click', cancelLift);

  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvasWrap);
  resize();

  animate();
}

function buildBase() {
  // Wooden plate
  const plateGeo = new THREE.BoxGeometry(
    SLOT_SPACING * NUM_LEVELS + 1.5,
    PLATE_THICKNESS,
    SLOT_SPACING * NUM_LEVELS + 1.5
  );
  const plateMat = new THREE.MeshStandardMaterial({
    color: 0x32243a, metalness: 0.4, roughness: 0.45,
  });
  const plate = new THREE.Mesh(plateGeo, plateMat);
  plate.receiveShadow = true;
  plate.position.y = 0;
  baseGroup.add(plate);

  // Bevel
  const bevelGeo = new THREE.BoxGeometry(
    SLOT_SPACING * NUM_LEVELS + 1.7,
    PLATE_THICKNESS * 0.4,
    SLOT_SPACING * NUM_LEVELS + 1.7
  );
  const bevelMat = new THREE.MeshStandardMaterial({
    color: 0x261a2e, metalness: 0.3, roughness: 0.6,
  });
  const bevel = new THREE.Mesh(bevelGeo, bevelMat);
  bevel.position.y = -PLATE_THICKNESS * 0.6;
  baseGroup.add(bevel);

  // Indentations on level 0 (decorative)
  const indMat = new THREE.MeshStandardMaterial({
    color: 0x180f23, metalness: 0.5, roughness: 0.4,
  });
  const indGeo = new THREE.CircleGeometry(MARBLE_RADIUS * 0.95, 32);
  for (let r = 0; r < NUM_LEVELS; r++) {
    for (let c = 0; c < NUM_LEVELS; c++) {
      const m = new THREE.Mesh(indGeo, indMat);
      m.rotation.x = -Math.PI / 2;
      const p = slotCenter(0, r, c);
      m.position.set(p.x, PLATE_THICKNESS / 2 + 0.001, p.z);
      baseGroup.add(m);
    }
  }
}

function resize() {
  if (!canvasWrap) return;
  const w = canvasWrap.clientWidth;
  const h = canvasWrap.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();

  // Pulse hovered/action slots gently
  const t = performance.now() * 0.003;
  slotGroup.children.forEach(m => {
    const baseScale = m.userData.baseScale ?? 1;
    m.scale.setScalar(baseScale + Math.sin(t) * 0.05);
  });

  renderer.render(scene, camera);
}

// ── Hit-testing & interaction ───────────────────────────────────────────

function onPointerMove(e) {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  updateHover();
}

function updateHover() {
  if (!state.game) return;
  raycaster.setFromCamera(pointer, camera);

  // Hit slot indicators first
  const slotHits = raycaster.intersectObjects(slotGroup.children, false);
  // Hit marbles for lift-from / retrieve
  const marbleHits = raycaster.intersectObjects(marbleGroup.children, false);

  let nextHover = null;
  let isMarble = false;

  if (slotHits.length) {
    nextHover = slotHits[0].object;
  } else if (marbleHits.length) {
    // Only highlight own marbles that are interactable
    const m = marbleHits[0].object;
    if (m.userData.interactable) {
      nextHover = m;
      isMarble = true;
    }
  }

  if (nextHover !== hovered) {
    if (hovered) {
      // restore
      if (lastHoverWasMarble) {
        const baseCol = hovered.userData.baseColor;
        if (baseCol !== undefined) hovered.material.emissive?.setHex(0x000000);
      } else if (hovered.material?.opacity !== undefined) {
        hovered.material.opacity = hovered.userData.baseOpacity ?? 0.5;
      }
    }
    if (nextHover) {
      if (isMarble) {
        nextHover.material.emissive?.setHex(0x6c8fff);
      } else if (nextHover.material?.opacity !== undefined) {
        nextHover.material.opacity = 0.95;
      }
    }
    hovered = nextHover;
    lastHoverWasMarble = isMarble;
  }

  canvas.style.cursor = nextHover ? 'pointer' : 'grab';
}

// Track pointer-down to distinguish taps from drag-rotates.
let pointerDownX = 0, pointerDownY = 0, pointerDownTime = 0;
const TAP_PIXEL_THRESHOLD = 10;
const TAP_TIME_THRESHOLD = 600; // ms

function onPointerDown(e) {
  pointerDownX = e.clientX;
  pointerDownY = e.clientY;
  pointerDownTime = performance.now();
}

function onPointerUp(e) {
  const dx = e.clientX - pointerDownX;
  const dy = e.clientY - pointerDownY;
  const moved = Math.hypot(dx, dy);
  const dt = performance.now() - pointerDownTime;
  if (moved > TAP_PIXEL_THRESHOLD || dt > TAP_TIME_THRESHOLD) return;
  if (!state.game) return;
  if (state.pending) return;

  // Sync raycaster to the release point (touch doesn't fire pointermove).
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

  raycaster.setFromCamera(pointer, camera);
  const slotHits = raycaster.intersectObjects(slotGroup.children, false);
  if (slotHits.length) {
    const info = slotHits[0].object.userData;
    handleSlotClick(info);
    return;
  }
  const marbleHits = raycaster.intersectObjects(marbleGroup.children, false);
  if (marbleHits.length) {
    const info = marbleHits[0].object.userData;
    if (info.interactable) handleMarbleClick(info);
  }
}

function handleSlotClick(info) {
  const g = state.game;
  if (!g) return;
  if (g.current_player !== state.yourPlayer || g.game_over) return;

  if (info.type === 'place') {
    sendPlace(info.lv, info.r, info.c);
  } else if (info.type === 'lift-target' && state.liftFrom) {
    const { lv: fl, r: fr, c: fc } = state.liftFrom;
    state.liftFrom = null;
    sendLift(fl, fr, fc, info.lv, info.r, info.c);
    document.getElementById('cancel-lift-btn').classList.add('hidden');
  }
}

function handleMarbleClick(info) {
  const g = state.game;
  if (!g) return;
  if (g.current_player !== state.yourPlayer || g.game_over) return;

  if (g.retrieve_open) {
    // Only own non-supporting marbles are interactable
    if (info.player === state.yourPlayer) {
      sendRetrieve(info.lv, info.r, info.c);
    }
    return;
  }

  // Start lift
  if (info.player === state.yourPlayer && info.canLift) {
    state.liftFrom = { lv: info.lv, r: info.r, c: info.c };
    updateStatus();
    document.getElementById('cancel-lift-btn').classList.remove('hidden');
    rebuildSlots();   // show lift targets
  }
}

function cancelLift() {
  state.liftFrom = null;
  document.getElementById('cancel-lift-btn').classList.add('hidden');
  rebuildSlots();
  updateStatus();
}

// ── Geometry sync ───────────────────────────────────────────────────────

function clearGroup(g) {
  while (g.children.length) {
    const c = g.children.pop();
    c.geometry?.dispose?.();
    c.material?.dispose?.();
  }
}

function colorForPlayer(p) {
  // From the local player's POV: yourPlayer always renders LIGHT, opponent DARK.
  const me = state.yourPlayer;
  return (p === me) ? PLAYER_COLOR_LIGHT : PLAYER_COLOR_DARK;
}

function isSupported(board, lv, r, c) {
  if (lv === 0) return true;
  const b = board[lv - 1];
  return b[r][c] != null && b[r + 1][c] != null
      && b[r][c + 1] != null && b[r + 1][c + 1] != null;
}

function isSupporting(board, lv, r, c) {
  if (lv >= NUM_LEVELS - 1) return false;
  const above = board[lv + 1];
  const s = levelSize(lv + 1);
  for (let r2 = Math.max(0, r - 1); r2 < Math.min(s, r + 1); r2++) {
    for (let c2 = Math.max(0, c - 1); c2 < Math.min(s, c + 1); c2++) {
      if (above[r2][c2] != null) return true;
    }
  }
  return false;
}

function rebuildMarbles() {
  clearGroup(marbleGroup);
  placedMarbles.clear();
  const g = state.game;
  if (!g) return;
  const myTurn = g.current_player === state.yourPlayer && !g.game_over;

  for (let lv = 0; lv < NUM_LEVELS; lv++) {
    const s = levelSize(lv);
    for (let r = 0; r < s; r++) {
      for (let c = 0; c < s; c++) {
        const p = g.board[lv][r][c];
        if (p == null) continue;
        const baseCol = colorForPlayer(p);
        const mat = new THREE.MeshStandardMaterial({
          color: baseCol,
          metalness: 0.05,
          roughness: 0.25,
          emissive: 0x000000,
        });
        const m = new THREE.Mesh(SHARED.marbleGeom, mat);
        const center = slotCenter(lv, r, c);
        m.position.set(center.x, center.y, center.z);
        m.castShadow = true;
        m.receiveShadow = true;

        const canLift = (p === state.yourPlayer) && !isSupporting(g.board, lv, r, c);
        const isMyRetrievable = g.retrieve_open && g.current_player === state.yourPlayer
                              && p === state.yourPlayer && canLift;
        m.userData = {
          player: p, lv, r, c, canLift, baseColor: baseCol,
          interactable: myTurn && (canLift || isMyRetrievable),
        };
        marbleGroup.add(m);
        placedMarbles.set(`${lv},${r},${c}`, m);
      }
    }
  }
}

function rebuildSlots() {
  clearGroup(slotGroup);
  actionSlots.clear();
  const g = state.game;
  if (!g) return;
  if (g.game_over) return;
  const myTurn = g.current_player === state.yourPlayer;
  if (!myTurn) return;
  if (g.retrieve_open) return; // no slot indicators during retrieval

  // Build set of empty supported slots
  const validSlots = [];
  for (let lv = 0; lv < NUM_LEVELS; lv++) {
    const s = levelSize(lv);
    for (let r = 0; r < s; r++) {
      for (let c = 0; c < s; c++) {
        if (g.board[lv][r][c] != null) continue;
        if (!isSupported(g.board, lv, r, c)) continue;
        validSlots.push({ lv, r, c });
      }
    }
  }

  if (state.liftFrom) {
    // In lift mode: highlight valid lift targets only.
    const src = state.liftFrom;
    // Temporarily remove source for support check
    const saved = g.board[src.lv][src.r][src.c];
    g.board[src.lv][src.r][src.c] = null;
    for (const slot of validSlots) {
      if (slot.lv <= src.lv) continue;
      if (!isSupported(g.board, slot.lv, slot.r, slot.c)) continue;
      addSlotIndicator(slot.lv, slot.r, slot.c, 'lift-target', HIGHLIGHT_COLOR);
    }
    g.board[src.lv][src.r][src.c] = saved;
    // Source mark
    addSlotIndicator(src.lv, src.r, src.c, 'lift-source', SOURCE_COLOR, true);
    return;
  }

  // Normal placement indicators (only if we have reserve)
  if (g.reserve[state.yourPlayer] > 0) {
    for (const slot of validSlots) {
      addSlotIndicator(slot.lv, slot.r, slot.c, 'place', HIGHLIGHT_COLOR);
    }
  }
}

function addSlotIndicator(lv, r, c, type, color, isSource=false) {
  const mat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: isSource ? 0.55 : 0.32,
    side: THREE.DoubleSide, depthWrite: false,
  });
  const m = new THREE.Mesh(SHARED.slotDiscGeom, mat);
  m.rotation.x = -Math.PI / 2;
  const pos = slotCenter(lv, r, c);
  // Sit the disc slightly above the floor of the slot for visibility.
  const y = (lv === 0)
    ? PLATE_THICKNESS / 2 + 0.012
    : pos.y - MARBLE_RADIUS + 0.005;
  m.position.set(pos.x, y, pos.z);
  m.userData = { type, lv, r, c, baseOpacity: mat.opacity, baseScale: 1 };
  slotGroup.add(m);
  actionSlots.set(m, m.userData);

  // Larger invisible hit target stacked on top so finger taps near the
  // slot still register, even if the visible disc is partially occluded.
  const hitMat = new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0, depthWrite: false, depthTest: false,
    side: THREE.DoubleSide,
  });
  const hit = new THREE.Mesh(SHARED.slotHitGeom, hitMat);
  hit.rotation.x = -Math.PI / 2;
  hit.position.set(pos.x, y + 0.002, pos.z);
  hit.renderOrder = 999;
  hit.userData = { type, lv, r, c, baseOpacity: 0, baseScale: 1, isHit: true };
  slotGroup.add(hit);
}

// Exposed sync function
window.boardReady = function () {
  init3D();
  // Initial render if state already present
  if (state.game) window.boardRender();
};

window.boardRender = function () {
  if (!renderer) init3D();
  if (!state.game) return;
  rebuildMarbles();
  rebuildSlots();
  // If it's no longer our turn, drop any pending lift selection.
  if (state.liftFrom &&
      (state.game.current_player !== state.yourPlayer || state.game.game_over)) {
    state.liftFrom = null;
    document.getElementById('cancel-lift-btn').classList.add('hidden');
  }
};
