# BT Multi Speaker

Program több Bluetooth hangszóró egyidejű lejátszásához — **Linux** és **Windows** verzióval.

---

## Windows

### Telepítés

```powershell
pip install -r requirements-windows.txt
```

### Használat

```powershell
# Hangkimenetek listázása (Bluetooth hangszórók is)
python bt_multi_speaker_win.py list

# Interaktív: válaszd ki a hangszórókat + teszthang
python bt_multi_speaker_win.py play --test-tone

# Konkrét eszköz indexekkel
python bt_multi_speaker_win.py play --device 4,7 --test-tone

# Név alapján + zene fájl
python bt_multi_speaker_win.py play --name "JBL","Sony" --file zenekar.wav
```

### Előfeltételek (Windows)

1. Párosítsd a hangszórókat: **Beállítások → Bluetooth és eszközök → Eszköz hozzáadása**
2. Kapcsold be mindegyiket — meg kell jelenniük hangkimenetként
3. A program **fájlokat és teszthangot** tud egyszerre küldeni minden kiválasztott eszközre

### Windows korlátok

- A **rendszerhang** (Spotify, YouTube, böngésző) nem megy automatikusan minden hangszóróra. Ehhez használj virtuális keverőt, pl. **VoiceMeeter Banana** (ingyenes).
- A BT hangszórók **nem lesznek tökéletesen szinkronban** (késleltetés miatt).
- Egyes laptopok BT adaptere csak **1 aktív A2DP** kapcsolatot bír.

---

## Linux

### Telepítés

```bash
# Debian / Ubuntu
sudo apt install bluez pipewire pipewire-pulse wireplumber pulseaudio-utils ffmpeg

# Fedora
sudo dnf install bluez pipewire pipewire-pulseaudio pulseaudio-utils ffmpeg
```

### Használat

```bash
# Eszközök listázása
python3 bt_multi_speaker.py list

# Interaktív csatlakozás (válaszd ki a hangszórókat)
python3 bt_multi_speaker.py connect

# Konkrét MAC címekkel + teszthang
python3 bt_multi_speaker.py connect --mac AA:BB:CC:DD:EE:01,AA:BB:CC:DD:EE:02 --test-tone

# Zene lejátszása minden hangszórón
python3 bt_multi_speaker.py connect --all-paired --play zenekar.wav

# Összevont kimenet eltávolítása
python3 bt_multi_speaker.py disconnect
```

### Előfeltételek (Linux)

1. A hangszórókat előbb párosítsd: `bluetoothctl` → `scan on` → `pair XX:XX:...` → `trust XX:XX:...`
2. A hangszóróknak **A2DP** (zene) profilt kell használniuk, nem csak handsfree-t.
3. A Bluetooth adapternek támogatnia kell több egyidejű A2DP kapcsolatot (sok adapter csak 1-et tud).

### Linux korlátok

- A Bluetooth késleltetés miatt a hangszórók **nem lesznek tökéletesen szinkronban** (100–300 ms eltérés gyakori).
- Ez nem ugyanaz, mint a Sonos-szerű multi-room rendszer; szoftveres összevonás PulseAudio/PipeWire szinten történik.
