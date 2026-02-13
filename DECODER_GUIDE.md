# TPMS Decoder System Guide

## Overview

The modular decoder system supports multiple TPMS sensor types without modifying the core application. Each sensor type has its own decoder class that handles identification and data parsing.

```
BLE Device -> Factory -> Decoder Selection -> Data Parsing -> Standard Output
```

1. **Factory** receives device info (name, UUIDs, manufacturer data)
2. **Tries each decoder** in priority order
3. **First matching decoder** handles the data
4. **Returns standardized format** for display

## Built-in Decoders

| Decoder | Manufacturer | Data Size | ID Method | Status |
|---------|-------------|-----------|-----------|--------|
| **TPMS3-16byte** | Generic BLE TPMS (VSTM/ZEEPIN/TP630-type) | 16 bytes | Name `TPMS{N}_*`, CID 0x0100 | **Tested & Confirmed** |
| BR-7byte | Generic BR | 7 bytes | Name "BR", UUID 0x27a5 | Reference |
| SYTPMS-6byte | SYTPMS | 6 bytes | Name "TPMS", 6-byte data | Reference |
| Generic | Unknown | 4+ bytes | Fallback | Always available |

## Adding a New Sensor Type

### Step 1: Create Decoder Class

Edit `sensor_decoders.py` and add your decoder:

```python
class MyTPMSDecoder(TPMSDecoder):
    """Your sensor description."""

    @property
    def name(self) -> str:
        return "MySensor-8byte"  # Unique identifier

    @property
    def manufacturer(self) -> str:
        return "Acme Corp"

    def can_decode(self, device_name: str, service_uuids: list, mfdata: bytes) -> bool:
        """Return True if this decoder can handle the data."""
        # Method 1: Check device name
        if device_name == "ACME-TPMS":
            return True
        # Method 2: Check data pattern / length
        if len(mfdata) == 8 and mfdata[0] == 0xFF:
            return True
        return False

    def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
        """
        Parse sensor data. MUST return dict with these fields:
        - status, battery, temperature
        - pressure_bar, pressure_psi
        - hex_data, decoder, valid
        """
        if len(mfdata) < 8:
            return None

        # Your parsing logic here
        temperature = mfdata[1] - 40
        pressure_kpa = (mfdata[2] << 8) | mfdata[3]
        pressure_bar = pressure_kpa / 100.0
        pressure_psi = pressure_bar / 0.0689476

        return {
            'status': mfdata[0],
            'battery': mfdata[4] / 10.0,
            'temperature': temperature,
            'pressure_bar': pressure_bar,
            'pressure_psi': pressure_psi,
            'hex_data': mfdata.hex(),
            'decoder': self.name,
            'valid': True,
        }
```

### Step 2: Register Decoder

In `sensor_decoders.py`, add to the factory's `__init__`:

```python
class TPMSDecoderFactory:
    def __init__(self):
        self.decoders = [
            BRTPMSDecoder(),
            TPMS3Decoder(),
            SYTPMSDecoder(),
            MyTPMSDecoder(),       # <-- Add before GenericTPMSDecoder
            GenericTPMSDecoder(),  # Always keep Generic last
        ]
```

### Step 3: Test

```bash
# Run the decoder self-test
python3 sensor_decoders.py

# Test with the interactive tool
./run.sh
# Option 5 to list decoders
# Option 1 to discover devices
```

## Real-World Case Study: Reverse Engineering TPMS3

This is how we decoded the TPMS3 sensor format from scratch.

### 1. Initial Discovery

Ran BLE scan and found device `TPMS3_334FE2` with Company ID `0x0100` and 16-byte manufacturer data.

### 2. First Packet Capture

```
82eaca334fe2 f5 01 03 00 52 0b 00 00 64 00
```

First 6 bytes (`82:EA:CA:33:4F:E2`) matched the BLE MAC address exactly.

### 3. Initial (Wrong) Hypothesis

We assumed each remaining byte was a separate field:
```
[6]=header [7]=position [8]=status [9]=alarm [10-11]=temp [12-13]=pressure [14]=battery [15]=end
```

This gave temperature 29C (correct!) but pressure always 0 (wrong!).

### 4. The Mystery: Bytes 6-7 "Changing Wildly"

Multiple captures showed bytes 6-7 changing dramatically:
```
f5 01 ...  (desk)
e8 f0 ...  (desk)
3f da ...  (tire loose)
21 c1 ...  (tire locked)
```

We couldn't explain what these were.

### 5. Research Breakthrough

Web search found the [Home Assistant ESPHome community](https://community.home-assistant.io/t/ble-tire-pressure-monitor/509927) had already decoded this format. **Bytes 6-9 are a 32-bit pressure value in Pascals (little-endian).**

### 6. Corrected Decode

```python
pressure_pa = data[6] | (data[7] << 8) | (data[8] << 16) | (data[9] << 24)
# Desk reading: 0x000301f5 = 197,109 Pa = 28.6 PSI absolute = 14.1 PSI gauge
# This is atmospheric pressure - CORRECT for a sensor on a desk!
```

### 7. Lesson Learned

The "wildly changing" bytes were actually the low-order bytes of a 4-byte integer. The high bytes (8-9) were relatively stable (`03 00`, `02 00`) because they represent ~190 kPa which only varies slightly. Always consider multi-byte fields before assuming single-byte fields.

## Common Patterns

### Pressure Units

| Sensor Type | Raw Unit | To PSI | To bar |
|-------------|----------|--------|--------|
| TPMS3 | Pascals (32-bit) | `* 0.000145038` | `* 0.00001` |
| BR | 0.1 PSI (16-bit) | `/ 10.0` | `/ 10.0 * 0.0689476` |
| Most sensors | kPa (16-bit) | `* 0.145038` | `/ 100.0` |

All sensors report **absolute pressure**. Subtract 14.5 PSI (1 atm) for gauge pressure.

### Data Encoding

| Type | Example | Decoding |
|------|---------|----------|
| Direct | `0x1E` = 30C | `value` |
| Offset | `0x3E` = 22C | `value - 40` |
| Scaled | `0x1D` = 2.9V | `value / 10` |
| LE 16-bit | `52 0b` = 2898 | `byte0 \| (byte1 << 8)` |
| LE 32-bit | `f5 01 03 00` = 197109 | `b0 \| (b1<<8) \| (b2<<16) \| (b3<<24)` |
| Signed byte | `0xF0` = -16C | `value - 256 if value > 127` |

### Checksum Algorithms

| Type | Description |
|------|-------------|
| Sum | `sum(data[0:N]) & 0xFFFF` |
| XOR | `data[0] ^ data[1] ^ ...` |
| CRC-16 | Polynomial (use `crcmod`) |
| None | TPMS3 has no checksum |

## Tips

1. **Start with device name / company ID** - easiest identification
2. **Collect many samples** - you need variation to identify fields
3. **Consider multi-byte fields** - bytes that "change wildly" may be low-order bytes of a larger integer
4. **Check community sources** - Home Assistant, ESPHome, Arduino forums often have decoded formats
5. **Absolute vs gauge** - sensors read atmospheric pressure on a desk, which is expected and correct

## Useful References

- **Home Assistant ESPHome TPMS:** https://community.home-assistant.io/t/ble-tire-pressure-monitor/509927
- **bkbilly/tpms_ble:** https://github.com/bkbilly/tpms_ble
- **theengs/decoder:** https://decoder.theengs.io/devices/TPMS.html
- **ricallinson/tpms:** https://github.com/ricallinson/tpms
- **CRC Catalogue:** https://reveng.sourceforge.io/crc-catalogue/
- **rtl_433 TPMS:** https://github.com/merbanan/rtl_433/tree/master/src/devices
