'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { WebSocketServer } = require('ws');
const L = require('./shared');

const PORT = Number(process.env.PORT) || 3030;
const PUBLIC = path.join(__dirname, 'public');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function servePublic(req, res) {
  let urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
  if (urlPath === '/') urlPath = '/index.html';
  if (urlPath === '/shared.js') {
    const file = path.join(__dirname, 'shared.js');
    res.writeHead(200, { 'Content-Type': MIME['.js'], 'Cache-Control': 'no-store' });
    fs.createReadStream(file).pipe(res);
    return;
  }
  const safe = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, '');
  const file = path.join(PUBLIC, safe);
  if (!file.startsWith(PUBLIC)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not found');
      return;
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    res.end(data);
  });
}

function lanIPs() {
  const out = [];
  const ifaces = os.networkInterfaces();
  for (const list of Object.values(ifaces)) {
    for (const n of list || []) {
      if (n.family === 'IPv4' && !n.internal) out.push(n.address);
    }
  }
  return out;
}

/** @type {Map<import('ws').WebSocket, any>} */
const clients = new Map();
let nextId = 1;
let seed = (Math.random() * 1e9) | 0;
let solid = L.generateTerrain(seed);
const bullets = [];
const digQueue = [];
let tick = 0;

function broadcast(obj, except = null) {
  const raw = JSON.stringify(obj);
  for (const [ws] of clients) {
    if (ws !== except && ws.readyState === 1) ws.send(raw);
  }
}

function send(ws, obj) {
  if (ws.readyState === 1) ws.send(JSON.stringify(obj));
}

function playerPublic(p) {
  return {
    id: p.id,
    name: p.name,
    color: p.color,
    x: p.x,
    y: p.y,
    angle: p.angle,
    hp: p.hp,
    alive: p.alive,
    weapon: p.weapon,
    kills: p.kills,
    deaths: p.deaths,
    facing: p.facing,
  };
}

function snapshot() {
  return {
    type: 'state',
    tick,
    players: [...clients.values()].map(playerPublic),
    bullets: bullets.map((b) => ({
      id: b.id,
      x: b.x,
      y: b.y,
      vx: b.vx,
      vy: b.vy,
      r: b.r,
      color: b.color,
    })),
    digs: digQueue.splice(0, digQueue.length),
  };
}

function spawnPlayer(p) {
  const rand = L.mulberry32((seed ^ (p.id * 9973) ^ (Date.now() & 0xffff)) >>> 0);
  const s = L.findSpawn(solid, rand);
  p.x = s.x;
  p.y = s.y;
  p.vx = 0;
  p.vy = 0;
  p.hp = 100;
  p.alive = true;
  p.cooldown = 0;
  p.rope = null;
}

function damagePlayer(p, dmg, killerId) {
  if (!p.alive) return;
  p.hp -= dmg;
  if (p.hp <= 0) {
    p.hp = 0;
    p.alive = false;
    p.deaths += 1;
    p.respawnAt = tick + 90;
    if (killerId && killerId !== p.id) {
      for (const other of clients.values()) {
        if (other.id === killerId) other.kills += 1;
      }
    }
    // death crater
    L.digCircle(solid, p.x, p.y, 18);
    digQueue.push({ x: p.x, y: p.y, r: 18 });
  }
}

function explode(x, y, digR, dmg, ownerId) {
  L.digCircle(solid, x, y, digR);
  digQueue.push({ x, y, r: digR });
  for (const p of clients.values()) {
    if (!p.alive) continue;
    const dx = p.x - x;
    const dy = p.y - y;
    const dist = Math.hypot(dx, dy);
    if (dist < digR + L.PLAYER_R) {
      const falloff = 1 - dist / (digR + L.PLAYER_R);
      damagePlayer(p, dmg * falloff, ownerId);
      const push = 6 * falloff;
      if (dist > 0.1) {
        p.vx += (dx / dist) * push;
        p.vy += (dy / dist) * push - 2;
      }
    }
  }
}

let bulletId = 1;
function fireWeapon(p) {
  const w = L.WEAPONS[p.weapon];
  if (!w || p.cooldown > 0 || !p.alive) return;
  p.cooldown = w.cooldown;

  if (w.melee) {
    const tx = p.x + Math.cos(p.angle) * 16;
    const ty = p.y + Math.sin(p.angle) * 16;
    L.digCircle(solid, tx, ty, w.dig);
    digQueue.push({ x: tx, y: ty, r: w.dig });
    for (const other of clients.values()) {
      if (other.id === p.id || !other.alive) continue;
      if (Math.hypot(other.x - tx, other.y - ty) < L.PLAYER_R + w.dig) {
        damagePlayer(other, w.damage, p.id);
      }
    }
    return;
  }

  const pellets = w.pellets || 1;
  for (let i = 0; i < pellets; i++) {
    const spread = (w.spread || 0) * (Math.random() - 0.5) * 2;
    const a = p.angle + spread;
    bullets.push({
      id: bulletId++,
      owner: p.id,
      x: p.x + Math.cos(a) * (L.PLAYER_R + 4),
      y: p.y + Math.sin(a) * (L.PLAYER_R + 4),
      vx: Math.cos(a) * w.speed,
      vy: Math.sin(a) * w.speed,
      r: w.radius,
      damage: w.damage,
      dig: w.dig,
      explode: !!w.explode,
      color: p.color,
      life: 90,
    });
  }
}

function movePlayer(p) {
  if (!p.alive) {
    if (p.respawnAt && tick >= p.respawnAt) spawnPlayer(p);
    return;
  }

  const inp = p.input || {};
  if (inp.left) p.vx -= L.MOVE_ACCEL;
  if (inp.right) p.vx += L.MOVE_ACCEL;
  p.vx *= L.FRICTION;
  if (p.vx > L.MAX_SPEED) p.vx = L.MAX_SPEED;
  if (p.vx < -L.MAX_SPEED) p.vx = -L.MAX_SPEED;
  if (p.vx > 0.15) p.facing = 1;
  if (p.vx < -0.15) p.facing = -1;

  // ground check
  const onGround = L.circleHitsTerrain(solid, p.x, p.y + 1, L.PLAYER_R);
  if (inp.jump && onGround) p.vy = L.JUMP_V;

  p.vy += L.GRAVITY;
  if (p.vy > 12) p.vy = 12;

  // separate axis resolution
  p.x += p.vx;
  if (L.circleHitsTerrain(solid, p.x, p.y, L.PLAYER_R)) {
    p.x -= p.vx;
    p.vx *= -0.2;
  }
  p.y += p.vy;
  if (L.circleHitsTerrain(solid, p.x, p.y, L.PLAYER_R)) {
    p.y -= p.vy;
    p.vy = p.vy > 0 ? 0 : p.vy * -0.15;
  }

  p.x = Math.max(L.PLAYER_R, Math.min(L.WIDTH - L.PLAYER_R, p.x));
  p.y = Math.max(L.PLAYER_R, Math.min(L.HEIGHT - L.PLAYER_R, p.y));

  if (typeof inp.angle === 'number') p.angle = inp.angle;
  if (inp.shoot) fireWeapon(p);
  if (inp.prevW) {
    p.weapon = (p.weapon + L.WEAPONS.length - 1) % L.WEAPONS.length;
    p.input.prevW = false;
  }
  if (inp.nextW) {
    p.weapon = (p.weapon + 1) % L.WEAPONS.length;
    p.input.nextW = false;
  }

  if (p.cooldown > 0) p.cooldown -= 1;
}

function updateBullets() {
  for (let i = bullets.length - 1; i >= 0; i--) {
    const b = bullets[i];
    b.life -= 1;
    b.vy += 0.12;
    b.x += b.vx;
    b.y += b.vy;

    let hit = false;
    if (!L.inBounds(b.x, b.y) || b.life <= 0) hit = true;
    else if (L.solidAt(solid, b.x, b.y)) hit = true;

    if (!hit) {
      for (const p of clients.values()) {
        if (!p.alive || p.id === b.owner) continue;
        if (Math.hypot(p.x - b.x, p.y - b.y) < L.PLAYER_R + b.r) {
          hit = true;
          if (b.explode) explode(b.x, b.y, b.dig, b.damage, b.owner);
          else {
            damagePlayer(p, b.damage, b.owner);
            L.digCircle(solid, b.x, b.y, b.dig);
            digQueue.push({ x: b.x, y: b.y, r: b.dig });
          }
          break;
        }
      }
    }

    if (hit) {
      if (b.explode && L.inBounds(b.x, b.y)) explode(b.x, b.y, b.dig, b.damage, b.owner);
      else if (!b.explode && L.inBounds(b.x, b.y)) {
        L.digCircle(solid, b.x, b.y, b.dig);
        digQueue.push({ x: b.x, y: b.y, r: b.dig });
      }
      bullets.splice(i, 1);
    }
  }
}

function gameTick() {
  tick += 1;
  for (const p of clients.values()) movePlayer(p);
  updateBullets();
  broadcast(snapshot());
}

const server = http.createServer(servePublic);
const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  if (clients.size >= L.MAX_PLAYERS) {
    send(ws, { type: 'error', message: 'Tele a szerver (max 8).' });
    ws.close();
    return;
  }

  const id = nextId++;
  const color = L.COLORS[(id - 1) % L.COLORS.length];
  const player = {
    id,
    name: `Féreg${id}`,
    color,
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
    angle: 0,
    facing: 1,
    hp: 100,
    alive: true,
    weapon: 0,
    cooldown: 0,
    kills: 0,
    deaths: 0,
    input: {},
    respawnAt: 0,
  };
  spawnPlayer(player);
  clients.set(ws, player);

  // Send welcome with terrain
  const terrainBuf = L.encodeTerrainRle(solid);
  send(ws, {
    type: 'welcome',
    id,
    seed,
    width: L.WIDTH,
    height: L.HEIGHT,
    weapons: L.WEAPONS.map((w) => ({ id: w.id, name: w.name })),
    terrain: Buffer.from(terrainBuf).toString('base64'),
    you: playerPublic(player),
  });
  broadcast({ type: 'join', player: playerPublic(player) }, ws);

  ws.on('message', (data) => {
    let msg;
    try {
      msg = JSON.parse(String(data));
    } catch {
      return;
    }
    const p = clients.get(ws);
    if (!p) return;

    if (msg.type === 'hello') {
      const name = String(msg.name || '').trim().slice(0, 16);
      if (name) p.name = name;
      broadcast({ type: 'join', player: playerPublic(p) });
      return;
    }

    if (msg.type === 'input') {
      p.input = {
        left: !!msg.left,
        right: !!msg.right,
        jump: !!msg.jump,
        shoot: !!msg.shoot,
        angle: typeof msg.angle === 'number' ? msg.angle : p.angle,
        prevW: !!msg.prevW,
        nextW: !!msg.nextW,
      };
      return;
    }

    if (msg.type === 'reset' && clients.size <= 2) {
      // host-ish reset if few players
      seed = (Math.random() * 1e9) | 0;
      solid = L.generateTerrain(seed);
      bullets.length = 0;
      for (const pl of clients.values()) {
        pl.kills = 0;
        pl.deaths = 0;
        spawnPlayer(pl);
      }
      const terrain = Buffer.from(L.encodeTerrainRle(solid)).toString('base64');
      broadcast({ type: 'map', seed, terrain });
    }
  });

  ws.on('close', () => {
    clients.delete(ws);
    broadcast({ type: 'leave', id });
  });
});

setInterval(gameTick, L.TICK_MS);

server.listen(PORT, '0.0.0.0', () => {
  const ips = lanIPs();
  console.log('');
  console.log('  LIERO LAN — multiplayer féregháború');
  console.log(`  Helyi:   http://127.0.0.1:${PORT}`);
  for (const ip of ips) console.log(`  LAN:    http://${ip}:${PORT}`);
  console.log('  Ctrl+C = kilépés');
  console.log('');
});
