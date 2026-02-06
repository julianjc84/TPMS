# BLE TPMS Protocol Documentation

## Overview

This document describes the Bluetooth Low Energy (BLE) protocol used by direct external TPMS sensors (model: https://aliexpress.com/item/1005004504977890.html).

## BLE Advertising Packet

### Device Information
- **Device Name:** "BR"
- **Service UUID:** 0x27a5 (Bluetooth Assigned Number for "pressure" in psi)
- **MAC Address Prefix:** ac:15:85 (may vary by batch)

### Advertising Data Structure

The BLE advertising packet contains three AD structures following the Bluetooth Core Specification (see [Bluetooth Assigned Numbers](https://www.bluetooth.com/specifications/assigned-numbers/)):

| Offset | Length | Type | Description |
|--------|--------|------|-------------|
| 0-3    | 3      | 0x03 | 16-bit Service UUID: 0x27a5 |
| 4-7    | 3      | 0x08 | Short Name: "BR" |
| 8-16   | 8      | 0xFF | Manufacturer Data (7 bytes + length/type) |

**Example Payload:**
```
0303a527 03084252 08ff281d130105a376
```

Breaking down the example:
- `03 03 a527` - Complete 16-bit UUID (0x27a5 = pressure psi)
- `03 08 4252` - Short name "BR" (0x42='B', 0x52='R')
- `08 ff 281d130105a376` - Manufacturer data with sensor readings

## Manufacturer Data Format

The manufacturer data contains 7 bytes of sensor information:

```
SS BB TT PP PP CC CC
```

| Field | Bytes | Description | Unit | Formula |
|-------|-------|-------------|------|---------|
| SS    | 1     | Status byte | -    | See status bits below |
| BB    | 1     | Battery voltage | V | value / 10 |
| TT    | 1     | Temperature | °C | value (signed) |
| PPPP  | 2     | Absolute pressure | psi | value / 10 |
| CCCC  | 2     | Checksum | -    | See checksum section |

### Status Byte (SS)

The status byte contains 8 flags encoded as: **ARSB2H1y**

| Bit | Hex | Name | Description |
|-----|-----|------|-------------|
| 7   | 0x80 | A - Alarm | Zero pressure alarm |
| 6   | 0x40 | R - Rotating | Wheel is rotating (>4 km/h) |
| 5   | 0x20 | S - Still | Standing still for ~15 minutes |
| 4   | 0x10 | B - Begin | Begin rotating (transition) |
| 3   | 0x08 | 2 - Decr2 | Decreasing pressure below 20.7 psi threshold |
| 2   | 0x04 | H - High | Rising pressure |
| 1   | 0x02 | 1 - Decr1 | Decreasing pressure above 20.7 psi threshold |
| 0   | 0x01 | y - Unknown | Reserved/unknown |

**Special Status Values:**
- `0xFF` - Low battery indicator (all bits set)
- `0x40` - Normal rotation
- `0x20` - Stationary
- `0x80` - Critical alarm

### Example Decoding

**Example packet:** `281d130105a376`

Parsing:
- Status: `0x28` = 0b00101000 = Still (bit 5) + Decr2 (bit 3)
- Battery: `0x1d` = 29 → 2.9 V
- Temperature: `0x13` = 19 → 19°C
- Pressure: `0x0105` = 261 → 26.1 psi
- Checksum: `0xa376` = 41846

Conversion to relative pressure (bar):
```
absolute_psi = 26.1
relative_psi = 26.1 - 14.5 = 11.6 psi
relative_bar = 11.6 × 0.0689476 = 0.80 bar
```

## Checksum Algorithm

The checksum is stored in the last 2 bytes (CCCC) as a 16-bit value (big-endian).

**Current Implementation Status:** The exact checksum algorithm is still being validated. Initial testing suggests:

1. **Simple sum hypothesis:**
   ```cpp
   uint16_t checksum = status + battery + temperature + (pressure_high << 8) + pressure_low;
   ```

2. **CRC-16 hypothesis:** May use CRC-16/XMODEM or similar polynomial

3. **XOR-based hypothesis:** Similar to 433 MHz version (see CC1101_TPMS_433.ino:172-178)

**Reference from 433 MHz protocol:**
```cpp
// 433 MHz checksum (8-bit XOR)
int chksum = byteArr[0]^byteArr[1]^byteArr[2]^byteArr[3]^byteArr[4]^byteArr[5]^byteArr[6]^byteArr[7];
```

**Validation Function (C++):**
```cpp
bool validateChecksum(const uint8_t* data, size_t len) {
  if (len < 7) return false;

  // Method 1: Simple sum
  uint16_t calculated = 0;
  for (int i = 0; i < 5; i++) {
    calculated += data[i];
  }

  // Extract received checksum (big-endian)
  uint16_t received = (data[5] << 8) | data[6];

  return calculated == received;
}
```

**Note:** This algorithm may need adjustment based on real-world testing. Monitor for invalid checksum errors and report patterns to refine the algorithm.

## Sensor Behavior

### Transmission Patterns

- **Pressure change:** Immediate transmission when pressure changes >0.5 psi
- **Stationary:** Transmits every 2-5 minutes when pressure is stable
- **Rotating:** More frequent transmissions (~10-30 seconds) when wheel rotates >4 km/h
- **Low battery:** May reduce transmission frequency

### Power Management

- **Battery:** CR1632 lithium coin cell (3.0V nominal)
- **Low battery threshold:** ~2.5V (status byte = 0xFF)
- **Expected lifespan:** 1-2 years depending on usage

### Activation

- Sensors activate when pressurized >10 psi
- No external trigger tool required
- May take 30-60 seconds after pressurization for first transmission
- Rotation detection requires sustained >4 km/h speed

## Comparison with Other Protocols

### 433 MHz TPMS (tpms_truck protocol)
- **Frequency:** 433.92 MHz
- **Modulation:** FSK, Manchester encoding
- **Bitrate:** 19200 baud
- **Packet:** 9 bytes (ID + wheel + pressure + temp + checksum)
- **Checksum:** 8-bit XOR
- **Reference:** https://github.com/merbanan/rtl_433/blob/master/src/devices/tpms_truck.c

### BLE TPMS (this protocol)
- **Frequency:** 2.4 GHz BLE
- **Advertising interval:** Variable (1-300 seconds)
- **Packet:** 7 bytes manufacturer data
- **Checksum:** 16-bit (algorithm TBD)
- **No sensor ID:** Identified by MAC address instead

## Implementation Notes

### Multi-Sensor Tracking

Unlike 433 MHz sensors that include a sensor ID in the payload, BLE sensors are identified by their unique MAC address. Implementations should:

1. Use MAC address as sensor identifier
2. Track last reading per MAC address
3. Support 4+ sensors simultaneously
4. Filter by MAC prefix if needed

### Pressure Conversion

The sensor reports **absolute pressure** in psi (1/10 resolution). For tire pressure displays:

```cpp
// Convert to relative pressure in bar
float absolute_psi = ((data[3] << 8) | data[4]) / 10.0;
float relative_psi = absolute_psi - 14.5;  // Subtract atmospheric pressure
float relative_bar = relative_psi * 0.0689476;
```

### Temperature Handling

Temperature is reported as a signed 8-bit integer in Celsius:
- Range: -128°C to +127°C
- Typical tire range: -20°C to +80°C

## Testing & Validation

To validate the checksum algorithm:

1. Capture 20+ packets from a sensor
2. Log raw manufacturer data with known-good readings
3. Test different checksum algorithms (sum, CRC-16, XOR)
4. Look for patterns in failed vs. passed checksums
5. Update validation function once pattern is confirmed

## References

- **Bluetooth Assigned Numbers:** https://www.bluetooth.com/specifications/assigned-numbers/
- **rtl_433 TPMS protocols:** https://github.com/merbanan/rtl_433/tree/master/src/devices
- **BLE TPMS implementations:**
  - https://www.instructables.com/BLE-Direct-Tire-Pressure-Monitoring-System-TPMS-Di/
  - https://github.com/ra6070/BLE-TPMS
  - https://forum.arduino.cc/t/arduino-ble-tpms-capteur-pression-pneus/592030/60
- **BLE Advertising Packet Format:** Bluetooth Core Specification Vol 3, Part C, Section 11
