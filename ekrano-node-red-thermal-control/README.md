# 🌡️ Battery Thermal Control for Node-RED

Automated thermal management system for battery storage installations using Node-RED, Victron Energy components, and Tuya-based AC units.

## Overview

This flow maintains optimal battery temperature (22.5-26.5°C, target 24.5°C) by automatically controlling an air conditioning unit based on real-time sensor data. It includes predictive algorithms, trend analysis, and comprehensive alerting.

## Features

- **Smart Temperature Control**: Maintains battery temperature within safe operating range
- **Multi-sensor Input**: Battery temperature, room temperature, outdoor temperature
- **Predictive Control**: Uses temperature trends to anticipate heating/cooling needs
- **Anti-cycling Protection**: Prevents rapid AC mode switching (10-minute minimum cycle)
- **Critical Alerts**: Telegram notifications for critical conditions
- **Data Logging**: InfluxDB integration for historical analysis
- **Manual Override**: Buttons for manual AC control when needed

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Victron GX     │────▶│   Node-RED      │────▶│   Tuya Bridge   │
│  (Sensors)      │     │  (Decision)     │     │   (AC Control)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                  ┌────────────┴────────────┐
                  │                         │
                  ▼                         ▼
           ┌──────────┐             ┌──────────────┐
           │ InfluxDB │             │   Telegram   │
           │ (Logs)   │             │   (Alerts)   │
           └──────────┘             └──────────────┘
```

## Requirements

### Hardware
- Victron Energy GX device (Cerbo GX, Venus GX, etc.)
- Battery with temperature sensor (e.g., SEPLOS BMS)
- Ruuvi tags or compatible temperature sensors (indoor/outdoor)
- Tuya-compatible AC unit with WiFi module

### Software
- Node-RED (typically running on Victron GX or separate host)
- InfluxDB 2.x (for data logging)
- Tuya Local Bridge API (for AC control)

### Node-RED Palettes
```
node-red-contrib-victron
node-red-contrib-influxdb
node-red-contrib-telegrambot
```

## Installation

1. **Import the Flow**
   - Open Node-RED
   - Menu → Import → Clipboard
   - Paste contents of `thermal-control-flow.json`
   - Click Import

2. **Configure Credentials**
   - Open the "📋 Set Configuration" function node
   - Replace all `YOUR_*` placeholders with your actual values

3. **Configure External Nodes**
   - Double-click "InfluxDB" node → Set your InfluxDB connection
   - Double-click "telegram bot" config → Add your bot token

4. **Adjust Victron Sensors**
   - Edit Victron input nodes to match your device services
   - Verify paths match your GX device configuration

5. **Deploy**
   - Click Deploy
   - Check debug panel for initialization messages

## Configuration Reference

### Temperature Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `battery.target` | 24.5°C | Ideal battery temperature |
| `battery.tolerance` | ±2°C | Normal operating range (22.5-26.5°C) |
| `battery.critical_hot` | 30°C | Emergency cooling threshold |
| `battery.critical_cold` | 18°C | Emergency heating threshold |
| `battery.warning_hot` | 28°C | Aggressive cooling threshold |
| `battery.warning_cold` | 20°C | Aggressive heating threshold |
| `room.min` | 20°C | Minimum room comfort |
| `room.max` | 26°C | Maximum room comfort |

### AC Device (Tuya)

```javascript
ac_device: {
    device_id: 'YOUR_TUYA_DEVICE_ID',    // From Tuya IoT Platform
    ip: 'YOUR_AC_LOCAL_IP',               // Local IP of AC unit
    local_key: 'YOUR_TUYA_LOCAL_KEY',     // From Tuya IoT Platform
    version: '3.3'                         // Tuya protocol version
}
```

**Getting Tuya Credentials:**
1. Create account at [Tuya IoT Platform](https://iot.tuya.com/)
2. Link your Tuya/Smart Life app
3. Add your device
4. Find device_id and local_key in device details

### Telegram Notifications

```javascript
telegram: {
    enabled: true,
    bot_token: 'YOUR_TELEGRAM_BOT_TOKEN',  // From @BotFather
    chat_id: 'YOUR_TELEGRAM_CHAT_ID',       // Your chat ID
    notify_critical: true,                   // Alert on critical temps
    notify_state_changes: true,              // Alert on mode changes
    min_repeat_minutes: 30                   // Minimum time between repeated alerts
}
```

**Creating Telegram Bot:**
1. Message @BotFather on Telegram
2. Send `/newbot` and follow instructions
3. Copy the bot token
4. Message your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat_id

### InfluxDB

Configure the InfluxDB node with:
- **URL**: `http://YOUR_HOST:8086`
- **Organization**: Your org name
- **Bucket**: `thermal_control`
- **Token**: Your InfluxDB API token

## Decision Logic

The controller uses a priority-based decision system:

1. **CRITICAL** (Immediate action)
   - Battery ≥30°C → Maximum cooling
   - Battery ≤18°C → Maximum heating

2. **WARNING** (Aggressive action)
   - Battery ≥28°C → High-fan cooling
   - Battery ≤20°C → High-fan heating

3. **TOLERANCE** (Normal regulation)
   - Battery >26.5°C → Cooling mode
   - Battery <22.5°C → Heating mode

4. **ROOM COMFORT** (When battery is OK)
   - Room >26°C → Light cooling
   - Room <20°C → Light heating

5. **OPTIMIZATION**
   - Large temp difference → Circulate air
   - Trend prediction → Preventive action
   - All optimal → Maintain current state

## Grafana Dashboard

Sample InfluxDB queries for visualization:

```flux
// Battery Temperature
from(bucket: "thermal_control")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "thermal_sensors")
  |> filter(fn: (r) => r._field == "battery_temp")

// AC Actions
from(bucket: "thermal_control")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "thermal_control")
  |> filter(fn: (r) => r._field == "action")
```

## Troubleshooting

### Common Issues

**"No config!" error**
- Ensure "Initialize on Deploy" inject node fires on startup
- Check that global context is working

**Bridge API errors**
- Verify Tuya Bridge is running and accessible
- Check local_key hasn't changed (re-pair if needed)
- Ensure AC unit is on same network

**Sensors offline**
- Check Victron GX device connectivity
- Verify service paths in Victron nodes
- Check sensor batteries (Ruuvi tags)

**No Telegram notifications**
- Verify bot token is correct
- Ensure bot was started (send /start to your bot)
- Check chat_id is numeric

### Debug Mode

Enable debug output by connecting a debug node to the 4th output of "Main Decision Controller" for detailed state information.

## Safety Notes

⚠️ **This system controls HVAC equipment. Ensure:**
- Physical temperature monitoring as backup
- Manual override capability at the AC unit
- Regular verification of sensor accuracy
- Appropriate electrical safety measures

## License

MIT License - Feel free to use and modify for your own installations.

## Contributing

Issues and pull requests welcome! Please test thoroughly before submitting.

---

*Built for Victron Energy + Node-RED enthusiasts managing battery thermal conditions.*
