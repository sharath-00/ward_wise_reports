import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))


class NorthZonesAnalyzer:
    """
    Evaluates telemetry & attributes for BBMP Panels across North Zone:
    - Sarvagna Nagar
    - Hebbal
    - Pulakesi Nagar

    Generates strictly the exact 2-Section format:
    - Section 1: Overview (Total Panels, Online, Offline, Offline PF, % Operational)
    - Section 2: Issue Breakdown (Low Voltage, High Voltage, Power Failure, MCB Trip, Panel Door Open)
    """

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        thresholds = thresholds or {}
        self.min_voltage = float(thresholds.get("min_voltage_v", 180.0))
        self.max_voltage = float(thresholds.get("max_voltage_v", 265.0))
        # 4-hour (240 min / 14400s) threshold matching ThingsBoard CCMS dashboard standard
        self.inactivity_mins = float(thresholds.get("inactivity_threshold_mins", 240.0))

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
        systime = telemetry.get("systime")
        last_activity_ts = attrs.get("lastActivityTime")
        now_sec = time.time()

        if systime:
            try:
                comm_ts_sec = float(systime)
            except (TypeError, ValueError):
                comm_ts_sec = float(last_activity_ts) / 1000.0 if last_activity_ts else 0.0
        elif last_activity_ts:
            try:
                comm_ts_sec = float(last_activity_ts) / 1000.0
            except (TypeError, ValueError):
                comm_ts_sec = 0.0
        else:
            comm_ts_sec = 0.0

        elapsed_seconds = (now_sec - comm_ts_sec) if comm_ts_sec > 0 else 9999999.0

        pkt_val = str(telemetry.get("pkt", attrs.get("pkt", "0")))
        is_pkt_8 = (pkt_val == "8")

        # Panel is Online if it communicated within 4-hour threshold and didn't latch Power Failure packet
        if is_pkt_8:
            is_online = False
        else:
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
        # Bit position 26 in fault bitmask, device state 'INSTALLED', and active within 15 days
        fault_int = 0
        fault_long = 0
        try:
            fault_int = int(telemetry.get("fault", 0) or 0)
        except (TypeError, ValueError):
            fault_int = 0
        try:
            fault_long = int(telemetry.get("faultLong", 0) or 0)
        except (TypeError, ValueError):
            fault_long = 0

        is_door_open = bool(((fault_int >> 26) & 1) or ((fault_long >> 26) & 1)) and (state == "INSTALLED") and (elapsed_seconds <= 15 * 86400)

        # Offline PF determination: pkt == 8 or offline with rv < 30V
        is_offline_pf = False
        if not is_online:
            if is_pkt_8:
                is_offline_pf = True
            elif phase == 1:
                if rv < 30.0:
                    is_offline_pf = True
            else:
                active_phases = sum(1 for v in [rv, yv, bv] if v >= 30.0)
                if active_phases == 0:
                    is_offline_pf = True

        # Classify Health states (Matching ThingsBoard Dashboard Fault Bitmasks)
        is_power_failure = False
        is_low_voltage = bool((fault_int & (1 << 0)) or (fault_int & (1 << 2)) or (fault_int & (1 << 4)))
        is_high_voltage = bool((fault_int & (1 << 1)) or (fault_int & (1 << 3)) or (fault_int & (1 << 5)))
        is_mcb_tripped = False

        if is_online:
            if phase == 1:
                if rv < 30.0:
                    is_power_failure = True
            else:  # 3-Phase
                active_phases = sum(1 for v in [rv, yv, bv] if v >= 30.0)
                if active_phases == 0:
                    is_power_failure = True

            # MCB Trip: Bit 30 (MCB) or Bit 23 (ROC) in fault bitmask OR live contactor ON with 0A load
            is_mcb_fault_bit = bool((fault_int & (1 << 30)) or (fault_int & (1 << 23)))
            if is_mcb_fault_bit or (rly == 1 and (rv >= self.min_voltage) and (ri == 0.0 and yi == 0.0 and bi == 0.0)):
                is_mcb_tripped = True

        is_offline = (not is_online) and (not is_offline_pf)

        return {
            "id": panel.get("id"),
            "name": name,
            "label": label,
            "ward_code": ward_code,
            "zone": zone,
            "is_online": is_online,
            "is_offline": is_offline,
            "is_offline_pf": is_offline_pf,
            "is_power_failure": is_power_failure,
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
        offline_pf_count = sum(1 for p in analyzed_panels if p["is_offline_pf"])
        # Non-PF Offline panels (Offline due to communication / network inactivity)
        offline_count = sum(1 for p in analyzed_panels if (not p["is_online"]) and (not p["is_offline_pf"]))

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
