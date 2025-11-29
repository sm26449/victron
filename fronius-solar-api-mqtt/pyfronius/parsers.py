"""Data parsers for Fronius Solar API responses."""

import logging
from html import unescape
from typing import Any, Callable, Dict, List, Optional, Tuple

from .const import INVERTER_DEVICE_TYPE, OHMPILOT_STATE_CODES
from .units import (
    AMPERE, DEGREE_CELSIUS, HERTZ, PERCENT, VOLT, VOLTAMPERE,
    VOLTAMPEREREACTIVE, VOLTAMPEREREACTIVE_HOUR, WATT, WATT_HOUR
)

_LOGGER = logging.getLogger(__name__)


# Type alias for the sensor dictionary format
SensorDict = Dict[str, Dict[str, Any]]


def _extract_value(
    data: Dict[str, Any],
    key: str,
    unit: Optional[str] = None,
    nested_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extract a value from data dictionary and format as sensor value.

    Args:
        data: Source dictionary
        key: Key to extract
        unit: Optional unit string
        nested_key: If set, extract from data[key][nested_key] instead

    Returns:
        Dictionary with 'value' and optional 'unit', or None if key not found
    """
    if key not in data:
        return None

    value = data[key]
    if nested_key is not None:
        if not isinstance(value, dict) or nested_key not in value:
            return None
        value = value[nested_key]

    if unit is not None:
        return {"value": value, "unit": unit}
    return {"value": value}


def _extract_with_unit(
    data: Dict[str, Any],
    key: str
) -> Optional[Dict[str, Any]]:
    """
    Extract a value that has its own Unit field (like inverter data).

    Args:
        data: Source dictionary
        key: Key to extract (expects data[key] = {"Value": x, "Unit": y})

    Returns:
        Dictionary with 'value' and 'unit', or None if key not found
    """
    if key not in data:
        return None

    item = data[key]
    if not isinstance(item, dict):
        return None

    return {
        "value": item.get("Value"),
        "unit": item.get("Unit")
    }


def _map_fields(
    data: Dict[str, Any],
    field_mapping: List[Tuple[str, str, Optional[str]]]
) -> SensorDict:
    """
    Map multiple fields from source data to sensor dictionary.

    Args:
        data: Source dictionary
        field_mapping: List of (source_key, dest_key, unit) tuples

    Returns:
        Dictionary of mapped sensor values
    """
    result: SensorDict = {}
    for source_key, dest_key, unit in field_mapping:
        value = _extract_value(data, source_key, unit)
        if value is not None:
            result[dest_key] = value
    return result


def _map_fields_with_unit(
    data: Dict[str, Any],
    field_mapping: List[Tuple[str, str]]
) -> SensorDict:
    """
    Map multiple fields that have embedded Unit fields.

    Args:
        data: Source dictionary
        field_mapping: List of (source_key, dest_key) tuples

    Returns:
        Dictionary of mapped sensor values
    """
    result: SensorDict = {}
    for source_key, dest_key in field_mapping:
        value = _extract_with_unit(data, source_key)
        if value is not None:
            result[dest_key] = value
    return result


# ============================================================================
# LED Data Parser
# ============================================================================

def parse_led_data(data: Dict[str, Any]) -> SensorDict:
    """Parse LED status data from GetLoggerLEDInfo."""
    _LOGGER.debug("Converting system led data: '%s'", data)
    sensor: SensorDict = {}

    led_mapping = {
        "PowerLED": "power_led",
        "SolarNetLED": "solar_net_led",
        "SolarWebLED": "solar_web_led",
        "WLANLED": "wlan_led",
    }

    for source_key, dest_key in led_mapping.items():
        if source_key in data:
            sensor[dest_key] = {
                "color": data[source_key]["Color"],
                "state": data[source_key]["State"],
            }

    return sensor


# ============================================================================
# Power Flow Parser
# ============================================================================

def parse_power_flow(data: Dict[str, Any]) -> SensorDict:
    """Parse power flow data from GetPowerFlowRealtimeData."""
    _LOGGER.debug("Converting system power flow data: '%s'", data)
    sensor: SensorDict = {}

    site = data.get("Site", {})
    inverters_data = data.get("Inverters", {})

    # Backwards compatibility - single inverter
    if inverters_data.get("1"):
        inverter = inverters_data["1"]
        if "Battery_Mode" in inverter:
            sensor["battery_mode"] = {"value": inverter["Battery_Mode"]}
        if "SOC" in inverter:
            sensor["state_of_charge"] = {"value": inverter["SOC"], "unit": PERCENT}

    # Multiple inverters
    for index, inverter in enumerate(inverters_data):
        if isinstance(inverter, dict):
            if "Battery_Mode" in inverter:
                sensor[f"battery_mode_{index}"] = {"value": inverter["Battery_Mode"]}
            if "SOC" in inverter:
                sensor[f"state_of_charge_{index}"] = {
                    "value": inverter["SOC"],
                    "unit": PERCENT
                }

    # Site data mapping
    site_mapping = [
        ("BackupMode", "backup_mode", None),
        ("BatteryStandby", "battery_standby", None),
        ("E_Day", "energy_day", WATT_HOUR),
        ("E_Total", "energy_total", WATT_HOUR),
        ("E_Year", "energy_year", WATT_HOUR),
        ("Meter_Location", "meter_location", None),
        ("Mode", "meter_mode", None),
        ("P_Akku", "power_battery", WATT),
        ("P_Grid", "power_grid", WATT),
        ("P_Load", "power_load", WATT),
        ("P_PV", "power_photovoltaics", WATT),
        ("rel_Autonomy", "relative_autonomy", PERCENT),
        ("rel_SelfConsumption", "relative_self_consumption", PERCENT),
    ]

    sensor.update(_map_fields(site, site_mapping))
    return sensor


# ============================================================================
# Meter Data Parsers
# ============================================================================

# Meter field mappings - (source_key, dest_key, unit)
METER_FIELD_MAPPING = [
    # Current
    ("Current_AC_Phase_1", "current_ac_phase_1", AMPERE),
    ("ACBRIDGE_CURRENT_ACTIVE_MEAN_01_F32", "current_ac_phase_1", AMPERE),
    ("Current_AC_Phase_2", "current_ac_phase_2", AMPERE),
    ("ACBRIDGE_CURRENT_ACTIVE_MEAN_02_F32", "current_ac_phase_2", AMPERE),
    ("Current_AC_Phase_3", "current_ac_phase_3", AMPERE),
    ("ACBRIDGE_CURRENT_ACTIVE_MEAN_03_F32", "current_ac_phase_3", AMPERE),
    # Energy reactive
    ("EnergyReactive_VArAC_Sum_Consumed", "energy_reactive_ac_consumed",
     VOLTAMPEREREACTIVE_HOUR),
    ("EnergyReactive_VArAC_Sum_Produced", "energy_reactive_ac_produced",
     VOLTAMPEREREACTIVE_HOUR),
    # Energy real
    ("EnergyReal_WAC_Minus_Absolute", "energy_real_ac_minus", WATT_HOUR),
    ("EnergyReal_WAC_Plus_Absolute", "energy_real_ac_plus", WATT_HOUR),
    ("EnergyReal_WAC_Sum_Consumed", "energy_real_consumed", WATT_HOUR),
    ("SMARTMETER_ENERGYACTIVE_CONSUMED_SUM_F64", "energy_real_consumed", WATT_HOUR),
    ("EnergyReal_WAC_Sum_Produced", "energy_real_produced", WATT_HOUR),
    ("SMARTMETER_ENERGYACTIVE_PRODUCED_SUM_F64", "energy_real_produced", WATT_HOUR),
    # Frequency
    ("Frequency_Phase_Average", "frequency_phase_average", HERTZ),
    # Power apparent
    ("PowerApparent_S_Phase_1", "power_apparent_phase_1", VOLTAMPERE),
    ("PowerApparent_S_Phase_2", "power_apparent_phase_2", VOLTAMPERE),
    ("PowerApparent_S_Phase_3", "power_apparent_phase_3", VOLTAMPERE),
    ("PowerApparent_S_Sum", "power_apparent", VOLTAMPERE),
    # Power factor
    ("PowerFactor_Phase_1", "power_factor_phase_1", None),
    ("PowerFactor_Phase_2", "power_factor_phase_2", None),
    ("PowerFactor_Phase_3", "power_factor_phase_3", None),
    ("PowerFactor_Sum", "power_factor", None),
    # Power reactive
    ("PowerReactive_Q_Phase_1", "power_reactive_phase_1", VOLTAMPEREREACTIVE),
    ("PowerReactive_Q_Phase_2", "power_reactive_phase_2", VOLTAMPEREREACTIVE),
    ("PowerReactive_Q_Phase_3", "power_reactive_phase_3", VOLTAMPEREREACTIVE),
    ("PowerReactive_Q_Sum", "power_reactive", VOLTAMPEREREACTIVE),
    # Power real
    ("PowerReal_P_Phase_1", "power_real_phase_1", WATT),
    ("SMARTMETER_POWERACTIVE_01_F64", "power_real_phase_1", WATT),
    ("PowerReal_P_Phase_2", "power_real_phase_2", WATT),
    ("SMARTMETER_POWERACTIVE_02_F64", "power_real_phase_2", WATT),
    ("PowerReal_P_Phase_3", "power_real_phase_3", WATT),
    ("SMARTMETER_POWERACTIVE_03_F64", "power_real_phase_3", WATT),
    ("PowerReal_P_Sum", "power_real", WATT),
    # Voltage phase
    ("Voltage_AC_Phase_1", "voltage_ac_phase_1", VOLT),
    ("Voltage_AC_Phase_2", "voltage_ac_phase_2", VOLT),
    ("Voltage_AC_Phase_3", "voltage_ac_phase_3", VOLT),
    # Voltage phase to phase
    ("Voltage_AC_PhaseToPhase_12", "voltage_ac_phase_to_phase_12", VOLT),
    ("Voltage_AC_PhaseToPhase_23", "voltage_ac_phase_to_phase_23", VOLT),
    ("Voltage_AC_PhaseToPhase_31", "voltage_ac_phase_to_phase_31", VOLT),
    # Other
    ("Meter_Location_Current", "meter_location", None),
    ("Enable", "enable", None),
    ("Visible", "visible", None),
]


def parse_meter_data(data: Dict[str, Any]) -> SensorDict:
    """Parse meter data from GetMeterRealtimeData (device scope)."""
    _LOGGER.debug("Converting meter data: '%s'", data)
    meter = _map_fields(data, METER_FIELD_MAPPING)

    # Handle nested Details
    if "Details" in data:
        details = data["Details"]
        if "Manufacturer" in details:
            meter["manufacturer"] = {"value": details["Manufacturer"]}
        if "Model" in details:
            meter["model"] = {"value": details["Model"]}
        if "Serial" in details:
            meter["serial"] = {"value": details["Serial"]}

    return meter


def parse_system_meter_data(data: Dict[str, Any]) -> SensorDict:
    """Parse system meter data from GetMeterRealtimeData (system scope)."""
    _LOGGER.debug("Converting system meter data: '%s'", data)
    sensor: SensorDict = {"meters": {}}

    for device_id, device_data in data.items():
        sensor["meters"][device_id] = parse_meter_data(device_data)

    return sensor


# ============================================================================
# Inverter Data Parsers
# ============================================================================

# Inverter common data field mappings - uses embedded Unit
INVERTER_COMMON_MAPPING = [
    ("DAY_ENERGY", "energy_day"),
    ("TOTAL_ENERGY", "energy_total"),
    ("YEAR_ENERGY", "energy_year"),
    ("FAC", "frequency_ac"),
    ("IAC", "current_ac"),
    ("IDC", "current_dc"),
    ("PAC", "power_ac"),
    ("UAC", "voltage_ac"),
    ("UDC", "voltage_dc"),
]


def parse_inverter_data(data: Dict[str, Any]) -> SensorDict:
    """Parse inverter data from GetInverterRealtimeData (device scope)."""
    _LOGGER.debug("Converting inverter data from '%s'", data)
    sensor = _map_fields_with_unit(data, INVERTER_COMMON_MAPPING)

    # Handle multiple DC inputs (IDC_2 through IDC_9, UDC_2 through UDC_9)
    for i in range(2, 10):
        idc_key = f"IDC_{i}"
        udc_key = f"UDC_{i}"
        if idc_key in data:
            sensor[f"current_dc_{i}"] = _extract_with_unit(data, idc_key)
        if udc_key in data:
            sensor[f"voltage_dc_{i}"] = _extract_with_unit(data, udc_key)

    # Handle DeviceStatus
    if "DeviceStatus" in data:
        status = data["DeviceStatus"]
        status_mapping = [
            ("InverterState", "inverter_state", None),
            ("ErrorCode", "error_code", None),
            ("StatusCode", "status_code", None),
            ("LEDState", "led_state", None),
            ("LEDColor", "led_color", None),
        ]
        sensor.update(_map_fields(status, status_mapping))

    return sensor


def parse_inverter_3p_data(data: Dict[str, Any]) -> SensorDict:
    """Parse inverter 3-phase data."""
    _LOGGER.debug("Converting inverter 3p data from '%s'", data)

    mapping = [
        ("IAC_L1", "current_ac_phase_1"),
        ("IAC_L2", "current_ac_phase_2"),
        ("IAC_L3", "current_ac_phase_3"),
        ("UAC_L1", "voltage_ac_phase_1"),
        ("UAC_L2", "voltage_ac_phase_2"),
        ("UAC_L3", "voltage_ac_phase_3"),
    ]

    return _map_fields_with_unit(data, mapping)


def parse_system_inverter_data(data: Dict[str, Any]) -> SensorDict:
    """Parse system inverter data from GetInverterRealtimeData (system scope)."""
    _LOGGER.debug("Converting system inverter data: '%s'", data)
    sensor: SensorDict = {
        "energy_day": {"value": 0, "unit": WATT_HOUR},
        "energy_total": {"value": 0, "unit": WATT_HOUR},
        "energy_year": {"value": 0, "unit": WATT_HOUR},
        "power_ac": {"value": 0, "unit": WATT},
        "inverters": {},
    }

    data_keys = [
        ("DAY_ENERGY", "energy_day"),
        ("TOTAL_ENERGY", "energy_total"),
        ("YEAR_ENERGY", "energy_year"),
        ("PAC", "power_ac"),
    ]

    for source_key, dest_key in data_keys:
        if source_key not in data:
            continue

        values_data = data[source_key]
        unit = values_data.get("Unit", WATT_HOUR if "ENERGY" in source_key else WATT)

        for inv_id, value in values_data.get("Values", {}).items():
            if inv_id not in sensor["inverters"]:
                sensor["inverters"][inv_id] = {}
            sensor["inverters"][inv_id][dest_key] = {"value": value, "unit": unit}
            sensor[dest_key]["value"] += value or 0

    return sensor


# ============================================================================
# Storage Data Parsers
# ============================================================================

STORAGE_CONTROLLER_MAPPING = [
    ("Capacity_Maximum", "capacity_maximum", "Ah"),
    ("DesignedCapacity", "capacity_designed", "Ah"),
    ("Current_DC", "current_dc", AMPERE),
    ("Voltage_DC", "voltage_dc", VOLT),
    ("Voltage_DC_Maximum_Cell", "voltage_dc_maximum_cell", VOLT),
    ("Voltage_DC_Minimum_Cell", "voltage_dc_minimum_cell", VOLT),
    ("StateOfCharge_Relative", "state_of_charge", PERCENT),
    ("Temperature_Cell", "temperature_cell", DEGREE_CELSIUS),
    ("Enable", "enable", None),
]

STORAGE_MODULE_EXTRA_MAPPING = [
    ("Temperature_Cell_Maximum", "temperature_cell_maximum", DEGREE_CELSIUS),
    ("Temperature_Cell_Minimum", "temperature_cell_minimum", DEGREE_CELSIUS),
    ("CycleCount_BatteryCell", "cycle_count_cell", None),
    ("Status_BatteryCell", "status_cell", None),
]


def _parse_storage_details(data: Dict[str, Any], result: SensorDict) -> None:
    """Parse storage device details."""
    if "Details" in data:
        details = data["Details"]
        if "Manufacturer" in details:
            result["manufacturer"] = {"value": details["Manufacturer"]}
        if "Model" in details:
            result["model"] = {"value": details["Model"]}
        if "Serial" in details:
            result["serial"] = {"value": details["Serial"]}


def parse_controller_data(data: Dict[str, Any]) -> SensorDict:
    """Parse storage controller data."""
    controller = _map_fields(data, STORAGE_CONTROLLER_MAPPING)
    _parse_storage_details(data, controller)
    return controller


def parse_module_data(data: Dict[str, Any]) -> SensorDict:
    """Parse storage module data."""
    module = _map_fields(data, STORAGE_CONTROLLER_MAPPING + STORAGE_MODULE_EXTRA_MAPPING)
    _parse_storage_details(data, module)
    return module


def parse_storage_data(data: Dict[str, Any]) -> SensorDict:
    """Parse storage data from GetStorageRealtimeData (device scope)."""
    _LOGGER.debug("Converting storage data from '%s'", data)
    sensor: SensorDict = {}

    if "Controller" in data:
        sensor.update(parse_controller_data(data["Controller"]))

    if "Modules" in data:
        sensor["modules"] = {}
        for idx, module in enumerate(data["Modules"]):
            sensor["modules"][idx] = parse_module_data(module)

    return sensor


def parse_system_storage_data(data: Dict[str, Any]) -> SensorDict:
    """Parse system storage data from GetStorageRealtimeData (system scope)."""
    _LOGGER.debug("Converting system storage data: '%s'", data)
    sensor: SensorDict = {"storages": {}}

    for device_id, device_data in data.items():
        sensor["storages"][device_id] = parse_storage_data(device_data)

    return sensor


# ============================================================================
# OhmPilot Data Parser
# ============================================================================

def parse_ohmpilot_data(data: Dict[str, Any]) -> SensorDict:
    """Parse OhmPilot data."""
    _LOGGER.debug("Converting ohmpilot data from '%s'", data)
    device: SensorDict = {}

    if "CodeOfError" in data:
        device["error_code"] = {"value": data["CodeOfError"]}

    if "CodeOfState" in data:
        state_code = data["CodeOfState"]
        device["state_code"] = {"value": state_code}
        device["state_message"] = {
            "value": OHMPILOT_STATE_CODES.get(state_code, "Unknown")
        }

    if "Details" in data:
        details = data["Details"]
        for key in ["Hardware", "Manufacturer", "Model", "Serial", "Software"]:
            if key in details:
                device[key.lower()] = {"value": details[key]}

    energy_power_mapping = [
        ("EnergyReal_WAC_Sum_Consumed", "energy_real_ac_consumed", WATT_HOUR),
        ("PowerReal_PAC_Sum", "power_real_ac", WATT),
        ("Temperature_Channel_1", "temperature_channel_1", DEGREE_CELSIUS),
    ]
    device.update(_map_fields(data, energy_power_mapping))

    return device


def parse_system_ohmpilot_data(data: Dict[str, Any]) -> SensorDict:
    """Parse system OhmPilot data."""
    _LOGGER.debug("Converting system ohmpilot data: '%s'", data)
    sensor: SensorDict = {"ohmpilots": {}}

    for device_id, device_data in data.items():
        sensor["ohmpilots"][device_id] = parse_ohmpilot_data(device_data)

    return sensor


# ============================================================================
# Active Device Info Parser
# ============================================================================

def parse_active_device_info(data: Dict[str, Any]) -> SensorDict:
    """Parse active device info from GetActiveDeviceInfo."""
    _LOGGER.debug("Converting system active device data: '%s'", data)
    sensor: SensorDict = {}

    device_types = [
        ("Inverter", "inverters", ["DT", "Serial"]),
        ("Meter", "meters", ["Serial"]),
        ("Ohmpilot", "ohmpilots", ["Serial"]),
        ("Storage", "storages", ["Serial"]),
        ("StringControl", "string_controls", ["Serial"]),
    ]

    for source_key, dest_key, extra_fields in device_types:
        if source_key not in data:
            continue

        devices = []
        for device_id, device in data[source_key].items():
            device_info: Dict[str, Any] = {"device_id": device_id}
            if "DT" in extra_fields and "DT" in device:
                device_info["device_type"] = device["DT"]
            if "Serial" in device:
                device_info["serial_number"] = device["Serial"]
            devices.append(device_info)
        sensor[dest_key] = devices

    # Special handling for SensorCard (has ChannelNames)
    if "SensorCard" in data:
        sensor_cards = []
        for device_id, device in data["SensorCard"].items():
            sensor_card: Dict[str, Any] = {
                "device_id": device_id,
                "device_type": device.get("DT"),
            }
            if "Serial" in device:
                sensor_card["serial_number"] = device["Serial"]
            if "ChannelNames" in device:
                sensor_card["channel_names"] = [
                    name.lower().replace(" ", "_")
                    for name in device["ChannelNames"]
                ]
            sensor_cards.append(sensor_card)
        sensor["sensor_cards"] = sensor_cards

    return sensor


# ============================================================================
# Inverter Info Parser
# ============================================================================

def parse_inverter_info(data: Dict[str, Any]) -> SensorDict:
    """Parse inverter info from GetInverterInfo."""
    _LOGGER.debug("Converting inverter info: '%s'", data)
    inverters = []

    for inverter_index, inverter_info in data.items():
        inverter: Dict[str, Any] = {
            "device_id": {"value": inverter_index},
            "device_type": {"value": inverter_info["DT"]},
            "pv_power": {"value": inverter_info["PVPower"], "unit": WATT},
            "status_code": {"value": inverter_info["StatusCode"]},
            "unique_id": {"value": inverter_info["UniqueID"]},
        }

        # Add manufacturer and model if known
        if inverter_info["DT"] in INVERTER_DEVICE_TYPE:
            inverter["device_type"].update(INVERTER_DEVICE_TYPE[inverter_info["DT"]])

        # Optional fields
        if "CustomName" in inverter_info:
            inverter["custom_name"] = {"value": unescape(inverter_info["CustomName"])}
        if "ErrorCode" in inverter_info:
            inverter["error_code"] = {"value": inverter_info["ErrorCode"]}
        if "Show" in inverter_info:
            inverter["show"] = {"value": inverter_info["Show"]}

        inverters.append(inverter)

    return {"inverters": inverters}


# ============================================================================
# Logger Info Parser
# ============================================================================

def parse_logger_info(data: Dict[str, Any]) -> SensorDict:
    """Parse logger info from GetLoggerInfo."""
    _LOGGER.debug("Converting Logger info: '%s'", data)
    sensor: SensorDict = {}

    # CO2 factor with unit
    if "CO2Factor" in data and "CO2Unit" in data:
        co2_unit = unescape(data["CO2Unit"])
        sensor["co2_factor"] = {
            "value": data["CO2Factor"],
            "unit": f"{co2_unit}/kWh",
        }

    # Cash-related with currency
    if "CashCurrency" in data:
        cash_currency = unescape(data["CashCurrency"])
        if "CashFactor" in data:
            sensor["cash_factor"] = {
                "value": data["CashFactor"],
                "unit": f"{cash_currency}/kWh",
            }
        if "DeliveryFactor" in data:
            sensor["delivery_factor"] = {
                "value": data["DeliveryFactor"],
                "unit": f"{cash_currency}/kWh",
            }

    # Simple string/int fields
    simple_mapping = [
        ("HWVersion", "hardware_version", None),
        ("SWVersion", "software_version", None),
        ("PlatformID", "hardware_platform", None),
        ("ProductID", "product_type", None),
        ("TimezoneLocation", "time_zone_location", None),
        ("TimezoneName", "time_zone", None),
        ("UTCOffset", "utc_offset", None),
        ("UniqueID", "unique_identifier", None),
    ]
    sensor.update(_map_fields(data, simple_mapping))

    return sensor
