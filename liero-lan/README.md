# LIERO LAN

Böngészős, multiplayer, **Liero-szerű** 2D féregháború helyi hálózaton (Wi‑Fi / LAN).

## Indítás (host gép)

```bash
cd liero-lan
npm install
npm start
```

Windows: `start.bat`

A konzol kiírja:
- `http://127.0.0.1:3030` — host
- `http://<LAN-IP>:3030` — többi gép / telefon ugyanazon a Wi‑Fin

## Irányítás

| Billentyű | Akció |
|-----------|--------|
| A / D | Mozgás |
| W / Space | Ugrás |
| Egér | Célzás (kurzor) |
| Bal katt / J | Lövés |
| Q / E vagy görgő | Fegyverváltás |

## Fegyverek

Pisztoly, sörétes, bazooka, fúró, aknavető — rombolható terep, respawn, kill/death tábla.

## Hálózat

Egy gép futtatja a Node szervert; a többiek csak böngészővel csatlakoznak. Max 8 játékos.
