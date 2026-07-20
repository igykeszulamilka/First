# First — KAPCS (Shelly LAN panel)

Kis helyi HTML panel Shelly okoseszközök kapcsolgatásához a LAN-on.

## Indítás

A saját gépeden, ugyanazon a Wi‑Fi/LAN hálózaton, ahol a Shellyk vannak:

```bash
cd shelly-panel
python3 server.py
```

Nyisd meg: [http://127.0.0.1:8787](http://127.0.0.1:8787)

A kis Python szerver azért kell, mert a böngésző közvetlenül gyakran nem tudja hívni a Shelly HTTP API-t (CORS). A szerver proxyzza a kéréseket.

## Használat

1. Add meg egy Shelly **IP** címét (vagy indíts **Hálózat keresése**t `/24` tartománnyal).
2. Kapcsold BE/KI a kapcsolókat, redőnynél: Fel / Le / Stop.
3. A lista a böngésző `localStorage`-ében marad.

Támogatott: Shelly Gen1 (relé / light / roller) és Gen2+ (Switch / Light / Cover) RPC.

## Megjegyzés

Ezt a Cloud Agent környezetben csak a kódot tudjuk megírni — a valódi eszközökhöz a panelnek a **te otthoni gépeden** kell futnia.
