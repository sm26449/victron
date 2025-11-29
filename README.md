# Victron Energy Tools Collection

A collection of Node-RED flows, Python services, and monitoring configurations for Victron Energy and Fronius systems, focusing on battery management, thermal control, data visualization, and solar inverter integration.

## Projects

### [DVCC Smart Control System](./ekrano-node-red-charge-and-discharge-control/)
Node-RED flows for intelligent charge and discharge control of Victron battery systems.
- Dynamic grid setpoint control
- DVCC (Distributed Voltage and Current Control) automation
- Smart charge/discharge scheduling

### [Battery Thermal Control](./ekrano-node-red-thermal-control/)
Automated thermal management system for battery storage installations.
- Maintains optimal battery temperature (22.5-26.5°C)
- Tuya-based AC unit control
- Telegram alerts for critical conditions
- InfluxDB logging for historical analysis

### [MQTT to Grafana Stack](./mqtt-telegraf-influxdb-grafana/)
Complete monitoring pipeline for Victron data visualization.
- Telegraf configuration for MQTT data collection
- InfluxDB storage with organized measurements
- Grafana dashboard for real-time monitoring

### [Fronius Modbus MQTT](./fronius-modbus-mqtt/) - Ready for deployment
Python service for reading Fronius inverter and meter data via Modbus TCP and publishing to MQTT.
- Modbus TCP communication with Fronius inverters and smart meters
- MQTT publishing for integration with home automation systems
- InfluxDB support for data logging
- Docker ready with production compose files
- Configurable register mapping

### [Fronius Solar API MQTT](./fronius-solar-api-mqtt/) - Work in progress
Python service for collecting data from Fronius inverters via Solar API and publishing to MQTT.
- Solar API V1 integration
- MQTT publishing
- InfluxDB support
- Docker ready

## Documentation

The `docs/` folder contains technical documentation for the supported devices:

### Fronius Documentation (`docs/fronius/`)
- Solar API V0 and V1 specifications
- Modbus TCP/RTU protocol documentation
- Register maps for inverters and meters
- State codes and event flags reference
- Smart Meter operating instructions

### Victron Documentation (`docs/victron/`)
- Wiring diagrams and integration guides

## Requirements

- Victron Energy GX device (Cerbo GX, Venus GX, etc.)
- Node-RED (on GX device or separate host)
- InfluxDB 2.x
- Grafana (optional, for visualization)
- Python 3.9+ (for Fronius services)
- Docker (optional, for containerized deployment)

## Quick Start

1. Clone this repository
2. Navigate to the project you need
3. Follow the README in each subfolder for specific setup instructions

## Screenshots

### Grafana Dashboard
![Grafana Dashboard](./mqtt-telegraf-influxdb-grafana/screenshot/grafana_1.png)

### DVCC Control
![DVCC Control](./ekrano-node-red-charge-and-discharge-control/screenshot/dvcc_setGridPoint.png)

### Thermal Control
![Thermal Control](./ekrano-node-red-thermal-control/screenshot/Screenshot%202025-11-27%20at%2017.16.58.png)

## License

MIT License

Copyright (c) 2025 Stefan M

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Disclaimer

This software is provided for educational and informational purposes only.
The author assumes no responsibility for any damages, losses, or issues arising
from the use of this software. Use at your own risk.

## Author

**Stefan M**
Email: sm24559@diysolar.ro

---

*Built for the Victron Energy + Fronius + Node-RED community*
