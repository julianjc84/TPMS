# BLE TPMS Protocol Documentation

## Overview

This document describes the Bluetooth Low Energy (BLE) protocols used by external TPMS sensors. Two sensor families are documented:

1. **TPMS{N} / ZEEPIN-type** - 16-byte manufacturer data (Company ID 0x0100) - **Tested & Confirmed**
2. **BR-type** - 7-byte manufacturer data (Service UUID 0x27a5) - Reference only

---

## TPMS{N} Protocol (ZEEPIN/TP630-type) - CONFIRMED

This is the most common cheap external BLE TPMS cap sensor sold on AliExpress. Confirmed working through real-world packet capture and community documentation.

### Known Brands Using This Protocol

This protocol is shared across many brands and resellers. The hardware and firmware are generic Chinese BLE TPMS modules rebranded by different sellers:

- **VSTM / Visture** - Visture (visture.com) primarily makes 433 MHz solar display TPMS systems (D02N, Q01W models), but their brand name is also applied to BLE-only cap sensors by resellers
- **ZEEPIN / TP630** - Common AliExpress brand
- **WISTEK** - Another AliExpress reseller
- Dozens of unbranded/white-label sellers on AliExpress, Amazon, Banggood

All use the same chipset, protocol, and naming convention regardless of brand.

### Device Identification

| Property | Value |
|----------|-------|
| **Device Name** | `TPMS{N}_{XXXXXX}` |
| **Name Format** | N = tire position (1-4), XXXXXX = last 3 MAC octets hex |
| **Position Map** | 1=Front Left, 2=Front Right, 3=Rear Left, 4=Rear Right |
| **Company ID** | `0x0100` (256) - registered to TomTom International BV, used without authorization |
| **Packet Size** | 16 bytes manufacturer data |
| **Communication** | Broadcast-only (no pairing, no connection, unencrypted) |
| **Frequency** | 2.4 GHz (standard BLE) |

Example: `TPMS3_334FE2` = Rear Left sensor, MAC ending in `33:4F:E2`

**Note on Company ID:** 0x0100 is officially registered to TomTom in the Bluetooth SIG Assigned Numbers database. These Chinese sensors use it without authorization - a common practice with cheap BLE devices. Some code (ra6070/BLE-TPMS, ricallinson/tpms) references `0x0001` due to byte-order differences.

### Manufacturer Data Format (16 bytes)

```
MM MM MM MM MM MM PP PP PP PP TT TT UU UU BB FF
```

| Bytes | Field | Type | Unit | Formula |
|-------|-------|------|------|---------|
| 0-5 | MAC Address | 6 bytes | - | Sensor identification (matches BLE MAC) |
| 6-9 | **Pressure** | uint32 LE | Gauge Pascals | `* 0.000145038` = PSI gauge |
| 10-11 | **Temperature** | uint16 LE | 0.01 C | `/ 100.0` = Celsius |
| 12-13 | Reserved | uint16 | - | Always `0x0000` in observations |
| 14 | **Battery** | uint8 | % | Direct percentage (0-100) |
| 15 | Flags | uint8 | - | Always `0x00` in observations |

### Pressure Conversion

The sensor reports **gauge pressure** (relative to atmospheric) in Pascals. No atmospheric subtraction needed - 0 = atmospheric.

```python
# Raw bytes 6-9 as uint32 little-endian
pressure_pa = mfdata[6] | (mfdata[7] << 8) | (mfdata[8] << 16) | (mfdata[9] << 24)

# Convert to display units (already gauge - no subtraction needed!)
pressure_psi = pressure_pa * 0.000145038     # Gauge PSI
pressure_bar = pressure_pa * 0.00001         # Gauge bar
pressure_kpa = pressure_pa / 1000.0          # Gauge kPa
```

**Important:** The ESPHome community documentation describes this as "absolute Pascals" but real-world testing confirms it is **gauge pressure**:
- Sensor off tire (ambient): raw value = 0 → 0 PSI (correct for gauge, would be ~14.5 for absolute)
- Sensor on 30 PSI tire: raw value = 204,505 → 29.7 PSI (matches gauge, would need to be ~47 PSI for absolute)

### ESPHome Reference Implementation

```cpp
esp32_ble_tracker:
  on_ble_manufacturer_data_advertise:
    manufacturer_id: "0100"
    then:
      - lambda: |-
          if(x.size() == 16) {
            uint32_t pressure = x[6] | (x[7] << 8) | (x[8] << 16) | (x[9] << 24);
            float psi = pressure * 0.000145038;  // Gauge PSI (no atm subtraction needed)
            float temp_c = (x[10] | (x[11] << 8)) / 100.0;
            int battery = x[14];
          }
```

**Note:** The ESPHome community code `value * 0.000145038` gives gauge PSI directly. Some community docs incorrectly describe this as "absolute" but real-world testing confirms it is gauge (0 = atmospheric).

### Captured Packet Examples

Sensor MAC: `82:EA:CA:33:4F:E2` (TPMS3_334FE2 = Rear Left)

| Context | Full HEX (16 bytes) | Pressure (gauge) | Temp | Batt |
|---------|---------------------|-----------------|------|------|
| Desk (residual pressure) | `82eaca334fe2 f5010300 520b 0000 64 00` | 197.1 kPa / 28.6 PSI | 28.98 C | 100% |
| Desk (residual pressure) | `82eaca334fe2 e8f00200 580b 0000 64 00` | 192.7 kPa / 28.0 PSI | 29.04 C | 100% |
| On tire, loose | `82eaca334fe2 3fda0200 020b 0000 63 00` | 187.0 kPa / 27.3 PSI | 28.18 C | 99% |
| On tire, locked (26-28 PSI) | `82eaca334fe2 21c10200 070b 0000 64 00` | 180.5 kPa / 26.2 PSI | 28.23 C | 100% |
| On tire (~30 PSI) | `82eaca334fe2 d91e0300 f409 0000 62 00` | 204.5 kPa / 29.7 PSI | 25.0 C | 98% |
| Ambient (off tire) | `82eaca334fe2 00000000 2508 0000 63 01` | 0 kPa / 0.0 PSI | 21.0 C | 99% |

**Key insights:**
- Pressure is **gauge** (relative to atmospheric), not absolute. Zero = atmospheric.
- Early "desk" readings of ~28 PSI were residual tire pressure sealed in the sensor, not atmospheric.
- The "wildly changing" bytes 6-7 are the low-order bytes of the 32-bit gauge pressure value in Pascals.
- Byte 15 changes to `0x01` when pressure is zero (possible low-pressure alarm flag).

### Sensor Behavior

#### Sleep / Wake Cycle

These sensors use aggressive power management to preserve the CR1632 battery. **The MEMS pressure sensor interrupt is the ONLY wake mechanism.** This unit contains no roll switch, gyroscope, or accelerometer - confirmed through extensive testing. Motion, rotation, and vibration have zero effect. Some higher-end TPMS sensors from other manufacturers may include a roll switch or accelerometer for motion-based wake, but this VSTM/ZEEPIN-type unit relies entirely on pressure changes for maximum battery life.

| State | Broadcast Interval | Trigger |
|-------|-------------------|---------|
| **Deep Sleep** | No broadcasts | Default state. Only pressure change can wake. |
| **Wake Burst** | Every ~4 seconds for ~36 seconds | Pressure change triggers initial burst of ~10 packets |
| **Timer Wake** | Brief (1-2 packets) ~1.7 min after burst | Internal timer fires once, then back to deep sleep |
| **On-Tire (thermal)** | Every ~4-7 minutes (varies) | Thermal pressure fluctuations trigger interrupt |
| **On-Tire (driving)** | More frequent (not yet measured) | Pressure changes from tire flex, braking, temperature |

**Wake mechanism:**
- **Pressure change** (the ONLY mechanism) - The MEMS pressure sensor generates a hardware interrupt when pressure crosses a threshold. This wakes the MCU from near-zero power deep sleep. Examples: inflating/deflating a tire, screwing sensor onto a pressurized valve, or blowing air directly into the sensor opening
- **There is NO motion/rotation sensor** - Confirmed: spinning the sensor, rolling it, shaking it, spinning the tire with it attached - none of these wake it. This unit has no roll switch, gyroscope, or accelerometer.
- **Internal timer** - Not a repeating wake mechanism. Fires once ~1.7 minutes after a wake burst, then stops.

**Confirmed sleep cycle (tested, sensor OFF tire with no pressure):**

```
00:00  Pressure change detected (e.g., blowing into sensor)
00:00  Wake burst begins - broadcasts every ~4 seconds
00:36  Wake burst ends after ~10 packets (36 seconds)
00:36  Sensor enters light sleep
01:42  Timer wake - broadcasts 1-2 packets (+102 seconds / 1.7 minutes)
01:46  Sensor enters deep sleep
09:00+ No further broadcasts - deep sleep is permanent until next pressure change
```

**Confirmed on-tire behavior (tested, sensor ON tire idle in sun):**

The sensor does NOT use a periodic timer when on a tire. Instead, **thermal pressure changes from sun/ambient temperature naturally trigger the pressure interrupt**, causing periodic wakes:

```
07:05  Wake burst ends after reattaching sensor (24.5 PSI, 21°C)
07:43  +38.5 min - first thermal wake (24.7 PSI, 21°C)
07:49  +6.1 min  - pressure rising (24.8 PSI, 21°C)
07:53  +3.7 min  - sun heating up (25.0 PSI, 23°C)
07:57  +4.1 min  - warming faster (25.1 PSI, 25°C)
08:04  +6.8 min  - still rising (25.3 PSI, 26°C)
08:10  +6.0 min  - steady climb (25.3 PSI, 26°C)
08:11  +1.4 min  - accelerating (25.5 PSI, 28°C)
```

**Key observations from on-tire data:**
- Pressure rose from 24.5 → 25.5 PSI (+1.0 PSI) as temperature climbed 21 → 28°C (+7°C)
- This follows Gay-Lussac's Law: gas pressure increases proportionally with temperature
- Wake intervals are **irregular** (38.5m, 6.1m, 3.7m, 4.1m, 6.8m, 6.0m, 1.4m) because they depend on the rate of pressure change, not a fixed timer
- Intervals shortened as the sun got hotter and pressure changed faster
- Each wake produces only 1-2 packets (not a full burst) - very battery-efficient
- **There is no periodic timer** - the sensor is purely event-driven by real pressure fluctuations

**This explains real-world behavior:**
- On a parked car in stable temperature: very infrequent wakes (pressure barely changes)
- On a parked car in sun: wakes every few minutes as thermal expansion changes pressure
- While driving: frequent wakes from tire flex, braking forces, and road-induced pressure pulses
- Overnight in garage: may go hours between wakes as temperature slowly drops

**Deep sleep is truly off.** The sensor does not monitor, poll, or broadcast. The only active circuit is the MEMS pressure sensor's hardware interrupt, which draws near-zero current. This is how a CR1632 (~130 mAh) can last 1-2 years with no motion sensor to drain the battery.

**With zero/no pressure:** The sensor goes to deep sleep after the single timer wake and does NOT continue periodic broadcasting. It will only wake again on the next pressure change. Confirmed - sensor monitored for 9+ minutes with no further broadcasts.

**With sustained pressure (on a tire):** The sensor wakes whenever thermal or mechanical pressure fluctuations cross the interrupt threshold. There is no fixed broadcast interval - it is entirely event-driven.

**Sleep triggers:**
- No pressure change after the ~36 second wake burst
- Escalating sleep: one timer wake at ~1.7 min, then permanent deep sleep
- Sensors ship in "storage mode" (deep sleep) - first pressurization activates them

**Tested observations:**
- Rolling sensor on table: does NOT wake it
- Brief hand spin: does NOT wake it
- Shaking/vibrating sensor: does NOT wake it
- Spinning the tire with sensor attached: does NOT wake it
- Blowing into the sensor opening: DOES wake it (confirmed, no adapter needed)
- Slowly screwing onto valve stem (air flow = pressure change): DOES wake it
- Wake burst: ~10 packets over ~36 seconds at ~4 second intervals
- One timer wake ~1.7 minutes later (1-2 packets), then permanent deep sleep
- On-tire idle in sun: wakes every ~4-7 minutes from thermal pressure changes
- No motion/roll sensor present in this unit

**For bench testing without a tire:**
1. **Blow into the sensor** - confirmed: blowing air directly into the sensor opening with no adapter or valve reliably wakes it from deep sleep
2. Screw onto any pressurized Schrader valve (bike tube, car tire, etc.)
3. Partially screw on/off a valve repeatedly to create pressure puffs

#### Valve Stem Installation & Twist-Lock

External cap TPMS sensors install onto standard Schrader valve stems:

1. **Remove** the standard valve cap (twist counter-clockwise)
2. **(Optional)** Screw on the **anti-theft lock nut** down the valve stem threads
3. **Screw on the TPMS sensor** (clockwise) until snug on the valve stem
4. **Tighten the lock nut** upward toward the sensor body using the included hex spanner wrench, while holding the sensor in place

The twist-lock / anti-theft nut serves dual purposes:
- **Anti-theft:** Prevents casual removal. Only the included hex spanner wrench can loosen it
- **Valve core depression:** When fully seated and locked, an **internal pin inside the sensor body depresses the Schrader valve core**. This opens a path from the tire's internal air pressure to the sensor's pressure transducer

**Important:** If the twist-lock is not engaged (or the sensor is loosely placed on the valve), the sensor only reads ambient atmospheric pressure (~101 kPa / ~14.5 PSI absolute), which appears as ~0 PSI gauge. The lock nut wrench should be kept in the vehicle for tire changes.

**Note:** The act of screwing the sensor onto a valve is itself a wake trigger - the pin depressing the valve core causes air flow into the sensor cavity, creating a pressure change that wakes it from sleep.

#### Internal Components

- **MCU + BLE SoC** - Low-cost BLE 5.0 system-on-chip (likely Telink, Holychip/HC, or similar)
- **MEMS pressure sensor** - Capacitive/piezoresistive absolute pressure transducer (0-50 PSI range)
- **Temperature sensor** - Integrated into pressure MEMS die or separate thermistor
- **No motion sensor** - Confirmed: this unit contains no roll switch, gyroscope, or accelerometer. All wake/sleep behavior is driven purely by the MEMS pressure sensor interrupt. Some higher-end TPMS units from other manufacturers may include motion sensors, but these cheap VSTM/ZEEPIN units optimize battery life by omitting them entirely
- **Housing** - ABS/polycarbonate, ~20-25mm diameter, IP67 waterproof, rubber O-ring seal

#### Battery

- **Type:** CR1632 lithium coin cell (3.0V nominal, ~120-140 mAh)
- **Byte 14:** Direct percentage (0-100%)
- **Lifespan:** 1-2 years typical
- **Low battery:** May reduce broadcast frequency
- **Note:** BLE scanning does NOT impact sensor battery - the sensor is a pure broadcaster that never receives incoming data

#### Compatible Phone Apps

These sensors work with several generic BLE TPMS apps:
- **BLE TPMS** (com.po.tyrecheck)
- **Multi Wheel BLE TPMS** by SYSGRATION LTD
- **Dynamic BLE TPMS**
- **Light TPMS**
- **TPMS-advanced** (open-source, github.com/VincentMasselis/TPMS-advanced)

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
| Pressure | 32-bit LE, gauge Pascals | 16-bit BE, 0.1 PSI absolute |
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

- **TPMS{N} sensors** report **gauge pressure** (0 = atmospheric). No subtraction needed.
- **BR sensors** report **absolute pressure** (includes atmospheric). Subtract ~14.5 PSI for gauge.
- Check your sensor type - not all BLE TPMS sensors use the same convention.

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
