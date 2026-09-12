# BBMP Street Lighting Telemetry & Health Monitoring System

Automated ThingsBoard (Schnell IoT) reporting pipelines for BBMP CCMS panels, delivering real-time health analytics, issue breakdowns, and formatted alerts to Google Chat Spaces.

---

## 🎯 Target Monitoring Scopes

### 1. BBMP Central Zone
Monitors the 3 BBMP Central Zone regions:
- **CV Raman Nagar**
- **Shanthi Nagar**
- **Shivaji Nagar**

### 2. BBMP North Zone
Monitors the 3 BBMP North Zone regions:
- **Sarvagna Nagar**
- **Hebbal**
- **Pulakesi Nagar** (ThingsBoard: `PulakeshiNagar`)

### 3. Ward Level Reports (Ward 167 & Ward 118)
- **Shanthi Nagar (Ward 167)**: `SNTR-W167`
- **Shivaji Nagar (Ward 118)**: `SVJR-W118`

---

## 🚀 Execution Commands

### 1. Health Status Reports (CCMS 2-Section Report)

#### BBMP Central Zone (3 Zones)
```bash
# Dry run preview in console (CV Raman Nagar, Shanthi Nagar, Shivaji Nagar)
python zones_report/main_zones.py

# Send Central Zone report to Google Chat Space
python zones_report/main_zones.py --send

# Target specific Central zone only
python zones_report/main_zones.py --zone cv_raman_nagar --send
python zones_report/main_zones.py --zone shanthi_nagar --send
python zones_report/main_zones.py --zone shivaji_nagar --send
```

#### BBMP North Zone (3 Zones)
```bash
# Dry run preview in console (Sarvagna Nagar, Hebbal, Pulakesi Nagar)
python north_zone_report/main_north_zone.py

# Send North Zone report to Google Chat Space
python north_zone_report/main_north_zone.py --send

# Target specific North zone only
python north_zone_report/main_north_zone.py --zone sarvagna_nagar --send
python north_zone_report/main_north_zone.py --zone hebbal --send
python north_zone_report/main_north_zone.py --zone pulakesi_nagar --send
```

---

### 2. Voltage Anomaly Interval Tracker (Low & High Voltage Alerts)

```bash
# Central Zone Voltage Tracker
python voltage_interval_tracker/main_voltage_tracker.py --region central
python voltage_interval_tracker/main_voltage_tracker.py --region central --send --send-only-on-change

# North Zone Voltage Tracker
python voltage_interval_tracker/main_voltage_tracker.py --region north
python voltage_interval_tracker/main_voltage_tracker.py --region north --send --send-only-on-change

# Target specific zone
python voltage_interval_tracker/main_voltage_tracker.py --zone hebbal
```

---

### 3. MCB Trip Interval Tracker

```bash
# Central Zone MCB Tracker
python mcb_interval_tracker/main_mcb_tracker.py --region central
python mcb_interval_tracker/main_mcb_tracker.py --region central --send --send-only-on-change

# North Zone MCB Tracker
python mcb_interval_tracker/main_mcb_tracker.py --region north
python mcb_interval_tracker/main_mcb_tracker.py --region north --send --send-only-on-change

# Target specific zone
python mcb_interval_tracker/main_mcb_tracker.py --zone sarvagna_nagar
```

---

### 4. Ward Specific Monitor (Ward 167 & 118)
```bash
# Send both ward reports
python main.py --send

# Dry-run
python main.py --dry-run
python main.py --ward 167 --dry-run
python main.py --ward 118 --dry-run
```

---

## ⚡ GitHub Secrets & Environment Variables

For the standard **2-Chat Setup** (Central Zone Chat & North Zone Chat), you only need to configure these **2 Webhook Secrets**:

| Secret Name | Purpose | Chat Space Destination |
|---|---|---|
| `CENTRAL_ZONE_GOOGLE_CHAT_WEBHOOK_URL` | Receives Central Zone CCMS, Voltage Anomaly & MCB Trip alerts | 🏛️ **Central Zone Chat Space** |
| `NORTH_ZONE_GOOGLE_CHAT_WEBHOOK_URL` | Receives North Zone CCMS, Voltage Anomaly & MCB Trip alerts | 🌲 **North Zone Chat Space** |

### Optional Granular Webhooks (If separate chats are desired per alert type):
| Secret Name | Description |
|---|---|
| `CENTRAL_VOLTAGE_GOOGLE_CHAT_WEBHOOK_URL` | Central Zone Voltage Alerts only |
| `NORTH_VOLTAGE_GOOGLE_CHAT_WEBHOOK_URL` | North Zone Voltage Alerts only |
| `CENTRAL_MCB_GOOGLE_CHAT_WEBHOOK_URL` | Central Zone MCB Trip Alerts only |
| `NORTH_MCB_GOOGLE_CHAT_WEBHOOK_URL` | North Zone MCB Trip Alerts only |
| `GOOGLE_CHAT_WEBHOOK_URL` | General Fallback Webhook |

### Authentication Secrets:
| Secret Name | Description |
|---|---|
| `THINGSBOARD_BASE_URL` | ThingsBoard Base URL (`https://schnelliot.in`) |
| `THINGSBOARD_USERNAME` | ThingsBoard User Account Email |
| `THINGSBOARD_PASSWORD` | ThingsBoard Password |

---

## ⚡ GitHub Actions & API Repository Dispatch

### Trigger via Repository Dispatch API

#### A. Central Zone Reports
```bash
# CCMS Health Report
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_PAT_TOKEN" \
  https://api.github.com/repos/sharath-00/ward_wise_reports/dispatches \
  -d '{"event_type": "send_central_zone_report", "client_payload": {"zone": "all"}}'

# Voltage Interval Analysis
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_PAT_TOKEN" \
  https://api.github.com/repos/sharath-00/ward_wise_reports/dispatches \
  -d '{"event_type": "voltage_interval_analysis", "client_payload": {"region": "central", "send_only_on_change": false}}'

# MCB Trip Analysis
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_PAT_TOKEN" \
  https://api.github.com/repos/sharath-00/ward_wise_reports/dispatches \
  -d '{"event_type": "mcb_trip_analysis", "client_payload": {"region": "central", "send_only_on_change": false}}'
```

#### B. North Zone Reports
```bash
# CCMS Health Report
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_PAT_TOKEN" \
  https://api.github.com/repos/sharath-00/ward_wise_reports/dispatches \
  -d '{"event_type": "send_north_zone_report", "client_payload": {"zone": "all"}}'

# Voltage Interval Analysis
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_PAT_TOKEN" \
  https://api.github.com/repos/sharath-00/ward_wise_reports/dispatches \
  -d '{"event_type": "voltage_interval_analysis", "client_payload": {"region": "north", "send_only_on_change": false}}'

# MCB Trip Analysis
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_PAT_TOKEN" \
  https://api.github.com/repos/sharath-00/ward_wise_reports/dispatches \
  -d '{"event_type": "mcb_trip_analysis", "client_payload": {"region": "north", "send_only_on_change": false}}'
```

---

## 📁 Repository Structure

- [`zones_report/`](file:///d:/Schnell/Central_Zone_Chat/zones_report): Central Zone report module (CV Raman Nagar, Shanthi Nagar, Shivaji Nagar).
- [`north_zone_report/`](file:///d:/Schnell/Central_Zone_Chat/north_zone_report): North Zone report module (Sarvagna Nagar, Hebbal, Pulakesi Nagar).
- [`voltage_interval_tracker/`](file:///d:/Schnell/Central_Zone_Chat/voltage_interval_tracker): Voltage fluctuation interval tracker.
- [`mcb_interval_tracker/`](file:///d:/Schnell/Central_Zone_Chat/mcb_interval_tracker): MCB Trip interval tracker.
- [`door_interval_tracker/`](file:///d:/Schnell/Central_Zone_Chat/door_interval_tracker): Door Tamper interval tracker.
- [`ward_devices.json`](file:///d:/Schnell/Central_Zone_Chat/ward_devices.json): Inventory of panels for W167 & W118.
- [`main.py`](file:///d:/Schnell/Central_Zone_Chat/main.py): Ward 167 & 118 CLI runner.
