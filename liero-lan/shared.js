'use strict';

/**
 * Shared Liero-LAN helpers — works in Node (module.exports) and browser (globalThis.Liero).
 */

const WIDTH = 1280;
const HEIGHT = 720;
const TICK_MS = 1000 / 30;
const MAX_PLAYERS = 8;
const PLAYER_R = 7;
const GRAVITY = 0.35;
const MOVE_ACCEL = 0.55;
const MAX_SPEED = 4.2;
const JUMP_V = -7.2;
const FRICTION = 0.82;

const WEAPONS = [
  { id: 'pistol', name: 'Pisztoly', cooldown: 10, ammo: Infinity, speed: 14, spread: 3, spread: 12, dig: 4, spread: 1, life: 0 },
  { id: 'shotgun', name: 'Sörétes', cooldown: 35, ammo: Infinity, speed: 12, radius: 2.5, damage: 8, dig: 6, pellets: 6, spread: 0.18 },
  { id: 'bazooka', name: 'Bazooka', cooldown: 55, ammo: Infinity, speed: 8, radius: 5, damage: 38, dig: 42, pellets: 1, life: 0, explode: true },
  { id: 'torch', name: 'Fúró', cooldown: 3, ammo: Infinity, speed: 10, radius: 2, damage: 2, dig: 16, pellets: 1, life: 0, melee: true },
  { id: 'mine', name: 'Aknavető', cooldown: 45, ammo: Infinity, speed: 6, radius: 4, damage: 28, dig: 30, pellets: 1, life: 0.05, explode: true },
];

const COLORS = ['#ff5a3d', '#3dffb5', '#ffd23d', '#5aa9ff', '#ff5ad5', '#a8ff3d', '#ff9a3d', '#c07bff'];

function mulberry32(seed) {
  let t = seed >>> 0;
  return function rand() {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function idx(x, y) {
  return (y | 0) * WIDTH + (x | 0);
}

function inBounds(x, y) {
  return x >= 0 && y >= 0 && x < WIDTH && y < HEIGHT;
}

function generateTerrain(seed) {
  const rand = mulberry32(seed);
  const solid = new Uint8Array(WIDTH * HEIGHT);

  // Base dirt fill below wavy surface
  for (let x = 0; x < WIDTH; x++) {
    const surface =
      160 +
      Math.sin(x * 0.01) * 40 +
      Math.sin(x * 0.027 + 2) * 28 +
      Math.sin(x * 0.07) * 12 +
      (rand() - 0.5) * 8;
    for (let y = 0; y < HEIGHT; y++) {
      if (y > surface) solid[idx(x, y)] = 1;
    }
  }

  // Carve caves
  const caves = 28 + Math.floor(rand() * 10);
  for (let i = 0; i < caves; i++) {
    let cx = 80 + rand() * (WIDTH - 160);
    let cy = 220 + rand() * (HEIGHT - 280);
    const steps = 40 + Math.floor(rand() * 80);
    for (let s = 0; s < steps; s++) {
      const r = 10 + rand() * 22;
      digCircle(solid, cx, cy, r);
      cx += (rand() - 0.5) * 28;
      cy += (rand() - 0.5) * 22;
      cx = Math.max(40, Math.min(WIDTH - 40, cx));
      cy = Math.max(120, Math.min(HEIGHT - 40, cy));
    }
  }

  // Border walls / floor stay solid-ish: soft floor belt
  for (let x = 0; x < WIDTH; x++) {
    for (let y = HEIGHT - 18; y < HEIGHT; y++) solid[idx(x, y)] = 1;
    for (let y = 0; y < 8; y++) solid[idx(x, y)] = 0;
  }

  return solid;
}

function digCircle(solid, cx, cy, r) {
  const r2 = r * r;
  const x0 = Math.max(0, Math.floor(cx - r - 1));
  const x1 = Math.min(WIDTH - 1, Math.ceil(cx + r + 1));
  const y0 = Math.max(0, Math.floor(cy - r - 1));
  const y1 = Math.min(HEIGHT - 1, Math.ceil(cy + r + 1));
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - cy;
      if (dx * dx + dy * dy <= r2) solid[idx(x, y)] = 0;
    }
  }
}

function solidAt(solid, x, y) {
  const ix = x | 0;
  const iy = y | 0;
  if (!inBounds(ix, iy)) return true;
  return solid[idx(ix, iy)] === 1;
}

function circleHitsTerrain(solid, cx, cy, r) {
  const samples = 12;
  for (let i = 0; i < samples; i++) {
    const a = (i / samples) * Math.PI * 2;
    if (solidAt(solid, cx + Math.cos(a) * r, cy + Math.sin(a) * r)) return true;
  }
  return solidAt(solid, cx, cy);
}

function findSpawn(solid, attemptRand) {
  for (let i = 0; i < 200; i++) {
    const x = 40 + attemptRand() * (WIDTH - 80);
    const y = 40 + attemptRand() * (HEIGHT - 120);
    if (!circleHitsTerrain(solid, x, y, PLAYER_R + 2)) {
      // prefer air with ground nearby below
      let ground = false;
      for (let dy = 1; dy < 40; dy++) {
        if (solidAt(solid, x, y + PLAYER_R + dy)) {
          ground = true;
          break;
        }
      }
      if (ground || i > 120) return { x, y };
    }
  }
  return { x: WIDTH / 2, y: 80 };
}

function encodeTerrainRle(solid) {
  const out = [];
  let i = 0;
  while (i < solid.length) {
    const v = solid[i];
    let n = 1;
    while (i + n < solid.length && solid[i + n] === v && n < 65535) n++;
    out.push(v, n & 255, (n >> 8) & 255);
    i += n;
  }
  return Uint8Array.from(out);
}

function decodeTerrainRle(buf, length = WIDTH * HEIGHT) {
  const solid = new Uint8Array(length);
  const data = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let i = 0;
  let o = 0;
  while (i + 2 < data.length && o < length) {
    const v = data[i++];
    const n = data[i++] | (data[i++] << 8);
    solid.fill(v, o, Math.min(length, o + n));
    o += n;
  }
  return solid;
}

const api = {
  WIDTH,
  HEIGHT,
  TICK_MS,
  MAX_PLAYERS,
  PLAYER_R,
  GRAVITY,
  MOVE_ACCEL,
  MAX_SPEED,
  JUMP_V,
  FRICTION,
  WEAPONS,
  COLORS,
  mulberry32,
  idx,
  inBounds,
  generateTerrain,
  digCircle,
  solidAt,
  circleHitsTerrain,
  findSpawn,
  encodeTerrainRle,
  decodeTerrainRle,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
} else {
  globalThis.Liero = api;
}
