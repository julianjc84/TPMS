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

| Decoder | Sensor Type | Data Size | Identification | Status |
|---------|------------|-----------|----------------|--------|
| **TPMS3-16byte** | Generic BLE TPMS (VSTM/ZEEPIN/TP630) | 16 bytes | Name `TPMS{N}_*`, CID 0x0100 | **Tested** |
| BR-7byte | Generic "BR" sensors | 7 bytes | Name "BR", UUID 0x27a5 | Reference |
| SYTPMS-6byte | SYTPMS sensors | 6 bytes | Name "TPMS", 6-byte data | Reference |
| Generic | Unknown sensors | 4+ bytes | Fallback with heuristics | Always |

**Tested with:** Generic external BLE TPMS cap sensors (VSTM/Visture, ZEEPIN/TP630, WISTEK, and other rebranded variants widely sold on AliExpress/Amazon)

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
  Rear Left          (82:EA:CA:33:4F:E2)

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
#    MAC Address          Name            RSSI   Decoder          TPMS?
---------------------------------------------------------------------------
1    82:EA:CA:33:4F:E2   TPMS3_334FE2   -45    TPMS3-16byte     TPMS Sensor
2    AC:15:85:C3:A2:01   BR             -48    BR-7byte         BR Sensor
3    AA:BB:CC:DD:EE:FF   Unknown        -72    Unknown
```

Select sensors by number, or press `a` to auto-select all detected TPMS devices.

### Live Monitoring

```
Sensor          Decoder        Pressure                Temp    Battery   Note              HEX Packet
------------------------------------------------------------------------------------------------------
Rear Left       TPMS3-16byte   1.82 bar (26.4 psi)     29C     100%      Pos:RL Abs:40.9   82eaca334fe2...
Front Left      BR-7byte       2.15 bar (31.2 psi)     22C     2.9V      ROTAT             281d160105a376
```

Press `Ctrl+C` to stop monitoring and return to menu.

## Sensor Behavior

### TPMS{N} Sensors (most common)

**Primary wake trigger is PRESSURE CHANGE, not motion.** These cheap cap sensors do not have a true accelerometer - they use a basic roll switch that only works at driving speeds. Rolling or spinning the sensor by hand will NOT wake it.

**Sleep / Wake cycle:**
- **Storage / Deep sleep** - No broadcasts. Factory default; extended inactivity
- **Idle (pressurized)** - Broadcasts every 1-5 minutes with stable pressure
- **Active (driving)** - Broadcasts every 10-30 seconds (roll switch detects rotation)
- **Pressure event** - Immediate burst on pressure change >1.2 PSI

**What wakes the sensor:**
- Pressure change (primary) - inflating, deflating, screwing onto a valve, blowing air into it
- Sustained wheel rotation at driving speed (>15-20 km/h)
- Internal timer (2-15 min periodic check)

**What does NOT wake the sensor:**
- Rolling it on a table
- Brief hand spins
- Shaking or tapping

**Tip:** If no sensor is detected, deflate/inflate the tire slightly, or slowly screw the sensor on/off the valve to create air flow. See [PROTOCOL.md](PROTOCOL.md) for full details.

**Valve interaction:** An internal pin depresses the Schrader valve core when the sensor is screwed on, opening an air path. A twist-lock nut must be engaged for a proper seal. Without engagement, the sensor only reads atmospheric pressure (~0 PSI gauge).

### BR Sensors

- **Rotating:** Frequent broadcasts (~10-30s) above 4 km/h
- **Stationary:** Every 2-5 minutes
- **Pressure change:** Immediate transmission on >0.5 psi change

## Requirements

- Python 3.7+
- Bluetooth adapter
- Linux, macOS, or Windows

Dependencies installed automatically by `setup.sh`:
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

1. Create a decoder class in `sensor_decoders.py`
2. Implement `can_decode()` to identify your sensor
3. Implement `decode()` to parse the data
4. Register it in the factory

See [DECODER_GUIDE.md](DECODER_GUIDE.md) for a complete guide with a real-world reverse-engineering case study.

## Troubleshooting

### No sensors detected
- Verify Bluetooth is enabled
- **Sensor is likely asleep** - these sensors wake on PRESSURE CHANGE, not motion
- To wake: deflate/inflate the tire briefly, or slowly screw the sensor on/off a valve
- Rolling or shaking the sensor will NOT wake it
- Use the interactive discovery (option 1) and keep scanning in 5-second rounds
- Use a BLE scanner app (e.g., nRF Connect) to verify the sensor is broadcasting
- Move closer to sensors (<5m)

### Sensor reads ~0 PSI gauge on a tire
- The twist-lock mechanism may not be engaged
- Sensor must fully depress the Schrader valve core to read tire pressure
- Without engagement, it correctly reads atmospheric pressure (~14.5 PSI absolute = ~0 gauge)

### Setup issues
- If `pip install` fails with "externally-managed-environment", use `./setup.sh` (uses venv)
- If `python3-venv` is missing: `sudo apt install python3-venv`

## References

- **TPMS Protocol Details:** [PROTOCOL.md](PROTOCOL.md)
- **Home Assistant ESPHome TPMS:** https://community.home-assistant.io/t/ble-tire-pressure-monitor/509927
- **ricallinson/tpms:** https://github.com/ricallinson/tpms
- **bkbilly/tpms_ble:** https://github.com/bkbilly/tpms_ble
- **theengs/decoder:** https://decoder.theengs.io/devices/TPMS.html
- **Instructables BLE TPMS:** https://www.instructables.com/BLE-Direct-Tire-Pressure-Monitoring-System-TPMS-Di/

## License

This project is provided as-is for educational and personal use.
