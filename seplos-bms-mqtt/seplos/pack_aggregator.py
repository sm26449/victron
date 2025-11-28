"""
Pack Aggregator - calculates aggregate values for entire battery pack
"""

import time
import json
from .logging_setup import get_logger


class PackAggregator:
    """
    Pack Aggregator class - calculates aggregate values for entire battery pack

    Features:
    - Aggregates data from multiple batteries
    - Calculates pack totals, averages, min/max values
    - MQTT autodiscovery for Home Assistant
    - Optional InfluxDB integration
    """

    def __init__(self, mqtt_manager, mqtt_prefix, influxdb_manager=None):
        self.mqtt = mqtt_manager
        self.mqtt_prefix = mqtt_prefix
        self.influxdb = influxdb_manager
        self.batteries = {}
        self.pack_declared = False
        self.last_publish_time = 0
        self.publish_interval = 2
        self.log = get_logger()

    def update_battery_data(self, batt_id, data_type, value):
        """Update stored data for a battery"""
        if batt_id not in self.batteries:
            self.batteries[batt_id] = {}
        self.batteries[batt_id][data_type] = value
        self.batteries[batt_id]['last_update'] = time.time()

    def get_battery_data(self, batt_id):
        """Get all data for a specific battery"""
        return self.batteries.get(batt_id, {})

    def get_all_batteries(self):
        """Get all battery data"""
        return self.batteries

    def get_online_batteries(self, timeout=60):
        """Get batteries that have been updated within timeout seconds"""
        current_time = time.time()
        return {k: v for k, v in self.batteries.items()
                if current_time - v.get('last_update', 0) < timeout}

    def get_stale_batteries(self, timeout=120):
        """Get batteries that haven't been updated within timeout seconds"""
        current_time = time.time()
        return {k: v for k, v in self.batteries.items()
                if current_time - v.get('last_update', 0) >= timeout}

    def autodiscovery_pack(self):
        """Send MQTT autodiscovery for pack aggregate sensors"""
        if self.pack_declared:
            return

        self.log.info("Sending autodiscovery block for Pack Aggregate")

        sensors = [
            # Voltage & Current
            ("voltage", "measurement", "V", "Pack Total Voltage"),
            ("current", "measurement", "A", "Pack Total Current"),
            ("power", "measurement", "W", "Pack Total Power"),
            # Capacity & Energy
            ("", "measurement", "Ah", "Pack Total Capacity"),
            ("", "measurement", "Ah", "Pack Remaining Capacity"),
            ("energy", "measurement", "kWh", "Pack Energy Remaining"),
            ("energy", "measurement", "kWh", "Pack Energy To Full"),
            # SOC
            ("", "measurement", "%", "Pack Average SOC"),
            ("", "measurement", "%", "Pack Min SOC"),
            ("", "measurement", "%", "Pack Max SOC"),
            ("", "measurement", "%", "Pack SOC Spread"),
            # Cell Voltages (global)
            ("voltage", "measurement", "V", "Pack Min Cell Voltage"),
            ("voltage", "measurement", "V", "Pack Max Cell Voltage"),
            ("voltage", "measurement", "mV", "Pack Cell Delta"),
            ("voltage", "measurement", "V", "Pack Avg Cell Voltage"),
            # Temperatures (global)
            ("temperature", "measurement", "°C", "Pack Min Temp"),
            ("temperature", "measurement", "°C", "Pack Max Temp"),
            ("temperature", "measurement", "°C", "Pack Avg Temp"),
            # Status & Health
            ("", "measurement", "", "Pack Batteries Online"),
            ("", "measurement", "", "Pack Total Alarms"),
            ("", "measurement", "", "Pack Total Protections"),
            ("", "measurement", "cycles", "Pack Max Cycles"),
            ("", "measurement", "%", "Pack Min SOH"),
            ("", "", "", "Pack Status"),
            # Balancing
            ("", "measurement", "", "Pack Balancing Cells"),
            # Current limits
            ("current", "measurement", "A", "Pack Max Discharge Current"),
            ("current", "measurement", "A", "Pack Max Charge Current"),
        ]

        for dev_cla, state_class, unit, name in sensors:
            self._autodiscovery_sensor(dev_cla, state_class, unit, name)

        self.mqtt.publish(f"{self.mqtt_prefix}/pack/state", "online", retain=True)
        self.pack_declared = True
        self.log.info("Pack Aggregate autodiscovery complete")

    def _autodiscovery_sensor(self, dev_cla, state_class, sensor_unit, sensor_name):
        """Send autodiscovery for a single pack sensor"""
        name_under = sensor_name.lower().replace(' ', '_')

        mqtt_packet = {
            "name": sensor_name,
            "stat_t": f"{self.mqtt_prefix}/pack/{name_under}",
            "avty_t": f"{self.mqtt_prefix}/pack/state",
            "uniq_id": f"seplos_{name_under}",
            "dev": {
                "ids": "seplos_pack",
                "name": "Seplos Battery Pack",
                "sw": "seplos-bms-mqtt 2.4",
                "mdl": "Seplos Pack Aggregate",
                "mf": "Seplos"
            },
            "origin": {
                "name": "seplos-bms-mqtt",
                "sw": "2.4",
                "url": "https://github.com/sm2669/seplos-bms-mqtt"
            }
        }

        if dev_cla:
            mqtt_packet["dev_cla"] = dev_cla
        if state_class:
            mqtt_packet["stat_cla"] = state_class
        if sensor_unit:
            mqtt_packet["unit_of_meas"] = sensor_unit

        self.mqtt.publish(f"homeassistant/sensor/seplos_pack/{name_under}/config",
                         json.dumps(mqtt_packet), retain=True)

    def calculate_and_publish(self):
        """Calculate aggregate values and publish to MQTT"""
        current_time = time.time()
        if current_time - self.last_publish_time < self.publish_interval:
            return

        online_batts = self.get_online_batteries()
        if not online_batts:
            return

        # Ensure autodiscovery is sent
        if not self.pack_declared:
            self.autodiscovery_pack()

        self.last_publish_time = current_time
        num_batteries = len(online_batts)

        # Collect values
        voltages = [b.get('pack_voltage', 0) for b in online_batts.values() if b.get('pack_voltage')]
        currents = [b.get('current', 0) for b in online_batts.values() if 'current' in b]
        powers = [b.get('power', 0) for b in online_batts.values() if 'power' in b]
        socs = [b.get('soc', 0) for b in online_batts.values() if b.get('soc')]
        sohs = [b.get('soh', 0) for b in online_batts.values() if b.get('soh')]
        remaining_caps = [b.get('remaining_capacity', 0) for b in online_batts.values() if b.get('remaining_capacity')]
        total_caps = [b.get('total_capacity', 0) for b in online_batts.values() if b.get('total_capacity')]
        cycles_list = [b.get('cycles', 0) for b in online_batts.values() if b.get('cycles')]

        # Cell voltages from all batteries
        all_cell_voltages = []
        for b in online_batts.values():
            for i in range(1, 17):
                cell_v = b.get(f'cell_{i}')
                if cell_v and cell_v > 0:
                    all_cell_voltages.append(cell_v)

        # All temperatures
        all_temps = []
        for b in online_batts.values():
            for key in ['cell_temp_1', 'cell_temp_2', 'cell_temp_3', 'cell_temp_4',
                       'ambient_temp', 'min_cell_temp', 'max_cell_temp']:
                temp = b.get(key)
                if temp is not None and -40 < temp < 100:
                    all_temps.append(temp)

        # Alarms and protections
        alarm_counts = [b.get('alarm_count', 0) for b in online_batts.values()]
        protection_counts = [b.get('protection_count', 0) for b in online_batts.values()]
        balancing_counts = [b.get('balancing_count', 0) for b in online_batts.values()]

        # Max currents
        max_discharge_curts = [b.get('maxdiscurt', 0) for b in online_batts.values() if b.get('maxdiscurt')]
        max_charge_curts = [b.get('maxchgcurt', 0) for b in online_batts.values() if b.get('maxchgcurt')]

        # Status determination
        statuses = [b.get('status', '') for b in online_batts.values()]
        pack_status = "Standby"
        if any(s == "Charge" for s in statuses):
            pack_status = "Charging"
        elif any(s == "Discharge" for s in statuses):
            pack_status = "Discharging"
        elif any(s == "Floating charge" for s in statuses):
            pack_status = "Float Charging"

        # Publish aggregates
        prefix = f"{self.mqtt_prefix}/pack"

        # Batteries online
        self.mqtt.publish_if_changed(f"{prefix}/pack_batteries_online", num_batteries)

        # Voltage (average - batteries are in parallel)
        avg_voltage = 0
        if voltages:
            avg_voltage = round(sum(voltages) / len(voltages), 2)
            self.mqtt.publish_if_changed(f"{prefix}/pack_total_voltage", avg_voltage)

        # Current & Power (sum - batteries in parallel)
        total_remaining = 0
        if currents:
            total_current = round(sum(currents), 2)
            self.mqtt.publish_if_changed(f"{prefix}/pack_total_current", total_current)
        if powers:
            total_power = int(sum(powers))
            self.mqtt.publish_if_changed(f"{prefix}/pack_total_power", total_power)

        # Capacity (sum)
        if total_caps:
            self.mqtt.publish_if_changed(f"{prefix}/pack_total_capacity", round(sum(total_caps), 2))
        if remaining_caps:
            total_remaining = sum(remaining_caps)
            self.mqtt.publish_if_changed(f"{prefix}/pack_remaining_capacity", round(total_remaining, 2))

            # Energy calculations (kWh)
            if voltages:
                energy_remaining = round((total_remaining * avg_voltage) / 1000, 2)
                self.mqtt.publish_if_changed(f"{prefix}/pack_energy_remaining", energy_remaining)

                if total_caps:
                    energy_to_full = round(((sum(total_caps) - total_remaining) * avg_voltage) / 1000, 2)
                    self.mqtt.publish_if_changed(f"{prefix}/pack_energy_to_full", energy_to_full)

        # SOC stats
        if socs:
            self.mqtt.publish_if_changed(f"{prefix}/pack_average_soc", round(sum(socs) / len(socs), 1))
            self.mqtt.publish_if_changed(f"{prefix}/pack_min_soc", round(min(socs), 1))
            self.mqtt.publish_if_changed(f"{prefix}/pack_max_soc", round(max(socs), 1))
            self.mqtt.publish_if_changed(f"{prefix}/pack_soc_spread", round(max(socs) - min(socs), 1))

        # SOH
        if sohs:
            self.mqtt.publish_if_changed(f"{prefix}/pack_min_soh", round(min(sohs), 1))

        # Cycles
        if cycles_list:
            self.mqtt.publish_if_changed(f"{prefix}/pack_max_cycles", max(cycles_list))

        # Global cell voltages
        if all_cell_voltages:
            min_cell = min(all_cell_voltages)
            max_cell = max(all_cell_voltages)
            self.mqtt.publish_if_changed(f"{prefix}/pack_min_cell_voltage", round(min_cell, 3))
            self.mqtt.publish_if_changed(f"{prefix}/pack_max_cell_voltage", round(max_cell, 3))
            self.mqtt.publish_if_changed(f"{prefix}/pack_cell_delta", int((max_cell - min_cell) * 1000))
            self.mqtt.publish_if_changed(f"{prefix}/pack_avg_cell_voltage",
                                        round(sum(all_cell_voltages) / len(all_cell_voltages), 3))

        # Temperatures
        if all_temps:
            self.mqtt.publish_if_changed(f"{prefix}/pack_min_temp", round(min(all_temps), 1))
            self.mqtt.publish_if_changed(f"{prefix}/pack_max_temp", round(max(all_temps), 1))
            self.mqtt.publish_if_changed(f"{prefix}/pack_avg_temp", round(sum(all_temps) / len(all_temps), 1))

        # Alarms & Protections
        self.mqtt.publish_if_changed(f"{prefix}/pack_total_alarms", sum(alarm_counts))
        self.mqtt.publish_if_changed(f"{prefix}/pack_total_protections", sum(protection_counts))
        self.mqtt.publish_if_changed(f"{prefix}/pack_balancing_cells", sum(balancing_counts))

        # Current limits (minimum across all batteries for safety)
        if max_discharge_curts:
            self.mqtt.publish_if_changed(f"{prefix}/pack_max_discharge_current", min(max_discharge_curts))
        if max_charge_curts:
            self.mqtt.publish_if_changed(f"{prefix}/pack_max_charge_current", min(max_charge_curts))

        # Status
        self.mqtt.publish_if_changed(f"{prefix}/pack_status", pack_status)

        # Write to InfluxDB if enabled
        if self.influxdb and self.influxdb.is_enabled():
            # Write individual battery data
            for batt_id, batt_data in online_batts.items():
                self.influxdb.write_battery_data(batt_id, batt_data)

            # Write pack aggregate data
            pack_data = {
                'total_voltage': avg_voltage if voltages else None,
                'total_current': sum(currents) if currents else None,
                'total_power': sum(powers) if powers else None,
                'total_capacity': sum(total_caps) if total_caps else None,
                'remaining_capacity': total_remaining if remaining_caps else None,
                'energy_remaining': round((total_remaining * avg_voltage) / 1000, 2) if remaining_caps and voltages else None,
                'energy_to_full': round(((sum(total_caps) - total_remaining) * avg_voltage) / 1000, 2) if total_caps and remaining_caps and voltages else None,
                'average_soc': round(sum(socs) / len(socs), 1) if socs else None,
                'min_soc': round(min(socs), 1) if socs else None,
                'max_soc': round(max(socs), 1) if socs else None,
                'soc_spread': round(max(socs) - min(socs), 1) if socs else None,
                'min_soh': round(min(sohs), 1) if sohs else None,
                'max_cycles': max(cycles_list) if cycles_list else None,
                'min_cell_voltage': round(min(all_cell_voltages), 3) if all_cell_voltages else None,
                'max_cell_voltage': round(max(all_cell_voltages), 3) if all_cell_voltages else None,
                'cell_delta': int((max(all_cell_voltages) - min(all_cell_voltages)) * 1000) if all_cell_voltages else None,
                'avg_cell_voltage': round(sum(all_cell_voltages) / len(all_cell_voltages), 3) if all_cell_voltages else None,
                'min_temp': round(min(all_temps), 1) if all_temps else None,
                'max_temp': round(max(all_temps), 1) if all_temps else None,
                'avg_temp': round(sum(all_temps) / len(all_temps), 1) if all_temps else None,
                'batteries_online': num_batteries,
                'total_alarms': sum(alarm_counts),
                'total_protections': sum(protection_counts),
                'balancing_cells': sum(balancing_counts),
                'max_discharge_current': min(max_discharge_curts) if max_discharge_curts else None,
                'max_charge_current': min(max_charge_curts) if max_charge_curts else None,
                'status': pack_status
            }
            self.influxdb.write_pack_data(pack_data)
