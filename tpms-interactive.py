#!/usr/bin/env python3
"""
BLE TPMS Monitor - Interactive Version

Discover, select, and monitor BLE tire pressure sensors
with a color-coded real-time display.

Usage:
    python tpms-interactive.py
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

# Optional color support
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

    class Fore:
        RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = WHITE = RESET = ""

    class Style:
        BRIGHT = DIM = RESET_ALL = ""

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from sensor_decoders import TPMSDecoderFactory

# Resolve paths relative to script location (not CWD)
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "tpms_config.json"

# Settings
SHOW_HEX_PACKETS = True
DEDUP_INTERVAL = 1.0  # Minimum seconds between updates per sensor

# State
decoder_factory = TPMSDecoderFactory()
monitored_sensors = {}
sensor_data = {}


# ── Helpers ──────────────────────────────────────────────────────────────

def clear_screen():
    """Clear terminal using ANSI escape."""
    print("\033[2J\033[H", end="", flush=True)


def print_header(text):
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{text:^60}")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")


def prompt(msg="Press Enter to continue..."):
    input(f"\n{Style.DIM}{msg}{Style.RESET_ALL}")


def get_status_color(status, battery):
    if status == 0xFF or battery < 2.5:
        return Fore.RED
    if status & 0x80:
        return Fore.RED
    if status & 0x40:
        return Fore.GREEN
    return Fore.WHITE


STATUS_FLAGS = [
    (0x80, "ALARM"), (0x40, "ROTAT"), (0x20, "STILL"), (0x10, "BGROT"),
    (0x08, "DECR2"), (0x04, "RISIN"), (0x02, "DECR1"),
]


def format_status_flags(status):
    if status == 0xFF:
        return "LBATT"
    flags = [label for mask, label in STATUS_FLAGS if status & mask]
    return " ".join(flags) if flags else "OK"


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to uppercase for consistent lookups."""
    return mac.upper()


# ── Config ───────────────────────────────────────────────────────────────

def save_config():
    config = {
        'sensors': monitored_sensors,
        'last_updated': datetime.now().isoformat(),
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"{Fore.GREEN}Configuration saved to {CONFIG_FILE.name}{Style.RESET_ALL}")


def load_config():
    global monitored_sensors
    if not CONFIG_FILE.exists():
        return
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        monitored_sensors = config.get('sensors', {})
        # Normalize stored MAC addresses
        monitored_sensors = {normalize_mac(k): v for k, v in monitored_sensors.items()}
        if monitored_sensors:
            print(f"{Fore.GREEN}Loaded {len(monitored_sensors)} sensor(s) from config{Style.RESET_ALL}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"{Fore.YELLOW}Could not load config: {e}{Style.RESET_ALL}")


# ── Decode ───────────────────────────────────────────────────────────────

def decode_sensor_data(device_name, service_uuids, mfdata):
    """Decode manufacturer data using the appropriate decoder."""
    decoder = decoder_factory.get_decoder(device_name, service_uuids, mfdata)
    result = decoder.decode(mfdata)
    if result:
        result['timestamp'] = time.time()
        result['device_name'] = device_name
    return result


# ── Discovery ────────────────────────────────────────────────────────────

async def discover_devices(duration=10):
    """Scan for nearby BLE devices and return results."""
    devices = {}

    print(f"{Fore.YELLOW}Scanning for BLE devices ({duration}s)...{Style.RESET_ALL}")

    def on_device(device: BLEDevice, adv: AdvertisementData):
        mac = normalize_mac(device.address)

        # Identify decoder type from manufacturer data
        decoder_name = "Unknown"
        if adv.manufacturer_data:
            mfdata = list(adv.manufacturer_data.values())[0]
            decoder = decoder_factory.get_decoder(
                device.name or "", adv.service_uuids or [], mfdata
            )
            decoder_name = decoder.name

        # Keep strongest signal per device
        if mac not in devices or adv.rssi > devices[mac]['rssi']:
            devices[mac] = {
                'name': device.name or "Unknown",
                'rssi': adv.rssi,
                'service_uuids': adv.service_uuids,
                'decoder': decoder_name,
            }

    try:
        scanner = BleakScanner(detection_callback=on_device)
        await scanner.start()
        await asyncio.sleep(duration)
        await scanner.stop()
    except Exception as e:
        print(f"{Fore.RED}BLE scan failed: {e}{Style.RESET_ALL}")
        print(f"{Style.DIM}Check that Bluetooth is enabled.{Style.RESET_ALL}")
        return {}

    print(f"{Fore.GREEN}Found {len(devices)} device(s){Style.RESET_ALL}\n")
    return devices


def display_discovered_devices(devices):
    """Print discovered devices table. Returns sorted list for selection."""
    if not devices:
        print(f"{Fore.RED}No devices found. Make sure Bluetooth is enabled.{Style.RESET_ALL}")
        return []

    print(f"{Fore.CYAN}{Style.BRIGHT}"
          f"{'#':<4} {'MAC Address':<20} {'Name':<20} {'RSSI':<6} {'Decoder':<15} {'TPMS?'}"
          f"{Style.RESET_ALL}")
    print("-" * 90)

    devices_list = sorted(devices.items())
    for idx, (mac, info) in enumerate(devices_list, 1):
        is_tpms = info['decoder'] not in ("Unknown", "Generic")
        indicator = ""
        if is_tpms:
            indicator = f"{Fore.GREEN}Yes ({info['decoder']}){Style.RESET_ALL}"
        elif info['decoder'] == "Generic":
            indicator = f"{Fore.YELLOW}? (Generic){Style.RESET_ALL}"

        color = Fore.GREEN if is_tpms else Fore.WHITE
        print(f"{color}{idx:<4} {mac:<20} {info['name'][:20]:<20} "
              f"{info['rssi']:<6} {info['decoder']:<15} {indicator}{Style.RESET_ALL}")

    return devices_list


def select_sensors(devices_list):
    """Interactive sensor selection from discovered devices."""
    global monitored_sensors

    if not devices_list:
        return

    print(f"\n{Fore.CYAN}Select sensors to monitor:{Style.RESET_ALL}")
    print("  Enter numbers separated by spaces (e.g., '1 2 3')")
    print("  Enter 'a' to auto-select all detected TPMS devices")
    print("  Enter 'q' to skip")

    choice = input(f"\n{Fore.YELLOW}Your selection: {Style.RESET_ALL}").strip().lower()

    if choice == 'q' or not choice:
        return

    indices = []
    if choice == 'a':
        indices = [
            i for i, (_, info) in enumerate(devices_list, 1)
            if info['decoder'] not in ("Unknown", "Generic")
        ]
        if not indices:
            print(f"{Fore.YELLOW}No TPMS sensors detected.{Style.RESET_ALL}")
            return
    else:
        try:
            indices = [int(x) for x in choice.split()]
        except ValueError:
            print(f"{Fore.RED}Invalid input.{Style.RESET_ALL}")
            return

    for idx in indices:
        if not (1 <= idx <= len(devices_list)):
            print(f"{Fore.RED}#{idx} out of range, skipping.{Style.RESET_ALL}")
            continue

        mac, info = devices_list[idx - 1]
        default_name = f"Sensor {len(monitored_sensors) + 1}"
        name = input(f"Name for {mac} [{default_name}]: ").strip() or default_name

        monitored_sensors[mac] = {
            'name': name,
            'added': datetime.now().isoformat(),
        }
        print(f"{Fore.GREEN}Added: {name} ({mac}){Style.RESET_ALL}")

    if monitored_sensors:
        save_config()


# ── Monitoring ───────────────────────────────────────────────────────────

def display_monitoring_ui():
    """Render the live monitoring display."""
    clear_screen()
    print_header("TPMS BLE Monitor - Live View")

    print(f"{Fore.CYAN}Sensors: {len(monitored_sensors)}    "
          f"Time: {datetime.now().strftime('%H:%M:%S')}{Style.RESET_ALL}\n")

    if not sensor_data:
        print(f"{Fore.YELLOW}Waiting for sensor data...{Style.RESET_ALL}")
        print(f"{Style.DIM}(Make sure sensors are pressurized and nearby){Style.RESET_ALL}")
        print(f"\n{Style.DIM}Press Ctrl+C to stop{Style.RESET_ALL}")
        return

    # Build header
    cols = f"{'Sensor':<15} {'Decoder':<12} {'Pressure':<22} {'Temp':<8} {'Batt':<8} {'Status':<15}"
    if SHOW_HEX_PACKETS:
        cols += f" {'HEX':<16}"
    cols += f" {'Age'}"

    print(f"{Fore.CYAN}{Style.BRIGHT}{cols}{Style.RESET_ALL}")
    print("-" * len(cols))

    for mac, data in sensor_data.items():
        name = monitored_sensors.get(mac, {}).get('name', mac[-8:])
        age = int(time.time() - data['timestamp'])
        color = get_status_color(data['status'], data['battery'])
        batt_color = Fore.RED if data['battery'] < 2.5 else Fore.GREEN
        decoder_color = Fore.YELLOW if data.get('decoder') == "Generic" else Fore.CYAN

        pressure = f"{data['pressure_bar']:>4.2f} bar ({data['pressure_psi']:>4.1f} psi)"
        status = format_status_flags(data['status'])
        if data.get('warning'):
            status += f" {Fore.RED}!{Style.RESET_ALL}"

        line = (f"{color}{name:<15} "
                f"{decoder_color}{data.get('decoder', '?'):<12}{color} "
                f"{pressure:<22} "
                f"{data['temperature']:>4}C   "
                f"{batt_color}{data['battery']:>4.1f}V{color}  "
                f"{status:<15}")

        if SHOW_HEX_PACKETS:
            line += f" {Fore.YELLOW}{data['hex_data']:<16}{color}"

        line += f" {Style.DIM}{age}s{Style.RESET_ALL}"
        print(line)

    print(f"\n{Style.DIM}Press Ctrl+C to stop{Style.RESET_ALL}")


async def monitor_sensors():
    """Live monitoring loop for selected sensors."""
    global sensor_data

    if not monitored_sensors:
        print(f"{Fore.RED}No sensors configured. Discover sensors first.{Style.RESET_ALL}")
        return

    monitored_macs = set(monitored_sensors.keys())
    last_update = {}  # MAC -> timestamp for deduplication

    def on_device(device: BLEDevice, adv: AdvertisementData):
        mac = normalize_mac(device.address)
        if mac not in monitored_macs:
            return
        if not adv.manufacturer_data:
            return

        # Deduplicate rapid callbacks
        now = time.time()
        if mac in last_update and (now - last_update[mac]) < DEDUP_INTERVAL:
            return
        last_update[mac] = now

        for company_id, mfdata in adv.manufacturer_data.items():
            data = decode_sensor_data(
                device.name or "", adv.service_uuids or [], mfdata
            )
            if data:
                sensor_data[mac] = data
                display_monitoring_ui()

    try:
        scanner = BleakScanner(detection_callback=on_device)
        await scanner.start()
    except Exception as e:
        print(f"{Fore.RED}BLE scan failed: {e}{Style.RESET_ALL}")
        return

    try:
        while True:
            await asyncio.sleep(5)
            display_monitoring_ui()
    except KeyboardInterrupt:
        pass
    finally:
        await scanner.stop()
        print(f"\n{Fore.YELLOW}Monitoring stopped.{Style.RESET_ALL}")


# ── Menu ─────────────────────────────────────────────────────────────────

async def main_menu():
    while True:
        clear_screen()
        print_header("BLE TPMS Monitor")

        # Show configured sensors
        print(f"{Fore.CYAN}Configured Sensors:{Style.RESET_ALL}")
        if monitored_sensors:
            for mac, info in monitored_sensors.items():
                print(f"  {Fore.GREEN}*{Style.RESET_ALL} {info['name']:<20} ({mac})")
        else:
            print(f"  {Fore.YELLOW}None - use option 1 to discover{Style.RESET_ALL}")

        # Menu options
        print(f"\n{Fore.CYAN}Options:{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}1{Style.RESET_ALL} - Discover and select sensors")
        print(f"  {Fore.GREEN}2{Style.RESET_ALL} - Start monitoring")
        print(f"  {Fore.GREEN}3{Style.RESET_ALL} - Remove a sensor")
        print(f"  {Fore.GREEN}4{Style.RESET_ALL} - Clear all sensors")
        print(f"  {Fore.GREEN}5{Style.RESET_ALL} - List available decoders")
        print(f"  {Fore.GREEN}q{Style.RESET_ALL} - Quit")

        choice = input(f"\n{Fore.YELLOW}Select option: {Style.RESET_ALL}").strip().lower()

        if choice == '1':
            devices = await discover_devices(duration=10)
            devices_list = display_discovered_devices(devices)
            select_sensors(devices_list)
            prompt()

        elif choice == '2':
            if monitored_sensors:
                await monitor_sensors()
            else:
                print(f"\n{Fore.RED}No sensors configured. Use option 1 first.{Style.RESET_ALL}")
            prompt()

        elif choice == '3':
            if not monitored_sensors:
                print(f"\n{Fore.YELLOW}No sensors to remove.{Style.RESET_ALL}")
                prompt()
                continue

            print(f"\n{Fore.CYAN}Select sensor to remove:{Style.RESET_ALL}")
            items = list(monitored_sensors.items())
            for idx, (mac, info) in enumerate(items, 1):
                print(f"  {idx}. {info['name']} ({mac})")

            raw = input(f"\n{Fore.YELLOW}Enter number (0 to cancel): {Style.RESET_ALL}").strip()
            try:
                idx = int(raw)
                if 1 <= idx <= len(items):
                    mac, info = items[idx - 1]
                    del monitored_sensors[mac]
                    save_config()
                    print(f"{Fore.GREEN}Removed: {info['name']}{Style.RESET_ALL}")
            except (ValueError, IndexError):
                if raw != '0':
                    print(f"{Fore.RED}Invalid selection.{Style.RESET_ALL}")
            prompt()

        elif choice == '4':
            if not monitored_sensors:
                print(f"\n{Fore.YELLOW}No sensors to clear.{Style.RESET_ALL}")
                prompt()
                continue

            confirm = input(f"\n{Fore.RED}Clear all sensors? (yes/no): {Style.RESET_ALL}").strip().lower()
            if confirm == 'yes':
                monitored_sensors.clear()
                sensor_data.clear()
                save_config()
                print(f"{Fore.GREEN}All sensors cleared.{Style.RESET_ALL}")
            prompt()

        elif choice == '5':
            print(f"\n{Fore.CYAN}Available Decoders:{Style.RESET_ALL}")
            for name, manufacturer in decoder_factory.list_decoders():
                print(f"  {Fore.GREEN}*{Style.RESET_ALL} {name:<20} ({manufacturer})")
            prompt()

        elif choice == 'q':
            print(f"\n{Fore.CYAN}Goodbye!{Style.RESET_ALL}\n")
            break


# ── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    load_config()

    if not HAS_COLOR:
        print("Tip: Install 'colorama' for colored output: pip install colorama\n")

    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Goodbye!{Style.RESET_ALL}\n")
