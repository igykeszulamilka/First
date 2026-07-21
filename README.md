# BT Multi Speaker

Linux program több Bluetooth hangszóró egyidejű lejátszásához.

## Telepítés

```bash
# Debian / Ubuntu
sudo apt install bluez pipewire pipewire-pulse wireplumber pulseaudio-utils ffmpeg

# Fedora
sudo dnf install bluez pipewire pipewire-pulseaudio pulseaudio-utils ffmpeg
```

## Használat

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

## Előfeltételek

1. A hangszórókat előbb párosítsd: `bluetoothctl` → `scan on` → `pair XX:XX:...` → `trust XX:XX:...`
2. A hangszóróknak **A2DP** (zene) profilt kell használniuk, nem csak handsfree-t.
3. A Bluetooth adapternek támogatnia kell több egyidejű A2DP kapcsolatot (sok adapter csak 1-et tud).

## Korlátok

- A Bluetooth késleltetés miatt a hangszórók **nem lesznek tökéletesen szinkronban** (100–300 ms eltérés gyakori).
- Ez nem ugyanaz, mint a Sonos-szerű multi-room rendszer; szoftveres összevonás PulseAudio/PipeWire szinten történik.
