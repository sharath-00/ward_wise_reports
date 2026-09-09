import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("MCBAnalyzer")

# Exact 32 Fault Types from ThingsBoard CCMS Dashboard
FAULT_TYPES = [
    "RVL", "RVH", "YVL", "YVH", "BVL", "BVH",
    "RCL", "RCH", "YCL", "YCH", "BCL", "BCH",
    "RPL", "RPH", "YPL", "YPH", "BPL", "BPH",
    "MTR", "RTC", "RIC", "YIC", "BIC",
    "ROC", "YOC", "BOC",
    "TPR", "RCF", "YCF", "BCF",
    "MCB", "BPS"
]


class MCBAnalyzer:
    """
    Evaluates live panel telemetry to detect MCB Trip conditions
    specifically for the 4 BBMP Central Zones, matching the ThingsBoard
    'SLC Panels with MCB Trips' dashboard widget.
    """

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        thresholds = thresholds or {}
        self.min_voltage = float(thresholds.get("min_voltage_v", 180.0))
        self.max_voltage = float(thresholds.get("max_voltage_v", 265.0))
        # 4-hour (14400s) threshold used in ThingsBoard widget
        self.inactivity_threshold_sec = float(thresholds.get("inactivity_threshold_sec", 14400.0))

    def decode_fault_string(self, fault_int: int) -> str:
        """Decode integer bitmask into standard ThingsBoard fault string."""
        if not fault_int:
            return ""
        fault_parts = []
        for code in range(min(len(FAULT_TYPES), 32)):
            if (fault_int & (1 << code)) != 0:
                fault_parts.append(FAULT_TYPES[code])
        return " / ".join(fault_parts)

    def parse_volt(self, val: Any) -> float:
        try:
            v = float(val)
            return round(v / 1000.0, 1) if v > 1000 else round(v, 1)
        except (TypeError, ValueError):
            return 0.0

    def parse_curr(self, val: Any) -> float:
        try:
            c = float(val)
            return round(c / 1000.0, 2) if c > 500 else round(c, 2)
        except (TypeError, ValueError):
            return 0.0

    def evaluate_panel(self, panel: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a single panel for MCB Trip condition and health metrics.
        """
        attrs = panel.get("attributes", {})
        telemetry = panel.get("telemetry", {})

        raw_id = panel.get("id")
        dev_id = raw_id if isinstance(raw_id, str) else (raw_id.get("id") if isinstance(raw_id, dict) else "")

        name = panel.get("name", "Unknown")
        label = panel.get("label", name)
        ward = panel.get("ward") or attrs.get("wardName", "")
        zone = panel.get("zone") or attrs.get("zoneName", "")
        location = attrs.get("location") or panel.get("location", "")
        latitude = str(attrs.get("latitude") or attrs.get("slatitude") or panel.get("latitude") or attrs.get("lat") or "").strip()
        longitude = str(attrs.get("longitude") or attrs.get("slongitude") or panel.get("longitude") or attrs.get("lng") or attrs.get("long") or "").strip()

        state = str(attrs.get("state", "INSTALLED")).upper()
        # Active commissioned panels (exclude warehouse stock INSTALLABLE)
        is_commissioned = state in {"INSTALLED", "ACTIVATED", "TESTED"}

        # 1. Connectivity Check (matches ThingsBoard widget logic)
        systime = telemetry.get("systime")
        last_activity_ts = attrs.get("lastActivityTime")
        now_sec = time.time()

        if systime:
            comm_ts_sec = float(systime)
        elif last_activity_ts:
            comm_ts_sec = float(last_activity_ts) / 1000.0
        else:
            comm_ts_sec = 0.0

        is_online = (now_sec - comm_ts_sec) <= self.inactivity_threshold_sec if comm_ts_sec > 0 else False
        pkt = str(telemetry.get("pkt", ""))
        if pkt == "8":
            comm_status = "Offline(PF)"
        elif is_online:
            comm_status = "Online"
        else:
            comm_status = "Offline"

        last_comm_dt = (
            datetime.fromtimestamp(comm_ts_sec, tz=IST).strftime("%d/%m/%Y, %I:%M:%S %p")
            if comm_ts_sec > 0
            else "-"
        )

        # 2. Voltage & Phase Check
        phase = int(attrs.get("phase", 1))
        rv = self.parse_volt(telemetry.get("rv", 0))
        yv = self.parse_volt(telemetry.get("yv", 0))
        bv = self.parse_volt(telemetry.get("bv", 0))

        ri = self.parse_curr(telemetry.get("ri", 0))
        yi = self.parse_curr(telemetry.get("yi", 0))
        bi = self.parse_curr(telemetry.get("bi", 0))

        try:
            rly = int(telemetry.get("rly", 0))
        except (TypeError, ValueError):
            rly = 0

        mode = "MANUAL" if rly > 1 else "AUTO"

        # 3. Fault Bitmask Evaluation:
        # Bit 30: MCB (ThingsBoard standard MCB Trip fault register)
        # Bit 23: ROC (Relay Output Closed with 0A load)
        fault_int = 0
        try:
            fault_int = int(telemetry.get("fault", 0))
        except (TypeError, ValueError):
            fault_int = 0

        fault_str = self.decode_fault_string(fault_int)
        is_mcb_bit = bool((fault_int & (1 << 30)) != 0)

        # Contactor ON with 0A load check
        is_voltage_available = False
        if phase == 1:
            is_voltage_available = rv >= self.min_voltage
        else:
            is_voltage_available = any(v >= self.min_voltage for v in [rv, yv, bv])

        total_current = ri + yi + bi
        is_instant_trip = (rly == 1) and is_voltage_available and (total_current == 0.0)

        # MCB Trip is active if Bit 30 is set in ThingsBoard OR live instant trip
        is_mcb_tripped = is_commissioned and (is_mcb_bit or is_instant_trip)

        return {
            "id": dev_id,
            "name": name,
            "label": label,
            "uid": label,
            "gateway_uid": name,
            "ward": ward,
            "zone": zone,
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "state": state,
            "is_commissioned": is_commissioned,
            "is_online": is_online,
            "comm_status": comm_status,
            "fault_code": fault_int,
            "fault_str": fault_str,
            "mode": mode,
            "relay_status": rly,
            "is_mcb_tripped": is_mcb_tripped,
            "voltages": {"r": rv, "y": yv, "b": bv},
            "currents": {"r": ri, "y": yi, "b": bi},
            "total_current": total_current,
            "last_comm_at": last_comm_dt,
            "last_comm_ts_sec": comm_ts_sec,
        }

    def filter_tripped_panels(self, panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and return only active commissioned panels that are currently MCB tripped."""
        evaluated = [self.evaluate_panel(p) for p in panels]
        return [p for p in evaluated if p["is_mcb_tripped"]]

