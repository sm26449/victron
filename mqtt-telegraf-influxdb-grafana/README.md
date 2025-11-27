# Telegraf Victron Energy Configuration

Configurație Telegraf pentru colectarea datelor de la Victron Venus OS via MQTT și stocarea în InfluxDB v2.

## Descriere

Această configurație:
- Se conectează la broker-ul MQTT al Venus OS
- Colectează toate datele publicate de Victron (baterii, invertoare PV, grid, etc.)
- Organizează datele în InfluxDB cu measurement-uri separate per tip de dispozitiv
- Permite query-uri simple: `SELECT * FROM "battery"`, `SELECT * FROM "pvinverter"`

## Structura Datelor

### Topic MQTT
```
N/<portal_id>/<device_type>/<instance>/<path...>
```

### Organizare InfluxDB
- **Measurement**: tipul dispozitivului (`battery`, `pvinverter`, `grid`, `system`, etc.)
- **Tags**: `portal_id`, `instance`, `field`, `subfield`, `detail`
- **Fields**: `value` (valoarea publicată de Victron)

## Variabile de Configurare

Creează un fișier `.env` sau configurează variabilele de mediu:

| Variabilă | Descriere | Exemplu |
|-----------|-----------|---------|
| `INFLUXDB_URL` | URL-ul InfluxDB | `http://influxdb:8086` sau `http://localhost:8086` |
| `INFLUXDB_TOKEN` | Token de autentificare InfluxDB v2 | Generat din InfluxDB UI |
| `INFLUXDB_ORG` | Organizația InfluxDB | `my-org` |
| `INFLUXDB_BUCKET` | Bucket-ul pentru date | `victron` |
| `MQTT_SERVER` | Adresa broker-ului MQTT | `ssl://192.168.x.x:8883` sau `tcp://192.168.x.x:1883` |
| `MQTT_USERNAME` | Username MQTT (dacă e necesar) | `admin` |
| `MQTT_PASSWORD` | Parola MQTT | `your-password` |
| `VICTRON_PORTAL_ID` | Portal ID Victron (12 caractere hex) | `c123456789` |

## Unde Găsești Portal ID

Portal ID-ul Victron se găsește în:
1. **VRM Portal**: Settings → General → VRM Portal ID
2. **Venus OS**: Settings → System → VRM Portal ID  
3. **Remote Console**: Settings → VRM online portal

## Exemple de Utilizare

### Cu Docker Compose

```yaml
services:
  telegraf:
    image: telegraf:latest
    environment:
      - INFLUXDB_URL=http://influxdb:8086
      - INFLUXDB_TOKEN=${INFLUXDB_TOKEN}
      - INFLUXDB_ORG=my-org
      - INFLUXDB_BUCKET=victron
      - MQTT_SERVER=ssl://192.168.88.250:8883
      - MQTT_USERNAME=admin
      - MQTT_PASSWORD=${MQTT_PASSWORD}
      - VICTRON_PORTAL_ID=c123456789
    volumes:
      - ./telegraf.conf:/etc/telegraf/telegraf.conf:ro
```

### Fișier .env

```env
INFLUXDB_URL=http://influxdb:8086
INFLUXDB_TOKEN=your-influxdb-token-here
INFLUXDB_ORG=PV-Stack
INFLUXDB_BUCKET=victron
MQTT_SERVER=ssl://192.168.88.250:8883
MQTT_USERNAME=admin
MQTT_PASSWORD=your-mqtt-password
VICTRON_PORTAL_ID=c123456789
```

### Rulare Manuală

```bash
# Export variabile
export INFLUXDB_URL="http://localhost:8086"
export INFLUXDB_TOKEN="your-token"
# ... etc

# Rulare telegraf
telegraf --config telegraf.conf
```

## Query-uri Exemplu (InfluxQL / Flux)

### InfluxQL
```sql
-- Starea bateriei
SELECT mean("value") FROM "battery" WHERE "field" = 'Soc' GROUP BY time(1m)

-- Producție PV
SELECT sum("value") FROM "pvinverter" WHERE "field" = 'Ac' AND "subfield" = 'Power' GROUP BY time(1h)

-- Consum din grid
SELECT mean("value") FROM "grid" WHERE "field" = 'Ac' AND "subfield" = 'Power'
```

### Flux
```flux
from(bucket: "victron")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "battery")
  |> filter(fn: (r) => r.field == "Soc")
```

## Troubleshooting

### Verifică conexiunea MQTT
```bash
# Test conexiune (necesită mosquitto-clients)
mosquitto_sub -h 192.168.x.x -p 8883 --cafile /path/to/ca.crt -u admin -P password -t "N/#" -v
```

### Verifică datele în InfluxDB
```bash
# Query rapid
influx query 'from(bucket:"victron") |> range(start:-5m) |> limit(n:10)'
```

### Logs Telegraf
```bash
docker logs telegraf-victron
# sau
journalctl -u telegraf -f
```

## Note

- Venus OS folosește SSL pe portul 8883 pentru MQTT securizat
- `insecure_skip_verify = true` este necesar dacă Venus OS folosește certificate self-signed
- Intervalul de 10s este un compromis bun între rezoluție și overhead

## Licență

MIT
