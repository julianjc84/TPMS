# BLE TPMS Protocol Documentation

## Overview

This document describes the Bluetooth Low Energy (BLE) protocols used by external TPMS sensors. Two sensor families are documented:

1. **TPMS{N} / ZEEPIN-type** - 16-byte manufacturer data (Company ID 0x0100) - **Tested & Confirmed**
2. **BR-type** - 7-byte manufacturer data (Service UUID 0x27a5) - Reference only

---

## TPMS{N} Protocol (ZEEPIN/TP630-type) - CONFIRMED

This is the most common cheap external BLE TPMS sensor sold on AliExpress. Confirmed working through real-world packet capture and community documentation.

### Device Identification

| Property | Value |
|----------|-------|
| **Device Name** | `TPMS{N}_{XXXXXX}` |
| **Name Format** | N = tire position (1-4), XXXXXX = last 3 MAC octets hex |
| **Position Map** | 1=Front Left, 2=Front Right, 3=Rear Left, 4=Rear Right |
| **Company ID** | `0x0100` (256) |
| **Packet Size** | 16 bytes manufacturer data |

Example: `TPMS3_334FE2` = Rear Left sensor, MAC ending in `33:4F:E2`

### Manufacturer Data Format (16 bytes)

```
MM MM MM MM MM MM PP PP PP PP TT TT UU UU BB FF
```

| Bytes | Field | Type | Unit | Formula |
|-------|-------|------|------|---------|
| 0-5 | MAC Address | 6 bytes | - | Sensor identification (matches BLE MAC) |
| 6-9 | **Pressure** | uint32 LE | Pascals | `* 0.000145038` = PSI absolute |
| 10-11 | **Temperature** | uint16 LE | 0.01 C | `/ 100.0` = Celsius |
| 12-13 | Reserved | uint16 | - | Always `0x0000` in observations |
| 14 | **Battery** | uint8 | % | Direct percentage (0-100) |
| 15 | Flags | uint8 | - | Always `0x00` in observations |

### Pressure Conversion

The sensor reports **absolute pressure** in Pascals. To get gauge (relative) pressure, subtract atmospheric:

```python
# Raw bytes 6-9 as uint32 little-endian
pressure_pa = mfdata[6] | (mfdata[7] << 8) | (mfdata[8] << 16) | (mfdata[9] << 24)

# Convert to display units
pressure_psi_abs = pressure_pa * 0.000145038     # Absolute PSI
pressure_psi     = pressure_psi_abs - 14.5        # Gauge PSI (subtract 1 atm)
pressure_bar     = pressure_pa * 0.00001          # Absolute bar
pressure_bar_gauge = pressure_bar - 1.01325       # Gauge bar (subtract 1 atm)
pressure_kpa     = pressure_pa / 1000.0           # Absolute kPa
```

### ESPHome Reference Implementation

```cpp
esp32_ble_tracker:
  on_ble_manufacturer_data_advertise:
    manufacturer_id: "0100"
    then:
      - lambda: |-
          if(x.size() == 16) {
            uint32_t pressure = x[6] | (x[7] << 8) | (x[8] << 16) | (x[9] << 24);
            float psi = pressure * 0.000145038;
            float temp_c = (x[10] | (x[11] << 8)) / 100.0;
            int battery = x[14];
          }
```

### Captured Packet Examples

Sensor MAC: `82:EA:CA:33:4F:E2` (TPMS3_334FE2 = Rear Left)

| Context | Full HEX (16 bytes) | Pressure (abs) | Temp | Batt |
|---------|---------------------|---------------|------|------|
| Desk, no tire | `82eaca334fe2 f5010300 520b 0000 64 00` | 197.1 kPa / 28.6 PSI | 28.98 C | 100% |
| Desk, no tire | `82eaca334fe2 e8f00200 580b 0000 64 00` | 192.7 kPa / 28.0 PSI | 29.04 C | 100% |
| On tire, loose | `82eaca334fe2 3fda0200 020b 0000 63 00` | 187.0 kPa / 27.3 PSI | 28.18 C | 99% |
| On tire, locked | `82eaca334fe2 21c10200 070b 0000 64 00` | 180.5 kPa / 26.2 PSI | 28.23 C | 100% |

**Key insight:** The desk readings (~28 PSI absolute = ~14 PSI gauge) correctly reflect atmospheric pressure. The "wildly changing" bytes 6-7 are the low-order bytes of the 32-bit pressure value in Pascals.

### Sensor Behavior

#### Sleep / Wake Cycle

External TPMS sensors use aggressive power management to preserve battery life:

| State | Broadcast Interval | Trigger |
|-------|-------------------|---------|
| **Deep Sleep** | No broadcasts | Default state when stationary for extended period |
| **Stationary Wake** | Every 2-5 minutes | Brief wake from internal timer |
| **Motion Active** | Every 10-30 seconds | Accelerometer detects sustained rotation |
| **Pressure Event** | Immediate burst | Rapid pressure change (>0.5 psi) |

**Wake triggers (from deep sleep):**
1. **Accelerometer / rotation** - Sustained wheel rotation (driving speed, not a brief spin). Some sensors require >20 km/h for initial activation
2. **Pressure change** - Inflating or deflating the tire
3. **Internal timer** - Periodic wake every 2-15 minutes (varies by manufacturer)

**Sleep triggers:**
- No rotation detected for 2-5 minutes
- Gradually increases sleep interval up to 15 minutes
- Some sensors stop broadcasting entirely after extended inactivity

#### Valve Stem Interaction

External cap TPMS sensors work by:
1. Screwing onto the Schrader valve stem
2. An internal pin depresses the valve core when fully seated
3. This opens a path to the tire's internal air pressure
4. A **twist-lock mechanism** on some models must be engaged to depress the core

**Important:** If the twist-lock is not engaged, the sensor only reads ambient atmospheric pressure (~101 kPa / ~14.5 PSI absolute), which appears as ~0 PSI gauge.

#### Battery

- **Type:** CR1632 lithium coin cell (3.0V nominal)
- **Byte 14:** Direct percentage (0-100%)
- **Lifespan:** 1-2 years typical
- **Low battery:** May reduce broadcast frequency

---

## BR Protocol (7-byte) - Reference

Older/alternative BLE TPMS sensors using "BR" device name.

### Device Identification

| Property | Value |
|----------|-------|
| **Device Name** | `BR` |
| **Service UUID** | `0x27a5` (pressure in psi) |
| **MAC Prefix** | `AC:15:85` (varies by batch) |
| **Packet Size** | 7 bytes manufacturer data |

### Advertising Data Structure

```
0303a527 03084252 08ff281d130105a376
```

| Segment | Meaning |
|---------|---------|
| `03 03 a527` | 16-bit UUID 0x27a5 |
| `03 08 4252` | Short name "BR" |
| `08 ff ...` | Manufacturer data (7 bytes) |

### Manufacturer Data Format (7 bytes)

```
SS BB TT PP PP CC CC
```

| Field | Bytes | Type | Unit | Formula |
|-------|-------|------|------|---------|
| SS | 1 | Status flags | - | See status bits |
| BB | 1 | Battery | V | `value / 10` |
| TT | 1 | Temperature | C | Signed byte |
| PPPP | 2 | Pressure | PSI | `value / 10` (absolute) |
| CCCC | 2 | Checksum | - | Algorithm TBD |

### Status Byte (SS) - BR Only

```
Bit:  7    6    5    4    3    2    1    0
      A    R    S    B    2    H    1    y
```

| Bit | Flag | Meaning |
|-----|------|---------|
| 7 | A - Alarm | Zero pressure alarm |
| 6 | R - Rotating | Wheel rotating (>4 km/h) |
| 5 | S - Still | Stationary for ~15 minutes |
| 4 | B - Begin | Transition to rotating |
| 3 | 2 - Decr2 | Pressure decreasing below 20.7 psi |
| 2 | H - High | Pressure rising |
| 1 | 1 - Decr1 | Pressure decreasing above 20.7 psi |
| 0 | y - Unknown | Reserved |

Special values: `0xFF` = low battery, `0x40` = rotating, `0x20` = stationary

### Example Decoding

Packet: `28 1d 13 01 05 a3 76`

- Status: `0x28` (Still + Decr2)
- Battery: `0x1d` = 29 = 2.9V
- Temperature: `0x13` = 19C
- Pressure: `0x0105` = 261 = 26.1 PSI absolute = 11.6 PSI gauge
- Checksum: `0xa376`

---

## Protocol Comparison

| Feature | TPMS{N} (16-byte) | BR (7-byte) |
|---------|-------------------|-------------|
| Identification | Device name + Company ID | Device name + UUID |
| Company ID | 0x0100 | N/A |
| Service UUID | N/A | 0x27a5 |
| Pressure | 32-bit LE, Pascals | 16-bit BE, 0.1 PSI |
| Temperature | 16-bit LE, 0.01 C | 8-bit signed, 1 C |
| Battery | Percentage (0-100%) | Voltage (value/10) |
| Status flags | None in packet | 8-bit encoded |
| Position | Encoded in device name | Not in packet |
| Checksum | None observed | 16-bit (algo TBD) |
| MAC in payload | Yes (first 6 bytes) | No |

## Implementation Notes

### Multi-Sensor Tracking

BLE TPMS sensors are identified by MAC address (not an in-packet ID). Implementations should:
1. Use MAC address as unique sensor key
2. Track last reading per MAC
3. Support 4+ simultaneous sensors
4. For TPMS{N} sensors, extract tire position from the device name digit

### Absolute vs Gauge Pressure

All BLE TPMS sensors report **absolute pressure** (includes atmospheric). For display:
- Subtract ~14.5 PSI (1 atmosphere at sea level) for gauge pressure
- Adjust atmospheric value for altitude if precision is needed

## References

- **Home Assistant ESPHome TPMS:** https://community.home-assistant.io/t/ble-tire-pressure-monitor/509927
- **ricallinson/tpms (Go):** https://github.com/ricallinson/tpms
- **mtigas/iOS-BLE-Tire-Logger:** https://github.com/mtigas/iOS-BLE-Tire-Logger
- **ra6070/BLE-TPMS (ESP32):** https://github.com/ra6070/BLE-TPMS
- **bkbilly/tpms_ble (HA):** https://github.com/bkbilly/tpms_ble
- **8bitmcu/ESPHome_BLE_TPMS:** https://github.com/8bitmcu/ESPHome_BLE_TPMS
- **theengs/decoder:** https://decoder.theengs.io/devices/TPMS.html
- **Instructables BLE TPMS:** https://www.instructables.com/BLE-Direct-Tire-Pressure-Monitoring-System-TPMS-Di/
- **Arduino Forum:** https://forum.arduino.cc/t/ble-tpms-sensors-decoding/1038638
- **Bluetooth Assigned Numbers:** https://www.bluetooth.com/specifications/assigned-numbers/
- **rtl_433 TPMS protocols:** https://github.com/merbanan/rtl_433/tree/master/src/devices
