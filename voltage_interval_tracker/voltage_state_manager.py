import os
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("VoltageStateManager")


class VoltageStateManager:
    """
    Manages state persistence and interval delta analysis for Low Voltage and High Voltage anomalies
    across BBMP Central Zones.
    """

    def __init__(self, state_file_path: Optional[str] = None):
        if state_file_path:
            self.state_file = state_file_path
        else:
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            self.state_file = os.path.join(curr_dir, "voltage_state.json")

    def load_previous_state(self) -> Dict[str, Any]:
        """Load historical voltage state from disk."""
        if not os.path.exists(self.state_file):
            logger.info(f"No previous state found at {self.state_file}. Starting fresh baseline.")
            return {
                "last_run_timestamp": None,
                "last_run_ist": None,
                "zones": {},
            }

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"Error loading previous state from {self.state_file}: {e}")
            return {
                "last_run_timestamp": None,
                "last_run_ist": None,
                "zones": {},
            }

    def save_current_state(self, current_state: Dict[str, Any]) -> bool:
        """Persist current voltage snapshot to disk."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_file)), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(current_state, f, indent=2)
            logger.info(f"Successfully saved updated voltage state snapshot to {self.state_file}.")
            return True
        except Exception as e:
            logger.error(f"Error saving state to {self.state_file}: {e}")
            return False

    def compute_interval_deltas(
        self,
        current_zone_voltage_anomalies: Dict[str, List[Dict[str, Any]]],
        previous_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare current live voltage anomaly panels against previous snapshot.
        Categorizes into:
        - newly_flagged: Panels that developed Low/High voltage during this interval
        - recovered: Panels previously abnormal, now normalized back into normal range
        - ongoing: Panels that were already abnormal and remain abnormal
        """
        now_ts = int(time.time() * 1000)
        now_ist = datetime.now(tz=IST).strftime("%d-%b-%Y %I:%M %p IST")
        prev_ts = previous_state.get("last_run_timestamp")
        prev_ist = previous_state.get("last_run_ist", "Initial Baseline")

        interval_mins = round((now_ts - prev_ts) / (1000.0 * 60.0), 1) if prev_ts else None

        prev_zones = previous_state.get("zones", {})
        delta_results: Dict[str, Any] = {
            "evaluated_at_ts": now_ts,
            "evaluated_at_ist": now_ist,
            "previous_run_ist": prev_ist,
            "interval_mins": interval_mins,
            "is_initial_run": prev_ts is None,
            "zones": {},
            "total_newly_flagged": 0,
            "total_new_low": 0,
            "total_new_high": 0,
            "total_recovered": 0,
            "total_ongoing": 0,
            "total_current_low": 0,
            "total_current_high": 0,
            "total_current_anomalies": 0,
        }

        updated_state_zones: Dict[str, Dict[str, Any]] = {}

        all_zone_names = sorted(set(list(current_zone_voltage_anomalies.keys()) + list(prev_zones.keys())))

        for z_name in all_zone_names:
            curr_anomalies = current_zone_voltage_anomalies.get(z_name, [])
            prev_zone_data = prev_zones.get(z_name, {})
            prev_anomalies_dict = prev_zone_data.get("voltage_anomaly_panels", {})

            curr_dict = {p["id"]: p for p in curr_anomalies if p.get("id")}

            newly_flagged = []
            recovered = []
            ongoing = []

            curr_low_cnt = sum(1 for p in curr_anomalies if p.get("is_low_voltage"))
            curr_high_cnt = sum(1 for p in curr_anomalies if p.get("is_high_voltage"))

            # 1. Check current anomaly panels against previous
            for dev_id, panel in curr_dict.items():
                if dev_id not in prev_anomalies_dict:
                    panel_copy = dict(panel)
                    panel_copy["anomaly_detected_ts"] = now_ts
                    panel_copy["anomaly_detected_ist"] = now_ist
                    panel_copy["anomaly_duration_mins"] = 0
                    newly_flagged.append(panel_copy)
                    if panel.get("is_low_voltage"):
                        delta_results["total_new_low"] += 1
                    if panel.get("is_high_voltage"):
                        delta_results["total_new_high"] += 1
                else:
                    prev_panel = prev_anomalies_dict[dev_id]
                    panel_copy = dict(panel)
                    orig_ts = prev_panel.get("anomaly_detected_ts", prev_ts or now_ts)
                    panel_copy["anomaly_detected_ts"] = orig_ts
                    panel_copy["anomaly_detected_ist"] = prev_panel.get("anomaly_detected_ist", prev_ist)
                    panel_copy["anomaly_duration_mins"] = round((now_ts - orig_ts) / (1000.0 * 60.0), 1)
                    ongoing.append(panel_copy)

            # 2. Check previous anomaly panels for RECOVERED / NORMALIZED panels
            for dev_id, prev_panel in prev_anomalies_dict.items():
                if dev_id not in curr_dict:
                    rec_panel = dict(prev_panel)
                    orig_ts = prev_panel.get("anomaly_detected_ts", prev_ts or now_ts)
                    rec_panel["recovered_at_ts"] = now_ts
                    rec_panel["recovered_at_ist"] = now_ist
                    rec_panel["total_anomaly_duration_mins"] = round((now_ts - orig_ts) / (1000.0 * 60.0), 1)
                    recovered.append(rec_panel)

            delta_results["zones"][z_name] = {
                "current_count": len(curr_dict),
                "current_low_count": curr_low_cnt,
                "current_high_count": curr_high_cnt,
                "newly_flagged": newly_flagged,
                "recovered": recovered,
                "ongoing": ongoing,
            }

            delta_results["total_newly_flagged"] += len(newly_flagged)
            delta_results["total_recovered"] += len(recovered)
            delta_results["total_ongoing"] += len(ongoing)
            delta_results["total_current_low"] += curr_low_cnt
            delta_results["total_current_high"] += curr_high_cnt
            delta_results["total_current_anomalies"] += len(curr_dict)

            # Build updated snapshot for zone
            active_anomalies_for_snapshot = {}
            for p in newly_flagged + ongoing:
                active_anomalies_for_snapshot[p["id"]] = {
                    "id": p["id"],
                    "name": p.get("name", ""),
                    "label": p.get("label", ""),
                    "uid": p.get("uid") or p.get("label", ""),
                    "gateway_uid": p.get("gateway_uid") or p.get("name", ""),
                    "ward": p.get("ward", ""),
                    "zone": p.get("zone", z_name),
                    "location": p.get("location", ""),
                    "latitude": p.get("latitude", ""),
                    "longitude": p.get("longitude", ""),
                    "comm_status": p.get("comm_status", "Online"),
                    "anomaly_type": p.get("anomaly_type", "LOW_VOLTAGE"),
                    "is_low_voltage": p.get("is_low_voltage", False),
                    "is_high_voltage": p.get("is_high_voltage", False),
                    "voltages": p.get("voltages", {}),
                    "currents": p.get("currents", {}),
                    "last_comm_at": p.get("last_comm_at", ""),
                    "anomaly_detected_ts": p.get("anomaly_detected_ts", now_ts),
                    "anomaly_detected_ist": p.get("anomaly_detected_ist", now_ist),
                }

            updated_state_zones[z_name] = {
                "voltage_anomaly_panels": active_anomalies_for_snapshot,
                "last_updated_ist": now_ist,
            }

        new_state_snapshot = {
            "last_run_timestamp": now_ts,
            "last_run_ist": now_ist,
            "zones": updated_state_zones,
        }

        return {
            "delta_analysis": delta_results,
            "new_state_snapshot": new_state_snapshot,
        }
