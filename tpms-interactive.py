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
from sensor_decoders import TPMSDecoderFactory, TPMS3Decoder

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
packet_stats = {}    # MAC -> {'count': int, 'timestamps': list, 'history': list}


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
    # Pass device_name to decoders that use it (e.g., TPMS3 for position)
    if isinstance(decoder, TPMS3Decoder):
        result = decoder.decode(mfdata, device_name=device_name)
    else:
        result = decoder.decode(mfdata)
    if result:
        result['timestamp'] = time.time()
        result['device_name'] = device_name
    return result


# ── Discovery ────────────────────────────────────────────────────────────

async def discover_devices(round_duration=5):
    """Live BLE discovery in 5-second rounds. Shows devices as they appear."""
    devices = {}
    last_count = 0

    def _print_table():
        """Redraw the device table."""
        clear_screen()
        tpms_count = sum(
            1 for d in devices.values()
            if d['decoder'] not in ("Unknown", "Generic")
        )
        configured_macs = set(monitored_sensors.keys())

        print(f"{Fore.CYAN}{Style.BRIGHT}BLE Device Discovery{Style.RESET_ALL}"
              f"  |  {Fore.GREEN}{len(devices)} found{Style.RESET_ALL}"
              f"  |  {Fore.GREEN}{tpms_count} TPMS{Style.RESET_ALL}\n")

        print(f"{Fore.CYAN}{Style.BRIGHT}"
              f"{'#':<4} {'MAC Address':<20} {'Name':<20} {'RSSI':<6} "
              f"{'Decoder':<18} {'TPMS?'}"
              f"{Style.RESET_ALL}")
        print("-" * 95)

        devices_list = sorted(devices.items())
        for idx, (mac, info) in enumerate(devices_list, 1):
            is_tpms = info['decoder'] not in ("Unknown", "Generic")
            indicator = ""
            if mac in configured_macs:
                indicator = f"{Fore.BLUE}[configured]{Style.RESET_ALL}"
            elif is_tpms:
                indicator = f"{Fore.GREEN}Yes ({info['decoder']}){Style.RESET_ALL}"
            elif info['decoder'] == "Generic":
                indicator = f"{Fore.YELLOW}? (Generic){Style.RESET_ALL}"

            color = Fore.GREEN if is_tpms else Fore.WHITE
            print(f"{color}{idx:<4} {mac:<20} {info['name'][:20]:<20} "
                  f"{info['rssi']:<6} {info['decoder']:<18} {indicator}"
                  f"{Style.RESET_ALL}")

    def on_device(device: BLEDevice, adv: AdvertisementData):
        nonlocal last_count
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
        is_new = mac not in devices
        if is_new or adv.rssi > devices[mac]['rssi']:
            devices[mac] = {
                'name': device.name or "Unknown",
                'rssi': adv.rssi,
                'service_uuids': adv.service_uuids,
                'decoder': decoder_name,
            }

        # Live refresh when new devices appear
        if is_new and len(devices) != last_count:
            last_count = len(devices)
            _print_table()

    try:
        scanner = BleakScanner(detection_callback=on_device)
        await scanner.start()

        # Scan in rounds
        keep_scanning = True
        while keep_scanning:
            _print_table()
            print(f"\n{Style.DIM}Scanning ({round_duration}s round)...{Style.RESET_ALL}",
                  end="", flush=True)

            await asyncio.sleep(round_duration)
            _print_table()

            print(f"\n{Fore.YELLOW}Continue scanning? "
                  f"[Enter]=5s more  [s]=select now  [q]=cancel{Style.RESET_ALL}",
                  end=" ", flush=True)

            # Non-blocking input
            choice = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input().strip().lower()
            )
            if choice == 's':
                keep_scanning = False
            elif choice == 'q':
                await scanner.stop()
                return {}
            # Enter or anything else = scan another 5s round

        await scanner.stop()
    except Exception as e:
        print(f"\n{Fore.RED}BLE scan failed: {e}{Style.RESET_ALL}")
        print(f"{Style.DIM}Check that Bluetooth is enabled.{Style.RESET_ALL}")
        return {}

    return devices


def display_discovered_devices(devices):
    """Print final discovered devices table. Returns sorted list for selection."""
    if not devices:
        print(f"{Fore.RED}No devices found. Make sure Bluetooth is enabled.{Style.RESET_ALL}")
        return []

    configured_macs = set(monitored_sensors.keys())
    tpms_count = sum(
        1 for d in devices.values()
        if d['decoder'] not in ("Unknown", "Generic")
    )

    print(f"\n{Fore.GREEN}{Style.BRIGHT}Scan complete: "
          f"{len(devices)} devices, {tpms_count} TPMS{Style.RESET_ALL}\n")

    print(f"{Fore.CYAN}{Style.BRIGHT}"
          f"{'#':<4} {'MAC Address':<20} {'Name':<20} {'RSSI':<6} "
          f"{'Decoder':<18} {'TPMS?'}"
          f"{Style.RESET_ALL}")
    print("-" * 95)

    devices_list = sorted(devices.items())
    for idx, (mac, info) in enumerate(devices_list, 1):
        is_tpms = info['decoder'] not in ("Unknown", "Generic")
        indicator = ""
        if mac in configured_macs:
            indicator = f"{Fore.BLUE}[configured]{Style.RESET_ALL}"
        elif is_tpms:
            indicator = f"{Fore.GREEN}Yes ({info['decoder']}){Style.RESET_ALL}"
        elif info['decoder'] == "Generic":
            indicator = f"{Fore.YELLOW}? (Generic){Style.RESET_ALL}"

        color = Fore.GREEN if is_tpms else Fore.WHITE
        print(f"{color}{idx:<4} {mac:<20} {info['name'][:20]:<20} "
              f"{info['rssi']:<6} {info['decoder']:<18} {indicator}"
              f"{Style.RESET_ALL}")

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

def display_monitoring_ui(monitor_start=None):
    """Render the live monitoring display with packet stats and history."""
    clear_screen()
    print_header("TPMS BLE Monitor - Live View")

    now = time.time()
    elapsed = int(now - monitor_start) if monitor_start else 0
    elapsed_str = f"{elapsed // 60}m {elapsed % 60:02d}s" if elapsed >= 60 else f"{elapsed}s"

    # Total packets across all sensors
    total_pkts = sum(s['count'] for s in packet_stats.values())

    print(f"{Fore.CYAN}Sensors: {len(monitored_sensors)}    "
          f"Time: {datetime.now().strftime('%H:%M:%S')}    "
          f"Elapsed: {elapsed_str}    "
          f"Total packets: {total_pkts}{Style.RESET_ALL}\n")

    if not sensor_data:
        print(f"{Fore.YELLOW}Waiting for sensor data...{Style.RESET_ALL}")
        print(f"{Style.DIM}(Make sure sensors are pressurized and nearby){Style.RESET_ALL}")
        print(f"\n{Style.DIM}Press Ctrl+C to stop{Style.RESET_ALL}")
        return

    # ── Current readings table ──
    cols = (f"{'Sensor':<15} {'Decoder':<14} {'Pressure':<22} "
            f"{'Temp':<6} {'Batt':<7} {'Pkts':<6} {'Pkt/m':<7} {'Age'}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{cols}{Style.RESET_ALL}")
    print("-" * 90)

    for mac, data in sensor_data.items():
        name = monitored_sensors.get(mac, {}).get('name', mac[-8:])
        age = int(now - data['timestamp'])
        color = get_status_color(data['status'], data['battery'])
        decoder_color = Fore.YELLOW if data.get('decoder') == "Generic" else Fore.CYAN

        pressure = f"{data['pressure_bar']:>5.2f} bar ({data['pressure_psi']:>5.1f} psi)"

        # Battery display: use % for TPMS3, volts for others
        batt_pct = data.get('battery_pct', 0)
        if batt_pct > 0:
            batt_color = Fore.RED if batt_pct < 20 else Fore.GREEN
            batt_str = f"{batt_pct}%"
        else:
            batt_color = Fore.RED if data['battery'] < 2.5 else Fore.GREEN
            batt_str = f"{data['battery']:.1f}V"

        # Packet stats
        stats = packet_stats.get(mac, {'count': 0, 'timestamps': []})
        pkt_count = stats['count']
        # Packets per minute (total session average)
        if pkt_count >= 2 and elapsed > 0:
            rate_str = f"{pkt_count / (elapsed / 60.0):.1f}"
        elif pkt_count == 1:
            rate_str = "<1"
        else:
            rate_str = "-"

        line = (f"{color}{name:<15} "
                f"{decoder_color}{data.get('decoder', '?'):<14}{color} "
                f"{pressure:<22} "
                f"{data['temperature']:>3}C  "
                f"{batt_color}{batt_str:<7}{color} "
                f"{pkt_count:<6} "
                f"{rate_str:<7} "
                f"{Style.DIM}{age}s{Style.RESET_ALL}")
        print(line)

    # ── Packet history ──
    has_history = any(
        len(packet_stats.get(mac, {}).get('history', [])) > 1
        for mac in sensor_data
    )
    if has_history:
        print(f"\n{Fore.CYAN}{Style.BRIGHT}Packet History "
              f"{Style.DIM}(showing gaps to find sleep cycle){Style.RESET_ALL}")
        print("-" * 105)
        for mac, data in sensor_data.items():
            name = monitored_sensors.get(mac, {}).get('name', mac[-8:])
            history = packet_stats.get(mac, {}).get('history', [])
            if len(history) <= 1:
                continue

            print(f"{Fore.CYAN}{name} ({len(history)} unique packets):{Style.RESET_ALL}")
            for i, pkt in enumerate(history):
                age_s = int(now - pkt['time'])
                ts = datetime.fromtimestamp(pkt['time']).strftime('%H:%M:%S')
                marker = " >>" if i == len(history) - 1 else "   "
                color = Fore.GREEN if i == len(history) - 1 else Style.DIM

                # Calculate gap from previous packet
                gap_str = ""
                if i > 0:
                    gap = pkt['time'] - history[i - 1]['time']
                    if gap >= 60:
                        gap_str = f"{Fore.YELLOW}  +{int(gap)}s ({gap/60:.1f}m) SLEEP GAP{Style.RESET_ALL}"
                    elif gap >= 10:
                        gap_str = f"{Style.DIM}  +{int(gap)}s{Style.RESET_ALL}"

                print(f"{color}{marker} {ts}  "
                      f"{pkt['pressure_bar']:>5.2f} bar "
                      f"({pkt['pressure_psi']:>5.1f} psi)  "
                      f"{pkt['temperature']:>3}C  "
                      f"{age_s:>5}s ago"
                      f"{Style.RESET_ALL}{gap_str}")

    if SHOW_HEX_PACKETS:
        print(f"\n{Fore.CYAN}{Style.BRIGHT}Packet Breakdown{Style.RESET_ALL}")
        print("-" * 90)
        for mac, data in sensor_data.items():
            name = monitored_sensors.get(mac, {}).get('name', mac[-8:])
            hex_str = data['hex_data'].replace(' ', '')
            raw = bytes.fromhex(hex_str)
            decoder_name = data.get('decoder', '')

            print(f"{Fore.CYAN}{name}  {Style.DIM}({decoder_name}){Style.RESET_ALL}")

            if 'TPMS3' in decoder_name and len(raw) >= 16:
                # TPMS3 16-byte annotated breakdown
                mac_hex = hex_str[0:12]
                press_hex = hex_str[12:20]
                temp_hex = hex_str[20:24]
                resv_hex = hex_str[24:28]
                batt_hex = hex_str[28:30]
                flag_hex = hex_str[30:32]

                press_pa = raw[6] | (raw[7] << 8) | (raw[8] << 16) | (raw[9] << 24)
                press_psi = press_pa * 0.000145038  # Gauge pressure (no atm subtraction)
                temp_c = (raw[10] | (raw[11] << 8)) / 100.0
                batt = raw[14]

                # Spaced hex with byte separators
                spaced = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
                print(f"  {Fore.YELLOW}{spaced}{Style.RESET_ALL}")
                print(f"  {Fore.GREEN}"
                      f"{'|--- MAC Address ---|':<25}"
                      f"{'|-- Pressure --|':<19}"
                      f"{'|Temp-|':<9}"
                      f"{'|Rsv-|':<8}"
                      f"{'Bat':<5}"
                      f"{'Flg'}"
                      f"{Style.RESET_ALL}")
                print(f"  {Style.DIM}"
                      f"  {mac_hex[:2]}:{mac_hex[2:4]}:{mac_hex[4:6]}:"
                      f"{mac_hex[6:8]}:{mac_hex[8:10]}:{mac_hex[10:12]}"
                      f"       {press_pa} Pa"
                      f"      {temp_c:.1f}C"
                      f"     ----"
                      f"  {batt}%"
                      f"   {raw[15]:02x}"
                      f"{Style.RESET_ALL}")
                print(f"  {Style.DIM}"
                      f"  Bytes 0-5              "
                      f"Bytes 6-9 (u32 LE)  "
                      f"B10-11   "
                      f"B12-13 "
                      f" B14  "
                      f"B15"
                      f"{Style.RESET_ALL}")
                print(f"  {Fore.WHITE}"
                      f"  = {press_psi:+.1f} psi gauge  "
                      f"({press_pa * 0.00001:.3f} bar)"
                      f"{Style.RESET_ALL}")

            elif 'BR' in decoder_name and len(raw) >= 7:
                # BR 7-byte annotated breakdown
                spaced = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
                print(f"  {Fore.YELLOW}{spaced}{Style.RESET_ALL}")
                print(f"  {Fore.GREEN}"
                      f"{'Sts':<5}{'Bat':<5}{'Tmp':<5}"
                      f"{'|Press|':<9}{'|Chksum|'}"
                      f"{Style.RESET_ALL}")
                press_raw = (raw[3] << 8) | raw[4]
                print(f"  {Style.DIM}"
                      f"0x{raw[0]:02x} "
                      f"{raw[1]/10:.1f}V "
                      f"{raw[2]}C  "
                      f"{press_raw/10:.1f} psi abs  "
                      f"0x{raw[5]:02x}{raw[6]:02x}"
                      f"{Style.RESET_ALL}")

            else:
                # Generic: just show spaced hex with byte indices
                spaced = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
                indices = '  '.join(f'{i:<2}' for i in range(len(raw)))
                print(f"  {Fore.YELLOW}{spaced}{Style.RESET_ALL}")
                print(f"  {Style.DIM}{indices}{Style.RESET_ALL}")

    print(f"\n{Style.DIM}Press Ctrl+C to stop{Style.RESET_ALL}")


async def monitor_sensors():
    """Live monitoring loop for selected sensors."""
    global sensor_data, packet_stats

    if not monitored_sensors:
        print(f"{Fore.RED}No sensors configured. Discover sensors first.{Style.RESET_ALL}")
        return

    HISTORY_MAX = 50  # Number of recent packets to keep for sleep cycle analysis

    monitored_macs = set(monitored_sensors.keys())
    last_display = {}  # MAC -> timestamp for display dedup
    monitor_start = time.time()

    # Reset stats for this session
    packet_stats = {mac: {'count': 0, 'timestamps': [], 'history': []}
                    for mac in monitored_macs}

    def on_device(device: BLEDevice, adv: AdvertisementData):
        mac = normalize_mac(device.address)
        if mac not in monitored_macs:
            return
        if not adv.manufacturer_data:
            return

        now = time.time()

        # Deduplicate rapid BLE callbacks (bleak fires multiple times per broadcast)
        if mac in last_display and (now - last_display[mac]) < DEDUP_INTERVAL:
            return
        last_display[mac] = now

        for company_id, mfdata in adv.manufacturer_data.items():
            data = decode_sensor_data(
                device.name or "", adv.service_uuids or [], mfdata
            )
            if not data:
                continue

            # Count meaningful (deduped) packets
            stats = packet_stats.setdefault(
                mac, {'count': 0, 'timestamps': [], 'history': []})
            stats['count'] += 1
            stats['timestamps'].append(now)
            # Keep only last 60s of timestamps for rate calc
            stats['timestamps'] = [
                t for t in stats['timestamps'] if now - t <= 60
            ]

            # Add to history (only when data actually changed)
            hex_data = data.get('hex_data', '')
            if not stats['history'] or stats['history'][-1]['hex'] != hex_data:
                stats['history'].append({
                    'hex': hex_data,
                    'pressure_psi': data['pressure_psi'],
                    'pressure_bar': data['pressure_bar'],
                    'temperature': data['temperature'],
                    'time': now,
                })
                if len(stats['history']) > HISTORY_MAX:
                    stats['history'] = stats['history'][-HISTORY_MAX:]

            sensor_data[mac] = data
            display_monitoring_ui(monitor_start)

    try:
        scanner = BleakScanner(detection_callback=on_device)
        await scanner.start()
    except Exception as e:
        print(f"{Fore.RED}BLE scan failed: {e}{Style.RESET_ALL}")
        return

    try:
        while True:
            await asyncio.sleep(5)
            display_monitoring_ui(monitor_start)
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
            devices = await discover_devices()
            if devices:
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
