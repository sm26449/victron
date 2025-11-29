# Fronius Solar API MQTT Collector

Collects data from Fronius solar inverters via Solar API and publishes to MQTT and/or InfluxDB.

**Status: Work in Progress**

## Features

- Reads data from Fronius DataManager via Solar API v1
- Supports multiple inverters (tested with 4x Fronius Symo)
- Supports Fronius Smart Meter
- Publishes to MQTT with `retain=true`
- Optional InfluxDB v2 storage
- Fast polling mode (1 second) for power/meter data
- Automatic reconnection on connection loss
- Human-readable status and error codes

## Architecture

```
┌─────────────────────┐     HTTP/JSON      ┌──────────────────┐
│  Fronius DataManager├───────────────────►│  fronius_collector│
│  (Solar API v1)     │                    │                  │
└─────────────────────┘                    └────────┬─────────┘
                                                    │
                                      ┌─────────────┼─────────────┐
                                      │             │             │
                                      ▼             ▼             ▼
                                   MQTT        InfluxDB        stdout
                               (optional)     (optional)       (logs)
```

## pyfronius Library

This project uses a forked and refactored version of [pyfronius](https://github.com/nielstron/pyfronius.git), an async Python client for the Fronius Solar API.

Original library by:
- Niels (nielstron)
- Gerrit Beine

The fork includes:
- Refactored code structure with separate parsers module
- Additional API endpoints support
- Type hints and improved error handling

## MQTT Topics

| Topic | Fields | Interval |
|-------|--------|----------|
| `fronius/power_flow/*` | 7 (grid_power, load_power, autonomy, etc.) | 1s (fast) |
| `fronius/meter/0/*` | 36 (power, voltage, current per phase, etc.) | 1s (fast) |
| `fronius/inverter/total/*` | 7 (power, pv_power_total, efficiency, etc.) | 10s |
| `fronius/inverter/{1-4}/*` | ~16 (power, status, error, efficiency, etc.) | 10s |
| `fronius/logger/*` | 6 (LED status, online, last_update) | 10s |

## Quick Start with Docker

1. Copy example config:
```bash
cp config/config.example.yaml config/config.yaml
```

2. Edit `config/config.yaml` with your settings

3. Build and run:
```bash
docker-compose up -d
```

## Configuration

```yaml
fronius:
  host: "http://192.168.1.100"    # DataManager URL
  inverter_ids: [1, 2, 3, 4]      # Inverter IDs
  meter_id: 0                      # Smart Meter ID
  poll_interval: 10                # Slow polling (seconds)
  poll_interval_fast: 1            # Fast polling for power/meter (0=disabled)
  poll_interval_inverter_info: 60  # Inverter info update interval

mqtt:
  enabled: true
  host: "192.168.1.50"
  port: 1883
  username: ""
  password: ""
  base_topic: "fronius"
  retain: true
  publish_mode: "on_change"        # or "always"

influxdb:
  enabled: false
  url: "http://192.168.1.50:8086"
  token: "your-token"
  org: "my-org"
  bucket: "fronius"
  write_mode: "on_change"
```

## Running without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python -m fronius_collector -c config/config.yaml
```

## Command Line Options

```bash
python -m fronius_collector --help

Options:
  -c, --config PATH    Path to configuration file
  -v, --verbose        Enable DEBUG logging
  --once               Collect data once and exit (useful for testing)
```

## Environment Variables

- `FRONIUS_CONFIG` - Path to config file (default: `config.yaml`)
- `TZ` - Timezone (e.g., `Europe/Bucharest`)

## Project Structure

```
fronius-solar-api-mqtt/
├── config/
│   ├── config.example.yaml
│   └── config.yaml
├── fronius_collector/
│   ├── __init__.py
│   ├── __main__.py         # Entry point
│   ├── collector.py        # Main data collector
│   ├── config.py           # Configuration handling
│   ├── const.py            # Status/error code mappings
│   ├── influxdb_client.py  # InfluxDB publisher
│   └── mqtt_client.py      # MQTT publisher
├── pyfronius/              # Fronius Solar API client (fork)
│   ├── __init__.py         # Main Fronius class
│   ├── const.py            # API constants
│   ├── models.py           # Data models
│   ├── parsers.py          # Response parsers
│   └── units.py            # Unit definitions
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

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

### pyfronius License

The `pyfronius/` directory is based on [pyfronius](https://github.com/nielstron/pyfronius) by Niels (nielstron) and Gerrit Beine, licensed under MIT.

## Disclaimer

This software is provided for educational and informational purposes only.
The author assumes no responsibility for any damages, losses, or issues arising
from the use of this software. Use at your own risk.

## Author

**Stefan M**
Email: sm24559@diysolar.ro
