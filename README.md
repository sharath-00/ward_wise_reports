# BBMP Shanthi Nagar (W167) & Shivaji Nagar (W118) Panel Monitor

A dedicated ThingsBoard (Schnell IoT) reporting pipeline that monitors smart street lighting panels strictly for **Shanthi Nagar (Ward 167)** and **Shivaji Nagar (Ward 118)**, generating automated health analytics and delivering rich **Google Chat Card v2** reports into **Google Spaces**.

---

## 🎯 Target Scope

| Ward Name | Ward Code | Total Monitored Panels |
|---|---|---|
| **Shanthi Nagar (Ward 167)** | `SNTR-W167` | **152 Panels** |
| **Shivaji Nagar (Ward 118)** | `SVJR-W118` | **57 Panels** |

---

## 🚀 Commands

### 1. Send Both Ward Reports to Google Spaces
```bash
python main.py --send
```

### 2. Send Specific Ward Only
```bash
# Shanthi Nagar (Ward 167)
python main.py --ward 167 --send

# Shivaji Nagar (Ward 118)
python main.py --ward 118 --send
```

### 3. Dry-Run (Local Console View Without Sending)
```bash
python main.py --dry-run
python main.py --ward 167 --dry-run
python main.py --ward 118 --dry-run
```

### 4. Schedule Automated Daily Reports
Broadcast reports daily at 9:00 AM and 6:00 PM:
```bash
python main.py --send --schedule "09:00,18:00"
```

---

## 📁 File Structure

- [`ward_devices.json`](file:///d:/Schnell/Central_Zone_Chat/ward_devices.json): Dedicated inventory of the 209 panels across W167 & W118.
- [`tb_client.py`](file:///d:/Schnell/Central_Zone_Chat/tb_client.py): Multi-threaded client that queries live attributes and telemetry for target panels.
- [`analyzer.py`](file:///d:/Schnell/Central_Zone_Chat/analyzer.py): Classifies Online/Offline, 0V Power supply failures, MCB tripping, and voltage faults.
- [`google_spaces.py`](file:///d:/Schnell/Central_Zone_Chat/google_spaces.py): Formats Google Chat Card v2 widgets and dispatches to Google Spaces webhook.
- [`main.py`](file:///d:/Schnell/Central_Zone_Chat/main.py): CLI runner and scheduler.
- [`.env`](file:///d:/Schnell/Central_Zone_Chat/.env): Credentials and Webhook configuration.
