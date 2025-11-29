"""
Serial Snooper - Modbus RTU protocol sniffer for Seplos BMS V3
"""

import signal
import sys
import serial
import json
from datetime import datetime, timezone
from .logging_setup import get_logger
from .utils import calc_crc16, to_lower_under


class SerialSnooper:
    """
    Serial Snooper class - sniffs Modbus RTU traffic from Seplos BMS

    Features:
    - Listens to RS485 serial bus traffic
    - Decodes Seplos BMS V3 Modbus protocol
    - MQTT autodiscovery for Home Assistant
    - Pack aggregate calculations via PackAggregator
    """

    def __init__(self, port, mqtt_manager, mqtt_prefix, pack_aggregator, baudrate=19200):
        self.port = port
        self.baudrate = baudrate
        self.mqtt = mqtt_manager
        self.mqtt_prefix = mqtt_prefix
        self.pack_aggregator = pack_aggregator
        self.data = bytearray(0)
        self.trashdata = False
        self.trashdataf = bytearray(0)
        self.batts_declared_set = set()
        self.log = get_logger()

        # Init the signal handler for a clean exit
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        # Timeout optimizat: 0.1s reduce consumul CPU semnificativ
        # La 19200 baud, un frame Modbus de 100 bytes ia ~52ms
        # Timeout de 100ms permite acumularea datelor și reduce ciclurile idle
        self.serial_timeout = 0.1
        self.log.info(f"Opening serial interface, port: {port} {baudrate} 8N1 timeout: {self.serial_timeout}")
        self.connection = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.serial_timeout
        )
        self.log.debug(self.connection)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        self.connection.open()

    def close(self):
        self.connection.close()

    def read_raw(self, n=256):
        """Citește până la n bytes din buffer-ul serial.

        Optimizare CPU: citim un bloc mai mare în loc de byte cu byte.
        La timeout (fără date), returnează bytes gol, permițând procesarea
        datelor acumulate în buffer.
        """
        return self.connection.read(n)

    def get_declared_batteries(self):
        """Get set of declared battery IDs"""
        return self.batts_declared_set.copy()

    def signal_handler(self, sig, frame):
        """Handle shutdown signals"""
        for batt_number in self.batts_declared_set:
            self.log.info(f"Sending offline signal for Battery {batt_number}")
            self.mqtt.publish(f"{self.mqtt_prefix}/battery_{batt_number}/state", "offline", retain=True)
        self.mqtt.disconnect()
        print('\nGoodbye\n')
        sys.exit(0)

    def process_data(self, data):
        """Buffer data and decode when interframe timeout occurs"""
        if len(data) <= 0:
            if len(self.data) > 2:
                self.data = self._decode_modbus(self.data)
            return
        for dat in data:
            self.data.append(dat)

    def autodiscovery_battery(self, unitIdentifier):
        """Send MQTT autodiscovery for a battery"""
        self.log.info(f"Sending autodiscovery block Battery {unitIdentifier}")

        # Pack Main Information (PIA - 0x1000)
        self._autodiscovery_sensor("voltage", "measurement", "V", "Pack Voltage", unitIdentifier)
        self._autodiscovery_sensor("current", "measurement", "A", "Current", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "Ah", "Remaining Capacity", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "Ah", "Total Capacity", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "Ah", "Total Discharge Capacity", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "%", "SOC", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "%", "SOH", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "cycles", "Cycles", unitIdentifier)
        self._autodiscovery_sensor("voltage", "measurement", "V", "Average Cell Voltage", unitIdentifier)
        self._autodiscovery_sensor("temperature", "measurement", "°C", "Average Cell Temp", unitIdentifier)
        self._autodiscovery_sensor("voltage", "measurement", "V", "Max Cell Voltage", unitIdentifier)
        self._autodiscovery_sensor("voltage", "measurement", "V", "Min Cell Voltage", unitIdentifier)
        self._autodiscovery_sensor("temperature", "measurement", "°C", "Max Cell Temp", unitIdentifier)
        self._autodiscovery_sensor("temperature", "measurement", "°C", "Min Cell Temp", unitIdentifier)
        self._autodiscovery_sensor("current", "measurement", "A", "MaxDisCurt", unitIdentifier)
        self._autodiscovery_sensor("current", "measurement", "A", "MaxChgCurt", unitIdentifier)
        self._autodiscovery_sensor("power", "measurement", "W", "Power", unitIdentifier)
        self._autodiscovery_sensor("voltage", "measurement", "mV", "Cell Delta", unitIdentifier)

        # Cell Voltages (PIB - 0x1100)
        for i in range(1, 17):
            self._autodiscovery_sensor("voltage", "measurement", "V", f"Cell {i}", unitIdentifier)

        # Cell Temperatures (PIB - 0x1110-0x1119)
        for i in range(1, 5):
            self._autodiscovery_sensor("temperature", "measurement", "°C", f"Cell Temp {i}", unitIdentifier)
        self._autodiscovery_sensor("temperature", "measurement", "°C", "Ambient Temp", unitIdentifier)
        self._autodiscovery_sensor("temperature", "measurement", "°C", "MOSFET Temp", unitIdentifier)

        # Status (PIC - 0x1200)
        self._autodiscovery_sensor("", "", "", "Status", unitIdentifier)

        # FET Status
        self._autodiscovery_sensor("", "", "", "FET Discharge", unitIdentifier)
        self._autodiscovery_sensor("", "", "", "FET Charge", unitIdentifier)
        self._autodiscovery_sensor("", "", "", "FET Current Limit", unitIdentifier)
        self._autodiscovery_sensor("", "", "", "FET Heater", unitIdentifier)

        # Balancing Status
        self._autodiscovery_sensor("", "", "", "Balancing Active", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "", "Balancing Count", unitIdentifier)
        self._autodiscovery_sensor("", "", "", "Balancing Cells", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "", "Balancing Bits", unitIdentifier)

        # Heating
        self._autodiscovery_sensor("", "", "", "Heating Active", unitIdentifier)

        # Alarms Summary
        self._autodiscovery_sensor("", "measurement", "", "Alarm Count", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "", "Protection Count", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "", "Failure Count", unitIdentifier)

        # Cell Alarm Bits (for debugging)
        self._autodiscovery_sensor("", "measurement", "", "Alarm Cell Undervolt", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "", "Alarm Cell Overvolt", unitIdentifier)
        self._autodiscovery_sensor("", "measurement", "", "Alarm Cell Temp", unitIdentifier)

        # Last Update timestamp
        self._autodiscovery_sensor("timestamp", "", "", "Last Update", unitIdentifier)

        self.log.info(f"Sending online signal for Battery {unitIdentifier}")
        self.mqtt.publish(f"{self.mqtt_prefix}/battery_{unitIdentifier}/state", "online", retain=True)

    def _autodiscovery_sensor(self, dev_cla, state_class, sensor_unit, sensor_name, batt_number):
        """Send autodiscovery for a single sensor"""
        name_under = to_lower_under(sensor_name)

        mqtt_packet = {
            "name": sensor_name,
            "stat_t": f"{self.mqtt_prefix}/battery_{batt_number}/{name_under}",
            "avty_t": f"{self.mqtt_prefix}/battery_{batt_number}/state",
            "uniq_id": f"seplos_battery_{batt_number}_{name_under}",
            "dev": {
                "ids": f"seplos_battery_{batt_number}",
                "name": f"Seplos BMS {batt_number}",
                "sw": "seplos-bms-mqtt 2.4",
                "mdl": "Seplos BMSv3 MQTT",
                "mf": "Seplos"
            },
            "origin": {
                "name": "seplos-bms-mqtt",
                "sw": "2.4",
                "url": "https://github.com/sm2669/seplos-bms-mqtt"
            }
        }
        # Add optional fields
        if dev_cla:
            mqtt_packet["dev_cla"] = dev_cla
        if state_class:
            mqtt_packet["stat_cla"] = state_class
        if sensor_unit:
            mqtt_packet["unit_of_meas"] = sensor_unit

        self.mqtt.publish(f"homeassistant/sensor/seplos_bms_{batt_number}/{name_under}/config",
                         json.dumps(mqtt_packet), retain=True)

    def _decode_modbus(self, data):
        """Decode Modbus frames (Request, Response, Exception)"""
        modbusdata = data
        bufferIndex = 0

        while True:
            unitIdentifier = 0
            functionCode = 0
            readByteCount = 0
            readData = bytearray(0)
            crc16 = 0
            responce = False
            needMoreData = False
            frameStartIndex = bufferIndex

            if len(modbusdata) > (frameStartIndex + 2):
                # Unit Identifier (Slave Address)
                unitIdentifier = modbusdata[bufferIndex]
                bufferIndex += 1
                # Function Code
                functionCode = modbusdata[bufferIndex]
                bufferIndex += 1

                if functionCode == 1:
                    # FC01 - Read Coils Response
                    expectedLenght = 7
                    if len(modbusdata) >= (frameStartIndex + expectedLenght):
                        bufferIndex = frameStartIndex + 2
                        readByteCount = modbusdata[bufferIndex]
                        bufferIndex += 1
                        expectedLenght = (5 + readByteCount)
                        if len(modbusdata) >= (frameStartIndex + expectedLenght):
                            index = 1
                            while index <= readByteCount:
                                readData.append(modbusdata[bufferIndex])
                                bufferIndex += 1
                                index += 1
                            crc16 = (modbusdata[bufferIndex] * 0x0100) + modbusdata[bufferIndex + 1]
                            metCRC16 = calc_crc16(modbusdata, bufferIndex)
                            bufferIndex += 2
                            if crc16 == metCRC16:
                                if self.trashdata:
                                    self.trashdata = False
                                    self.trashdataf += "]"
                                responce = True

                                # Pack Alarms and Status (PIC - 0x1200) - 18 bytes
                                if readByteCount == 18:
                                    self._process_alarm_status(unitIdentifier, readData)

                                modbusdata = modbusdata[bufferIndex:]
                                bufferIndex = 0
                        else:
                            needMoreData = True
                    else:
                        needMoreData = True

                elif functionCode == 4:
                    # FC04 - Read Input Registers Response
                    expectedLenght = 7
                    if len(modbusdata) >= (frameStartIndex + expectedLenght):
                        bufferIndex = frameStartIndex + 2
                        readByteCount = modbusdata[bufferIndex]
                        bufferIndex += 1
                        expectedLenght = (5 + readByteCount)
                        if len(modbusdata) >= (frameStartIndex + expectedLenght):
                            index = 1
                            while index <= readByteCount:
                                readData.append(modbusdata[bufferIndex])
                                bufferIndex += 1
                                index += 1
                            crc16 = (modbusdata[bufferIndex] * 0x0100) + modbusdata[bufferIndex + 1]
                            metCRC16 = calc_crc16(modbusdata, bufferIndex)
                            bufferIndex += 2
                            if crc16 == metCRC16:
                                if self.trashdata:
                                    self.trashdata = False
                                    self.trashdataf += "]"
                                responce = True

                                # Cell Pack information (PIB - 0x1100) - 52 bytes
                                if readByteCount == 52:
                                    self._process_cell_info(unitIdentifier, readData)

                                # Pack Main information (PIA - 0x1000) - 36 bytes
                                if readByteCount == 36:
                                    self._process_main_info(unitIdentifier, readData)

                                modbusdata = modbusdata[bufferIndex:]
                                bufferIndex = 0
                        else:
                            needMoreData = True
                    else:
                        needMoreData = True
            else:
                needMoreData = True

            if needMoreData:
                return modbusdata
            elif not responce:
                if self.trashdata:
                    self.trashdataf += " {:02x}".format(modbusdata[frameStartIndex])
                else:
                    self.trashdata = True
                    self.trashdataf = "Ignoring data: [{:02x}".format(modbusdata[frameStartIndex])
                bufferIndex = frameStartIndex + 1
                modbusdata = modbusdata[bufferIndex:]
                bufferIndex = 0

    def _process_alarm_status(self, unitIdentifier, readData):
        """Process FC01 alarm and status response (18 bytes)"""
        if unitIdentifier not in self.batts_declared_set:
            self.autodiscovery_battery(unitIdentifier)
            self.batts_declared_set.add(unitIdentifier)

        # Bytes 0-1: Cell undervoltage alarms
        cell_undervolt = (readData[1] << 8) | readData[0]
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/alarm_cell_undervolt", cell_undervolt)

        # Bytes 2-3: Cell overvoltage alarms
        cell_overvolt = (readData[3] << 8) | readData[2]
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/alarm_cell_overvolt", cell_overvolt)

        # Bytes 4-5: Cell temperature alarms
        cell_temp_alarm = (readData[5] << 8) | readData[4]
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/alarm_cell_temp", cell_temp_alarm)

        # Bytes 6-7: Cell balancing status
        balancing_bits = (readData[7] << 8) | readData[6]
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/balancing_bits", balancing_bits)
        balancing_count = bin(balancing_bits).count('1')
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/balancing_count", balancing_count)
        balancing_cells = [i+1 for i in range(16) if (balancing_bits >> i) & 1]
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/balancing_cells",
                                    ','.join(map(str, balancing_cells)) if balancing_cells else "none")

        # Byte 8: Operating status
        strStatus = "Unknown"
        if (readData[8] >> 0) & 1: strStatus = "Discharge"
        elif (readData[8] >> 1) & 1: strStatus = "Charge"
        elif (readData[8] >> 2) & 1: strStatus = "Floating charge"
        elif (readData[8] >> 3) & 1: strStatus = "Full charge"
        elif (readData[8] >> 4) & 1: strStatus = "Standby"
        elif (readData[8] >> 5) & 1: strStatus = "Off"
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/status", strStatus)

        # Byte 9-14: Various alarms (extracted for counting)
        alarm_cell_high_v = (readData[9] >> 0) & 1
        alarm_cell_overvolt_prot = (readData[9] >> 1) & 1
        alarm_cell_low_v = (readData[9] >> 2) & 1
        alarm_cell_undervolt_prot = (readData[9] >> 3) & 1
        alarm_pack_high_v = (readData[9] >> 4) & 1
        alarm_pack_overvolt_prot = (readData[9] >> 5) & 1
        alarm_pack_low_v = (readData[9] >> 6) & 1
        alarm_pack_undervolt_prot = (readData[9] >> 7) & 1

        alarm_charge_high_temp = (readData[10] >> 0) & 1
        alarm_charge_overtemp_prot = (readData[10] >> 1) & 1
        alarm_charge_low_temp = (readData[10] >> 2) & 1
        alarm_charge_undertemp_prot = (readData[10] >> 3) & 1
        alarm_discharge_high_temp = (readData[10] >> 4) & 1
        alarm_discharge_overtemp_prot = (readData[10] >> 5) & 1
        alarm_discharge_low_temp = (readData[10] >> 6) & 1
        alarm_discharge_undertemp_prot = (readData[10] >> 7) & 1

        alarm_ambient_high_temp = (readData[11] >> 0) & 1
        alarm_ambient_overtemp_prot = (readData[11] >> 1) & 1
        alarm_mosfet_high_temp = (readData[11] >> 4) & 1
        alarm_mosfet_overtemp_prot = (readData[11] >> 5) & 1
        alarm_heating_active = (readData[11] >> 6) & 1

        alarm_charge_current = (readData[12] >> 0) & 1
        alarm_charge_overcurrent_prot = (readData[12] >> 1) & 1
        alarm_charge_overcurrent_2_prot = (readData[12] >> 2) & 1
        alarm_discharge_current = (readData[12] >> 3) & 1
        alarm_discharge_overcurrent_prot = (readData[12] >> 4) & 1
        alarm_discharge_overcurrent_2_prot = (readData[12] >> 5) & 1
        alarm_short_circuit_prot = (readData[12] >> 6) & 1

        alarm_soc_low = (readData[14] >> 2) & 1
        alarm_soc_prot = (readData[14] >> 3) & 1
        alarm_cell_diff = (readData[14] >> 4) & 1

        # Byte 15: FET status
        fet_discharge = (readData[15] >> 0) & 1
        fet_charge = (readData[15] >> 1) & 1
        fet_current_limit = (readData[15] >> 2) & 1
        fet_heater = (readData[15] >> 3) & 1

        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/fet_discharge", "ON" if fet_discharge else "OFF")
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/fet_charge", "ON" if fet_charge else "OFF")
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/fet_current_limit", "ON" if fet_current_limit else "OFF")
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/fet_heater", "ON" if fet_heater else "OFF")

        # Byte 16: Balancing status
        balancing_active = (readData[16] >> 0) & 1
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/balancing_active", "ON" if balancing_active else "OFF")

        # Byte 17: Hardware failures
        failure_ntc = (readData[17] >> 0) & 1
        failure_afe = (readData[17] >> 1) & 1
        failure_charge_mosfet = (readData[17] >> 2) & 1
        failure_discharge_mosfet = (readData[17] >> 3) & 1
        failure_cell_diff = (readData[17] >> 4) & 1

        # Alarm summary
        alarm_count = sum([
            alarm_cell_high_v, alarm_cell_overvolt_prot, alarm_cell_low_v, alarm_cell_undervolt_prot,
            alarm_pack_high_v, alarm_pack_overvolt_prot, alarm_pack_low_v, alarm_pack_undervolt_prot,
            alarm_charge_high_temp, alarm_charge_overtemp_prot, alarm_charge_low_temp, alarm_charge_undertemp_prot,
            alarm_discharge_high_temp, alarm_discharge_overtemp_prot, alarm_discharge_low_temp, alarm_discharge_undertemp_prot,
            alarm_ambient_high_temp, alarm_ambient_overtemp_prot, alarm_mosfet_high_temp, alarm_mosfet_overtemp_prot,
            alarm_charge_current, alarm_charge_overcurrent_prot, alarm_discharge_current, alarm_discharge_overcurrent_prot,
            alarm_short_circuit_prot, alarm_soc_low, alarm_cell_diff
        ])
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/alarm_count", alarm_count)

        # Protection summary
        protection_count = sum([
            alarm_cell_overvolt_prot, alarm_cell_undervolt_prot,
            alarm_pack_overvolt_prot, alarm_pack_undervolt_prot,
            alarm_charge_overtemp_prot, alarm_charge_undertemp_prot,
            alarm_discharge_overtemp_prot, alarm_discharge_undertemp_prot,
            alarm_ambient_overtemp_prot, alarm_mosfet_overtemp_prot,
            alarm_charge_overcurrent_prot, alarm_charge_overcurrent_2_prot,
            alarm_discharge_overcurrent_prot, alarm_discharge_overcurrent_2_prot,
            alarm_short_circuit_prot, alarm_soc_prot
        ])
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/protection_count", protection_count)

        # Failure summary
        failure_count = sum([failure_ntc, failure_afe, failure_charge_mosfet, failure_discharge_mosfet, failure_cell_diff])
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/failure_count", failure_count)

        # Heating status
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/heating_active", "ON" if alarm_heating_active else "OFF")

        # Update pack aggregator
        self.pack_aggregator.update_battery_data(unitIdentifier, 'status', strStatus)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'alarm_count', alarm_count)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'protection_count', protection_count)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'balancing_count', balancing_count)

        # Publicăm last_update la fiecare pachet primit (PIC)
        last_update = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.mqtt.publish(f"{self.mqtt_prefix}/battery_{unitIdentifier}/last_update", last_update, retain=True)

    def _process_cell_info(self, unitIdentifier, readData):
        """Process FC04 cell information response (52 bytes)"""
        if unitIdentifier not in self.batts_declared_set:
            self.autodiscovery_battery(unitIdentifier)
            self.batts_declared_set.add(unitIdentifier)

        # Cell voltages 1-16 (bytes 0-31) - calculăm o singură dată
        cell_voltages = []
        for i in range(0, 32, 2):
            celda = round(((readData[i] << 8) | readData[i + 1]) / 1000.0, 3)
            cell_voltages.append(celda)
            cell_num = (i // 2) + 1
            self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/cell_{cell_num}", celda)
            self.pack_aggregator.update_battery_data(unitIdentifier, f'cell_{cell_num}', celda)

        # Cell temperatures 1-4 (bytes 32-39) - calculăm o singură dată
        for i in range(4):
            temp_raw = (readData[32 + i*2] << 8) | readData[33 + i*2]
            temp_celsius = round(temp_raw / 10.0 - 273.15, 1)
            self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/cell_temp_{i+1}", temp_celsius)
            self.pack_aggregator.update_battery_data(unitIdentifier, f'cell_temp_{i+1}', temp_celsius)

        # Ambient temperature (bytes 48-49)
        ambient_raw = (readData[48] << 8) | readData[49]
        ambient_celsius = round(ambient_raw / 10.0 - 273.15, 1)
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/ambient_temp", ambient_celsius)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'ambient_temp', ambient_celsius)

        # MOSFET temperature (bytes 50-51)
        power_raw = (readData[50] << 8) | readData[51]
        power_celsius = round(power_raw / 10.0 - 273.15, 1)
        self.mqtt.publish_if_changed(f"{self.mqtt_prefix}/battery_{unitIdentifier}/mosfet_temp", power_celsius)

        # Publicăm last_update la fiecare pachet primit (PIB)
        last_update = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.mqtt.publish(f"{self.mqtt_prefix}/battery_{unitIdentifier}/last_update", last_update, retain=True)

    def _process_main_info(self, unitIdentifier, readData):
        """Process FC04 main information response (36 bytes)"""
        readDataNumber = []
        for i in range(0, 36, 2):
            readDataNumber.append((readData[i] << 8) | readData[i + 1])

        if unitIdentifier not in self.batts_declared_set:
            self.autodiscovery_battery(unitIdentifier)
            self.batts_declared_set.add(unitIdentifier)

        # Pre-calculăm valorile o singură dată pentru a evita duplicarea
        pack_voltage = round(readDataNumber[0] / 100.0, 2)
        current_decimal = readDataNumber[1] if readDataNumber[1] <= 32767 else readDataNumber[1] - 65536
        current = round(current_decimal / 100.0, 2)
        remaining_capacity = round(readDataNumber[2] / 100.0, 2)
        total_capacity = round(readDataNumber[3] / 100.0, 2)
        total_discharge_capacity = readDataNumber[4] * 10
        soc = round(readDataNumber[5] / 10.0, 1)
        soh = round(readDataNumber[6] / 10.0, 1)
        cycles = readDataNumber[7]
        average_cell_voltage = round(readDataNumber[8] / 1000.0, 3)
        average_cell_temp = round(readDataNumber[9] / 10.0 - 273.15, 1)
        max_cell_voltage = round(readDataNumber[10] / 1000.0, 3)
        min_cell_voltage = round(readDataNumber[11] / 1000.0, 3)
        max_cell_temp = round(readDataNumber[12] / 10.0 - 273.15, 1)
        min_cell_temp = round(readDataNumber[13] / 10.0 - 273.15, 1)
        maxdiscurt = readDataNumber[15]
        maxchgcurt = readDataNumber[16]
        power = int(round(-current * pack_voltage))
        cell_delta = readDataNumber[10] - readDataNumber[11]

        # Publicăm pe MQTT
        prefix = f"{self.mqtt_prefix}/battery_{unitIdentifier}"
        self.mqtt.publish_if_changed(f"{prefix}/pack_voltage", pack_voltage)
        self.mqtt.publish_if_changed(f"{prefix}/current", current)
        self.mqtt.publish_if_changed(f"{prefix}/remaining_capacity", remaining_capacity)
        self.mqtt.publish_if_changed(f"{prefix}/total_capacity", total_capacity)
        self.mqtt.publish_if_changed(f"{prefix}/total_discharge_capacity", total_discharge_capacity)
        self.mqtt.publish_if_changed(f"{prefix}/soc", soc)
        self.mqtt.publish_if_changed(f"{prefix}/soh", soh)
        self.mqtt.publish_if_changed(f"{prefix}/cycles", cycles)
        self.mqtt.publish_if_changed(f"{prefix}/average_cell_voltage", average_cell_voltage)
        self.mqtt.publish_if_changed(f"{prefix}/average_cell_temp", average_cell_temp)
        self.mqtt.publish_if_changed(f"{prefix}/max_cell_voltage", max_cell_voltage)
        self.mqtt.publish_if_changed(f"{prefix}/min_cell_voltage", min_cell_voltage)
        self.mqtt.publish_if_changed(f"{prefix}/max_cell_temp", max_cell_temp)
        self.mqtt.publish_if_changed(f"{prefix}/min_cell_temp", min_cell_temp)
        self.mqtt.publish_if_changed(f"{prefix}/maxdiscurt", maxdiscurt)
        self.mqtt.publish_if_changed(f"{prefix}/maxchgcurt", maxchgcurt)
        self.mqtt.publish_if_changed(f"{prefix}/power", power)
        self.mqtt.publish_if_changed(f"{prefix}/cell_delta", cell_delta)

        # Publicăm last_update mereu (nu publish_if_changed) pentru a ști că funcționează
        last_update = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.mqtt.publish(f"{prefix}/last_update", last_update, retain=True)

        # Actualizăm pack aggregator cu aceleași valori pre-calculate
        self.pack_aggregator.update_battery_data(unitIdentifier, 'pack_voltage', pack_voltage)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'current', current)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'remaining_capacity', remaining_capacity)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'total_capacity', total_capacity)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'soc', soc)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'soh', soh)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'cycles', cycles)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'max_cell_voltage', max_cell_voltage)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'min_cell_voltage', min_cell_voltage)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'max_cell_temp', max_cell_temp)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'min_cell_temp', min_cell_temp)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'maxdiscurt', maxdiscurt)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'maxchgcurt', maxchgcurt)
        self.pack_aggregator.update_battery_data(unitIdentifier, 'power', power)

        # Calculate and publish pack aggregate
        self.pack_aggregator.calculate_and_publish()
