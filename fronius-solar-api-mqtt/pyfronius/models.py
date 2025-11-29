"""Data models for pyfronius."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class SensorValue:
    """Represents a sensor value with optional unit."""
    value: Any
    unit: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        if self.unit is not None:
            return {"value": self.value, "unit": self.unit}
        return {"value": self.value}


@dataclass
class LEDStatus:
    """LED status information."""
    color: str
    state: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary format."""
        return {"color": self.color, "state": self.state}


@dataclass
class DeviceDetails:
    """Common device details."""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    hardware: Optional[str] = None
    software: Optional[str] = None


@dataclass
class InverterInfo:
    """Inverter information from GetInverterInfo."""
    device_id: str
    device_type: int
    pv_power: float
    status_code: int
    unique_id: str
    custom_name: Optional[str] = None
    error_code: Optional[int] = None
    show: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None


@dataclass
class MeterData:
    """Smart meter data."""
    # Power measurements (W)
    power_real: Optional[float] = None
    power_real_phase_1: Optional[float] = None
    power_real_phase_2: Optional[float] = None
    power_real_phase_3: Optional[float] = None
    power_apparent: Optional[float] = None
    power_apparent_phase_1: Optional[float] = None
    power_apparent_phase_2: Optional[float] = None
    power_apparent_phase_3: Optional[float] = None
    power_reactive: Optional[float] = None
    power_reactive_phase_1: Optional[float] = None
    power_reactive_phase_2: Optional[float] = None
    power_reactive_phase_3: Optional[float] = None

    # Current measurements (A)
    current_ac_phase_1: Optional[float] = None
    current_ac_phase_2: Optional[float] = None
    current_ac_phase_3: Optional[float] = None

    # Voltage measurements (V)
    voltage_ac_phase_1: Optional[float] = None
    voltage_ac_phase_2: Optional[float] = None
    voltage_ac_phase_3: Optional[float] = None
    voltage_ac_phase_to_phase_12: Optional[float] = None
    voltage_ac_phase_to_phase_23: Optional[float] = None
    voltage_ac_phase_to_phase_31: Optional[float] = None

    # Frequency (Hz)
    frequency_phase_average: Optional[float] = None

    # Power factor
    power_factor: Optional[float] = None
    power_factor_phase_1: Optional[float] = None
    power_factor_phase_2: Optional[float] = None
    power_factor_phase_3: Optional[float] = None

    # Energy measurements (Wh)
    energy_real_consumed: Optional[float] = None
    energy_real_produced: Optional[float] = None
    energy_real_ac_minus: Optional[float] = None
    energy_real_ac_plus: Optional[float] = None
    energy_reactive_ac_consumed: Optional[float] = None
    energy_reactive_ac_produced: Optional[float] = None

    # Device info
    meter_location: Optional[int] = None
    enable: Optional[int] = None
    visible: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None


@dataclass
class InverterData:
    """Inverter realtime data."""
    # Energy (Wh)
    energy_day: Optional[float] = None
    energy_year: Optional[float] = None
    energy_total: Optional[float] = None

    # Power (W)
    power_ac: Optional[float] = None

    # AC measurements
    voltage_ac: Optional[float] = None
    current_ac: Optional[float] = None
    frequency_ac: Optional[float] = None

    # DC measurements (multiple MPPT inputs)
    voltage_dc: Optional[float] = None
    current_dc: Optional[float] = None
    voltage_dc_2: Optional[float] = None
    current_dc_2: Optional[float] = None

    # Status
    status_code: Optional[int] = None
    error_code: Optional[int] = None
    inverter_state: Optional[str] = None
    led_state: Optional[int] = None
    led_color: Optional[int] = None


@dataclass
class Inverter3PData:
    """Inverter 3-phase data."""
    current_ac_phase_1: Optional[float] = None
    current_ac_phase_2: Optional[float] = None
    current_ac_phase_3: Optional[float] = None
    voltage_ac_phase_1: Optional[float] = None
    voltage_ac_phase_2: Optional[float] = None
    voltage_ac_phase_3: Optional[float] = None


@dataclass
class PowerFlowData:
    """Power flow realtime data."""
    # Power values (W)
    power_grid: Optional[float] = None
    power_load: Optional[float] = None
    power_photovoltaics: Optional[float] = None
    power_battery: Optional[float] = None

    # Energy values (Wh)
    energy_day: Optional[float] = None
    energy_year: Optional[float] = None
    energy_total: Optional[float] = None

    # Percentages
    relative_autonomy: Optional[float] = None
    relative_self_consumption: Optional[float] = None

    # Battery
    state_of_charge: Optional[float] = None
    battery_mode: Optional[str] = None
    battery_standby: Optional[bool] = None
    backup_mode: Optional[bool] = None

    # Meter
    meter_location: Optional[str] = None
    meter_mode: Optional[str] = None


@dataclass
class StorageData:
    """Battery storage data."""
    # Capacity
    capacity_maximum: Optional[float] = None
    capacity_designed: Optional[float] = None

    # Electrical
    current_dc: Optional[float] = None
    voltage_dc: Optional[float] = None
    voltage_dc_maximum_cell: Optional[float] = None
    voltage_dc_minimum_cell: Optional[float] = None

    # State
    state_of_charge: Optional[float] = None
    temperature_cell: Optional[float] = None

    # Device info
    enable: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None


@dataclass
class OhmPilotData:
    """OhmPilot data."""
    error_code: Optional[int] = None
    state_code: Optional[int] = None
    state_message: Optional[str] = None
    energy_real_ac_consumed: Optional[float] = None
    power_real_ac: Optional[float] = None
    temperature_channel_1: Optional[float] = None

    # Device details
    hardware: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    software: Optional[str] = None


@dataclass
class LoggerInfo:
    """Logger/DataManager information."""
    hardware_version: Optional[str] = None
    software_version: Optional[str] = None
    hardware_platform: Optional[str] = None
    product_type: Optional[str] = None
    unique_identifier: Optional[str] = None
    time_zone: Optional[str] = None
    time_zone_location: Optional[str] = None
    utc_offset: Optional[int] = None
    co2_factor: Optional[float] = None
    cash_factor: Optional[float] = None
    delivery_factor: Optional[float] = None


@dataclass
class ActiveDeviceInfo:
    """Active device information."""
    inverters: List[Dict[str, Any]] = field(default_factory=list)
    meters: List[Dict[str, Any]] = field(default_factory=list)
    storages: List[Dict[str, Any]] = field(default_factory=list)
    ohmpilots: List[Dict[str, Any]] = field(default_factory=list)
    sensor_cards: List[Dict[str, Any]] = field(default_factory=list)
    string_controls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SystemInverterData:
    """System-wide inverter data."""
    energy_day: float = 0
    energy_year: float = 0
    energy_total: float = 0
    power_ac: float = 0
    inverters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
