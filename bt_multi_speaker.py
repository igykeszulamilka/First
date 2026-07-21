#!/usr/bin/env python3
"""
Több Bluetooth hangszóró egyidejű lejátszása Linuxon.

A program:
  1. Csatlakoztatja a kiválasztott BT hangszórókat (bluetoothctl)
  2. Létrehoz egy virtuális „összevont” kimenetet (PulseAudio / PipeWire)
  3. Oda irányítja a hangot, így minden csatlakoztatott eszköz egyszerre szól

Függőségek: bluez (bluetoothctl), pipewire-pulse VAGY pulseaudio, pactl, paplay
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable


COMBINED_SINK_NAME = "bt_multi_combined"


@dataclass(frozen=True)
class BluetoothDevice:
    mac: str
    name: str
    paired: bool
    connected: bool


@dataclass(frozen=True)
class AudioSink:
    name: str
    description: str


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        print(f"Hiba: a '{name}' parancs nem található. Telepítsd a szükséges csomagot.", file=sys.stderr)
        sys.exit(1)
    return path


def run(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def run_bluetoothctl(commands: Iterable[str]) -> str:
    script = "\n".join(commands) + "\n"
    result = run(["bluetoothctl"], input_text=script)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "bluetoothctl hiba")
    return result.stdout


def list_bluetooth_devices() -> list[BluetoothDevice]:
    output = run_bluetoothctl(["devices"])
    devices: list[BluetoothDevice] = []
    for line in output.splitlines():
        match = re.match(r"Device\s+([0-9A-F:]{17})\s+(.+)$", line.strip(), re.IGNORECASE)
        if not match:
            continue
        mac, name = match.group(1), match.group(2)
        info = run_bluetoothctl([f"info {mac}"])
        paired = "Paired: yes" in info
        connected = "Connected: yes" in info
        devices.append(BluetoothDevice(mac=mac, name=name, paired=paired, connected=connected))
    return devices


def connect_device(mac: str) -> None:
    print(f"  Csatlakozás: {mac} ...")
    output = run_bluetoothctl(
        [
            "power on",
            "agent on",
            "default-agent",
            f"connect {mac}",
        ]
    )
    if "Failed to connect" in output or "not available" in output.lower():
        raise RuntimeError(f"Nem sikerült csatlakozni: {mac}\n{output}")
    time.sleep(2)


def wait_for_sink(mac: str, timeout_sec: float = 20.0) -> AudioSink | None:
    mac_key = mac.replace(":", "_")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        for sink in list_audio_sinks():
            if "bluez_output" in sink.name and mac_key.lower() in sink.name.lower():
                return sink
        time.sleep(0.5)
    return None


def list_audio_sinks() -> list[AudioSink]:
    result = run(["pactl", "list", "short", "sinks"])
    sinks: list[AudioSink] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        index, name = parts[0], parts[1]
        description = parts[-1] if len(parts) >= 4 else name
        sinks.append(AudioSink(name=name, description=description))
        _ = index
    return sinks


def list_bluetooth_sinks() -> list[AudioSink]:
    return [sink for sink in list_audio_sinks() if sink.name.startswith("bluez_output.")]


def unload_combined_sink() -> None:
    result = run(["pactl", "list", "short", "modules"], check=False)
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        module_id, module_name = parts[0], parts[1]
        if module_name != "module-combine-sink":
            continue
        details = run(["pactl", "list", "modules", module_id], check=False).stdout
        if f'sink_name="{COMBINED_SINK_NAME}"' in details or f"sink_name={COMBINED_SINK_NAME}" in details:
            run(["pactl", "unload-module", module_id], check=False)


def create_combined_sink(sink_names: list[str]) -> None:
    if len(sink_names) < 2:
        raise ValueError("Legalább 2 hangszóró kell az egyidejű lejátszáshoz.")

    unload_combined_sink()
    slaves = ",".join(sink_names)
    result = run(
        [
            "pactl",
            "load-module",
            "module-combine-sink",
            f"sink_name={COMBINED_SINK_NAME}",
            f"slaves={slaves}",
            f'sink_properties=device.description="BT Multi Speaker"',
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Nem sikerült létrehozni az összevont kimenetet.\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def set_default_sink(name: str) -> None:
    run(["pactl", "set-default-sink", name])


def play_file(path: str) -> None:
    run(["paplay", path])


def play_test_tone() -> None:
    require_command("ffmpeg")
    tone = subprocess.check_output(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-f",
            "wav",
            "pipe:1",
        ]
    )
    proc = subprocess.Popen(
        ["paplay"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    proc.stdin.write(tone)
    proc.stdin.close()
    if proc.wait() != 0:
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(f"Teszthang lejátszása sikertelen: {err}")


def choose_devices_interactive(devices: list[BluetoothDevice]) -> list[BluetoothDevice]:
    if not devices:
        print("Nincs párosított Bluetooth eszköz.")
        print("Párosítsd a hangszórókat előbb: bluetoothctl → scan on → pair XX:XX:... → trust XX:XX:...")
        sys.exit(1)

    print("\nElérhető Bluetooth eszközök:")
    for i, dev in enumerate(devices, start=1):
        status = []
        if dev.paired:
            status.append("párosítva")
        if dev.connected:
            status.append("csatlakozva")
        status_text = f" ({', '.join(status)})" if status else ""
        print(f"  [{i}] {dev.name} — {dev.mac}{status_text}")

    print("\nAdd meg a számokat vesszővel (pl. 1,2,3), vagy 'all' az összeshez:")
    choice = input("> ").strip().lower()
    if choice == "all":
        return devices

    selected: list[BluetoothDevice] = []
    for part in choice.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        idx = int(part) - 1
        if 0 <= idx < len(devices):
            selected.append(devices[idx])
    if not selected:
        print("Nem választottál érvényes eszközt.", file=sys.stderr)
        sys.exit(1)
    return selected


def parse_mac_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    macs: list[str] = []
    for value in values:
        macs.extend(part.strip() for part in value.split(",") if part.strip())
    return macs or None


def find_devices_by_mac(devices: list[BluetoothDevice], macs: list[str]) -> list[BluetoothDevice]:
    by_mac = {d.mac.upper(): d for d in devices}
    selected: list[BluetoothDevice] = []
    for mac in macs:
        normalized = mac.upper()
        if normalized not in by_mac:
            print(f"Figyelmeztetés: ismeretlen MAC: {mac}", file=sys.stderr)
            continue
        selected.append(by_mac[normalized])
    return selected


def cmd_list(_: argparse.Namespace) -> None:
    print("=== Bluetooth eszközök ===")
    for dev in list_bluetooth_devices():
        flags = []
        if dev.paired:
            flags.append("párosítva")
        if dev.connected:
            flags.append("csatlakozva")
        print(f"{dev.mac}  {dev.name}  [{', '.join(flags) or '—'}]")

    print("\n=== Bluetooth audio kimenetek (pactl) ===")
    sinks = list_bluetooth_sinks()
    if not sinks:
        print("(nincs aktív bluez_output sink – csatlakoztasd a hangszórókat)")
    for sink in sinks:
        print(f"{sink.name}  —  {sink.description}")


def cmd_connect(args: argparse.Namespace) -> None:
    require_command("bluetoothctl")
    require_command("pactl")
    require_command("paplay")

    devices = list_bluetooth_devices()
    macs = parse_mac_list(args.mac)
    if macs:
        selected = find_devices_by_mac(devices, macs)
    elif args.all_paired:
        selected = [d for d in devices if d.paired]
    else:
        selected = choose_devices_interactive(devices)

    if len(selected) < 2 and not args.allow_single:
        print("Legalább 2 hangszórót válassz. Egy esetén használd a --allow-single kapcsolót.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{len(selected)} hangszóró csatlakoztatása...")
    sinks: list[AudioSink] = []

    for dev in selected:
        if not dev.connected:
            connect_device(dev.mac)
        sink = wait_for_sink(dev.mac)
        if sink is None:
            print(f"  Figyelmeztetés: nem jelent meg audio sink ehhez: {dev.name} ({dev.mac})", file=sys.stderr)
            continue
        print(f"  ✓ {dev.name} → {sink.name}")
        sinks.append(sink)

    if len(sinks) < 2 and not args.allow_single:
        print("\nHiba: kevesebb mint 2 hangszóró audio kimenete érhető el.", file=sys.stderr)
        print("Ellenőrizd, hogy A2DP profillal csatlakoznak-e (ne HFP/handsfree).", file=sys.stderr)
        sys.exit(1)

    if len(sinks) >= 2:
        print("\nÖsszevont kimenet létrehozása...")
        create_combined_sink([s.name for s in sinks])
        set_default_sink(COMBINED_SINK_NAME)
        print(f"Alapértelmezett kimenet: {COMBINED_SINK_NAME}")
    elif sinks:
        set_default_sink(sinks[0].name)
        print(f"Alapértelmezett kimenet: {sinks[0].name}")

    if args.play:
        print(f"\nLejátszás: {args.play}")
        play_file(args.play)
    elif args.test_tone:
        print("\nTeszthang lejátszása (440 Hz, 2 mp)...")
        play_test_tone()
    else:
        print("\nKész. Mostantól minden rendszerhang erre a kimenetre megy.")
        print("Lejátszáshoz: paplay zene.wav   vagy   python3 bt_multi_speaker.py connect --test-tone")


def cmd_disconnect(_: argparse.Namespace) -> None:
    require_command("pactl")
    unload_combined_sink()
    print("Összevont kimenet eltávolítva.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Több Bluetooth hangszóró egyidejű lejátszása Linuxon.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Példák:
  python3 bt_multi_speaker.py list
  python3 bt_multi_speaker.py connect
  python3 bt_multi_speaker.py connect --mac AA:BB:CC:DD:EE:01,AA:BB:CC:DD:EE:02 --test-tone
  python3 bt_multi_speaker.py connect --all-paired --play zenekar.wav
  python3 bt_multi_speaker.py disconnect

Megjegyzés: a Bluetooth késleltetés miatt a hangszórók nem lesznek tökéletesen szinkronban.
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="Bluetooth eszközök és audio kimenetek listázása")
    list_parser.set_defaults(func=cmd_list)

    connect_parser = sub.add_parser("connect", help="Csatlakozás és egyidejű lejátszás beállítása")
    connect_parser.add_argument("--mac", action="append", help="MAC cím(ek), vesszővel elválasztva")
    connect_parser.add_argument("--all-paired", action="store_true", help="Minden párosított eszköz")
    connect_parser.add_argument("--allow-single", action="store_true", help="Egy hangszóró is elég")
    connect_parser.add_argument("--play", metavar="FILE", help="WAV/FLAC fájl lejátszása")
    connect_parser.add_argument("--test-tone", action="store_true", help="440 Hz teszthang")
    connect_parser.set_defaults(func=cmd_connect)

    disconnect_parser = sub.add_parser("disconnect", help="Összevont kimenet eltávolítása")
    disconnect_parser.set_defaults(func=cmd_disconnect)

    return parser


def main() -> None:
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
