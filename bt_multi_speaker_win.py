#!/usr/bin/env python3
"""
Több Bluetooth hangszóró egyidejű lejátszása Windows-on.

Windows nem tud natívan egy „összevont” BT kimenetet létrehozni (mint Linux),
ezért ez a program ugyanazt a hangfájlt egyszerre küldi ki több eszközre
(WASAPI / sounddevice), mindegyik külön streamen.

Előfeltétel: a hangszórókat párosítsd a Windows Beállítások → Bluetooth menüben,
és csatlakoztasd őket (mindegyik megjelenik hangkimenetként).

Telepítés:
  pip install sounddevice numpy soundfile

Opcionális teszthanghoz csak numpy kell; fájllejátszáshoz soundfile.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
from dataclasses import dataclass

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    print(
        "Hiányzó csomagok. Telepítsd:\n  pip install sounddevice numpy soundfile",
        file=sys.stderr,
    )
    sys.exit(1)


@dataclass(frozen=True)
class OutputDevice:
    index: int
    name: str
    hostapi: str
    max_output_channels: int

    @property
    def is_bluetooth(self) -> bool:
        lowered = self.name.lower()
        return "bluetooth" in lowered or "bt " in lowered or lowered.startswith("bt-")


def query_devices() -> list[OutputDevice]:
    hostapis = {i: api["name"] for i, api in enumerate(sd.query_hostapis())}
    outputs: list[OutputDevice] = []
    for dev in sd.query_devices():
        if dev["max_output_channels"] < 1:
            continue
        outputs.append(
            OutputDevice(
                index=int(dev["index"]),
                name=str(dev["name"]),
                hostapi=hostapis.get(dev["hostapi"], "?"),
                max_output_channels=int(dev["max_output_channels"]),
            )
        )
    return outputs


def list_paired_bluetooth_speakers() -> list[str]:
    """Párosított Bluetooth hangeszközök nevei PowerShell-lel (ha elérhető)."""
    ps_script = r"""
$devices = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
    Where-Object { $_.Status -eq 'OK' -and $_.FriendlyName -notmatch 'Enumerator|Service|Adapter|RFCOMM|AG Audio|Hands-Free' }
$devices | ForEach-Object { $_.FriendlyName }
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names


def choose_devices_interactive(devices: list[OutputDevice], bluetooth_only: bool) -> list[OutputDevice]:
    candidates = [d for d in devices if d.is_bluetooth] if bluetooth_only else devices
    if not candidates:
        print("Nincs megfelelő hangkimenet.")
        if bluetooth_only:
            print("Tipp: csatlakoztasd a BT hangszórókat a Windows Beállításokban.")
            print("      Ha mégis minden eszközt látni akarsz, használd a --all-devices kapcsolót.")
        sys.exit(1)

    print("\nElérhető hangkimenetek:")
    for i, dev in enumerate(candidates, start=1):
        tag = " [Bluetooth]" if dev.is_bluetooth else ""
        print(f"  [{i}] {dev.name}{tag}")
        print(f"       index={dev.index}, csatornák={dev.max_output_channels}, API={dev.hostapi}")

    paired = list_paired_bluetooth_speakers()
    if paired:
        print("\nPárosított Bluetooth eszközök (rendszer):")
        for name in paired:
            print(f"  - {name}")

    print("\nAdd meg a számokat vesszővel (pl. 1,2,3), vagy 'all' az összeshez:")
    choice = input("> ").strip().lower()
    if choice == "all":
        return candidates

    selected: list[OutputDevice] = []
    for part in choice.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        idx = int(part) - 1
        if 0 <= idx < len(candidates):
            selected.append(candidates[idx])
    if not selected:
        print("Nem választottál érvényes eszközt.", file=sys.stderr)
        sys.exit(1)
    return selected


def parse_device_indices(values: list[str] | None) -> list[int] | None:
    if not values:
        return None
    indices: list[int] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part.isdigit():
                indices.append(int(part))
    return indices or None


def resolve_devices(
    devices: list[OutputDevice],
    indices: list[int] | None,
    names: list[str] | None,
    bluetooth_only: bool,
    all_devices_flag: bool,
) -> list[OutputDevice]:
    candidates = devices if all_devices_flag or not bluetooth_only else [d for d in devices if d.is_bluetooth]

    if indices:
        by_index = {d.index: d for d in devices}
        resolved = []
        for idx in indices:
            if idx not in by_index:
                print(f"Figyelmeztetés: nincs ilyen index: {idx}", file=sys.stderr)
                continue
            resolved.append(by_index[idx])
        return resolved

    if names:
        resolved = []
        for query in names:
            query_lower = query.lower()
            matches = [d for d in candidates if query_lower in d.name.lower()]
            if not matches:
                print(f"Figyelmeztetés: nincs találat: {query}", file=sys.stderr)
                continue
            resolved.append(matches[0])
        return resolved

    return choose_devices_interactive(candidates, bluetooth_only=bluetooth_only and not all_devices_flag)


def load_audio(path: str) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf
    except ImportError:
        print("A fájllejátszáshoz telepítsd: pip install soundfile", file=sys.stderr)
        sys.exit(1)

    data, samplerate = sf.read(path, always_2d=True, dtype="float32")
    return data, int(samplerate)


def make_test_tone(duration_sec: float = 2.0, samplerate: int = 48000, frequency: float = 440.0) -> tuple[np.ndarray, int]:
    t = np.linspace(0, duration_sec, int(samplerate * duration_sec), endpoint=False, dtype=np.float32)
    mono = (0.2 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
    stereo = np.column_stack([mono, mono])
    return stereo, samplerate


def fit_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    if audio.shape[1] == channels:
        return audio
    if channels == 1:
        return np.mean(audio, axis=1, keepdims=True).astype(np.float32)
    if audio.shape[1] == 1 and channels >= 2:
        return np.repeat(audio, channels, axis=1)
    if audio.shape[1] > channels:
        return audio[:, :channels]
    pad = np.zeros((audio.shape[0], channels - audio.shape[1]), dtype=np.float32)
    return np.concatenate([audio, pad], axis=1)


def play_on_device(device: OutputDevice, audio: np.ndarray, samplerate: int) -> None:
    channels = min(2, device.max_output_channels) or 1
    chunk = fit_channels(audio, channels)

    extra = None
    if sys.platform == "win32":
        try:
            extra = sd.WasapiSettings(exclusive=False)
        except Exception:
            extra = None

    with sd.OutputStream(
        device=device.index,
        samplerate=samplerate,
        channels=channels,
        dtype="float32",
        extra_settings=extra,
    ) as stream:
        block = 2048
        for start in range(0, len(chunk), block):
            stream.write(chunk[start : start + block])


def play_simultaneous(devices: list[OutputDevice], audio: np.ndarray, samplerate: int) -> None:
    if len(devices) < 1:
        raise ValueError("Legalább egy hangkimenet kell.")

    errors: list[str] = []

    def worker(dev: OutputDevice) -> None:
        try:
            play_on_device(dev, audio, samplerate)
        except Exception as exc:  # noqa: BLE001 — felhasználóbarát összegzés
            errors.append(f"{dev.name}: {exc}")

    threads = [threading.Thread(target=worker, args=(dev,), name=f"play-{dev.index}") for dev in devices]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if errors:
        raise RuntimeError("Lejátszási hibák:\n" + "\n".join(f"  - {e}" for e in errors))


def cmd_list(args: argparse.Namespace) -> None:
    devices = query_devices()
    print("=== Hangkimenetek (sounddevice) ===")
    for dev in devices:
        tag = " [Bluetooth]" if dev.is_bluetooth else ""
        print(f"[{dev.index}] {dev.name}{tag}")
        print(f"     API={dev.hostapi}, csatornák={dev.max_output_channels}")

    if not args.skip_bt:
        paired = list_paired_bluetooth_speakers()
        if paired:
            print("\n=== Párosított Bluetooth eszközök ===")
            for name in paired:
                print(f"  - {name}")


def cmd_play(args: argparse.Namespace) -> None:
    devices = query_devices()
    indices = parse_device_indices(args.device)
    selected = resolve_devices(
        devices,
        indices=indices,
        names=args.name,
        bluetooth_only=not args.all_devices,
        all_devices_flag=args.all_devices,
    )

    if len(selected) < 2 and not args.allow_single:
        print("Legalább 2 hangszórót válassz, vagy használd a --allow-single kapcsolót.", file=sys.stderr)
        sys.exit(1)

    print(f"\nLejátszás {len(selected)} eszközre:")
    for dev in selected:
        print(f"  → [{dev.index}] {dev.name}")

    if args.test_tone:
        audio, samplerate = make_test_tone()
    elif args.file:
        audio, samplerate = load_audio(args.file)
    else:
        print("Adj meg --test-tone vagy --file argumentumot.", file=sys.stderr)
        sys.exit(1)

    print("\nIndítás...")
    play_simultaneous(selected, audio, samplerate)
    print("Kész.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Több Bluetooth hangszóró egyidejű lejátszása Windows-on.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Példák:
  python bt_multi_speaker_win.py list
  python bt_multi_speaker_win.py play --test-tone
  python bt_multi_speaker_win.py play --device 4,7 --test-tone
  python bt_multi_speaker_win.py play --name "JBL","Sony" --file zene.wav
  python bt_multi_speaker_win.py play --all-devices --test-tone

Megjegyzés:
  - A hangszórókat előbb párosítsd: Beállítások → Bluetooth → Eszköz hozzáadása
  - A BT késleltetés miatt a hangszórók nem lesznek tökéletesen szinkronban
  - Rendszerhang (Spotify, YouTube) minden eszközre: használj VoiceMeeter Banana-t
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="Hangkimenetek listázása")
    list_parser.add_argument("--skip-bt", action="store_true", help="Ne kérdezze le a BT eszközöket")
    list_parser.set_defaults(func=cmd_list)

    play_parser = sub.add_parser("play", help="Hang lejátszása több eszközre egyszerre")
    play_parser.add_argument("--device", action="append", help="Eszköz index(ek), vesszővel")
    play_parser.add_argument("--name", action="append", help="Eszköz név részlet (pl. JBL)")
    play_parser.add_argument("--all-devices", action="store_true", help="Ne csak Bluetoothot mutasson")
    play_parser.add_argument("--allow-single", action="store_true", help="Egy eszköz is elég")
    play_parser.add_argument("--test-tone", action="store_true", help="440 Hz teszthang (2 mp)")
    play_parser.add_argument("--file", metavar="FILE", help="WAV/FLAC/OGG fájl")
    play_parser.set_defaults(func=cmd_play)

    return parser


def main() -> None:
    if sys.platform != "win32":
        print(
            "Ez a script Windows-ra készült. Linuxon használd: python3 bt_multi_speaker.py",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        print(f"\nHiba: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nMegszakítva.")
        sys.exit(130)


if __name__ == "__main__":
    main()
