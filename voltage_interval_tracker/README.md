# BBMP Central Zone — Voltage Anomaly (Low & High Voltage) Interval Tracker

A standalone interval delta tracking and automated Google Chat notification system for **Low Voltage** and **High Voltage** anomalies across the 4 BBMP Central Zones (**CV Raman Nagar**, **Sarvagna Nagar**, **Shanthi Nagar**, **Shivaji Nagar**).

## Overview

- **Input Issues (ThingsBoard Fault Telemetry)**:
  - **Low Voltage**: Telemetry fault bits `RVL`, `YVL`, `BVL`.
  - **High Voltage**: Telemetry fault bits `RVH`, `YVH`, `BVH`.
- **Interval Delta Tracking**: Compares live panel telemetry with the snapshot in `voltage_state.json`:
  - 🚨 **Newly Detected**: Detailed list of newly anomalous panels with exact voltages, zone, ward, location, Google Maps link, and communication status.
  - 🟢 **Normalized / Recovered**: Panels restored to normal operation (**count only**).
  - 🟡 **Ongoing**: Panels still experiencing low/high voltage.
- **Google Chat Alerts**: Sends clean, formatted notifications to Google Chat spaces.

## Usage

### 1. Console Summary Scan
```bash
python voltage_interval_tracker/main_voltage_tracker.py
```

### 2. Dispatch Notification to Google Chat
```bash
python voltage_interval_tracker/main_voltage_tracker.py --send
```

### 3. Interval / Cron Mode (Only sends alerts when changes occur)
```bash
python voltage_interval_tracker/main_voltage_tracker.py --send --send-only-on-change
```

### 4. Filter Specific Zone
```bash
python voltage_interval_tracker/main_voltage_tracker.py --zone sarvagna_nagar --send
```

### 5. Reset Historical State Baseline
```bash
python voltage_interval_tracker/main_voltage_tracker.py --reset-state
```

## Environment Variables

Configure in `.env`:
- `VOLTAGE_GOOGLE_CHAT_WEBHOOK_URL` (or `GOOGLE_CHAT_WEBHOOK_URL`)
- `TB_URL`, `TB_USERNAME`, `TB_PASSWORD`
