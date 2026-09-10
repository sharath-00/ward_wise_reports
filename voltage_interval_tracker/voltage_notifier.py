import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("VoltageNotifier")


class VoltageNotifier:
    """
    Formats and dispatches Voltage Anomaly (High / Low Voltage) Interval Delta Alerts to Google Chat Spaces.
    Highlights:
    - 🚨 NEW Voltage Alerts (Low Voltage <180V, High Voltage >265V) detected in this specific interval
    - 🟢 Normalized / Recovered Panels (Count summary only)
    - 🟡 Ongoing Voltage Anomaly Panels
    - 📊 Zone Summary Breakdown
    """

    def __init__(self, webhook_url: Optional[str] = None):
        raw_url = (
            webhook_url
            or os.getenv("VOLTAGE_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("MCB_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("ZONES_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
        )
        self.webhook_url = str(raw_url).strip() if raw_url else None

    def build_voltage_delta_report(self, delta_results: Dict[str, Any]) -> str:
        """Constructs formatted Google Chat message with delta breakdown for voltage anomalies."""
        eval_time = delta_results.get("evaluated_at_ist", "")
        prev_time = delta_results.get("previous_run_ist", "Initial Run")
        interval_mins = delta_results.get("interval_mins")
        is_initial = delta_results.get("is_initial_run", False)

        total_new = delta_results.get("total_newly_flagged", 0)
        total_new_low = delta_results.get("total_new_low", 0)
        total_new_high = delta_results.get("total_new_high", 0)
        total_rec = delta_results.get("total_recovered", 0)
        total_ongoing = delta_results.get("total_ongoing", 0)
        total_curr = delta_results.get("total_current_anomalies", 0)
        total_curr_low = delta_results.get("total_current_low", 0)
        total_curr_high = delta_results.get("total_current_high", 0)

        lines = [
            "⚡ *BBMP Central Zone — Voltage Anomaly (Low/High) Interval Tracker*",
            f"🕒 *Current Scan:* {eval_time}",
        ]

        if not is_initial and interval_mins is not None:
            lines.append(f"⏱️ *Interval:* Past {interval_mins} mins (Since {prev_time})")
        else:
            lines.append("📌 *Status:* Baseline Initialized")

        lines.append("")

        # High-level summary badges
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if total_new > 0:
            lines.append(
                f"🚨 *NEW Voltage Alerts:* *{total_new}* (🟡 Low: *{total_new_low}*, 🔴 High: *{total_new_high}*)  |  🟢 *Normalized:* *{total_rec}*  |  🟡 *Ongoing:* *{total_ongoing}*"
            )
        elif total_rec > 0:
            lines.append(f"✅ *No New Voltage Alerts*  |  🟢 *Normalized:* *{total_rec}*  |  🟡 *Ongoing:* *{total_ongoing}*")
        elif total_curr == 0:
            lines.append("✨ *ALL CLEAR:* All panels operating within normal voltage range across all 4 Central Zones!")
        else:
            lines.append(f"ℹ️ *Total Active Voltage Anomalies:* *{total_curr}* (Low: *{total_curr_low}*, High: *{total_curr_high}*) (No changes in this interval)")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        # 1. SECTION: NEWLY FLAGGED VOLTAGE ANOMALY PANELS (CRITICAL ALERT)
        all_new_panels = []
        for z_name, z_data in delta_results.get("zones", {}).items():
            for p in z_data.get("newly_flagged", []):
                p["zone_display"] = z_name
                all_new_panels.append(p)

        if all_new_panels:
            lines.append("🚨 *NEWLY DETECTED VOLTAGE ANOMALIES IN THIS INTERVAL:*")
            for idx, p in enumerate(all_new_panels, 1):
                panel_id = p.get("label") or p.get("uid") or p.get("id") or "Unknown"
                device_name = p.get("name") or p.get("gateway_uid") or "-"
                zone = p.get("zone_display") or p.get("zone", "")
                ward = p.get("ward", "")
                loc = p.get("location") or "Location not specified"
                comm_status = p.get("comm_status", "Online")
                last_comm = p.get("last_comm_at", "-")
                volts = p.get("voltages", {})
                v_str = f"R:{volts.get('r', 0)}V Y:{volts.get('y', 0)}V B:{volts.get('b', 0)}V"

                is_low = p.get("is_low_voltage", False)
                is_high = p.get("is_high_voltage", False)
                if is_low and is_high:
                    type_badge = "⚠️ *MIXED VOLTAGE ANOMALY*"
                elif is_low:
                    type_badge = "🟡 *LOW VOLTAGE*"
                elif is_high:
                    type_badge = "🔴 *HIGH VOLTAGE*"
                else:
                    type_badge = "⚡ *VOLTAGE ALERT*"

                lat = str(p.get("latitude") or "").strip()
                lng = str(p.get("longitude") or "").strip()
                if lat and lng:
                    maps_link = f"<https://www.google.com/maps?q={lat},{lng}|{lat}, {lng}>"
                elif lat or lng:
                    coord = lat or lng
                    maps_link = f"<https://www.google.com/maps?q={coord}|{coord}>"
                else:
                    maps_link = "Not Available"

                lines.append(f"  *{idx}. Panel ID:* `{panel_id}`  |  *Device Name:* `{device_name}`")
                lines.append(f"     ⚠️ *Anomaly:* {type_badge}")
                lines.append(f"     📍 *Zone:* {zone}  |  🏛️ *Ward:* {ward}")
                lines.append(f"     🗺️ *Lat, Long:* {maps_link}")
                lines.append(f"     🏠 *Location:* {loc}")
                lines.append(f"     ⚡ *Voltages:* `{v_str}`")
                lines.append(f"     📡 *Status:* {comm_status}  |  🕒 *Last Comm:* {last_comm}")
                lines.append("")
        elif not is_initial:
            lines.append("🟢 *New Voltage Alerts:* 0 new voltage anomalies detected in this interval.")
            lines.append("")

        # 2. SECTION: ZONE BREAKDOWN SUMMARY
        lines.append("📊 *Zone Breakdown:*")
        for z_name, z_data in delta_results.get("zones", {}).items():
            c_cnt = z_data.get("current_count", 0)
            l_cnt = z_data.get("current_low_count", 0)
            h_cnt = z_data.get("current_high_count", 0)
            n_cnt = len(z_data.get("newly_flagged", []))
            r_cnt = len(z_data.get("recovered", []))
            badge = "🔴" if h_cnt > 0 else ("🟡" if l_cnt > 0 else "🟢")
            lines.append(f"  {badge} *{z_name}:* Active: *{c_cnt}* (Low: *{l_cnt}*, High: *{h_cnt}*) | New: *{n_cnt}* | Normalized: *{r_cnt}*")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("_⚡ *Schnell IoT BBMP Central Zone Voltage Monitoring*_")
        return "\n".join(lines)

    def send_voltage_report(
        self,
        delta_results: Dict[str, Any],
        webhook_url_override: Optional[str] = None,
    ) -> bool:
        """Post the formatted delta report directly to Google Chat."""
        target_url = webhook_url_override or self.webhook_url
        if not target_url:
            logger.error("No Google Chat Webhook URL configured (checked VOLTAGE_GOOGLE_CHAT_WEBHOOK_URL, GOOGLE_CHAT_WEBHOOK_URL).")
            return False

        message_text = self.build_voltage_delta_report(delta_results)
        payload = {"text": message_text}

        max_retries = 3
        backoff_delays = [2, 4, 8]

        for attempt in range(max_retries):
            try:
                logger.info("Sending Voltage anomaly interval alert to Google Chat...")
                resp = requests.post(target_url, json=payload, timeout=15)
                if resp.status_code == 200:
                    logger.info("Alert posted successfully to Google Chat.")
                    return True
                elif resp.status_code in (429, 500, 502, 503, 504):
                    wait_time = backoff_delays[attempt]
                    logger.warning(
                        f"Google Chat returned status {resp.status_code}. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})... Response: {resp.text}"
                    )
                    import time
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to post to Google Chat: {resp.status_code} - {resp.text}")
                    return False
            except Exception as e:
                wait_time = backoff_delays[attempt]
                logger.warning(f"Error posting alert to Google Chat webhook: {e}. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                import time
                time.sleep(wait_time)

        logger.error(f"Failed to dispatch Voltage report to Google Chat after {max_retries} attempts.")
        return False
