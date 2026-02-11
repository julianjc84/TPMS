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
| **TPMS3-16byte** | Generic BLE TPMS (ZEEPIN/TP630) | 16 bytes | Name `TPMS{N}_*`, CID 0x0100 | **Tested** |
| BR-7byte | Generic "BR" sensors | 7 bytes | Name "BR", UUID 0x27a5 | Reference |
| SYTPMS-6byte | SYTPMS sensors | 6 bytes | Name "TPMS", 6-byte data | Reference |
| Generic | Unknown sensors | 4+ bytes | Fallback with heuristics | Always |

**Tested with:** Generic external BLE TPMS cap sensors (ZEEPIN/TP630-compatible, widely sold on AliExpress)

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

**Sleep / Wake cycle:**
- **Deep sleep** - No broadcasts. Default when stationary for extended period
- **Stationary wake** - Brief broadcast every 2-15 minutes (internal timer)
- **Motion active** - Broadcasts every 10-30 seconds when wheel is rotating
- **Pressure event** - Immediate burst on rapid pressure change

**Wake triggers:**
- Sustained wheel rotation (driving speed, not just a brief spin)
- Pressure change (inflating/deflating)
- Internal timer (2-15 min intervals)

**Tip:** If no sensor is detected, try spinning the tire at speed, or briefly deflate/inflate to trigger a pressure-change wake.

**Valve interaction:** External cap sensors depress the Schrader valve core pin when fully screwed on. Some have a twist-lock mechanism that must be engaged to access tire pressure. Without this, the sensor only reads atmospheric pressure.

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
- Sensors may be in deep sleep - spin the tire or change pressure to wake them
- Try a longer scan duration
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
