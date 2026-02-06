#!/usr/bin/env python3
"""
TPMS Sensor Decoder Library

Modular system for decoding different TPMS sensor protocols.
Add new sensor types by creating decoder classes.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

# Pressure conversion constants
ATM_PSI = 14.5       # Atmospheric pressure in PSI
PSI_TO_BAR = 0.0689476  # 1 PSI in BAR


def to_hex(data: bytes) -> str:
    """Convert bytes to hex string."""
    return data.hex()


def signed_byte(val: int) -> int:
    """Convert unsigned byte (0-255) to signed (-128 to 127)."""
    return val - 256 if val > 127 else val


def uuid_in_list(uuid: str, service_uuids: list) -> bool:
    """Check if a UUID string appears in a list of service UUIDs."""
    uuid_lower = uuid.lower()
    return any(uuid_lower in str(u).lower() for u in service_uuids)


class TPMSDecoder(ABC):
    """Base class for TPMS sensor decoders."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Decoder name."""
        pass

    @property
    @abstractmethod
    def manufacturer(self) -> str:
        """Sensor manufacturer."""
        pass

    @abstractmethod
    def can_decode(self, device_name: str, service_uuids: list, mfdata: bytes) -> bool:
        """
        Check if this decoder can handle the given sensor data.

        Args:
            device_name: BLE device name
            service_uuids: List of advertised service UUIDs
            mfdata: Manufacturer data bytes

        Returns:
            True if this decoder can handle this sensor
        """
        pass

    @abstractmethod
    def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
        """
        Decode manufacturer data into standardized sensor readings.

        Args:
            mfdata: Manufacturer data bytes

        Returns:
            Dict with keys: status, battery, temperature, pressure_bar,
            pressure_psi, hex_data, decoder, valid. Or None if invalid.
        """
        pass


class BRTPMSDecoder(TPMSDecoder):
    """
    Decoder for "BR" brand TPMS sensors.

    Protocol: SS BB TT PP PP CC CC (7 bytes)
    - SS: Status byte (ARSB2H1y flags)
    - BB: Battery (1/10 V)
    - TT: Temperature (°C, signed)
    - PPPP: Absolute pressure (1/10 psi, big-endian)
    - CCCC: Checksum (16-bit sum, big-endian)

    Service UUID: 0x27a5
    Device Name: "BR"
    """

    @property
    def name(self) -> str:
        return "BR-7byte"

    @property
    def manufacturer(self) -> str:
        return "Generic BR"

    def can_decode(self, device_name: str, service_uuids: list, mfdata: bytes) -> bool:
        if device_name == "BR":
            return True
        if service_uuids and uuid_in_list("27a5", service_uuids):
            return True
        # Only match on length if data also looks plausible (battery < 5V)
        if len(mfdata) == 7 and 0 < mfdata[1] < 50:
            return True
        return False

    def _validate_checksum(self, data: bytes) -> bool:
        calculated = sum(data[0:5]) & 0xFFFF
        received = (data[5] << 8) | data[6]
        return calculated == received

    def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
        if len(mfdata) < 7:
            return None

        valid = self._validate_checksum(mfdata)
        if not valid:
            return None

        status = mfdata[0]
        battery = mfdata[1] / 10.0
        temperature = signed_byte(mfdata[2])
        pressure_raw = (mfdata[3] << 8) | mfdata[4]
        pressure_abs_psi = pressure_raw / 10.0
        pressure_psi = pressure_abs_psi - ATM_PSI
        pressure_bar = pressure_psi * PSI_TO_BAR

        return {
            'status': status,
            'battery': battery,
            'temperature': temperature,
            'pressure_bar': pressure_bar,
            'pressure_psi': pressure_psi,
            'hex_data': to_hex(mfdata),
            'decoder': self.name,
            'valid': valid,
        }


class SYTPMSDecoder(TPMSDecoder):
    """
    Decoder for SYTPMS sensors (alternative format).

    Protocol: TT PP PP BB SS CC (6 bytes)
    - TT: Temperature (°C + 40 offset)
    - PPPP: Pressure (kPa, big-endian)
    - BB: Battery percentage (0-100)
    - SS: Status flags
    - CC: XOR checksum

    Service UUID: 0xfbb0
    Device Name: "TPMS" or "SY-TPMS"
    """

    @property
    def name(self) -> str:
        return "SYTPMS-6byte"

    @property
    def manufacturer(self) -> str:
        return "SYTPMS"

    def can_decode(self, device_name: str, service_uuids: list, mfdata: bytes) -> bool:
        if device_name and "TPMS" in device_name.upper() and len(mfdata) == 6:
            return True
        if service_uuids and uuid_in_list("fbb0", service_uuids):
            return True
        return False

    def _validate_checksum(self, data: bytes) -> bool:
        calculated = data[0] ^ data[1] ^ data[2] ^ data[3] ^ data[4]
        return calculated == data[5]

    def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
        if len(mfdata) < 6:
            return None

        valid = self._validate_checksum(mfdata)
        if not valid:
            return None

        temperature = mfdata[0] - 40
        pressure_kpa = (mfdata[1] << 8) | mfdata[2]
        battery_pct = mfdata[3]
        status = mfdata[4]

        pressure_bar = pressure_kpa / 100.0
        pressure_psi = pressure_bar / PSI_TO_BAR
        battery = 3.0 * (battery_pct / 100.0)

        return {
            'status': status,
            'battery': battery,
            'temperature': temperature,
            'pressure_bar': pressure_bar,
            'pressure_psi': pressure_psi,
            'hex_data': to_hex(mfdata),
            'decoder': self.name,
            'valid': valid,
        }


class GenericTPMSDecoder(TPMSDecoder):
    """
    Fallback decoder for unknown TPMS sensors.
    Attempts heuristic extraction - values may be incorrect.
    """

    @property
    def name(self) -> str:
        return "Generic"

    @property
    def manufacturer(self) -> str:
        return "Unknown"

    def can_decode(self, device_name: str, service_uuids: list, mfdata: bytes) -> bool:
        return len(mfdata) >= 4

    def decode(self, mfdata: bytes) -> Optional[Dict[str, Any]]:
        if len(mfdata) < 4:
            return None

        # Scan for pressure-like 16-bit values (plausible psi range)
        pressure_psi = 0.0
        pressure_bar = 0.0
        for i in range(len(mfdata) - 1):
            value = (mfdata[i] << 8) | mfdata[i + 1]
            if 100 < value < 800:  # 10-80 psi absolute
                pressure_psi = (value / 10.0) - ATM_PSI
                pressure_bar = pressure_psi * PSI_TO_BAR
                break

        # Best-effort field extraction
        temperature = mfdata[0] if mfdata[0] < 100 else 0
        battery = mfdata[1] / 10.0 if mfdata[1] < 50 else 0.0

        return {
            'status': mfdata[0],
            'battery': battery,
            'temperature': temperature,
            'pressure_bar': pressure_bar,
            'pressure_psi': pressure_psi,
            'hex_data': to_hex(mfdata),
            'decoder': self.name,
            'valid': False,
            'warning': 'Generic decoder - values may be incorrect',
        }


class TPMSDecoderFactory:
    """
    Factory for managing and selecting TPMS decoders.

    Usage:
        factory = TPMSDecoderFactory()
        decoder = factory.get_decoder(device_name, service_uuids, mfdata)
        result = decoder.decode(mfdata)
    """

    def __init__(self):
        self.decoders: List[TPMSDecoder] = [
            BRTPMSDecoder(),
            SYTPMSDecoder(),
            GenericTPMSDecoder(),  # Always last (fallback)
        ]

    def add_decoder(self, decoder: TPMSDecoder):
        """Add a custom decoder (inserted before the Generic fallback)."""
        self.decoders.insert(-1, decoder)

    def get_decoder(self, device_name: str, service_uuids: list, mfdata: bytes) -> TPMSDecoder:
        """Select the best matching decoder for the given sensor data."""
        for decoder in self.decoders:
            if decoder.can_decode(device_name, service_uuids, mfdata):
                return decoder
        return self.decoders[-1]

    def list_decoders(self) -> List[tuple]:
        """Get list of (name, manufacturer) for all decoders."""
        return [(d.name, d.manufacturer) for d in self.decoders]


if __name__ == "__main__":
    factory = TPMSDecoderFactory()

    print("Available decoders:")
    for name, manufacturer in factory.list_decoders():
        print(f"  - {name} ({manufacturer})")

    # Test BR decoder - construct a packet with valid checksum
    # Fields: status=0x28, battery=0x1d, temp=0x13, pressure=0x0105
    # Checksum = sum(0x28+0x1d+0x13+0x01+0x05) = 0x005e
    test_data = bytes.fromhex("281d130105005e")
    print(f"\nTest BR sensor packet: {test_data.hex()}")
    decoder = factory.get_decoder("BR", ["27a5"], test_data)
    print(f"  Decoder:     {decoder.name}")
    result = decoder.decode(test_data)
    if result:
        print(f"  Pressure:    {result['pressure_bar']:.2f} bar ({result['pressure_psi']:.1f} psi)")
        print(f"  Temperature: {result['temperature']}C")
        print(f"  Battery:     {result['battery']:.1f}V")
        print(f"  Status:      0x{result['status']:02x}")
        print(f"  Checksum:    {'PASS' if result['valid'] else 'FAIL'}")
    else:
        print("  Decode failed (invalid checksum or data)")

    # Note: Real-world packets (e.g., 281d130105a376 from README) may use
    # a different checksum algorithm. The simple-sum method needs validation
    # against live sensor data. See PROTOCOL.md for details.
