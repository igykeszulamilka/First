# First — KAPCS (Shelly LAN panel)

Kis helyi panel Shelly okoseszközök kapcsolgatásához a saját Wi‑Fi / LAN hálózatodon.

## Gyors indítás (ajánlott)

1. Klónozd / töltsd le a repo `shelly-panel` mappáját a **saját gépedre** (ugyanaz a Wi‑Fi, ahol a Shellyk vannak).
2. Windows: kattints a **`start.bat`**-ra.  
   Mac/Linux: `./start.sh` vagy `python3 server.py`
3. Megnyílik a böngésző: http://127.0.0.1:8787  
   Telefonról (ugyanaz a Wi‑Fi): `http://<a-gep-IP-je>:8787`

Python kell hozzá: https://www.python.org/downloads/  
(Windows telepítőnél pipáld be: *Add python.exe to PATH*.)

## Windows .exe

Ebből a Cloud / Linux környezetből **nem** tudok neked kész Windows `.exe`-t adni (az csak Windows gépen buildelhető).

A **saját Windows PC-den**, a `shelly-panel` mappában:

```bat
build_exe.bat
```

Kész fájl: `shelly-panel\dist\KAPCS.exe` — ezt már csak indítani kell (Python nélkül).

## Használat

1. Add meg egy Shelly **IP** címét, vagy **Hálózat keresése**.
2. Kapcsold BE/KI; redőnynél: Fel / Le / Stop.
3. A lista a böngészőben megmarad (`localStorage`).

Támogatott: Shelly Gen1 és Gen2+ (switch/relay, light, cover/roller).

## Miért kell a kis szerver?

A böngésző közvetlenül gyakran nem hívhatja a Shelly API-t (CORS). A `server.py` / `KAPCS.exe` kiszolgálja az oldalt és proxyzza a kéréseket.
