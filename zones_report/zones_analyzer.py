import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))


class ZonesAnalyzer:
    """
    Evaluates telemetry & attributes for BBMP Panels across 4 Zones:
    - CV Raman Nagar
    - Sarvagna Nagar
    - Shanthi Nagar
    - Shivaji Nagar

    Generates strictly the exact 2-Section format:
    - Section 1: Overview (Total Panels, Online, Offline, Offline PF, % Operational)
    - Section 2: Issue Breakdown (Low Voltage, High Voltage, Power Failure, MCB Trip, Panel Door Open)
    """

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        thresholds = thresholds or {}
        self.min_voltage = float(thresholds.get("min_voltage_v", 180.0))
        self.max_voltage = float(thresholds.get("max_voltage_v", 265.0))
        self.inactivity_mins = float(thresholds.get("inactivity_threshold_mins", 77.0))

    def _format_timestamp(self, ts_ms: Optional[int]) -> str:
        if not ts_ms:
            return "Never"
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=IST)
            return dt.strftime("%d-%b-%Y %I:%M %p")
        except Exception:
            return "Invalid TS"

    def analyze_single_panel(self, panel: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single panel's telemetry and attributes."""
        attrs = panel.get("attributes", {})
        telemetry = panel.get("telemetry", {})

        name = panel.get("name", "Unknown")
        label = panel.get("label", name)
        ward_code = panel.get("ward") or attrs.get("wardName", "")
        zone = panel.get("zone") or attrs.get("zoneName", "")

        # 1. Connectivity Check
        last_activity_ts = attrs.get("lastActivityTime")
        now_ts = int(time.time() * 1000)

        elapsed_seconds = (
            (now_ts - last_activity_ts) / 1000.0 if last_activity_ts else 999999
        )

        # Panel is Online if it communicated within inactivity threshold
        is_online = elapsed_seconds <= (self.inactivity_mins * 60)

        # 2. Voltage & Phase Check
        phase = int(attrs.get("phase", 1))

        def parse_volt(val):
            try:
                v = float(val)
                return v / 1000.0 if v > 1000 else v
            except (TypeError, ValueError):
                return 0.0

        rv = parse_volt(telemetry.get("rv", 0))
        yv = parse_volt(telemetry.get("yv", 0))
        bv = parse_volt(telemetry.get("bv", 0))

        def parse_curr(val):
            try:
                c = float(val)
                return c / 1000.0 if c > 500 else c
            except (TypeError, ValueError):
                return 0.0

        ri = parse_curr(telemetry.get("ri", 0))
        yi = parse_curr(telemetry.get("yi", 0))
        bi = parse_curr(telemetry.get("bi", 0))

        rly = int(telemetry.get("rly", 0))
        state = str(attrs.get("state", "INSTALLED")).upper()

        # Schnell IoT CCMS Door Tamper / Door Open:
        # Bit position 26 in fault bitmask AND device state is 'INSTALLED'
        fault_int = 0
        try:
            fault_int = int(telemetry.get("fault", 0)) | int(telemetry.get("faultLong", 0))
        except (TypeError, ValueError):
            fault_int = 0

        is_door_open = bool((fault_int >> 26) & 1) and (state == "INSTALLED")

        # Classify health status
        is_power_failure = False
        is_low_voltage = False
        is_high_voltage = False
        is_mcb_tripped = False

        if phase == 1:
            if rv < 30.0:
                is_power_failure = True
            elif rv < self.min_voltage:
                is_low_voltage = True
            elif rv > self.max_voltage:
                is_high_voltage = True
        else:  # 3-Phase
            active_phases = sum(1 for v in [rv, yv, bv] if v >= 30.0)
            if active_phases == 0:
                is_power_failure = True
            else:
                for v in [rv, yv, bv]:
                    if 30.0 <= v < self.min_voltage:
                        is_low_voltage = True
                    elif v > self.max_voltage:
                        is_high_voltage = True

        # MCB Trip: Relay ON (rly == 1), power available (rv >= min_voltage), but 0A current
        if rly == 1 and (rv >= self.min_voltage) and (ri == 0.0 and yi == 0.0 and bi == 0.0):
            is_mcb_tripped = True

        is_offline_pf = (not is_online) and is_power_failure

        return {
            "id": panel.get("id"),
            "name": name,
            "label": label,
            "ward_code": ward_code,
            "zone": zone,
            "is_online": is_online,
            "is_power_failure": is_power_failure,
            "is_offline_pf": is_offline_pf,
            "is_low_voltage": is_low_voltage,
            "is_high_voltage": is_high_voltage,
            "is_mcb_tripped": is_mcb_tripped,
            "is_door_open": is_door_open,
            "voltages": {"r": round(rv, 1), "y": round(yv, 1), "b": round(bv, 1)},
            "currents": {"r": round(ri, 2), "y": round(yi, 2), "b": round(bi, 2)},
            "relay_status": rly,
        }

    def generate_zone_report(
        self, zone_display_name: str, panels: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        # Keep only commissioned panels (INSTALLED / ACTIVATED) to match dashboard counts exactly
        active_panels = [
            p for p in panels
            if str(p.get("attributes", {}).get("state", "INSTALLED")).upper() in {"INSTALLED", "ACTIVATED"}
        ]
        analyzed_panels = [self.analyze_single_panel(p) for p in active_panels]

        total = len(analyzed_panels)
        online_count = sum(1 for p in analyzed_panels if p["is_online"])
        offline_count = total - online_count
        offline_pf_count = sum(1 for p in analyzed_panels if p["is_offline_pf"])

        low_voltage_count = sum(1 for p in analyzed_panels if p["is_low_voltage"])
        high_voltage_count = sum(1 for p in analyzed_panels if p["is_high_voltage"])
        power_fail_count = sum(1 for p in analyzed_panels if p["is_power_failure"])
        mcb_trip_count = sum(1 for p in analyzed_panels if p["is_mcb_tripped"])
        door_open_count = sum(1 for p in analyzed_panels if p["is_door_open"])

        # Relay ON / OFF is evaluated for active/online panels
        relay_on_count = sum(1 for p in analyzed_panels if p["is_online"] and p.get("relay_status") == 1)
        relay_off_count = sum(1 for p in analyzed_panels if p["is_online"] and p.get("relay_status") == 0)

        online_pct = round((online_count / total * 100.0), 1) if total > 0 else 0.0
        generated_at = datetime.now(tz=IST).strftime("%d-%b-%Y %I:%M %p IST")

        return {
            "zone_name": zone_display_name,
            "generated_at": generated_at,
            "section1_overview": {
                "total_panels": total,
                "online_panels": online_count,
                "offline_panels": offline_count,
                "offline_pf_panels": offline_pf_count,
                "online_pct": online_pct,
                "relay_on": relay_on_count,
                "relay_off": relay_off_count,
                "relay_status": f"{relay_on_count} ON / {relay_off_count} OFF",
            },
            "section2_issues": {
                "low_voltage": low_voltage_count,
                "high_voltage": high_voltage_count,
                "power_failure": power_fail_count,
                "mcb_trip": mcb_trip_count,
                "panel_door_open": door_open_count,
            },
        }
