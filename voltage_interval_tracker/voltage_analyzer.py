import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("VoltageAnalyzer")

FAULT_TYPES = [
    "RVL", "RVH", "YVL", "YVH", "BVL", "BVH",
    "RCL", "RCH", "YCL", "YCH", "BCL", "BCH",
    "RPL", "RPH", "YPL", "YPH", "BPL", "BPH",
    "MTR", "RTC", "RIC", "YIC", "BIC",
    "ROC", "YOC", "BOC",
    "TPR", "RCF", "YCF", "BCF",
    "MCB", "BPS"
]


class VoltageAnalyzer:
    """
    Evaluates live panel telemetry to detect Low Voltage (<180V) and High Voltage (>265V)
    conditions specifically for the 4 BBMP Central Zones.
    """

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        thresholds = thresholds or {}
        self.min_voltage = float(thresholds.get("min_voltage_v", 180.0))
        self.max_voltage = float(thresholds.get("max_voltage_v", 265.0))
        self.inactivity_threshold_sec = float(thresholds.get("inactivity_threshold_sec", 14400.0))
        self.max_offline_sec = float(thresholds.get("max_offline_sec", 15 * 86400.0))

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
        Evaluate a single panel for High and Low Voltage anomalies.
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
        is_installed = state == "INSTALLED" or state in {"INSTALLED", "ACTIVATED"}

        # 1. Connectivity Check
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

        is_active_within_window = (now_sec - comm_ts_sec) <= self.max_offline_sec if comm_ts_sec > 0 else False

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

        # 3. Fault Bitmask Evaluation from telemetry 'fault'
        fault_int = 0
        try:
            fault_int = int(telemetry.get("fault", 0) or 0)
        except (TypeError, ValueError):
            fault_int = 0

        fault_str = self.decode_fault_string(fault_int)

        # 4. Exact ThingsBoard "Input Issues" Classification (Matching ThingsBoard Dashboard):
        # Low Voltage: RVL (bit 0), YVL (bit 2), BVL (bit 4)
        is_low_voltage = bool(
            (fault_int & (1 << 0)) or (fault_int & (1 << 2)) or (fault_int & (1 << 4))
        )
        # High Voltage: RVH (bit 1), YVH (bit 3), BVH (bit 5)
        is_high_voltage = bool(
            (fault_int & (1 << 1)) or (fault_int & (1 << 3)) or (fault_int & (1 << 5))
        )

        is_power_failure = (pkt == "8") or (rv < 30.0 if phase == 1 else all(v < 30.0 for v in [rv, yv, bv]))

        # Valid voltage anomaly flag from ThingsBoard Input Issues
        is_voltage_anomaly = (is_low_voltage or is_high_voltage) and is_installed

        anomaly_type = "NONE"
        if is_voltage_anomaly:
            if is_low_voltage and is_high_voltage:
                anomaly_type = "MIXED_VOLTAGE"
            elif is_low_voltage:
                anomaly_type = "LOW_VOLTAGE"
            elif is_high_voltage:
                anomaly_type = "HIGH_VOLTAGE"

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
            "is_installed": is_installed,
            "is_online": is_online,
            "comm_status": comm_status,
            "phase": phase,
            "fault_code": fault_int,
            "fault_str": fault_str,
            "mode": mode,
            "relay_status": rly,
            "is_power_failure": is_power_failure,
            "is_low_voltage": is_low_voltage and is_installed,
            "is_high_voltage": is_high_voltage and is_installed,
            "is_voltage_anomaly": is_voltage_anomaly,
            "anomaly_type": anomaly_type,
            "voltages": {"r": rv, "y": yv, "b": bv},
            "currents": {"r": ri, "y": yi, "b": bi},
            "total_current": ri + yi + bi,
            "last_comm_at": last_comm_dt,
            "last_comm_ts_sec": comm_ts_sec,
        }

    def filter_voltage_anomaly_panels(self, panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and return only active commissioned panels with Low or High Voltage anomalies."""
        evaluated = [self.evaluate_panel(p) for p in panels]
        return [p for p in evaluated if p["is_voltage_anomaly"]]
