# BLE TPMS - Bluetooth Tire Pressure Monitoring System

Interactive desktop tool to monitor external TPMS sensors via Bluetooth Low Energy.

## Features

- **Interactive UI** - Menu-driven interface for discovering and monitoring sensors
- **Auto-Detection** - Automatically identifies TPMS sensors from all nearby BLE devices
- **Multi-Sensor** - Track 4+ sensors simultaneously with friendly names
- **Modular Decoders** - Plugin system supports different TPMS sensor types
- **Dual Units** - Pressure displayed in both BAR and PSI
- **HEX Packet View** - Raw BLE packet data for debugging
- **Color-Coded Display** - Status indicators at a glance
- **Saved Configuration** - Remembers your sensors between sessions
- **CSV Logging** - Optional data logging to file

## Supported Sensors

| Decoder | Sensor Type | Data Length | Identification |
|---------|------------|-------------|----------------|
| BR-7byte | Generic "BR" sensors | 7 bytes | Name "BR", UUID 0x27a5 |
| SYTPMS-6byte | SYTPMS sensors | 6 bytes | Name contains "TPMS" |
| Generic | Unknown sensors | 4+ bytes | Fallback with heuristics |

**Tested with:** https://aliexpress.com/item/1005004504977890.html

New sensor types can be added via the modular decoder system. See [DECODER_GUIDE.md](DECODER_GUIDE.md).

## Quick Start

```bash
# One-time setup (creates virtual environment, installs dependencies)
./setup.sh

# Run the monitor
./run.sh
```

## Usage

### Main Menu

```
BLE TPMS Monitor - Interactive
================================

Current Configuration:
  Front Left         (AC:15:85:C3:A2:01)
  Front Right        (AC:15:85:C3:A2:02)

Options:
  1 - Discover and select sensors
  2 - Start monitoring
  3 - Remove a sensor
  4 - Clear all sensors
  5 - List available decoders
  q - Quit
```

### Workflow

1. **Discover** - Scan for nearby BLE devices (option 1)
2. **Select** - Choose which sensors to monitor, give them names
3. **Monitor** - Start live monitoring (option 2)

### Device Discovery

```
#    MAC Address          Name       RSSI   Decoder          TPMS?
---------------------------------------------------------------------------
1    AC:15:85:C3:A2:01   BR         -45    BR-7byte         BR Sensor
2    AC:15:85:C3:A2:02   BR         -48    BR-7byte         BR Sensor
3    AA:BB:CC:DD:EE:FF   Unknown    -72    Unknown
```

Select sensors by number, or press `a` to auto-select all detected TPMS devices.

### Live Monitoring

```
Sensor          Decoder      Pressure                Temp    Battery   Status     HEX Packet        Age
---------------------------------------------------------------------------------------------------------
Front Left      BR-7byte     2.15 bar (31.2 psi)     22C     2.9V      ROTAT      281d160105a376    5s ago
Front Right     BR-7byte     2.10 bar (30.5 psi)     23C     3.0V      STILL      291e170106b487    3s ago
```

Press `Ctrl+C` to stop monitoring and return to menu.

## Requirements

- Python 3.7+
- Bluetooth adapter
- Linux, macOS, or Windows

Dependencies are installed automatically by `setup.sh`:
- `bleak` - Cross-platform BLE library (no sudo required)
- `colorama` - Colored terminal output

## Project Structure

```
TPMS/
├── tpms-interactive.py    # Main application
├── sensor_decoders.py     # Modular decoder library
├── setup.sh               # One-time setup (venv + dependencies)
├── run.sh                 # Launch the app
├── activate.sh            # Quick venv activation helper
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── PROTOCOL.md            # BLE TPMS protocol documentation
├── DECODER_GUIDE.md       # Guide for adding new sensor types
└── deprecated/            # Old implementations (reference only)
```

## Adding New Sensor Types

The modular decoder system makes it easy to support new TPMS sensors:

1. Create a decoder class in `sensor_decoders.py`
2. Implement `can_decode()` to identify your sensor
3. Implement `decode()` to parse the data
4. Register it in the factory

See [DECODER_GUIDE.md](DECODER_GUIDE.md) for a complete guide with examples and reverse-engineering tips.

## Data Format

**Output fields:**
- **Sensor** - Friendly name (configured during discovery)
- **Decoder** - Which decoder parsed the data
- **Pressure** - Relative pressure in BAR and PSI
- **Temp** - Temperature in Celsius
- **Battery** - Voltage (V)
- **Status** - Sensor status flags
- **HEX Packet** - Raw manufacturer data

**Status Flags:**

| Flag | Meaning |
|------|---------|
| ALARM | Zero pressure alarm |
| ROTAT | Wheel rotating (>4 km/h) |
| STILL | Standing still for ~15 minutes |
| BGROT | Begin rotating (transition) |
| DECR2 | Pressure decreasing below 20.7 psi |
| RISIN | Pressure rising |
| DECR1 | Pressure decreasing above 20.7 psi |
| LBATT | Low battery warning |

See [PROTOCOL.md](PROTOCOL.md) for full protocol details.

## Sensor Behavior

- **Pressure change:** Immediate transmission
- **Stationary:** Transmits every 2-5 minutes
- **Rotating:** More frequent (~10-30 seconds) above 4 km/h
- **Activation:** Pressurize above 10 psi (0.7 bar)
- **Battery:** CR1632, ~1-2 year lifespan, LBATT flag below ~2.5V

## Troubleshooting

### No sensors detected
- Verify Bluetooth is enabled
- Ensure sensors are pressurized (>10 psi)
- Try spinning the wheel to trigger transmission
- Use a BLE scanner app (e.g., nRF Connect) to verify sensor MAC addresses
- Move closer to sensors (<5m)

### Invalid checksums
- Move closer to sensors
- Reduce Bluetooth congestion
- Checksum algorithm may need refinement for your sensor model

### Setup issues
- If `pip install` fails with "externally-managed-environment", use `./setup.sh` (uses venv)
- If `python3-venv` is missing: `sudo apt install python3-venv`

## References

- https://www.instructables.com/BLE-Direct-Tire-Pressure-Monitoring-System-TPMS-Di/
- https://github.com/ra6070/BLE-TPMS
- https://forum.arduino.cc/t/arduino-ble-tpms-capteur-pression-pneus/592030/60
- Bluetooth Assigned Numbers: https://www.bluetooth.com/specifications/assigned-numbers/

## License

This project is provided as-is for educational and personal use.
