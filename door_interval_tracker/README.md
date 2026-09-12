# BBMP Central Zone — Panel Door Open Interval Tracker

A standalone interval delta tracking and automated Google Chat notification system for **Panel Door Open / Tamper (TPR)** events across the 4 BBMP Central Zones (**CV Raman Nagar**, **Sarvagna Nagar**, **Shanthi Nagar**, **Shivaji Nagar**).

## Overview

- **Real-Time Delta Analysis**: Compares live ThingsBoard panel telemetry against the previous state snapshot (`door_state.json`) to accurately categorize:
  - 🚨 **Newly Opened**: Panels whose doors opened during the interval (with full details: Panel ID, Device Name, Ward, Google Maps link, Location, Voltages, Communication Status).
  - 🟢 **Closed / Recovered**: Panels whose doors were previously open and are now closed/restored (**aggregate count only**).
  - 🟡 **Ongoing**: Panels that were already open and remain open.
- **Google Chat Alerts**: Sends clean, formatted notifications to Google Chat spaces.
- **Zero Redundant Alerts**: `--send-only-on-change` skips sending if no status changes occurred during the interval.

## Usage

### 1. Run Baseline / CLI Summary
```bash
python door_interval_tracker/main_door_tracker.py
```

### 2. Run with Google Chat Notification
```bash
python door_interval_tracker/main_door_tracker.py --send
```

### 3. Run on Interval / Cron (Only notify when changes occur)
```bash
python door_interval_tracker/main_door_tracker.py --send --send-only-on-change
```

### 4. Filter by Specific Zone
```bash
python door_interval_tracker/main_door_tracker.py --zone shivaji_nagar --send
```

### 5. Reset Historical State
```bash
python door_interval_tracker/main_door_tracker.py --reset-state
```

## Environment Variables

Configure in `.env`:
- `DOOR_GOOGLE_CHAT_WEBHOOK_URL` (or `GOOGLE_CHAT_WEBHOOK_URL`)
- `TB_URL`, `TB_USERNAME`, `TB_PASSWORD`
