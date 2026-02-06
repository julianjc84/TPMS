# TPMS Decoder System Guide

## Overview

The modular decoder system allows you to support **multiple TPMS sensor types** without modifying the core application. Each sensor type has its own decoder class that handles identification and data parsing.

## How It Works

```
BLE Device → Factory → Decoder Selection → Data Parsing → Standard Output
```

1. **Factory** receives device info (name, UUIDs, manufacturer data)
2. **Tries each decoder** in priority order
3. **First matching decoder** handles the data
4. **Returns standardized format** for display

## Built-in Decoders

| Decoder | Manufacturer | Data Length | Checksum | Notes |
|---------|--------------|-------------|----------|-------|
| BR-7byte | Generic BR | 7 bytes | 16-bit sum | Default sensor (0x27a5 UUID) |
| SYTPMS-6byte | SYTPMS | 6 bytes | XOR | Example alternative format |
| Generic | Unknown | 4+ bytes | None | Fallback with heuristics |

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
        return "Acme Corp"  # Manufacturer name

    def can_decode(self, device_name: str, service_uuids: list, mfdata: bytes) -> bool:
        """
        Identify your sensor.
        Return True if this decoder can handle the data.
        """
        # Method 1: Check device name
        if device_name == "ACME-TPMS":
            return True

        # Method 2: Check service UUID
        if service_uuids and "1234" in str(service_uuids).lower():
            return True

        # Method 3: Check data pattern
        if len(mfdata) == 8:  # Your specific length
            # Additional checks (e.g., first byte is always 0xFF)
            if mfdata[0] == 0xFF:
                return True

        return False

    def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
        """
        Parse your sensor's data format.

        MUST return dict with these fields:
        - status: int
        - battery: float (volts)
        - temperature: int (Celsius)
        - pressure_bar: float
        - pressure_psi: float
        - hex_data: str
        - decoder: str (self.name)
        - valid: bool (checksum OK)
        """
        if len(mfdata) < 8:
            return None

        # Your parsing logic
        status = mfdata[0]
        temperature = mfdata[1] - 40  # Example: offset encoding
        pressure_kpa = (mfdata[2] << 8) | mfdata[3]
        battery_raw = mfdata[4]

        # Convert to standard units
        battery = battery_raw / 10.0
        pressure_bar = pressure_kpa / 100.0
        pressure_psi = pressure_bar * 14.5038

        # Validate checksum (your algorithm)
        checksum_calc = sum(mfdata[0:7])
        valid = (checksum_calc & 0xFF) == mfdata[7]

        hex_data = ''.join(f'{b:02x}' for b in mfdata)

        return {
            'status': status,
            'battery': battery,
            'temperature': temperature,
            'pressure_bar': pressure_bar,
            'pressure_psi': pressure_psi,
            'hex_data': hex_data,
            'decoder': self.name,
            'valid': valid
        }
```

### Step 2: Register Decoder

In `sensor_decoders.py`, add to the factory:

```python
class TPMSDecoderFactory:
    def __init__(self):
        self.decoders = [
            BRTPMSDecoder(),
            SYTPMSDecoder(),
            MyTPMSDecoder(),      # ← Add your decoder here
            GenericTPMSDecoder(), # Always keep Generic last
        ]
```

### Step 3: Test Your Decoder

```bash
# Run the decoder test
python3 sensor_decoders.py

# Test with interactive tool
./run-interactive.sh
# Select option 5 to list decoders
# Select option 1 to discover devices
```

## Real-World Example: Reverse Engineering a New Sensor

### 1. Capture Raw Data

Run the tool with `SHOW_HEX_PACKETS = True` and collect packets:

```
Unknown Sensor: 85:c3:a2  HEX: ff1c0e01a5b3c8
Unknown Sensor: 85:c3:a2  HEX: ff1d0e01a6d2e9
Unknown Sensor: 85:c3:a2  HEX: ff1d0f01a7e1fa
```

### 2. Analyze Patterns

Compare multiple readings:

```
Packet 1: ff 1c 0e 01 a5 b3 c8
Packet 2: ff 1d 0e 01 a6 d2 e9
Packet 3: ff 1d 0f 01 a7 e1 fa
          │  │  │  └──┴── Changes (pressure?)
          │  │  └──────── Changes (temp?)
          │  └─────────── Changes (battery?)
          └────────────── Constant (status?)
```

### 3. Identify Fields

- Byte 0: `0xFF` constant → Status/header
- Byte 1: `0x1C→0x1D→0x1D` → Battery? Temperature?
- Byte 2: `0x0E→0x0E→0x0F` → Temperature? (14°C→15°C)
- Bytes 3-4: `0x01A5→0x01A6→0x01A7` → Pressure (421→422→423 = ~42 psi)
- Bytes 5-6: Varies → Checksum

### 4. Test Hypotheses

```python
def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
    # Hypothesis testing
    temp1 = mfdata[1]  # Try as direct temp
    temp2 = mfdata[2]  # Try as direct temp

    pressure_raw = (mfdata[3] << 8) | mfdata[4]
    pressure_psi = pressure_raw / 10.0  # Try different divisors

    print(f"Temp1: {temp1}°C, Temp2: {temp2}°C")
    print(f"Pressure: {pressure_psi} psi")
    # Compare with known values
```

### 5. Validate Checksum

Try common algorithms:

```python
# Method 1: Sum
checksum = sum(mfdata[0:5]) & 0xFFFF

# Method 2: XOR
checksum = mfdata[0] ^ mfdata[1] ^ mfdata[2] ^ mfdata[3] ^ mfdata[4]

# Method 3: CRC-16
import crcmod
crc16 = crcmod.predefined.Crc('crc-16')
crc16.update(mfdata[0:5])
checksum = crc16.crcValue

# Compare with bytes 5-6
received = (mfdata[5] << 8) | mfdata[6]
```

## Common Patterns

### Data Encoding

| Type | Example | Decoding |
|------|---------|----------|
| Direct | `0x1E` = 30°C | `value` |
| Offset | `0x3E` = 22°C | `value - 40` |
| Scaled | `0x1D` = 2.9V | `value / 10` |
| Big-endian 16-bit | `0x01A5` = 421 | `(byte1 << 8) \| byte2` |
| Signed byte | `0xF0` = -16°C | `value - 256 if value > 127` |

### Checksum Algorithms

| Type | Description | Example |
|------|-------------|---------|
| Sum | Add all bytes | `sum(data[0:5]) & 0xFFFF` |
| XOR | XOR all bytes | `data[0] ^ data[1] ^ ...` |
| CRC-16 | Polynomial checksum | `crcmod` library |
| None | No validation | Always `valid = True` |

## Pressure Conversion

Most sensors report **absolute pressure** in various units:

```python
# From kPa to bar
pressure_bar = pressure_kpa / 100.0

# From psi (absolute) to bar (relative)
pressure_rel_psi = pressure_abs_psi - 14.5  # Subtract atmospheric
pressure_bar = pressure_rel_psi * 0.0689476

# From bar (relative) to psi
pressure_psi = pressure_bar * 14.5038
```

## Tips

1. **Start with device name/UUID** - Easiest identification method
2. **Collect many samples** - Need variations to identify fields
3. **Test edge cases** - Low battery, temperature extremes, zero pressure
4. **Document your findings** - Add comments explaining the format
5. **Share discoveries** - Submit decoders for inclusion in the project

## Debugging

Enable detailed output:

```python
def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
    print(f"[{self.name}] Decoding: {mfdata.hex()}")
    # ... your code ...
    print(f"[{self.name}] Result: {result}")
    return result
```

## Example: Adding SYTPMS Support

See `SYTPMSDecoder` class in `sensor_decoders.py` for a complete example of an alternative format with:
- Different byte order
- XOR checksum
- Offset temperature encoding
- kPa pressure units

## Contributing

Found a new sensor type? Please contribute!

1. Create decoder class following the template
2. Test with real sensors
3. Document the protocol format
4. Submit a pull request or issue

## Reference

- **Bluetooth Assigned Numbers:** https://www.bluetooth.com/specifications/assigned-numbers/
- **CRC Algorithms:** https://reveng.sourceforge.io/crc-catalogue/
- **TPMS Protocols:** https://github.com/merbanan/rtl_433/tree/master/src/devices
