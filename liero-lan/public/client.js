'use strict';

(() => {
  const L = globalThis.Liero;
  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d', { alpha: false });
  const boot = document.getElementById('boot');
  const hud = document.getElementById('hud');
  const nameInput = document.getElementById('name');
  const joinBtn = document.getElementById('join');
  const weaponEl = document.getElementById('weapon');
  const hpbar = document.getElementById('hpbar');
  const scoreEl = document.getElementById('score');
  const netEl = document.getElementById('net');

  const saved = localStorage.getItem('liero.name') || '';
  if (saved) nameInput.value = saved;

  let ws = null;
  let myId = null;
  let solid = null;
  let terrainCanvas = null;
  let terrainCtx = null;
  let players = new Map();
  let bullets = [];
  let weapons = [];
  let camX = 0;
  let camY = 0;
  let connected = false;
  let lastStateAt = 0;

  const keys = new Set();
  const mouse = { x: L.WIDTH / 2, y: L.HEIGHT / 2, down: false };
  let prevW = false;
  let nextW = false;

  function decodeTerrain(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return L.decodeTerrainRle(bytes, L.WIDTH * L.HEIGHT);
  }

  function rebuildTerrainImage() {
    if (!terrainCanvas) {
      terrainCanvas = document.createElement('canvas');
      terrainCanvas.width = L.WIDTH;
      terrainCanvas.height = L.HEIGHT;
      terrainCtx = terrainCanvas.getContext('2d');
    }
    const img = terrainCtx.createImageData(L.WIDTH, L.HEIGHT);
    const d = img.data;
    for (let i = 0; i < solid.length; i++) {
      const o = i * 4;
      if (solid[i]) {
        const y = (i / L.WIDTH) | 0;
        const n = ((i * 17) ^ (y * 13)) & 7;
        d[o] = 90 + n * 6;
        d[o + 1] = 48 + n * 3;
        d[o + 2] = 24 + (n & 3);
        d[o + 3] = 255;
      } else {
        // sky / cave void
        const y = (i / L.WIDTH) | 0;
        const sky = Math.max(0, 1 - y / 260);
        d[o] = 18 + sky * 40;
        d[o + 1] = 14 + sky * 28;
        d[o + 2] = 12 + sky * 20;
        d[o + 3] = 255;
      }
    }
    terrainCtx.putImageData(img, 0, 0);
  }

  function applyDig(x, y, r) {
    L.digCircle(solid, x, y, r);
    if (!terrainCtx) return;
    const r2 = r * r;
    const x0 = Math.max(0, Math.floor(x - r - 1));
    const x1 = Math.min(L.WIDTH - 1, Math.ceil(x + r + 1));
    const y0 = Math.max(0, Math.floor(y - r - 1));
    const y1 = Math.min(L.HEIGHT - 1, Math.ceil(y + r + 1));
    const w = x1 - x0 + 1;
    const h = y1 - y0 + 1;
    const img = terrainCtx.getImageData(x0, y0, w, h);
    const d = img.data;
    for (let py = y0; py <= y1; py++) {
      for (let px = x0; px <= x1; px++) {
        const dx = px + 0.5 - x;
        const dy = py + 0.5 - y;
        if (dx * dx + dy * dy > r2) continue;
        const o = ((py - y0) * w + (px - x0)) * 4;
        const sky = Math.max(0, 1 - py / 260);
        d[o] = 18 + sky * 40;
        d[o + 1] = 14 + sky * 28;
        d[o + 2] = 12 + sky * 20;
        d[o + 3] = 255;
      }
    }
    terrainCtx.putImageData(img, x0, y0);
  }

  function wsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}`;
  }

  function connect() {
    const name = nameInput.value.trim().slice(0, 16) || 'Féreg';
    localStorage.setItem('liero.name', name);
    joinBtn.disabled = true;
    joinBtn.textContent = 'Csatlakozás…';

    ws = new WebSocket(wsUrl());
    ws.addEventListener('open', () => {
      connected = true;
      ws.send(JSON.stringify({ type: 'hello', name }));
      boot.hidden = true;
      hud.hidden = false;
      loopInput();
      requestAnimationFrame(frame);
    });
    ws.addEventListener('close', () => {
      connected = false;
      netEl.textContent = 'Kapcsolat bontva — frissíts';
      joinBtn.disabled = false;
      joinBtn.textContent = 'Csatlakozás';
      boot.hidden = false;
    });
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'welcome') {
        myId = msg.id;
        weapons = msg.weapons || [];
        solid = decodeTerrain(msg.terrain);
        rebuildTerrainImage();
        players.set(msg.you.id, msg.you);
        netEl.textContent = 'Online';
      } else if (msg.type === 'map') {
        solid = decodeTerrain(msg.terrain);
        rebuildTerrainImage();
      } else if (msg.type === 'join') {
        players.set(msg.player.id, msg.player);
      } else if (msg.type === 'leave') {
        players.delete(msg.id);
      } else if (msg.type === 'state') {
        lastStateAt = performance.now();
        players = new Map(msg.players.map((p) => [p.id, p]));
        bullets = msg.bullets || [];
        for (const d of msg.digs || []) applyDig(d.x, d.y, d.r);
        const me = players.get(myId);
        if (me) {
          weaponEl.textContent = (weapons[me.weapon] && weapons[me.weapon].name) || 'Fegyver';
          hpbar.style.transform = `scaleX(${Math.max(0, me.hp / 100)})`;
        }
        scoreEl.innerHTML = [...players.values()]
          .sort((a, b) => b.kills - a.kills)
          .map((p) => `${escapeHtml(p.name)} ${p.kills}/${p.deaths}`)
          .join('<br>');
      } else if (msg.type === 'error') {
        alert(msg.message || 'Hiba');
        joinBtn.disabled = false;
        joinBtn.textContent = 'Csatlakozás';
      }
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function canvasMouse(e) {
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / rect.width;
    const sy = canvas.height / rect.height;
    // screen coords in canvas pixel space (camera applied in world later)
    return {
      sx: (e.clientX - rect.left) * sx,
      sy: (e.clientY - rect.top) * sy,
    };
  }

  canvas.addEventListener('mousemove', (e) => {
    const m = canvasMouse(e);
    mouse.x = m.sx + camX;
    mouse.y = m.sy + camY;
  });
  canvas.addEventListener('mousedown', (e) => {
    if (e.button === 0) mouse.down = true;
  });
  window.addEventListener('mouseup', (e) => {
    if (e.button === 0) mouse.down = false;
  });
  canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (e.deltaY > 0) nextW = true;
    else prevW = true;
  }, { passive: false });

  window.addEventListener('keydown', (e) => {
    keys.add(e.code);
    if (e.code === 'KeyQ') prevW = true;
    if (e.code === 'KeyE') nextW = true;
    if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault();
  });
  window.addEventListener('keyup', (e) => keys.delete(e.code));

  function loopInput() {
    if (!connected || !ws || ws.readyState !== 1) return;
    const me = players.get(myId);
    let angle = me ? me.angle : 0;
    if (me) angle = Math.atan2(mouse.y - me.y, mouse.x - me.x);
    ws.send(JSON.stringify({
      type: 'input',
      left: keys.has('KeyA') || keys.has('ArrowLeft'),
      right: keys.has('KeyD') || keys.has('ArrowRight'),
      jump: keys.has('KeyW') || keys.has('Space') || keys.has('ArrowUp'),
      shoot: mouse.down || keys.has('KeyJ'),
      angle,
      prevW,
      nextW,
    }));
    prevW = false;
    nextW = false;
    setTimeout(loopInput, 1000 / 30);
  }

  function frame() {
    const me = players.get(myId);
    if (me) {
      camX = me.x - canvas.width / 2;
      camY = me.y - canvas.height / 2;
      camX = Math.max(0, Math.min(L.WIDTH - canvas.width, camX));
      camY = Math.max(0, Math.min(L.HEIGHT - canvas.height, camY));
    }

    // keep mouse world pos updated relative to camera while idle
    // (mousemove already stores world)

    ctx.fillStyle = '#100b08';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (terrainCanvas) ctx.drawImage(terrainCanvas, -camX, -camY);

    // bullets
    for (const b of bullets) {
      ctx.beginPath();
      ctx.fillStyle = b.color || '#fff';
      ctx.arc(b.x - camX, b.y - camY, Math.max(2, b.r), 0, Math.PI * 2);
      ctx.fill();
    }

    // players
    for (const p of players.values()) {
      if (!p.alive) continue;
      const x = p.x - camX;
      const y = p.y - camY;

      // body
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.ellipse(x, y, L.PLAYER_R + 1, L.PLAYER_R, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#1a100a';
      ctx.lineWidth = 2;
      ctx.stroke();

      // eye / face toward aim
      const ex = x + Math.cos(p.angle) * 3.5;
      const ey = y + Math.sin(p.angle) * 3.5 - 1;
      ctx.fillStyle = '#fff6e8';
      ctx.beginPath();
      ctx.arc(ex, ey, 2.2, 0, Math.PI * 2);
      ctx.fill();

      // weapon barrel
      ctx.strokeStyle = '#2a1a12';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + Math.cos(p.angle) * 16, y + Math.sin(p.angle) * 16);
      ctx.stroke();

      // name
      ctx.fillStyle = p.id === myId ? '#ffe29a' : '#e8d2b0';
      ctx.font = '600 12px "IBM Plex Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(p.name, x, y - L.PLAYER_R - 8);

      if (p.id === myId) {
        // crosshair at mouse
        const hx = mouse.x - camX;
        const hy = mouse.y - camY;
        ctx.strokeStyle = 'rgba(255,200,100,0.85)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hx - 8, hy);
        ctx.lineTo(hx + 8, hy);
        ctx.moveTo(hx, hy - 8);
        ctx.lineTo(hx, hy + 8);
        ctx.stroke();
      }
    }

    if (performance.now() - lastStateAt > 2000 && connected) {
      netEl.textContent = 'Lag / nincs state…';
    }

    requestAnimationFrame(frame);
  }

  joinBtn.addEventListener('click', connect);
  nameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') connect();
  });
})();
