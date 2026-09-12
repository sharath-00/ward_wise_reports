import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("MCBNotifier")


class MCBNotifier:
    """
    Formats and dispatches MCB Trip Interval Delta Alerts to Google Chat Spaces.
    Highlights:
    - 🚨 NEW MCB Trips detected in this specific interval (with exact location & voltages)
    - 🟢 Recovered / Restored Panels
    - 🟡 Ongoing Tripped Panels
    - 📊 Zone Summary Breakdown
    """

    def __init__(self, webhook_url: Optional[str] = None, region: str = "central"):
        self.region = region.lower()
        if self.region == "north":
            raw_url = (
                webhook_url
                or os.getenv("NORTH_MCB_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("NORTH_ZONE_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("MCB_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
            )
        else:
            raw_url = (
                webhook_url
                or os.getenv("CENTRAL_MCB_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("CENTRAL_ZONE_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("MCB_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("ZONES_GOOGLE_CHAT_WEBHOOK_URL")
                or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
            )
        self.webhook_url = str(raw_url).strip() if raw_url else None

    def build_mcb_delta_report(self, delta_results: Dict[str, Any]) -> str:
        """Constructs formatted Google Chat message with delta breakdown."""
        eval_time = delta_results.get("evaluated_at_ist", "")
        prev_time = delta_results.get("previous_run_ist", "Initial Run")
        interval_mins = delta_results.get("interval_mins")
        is_initial = delta_results.get("is_initial_run", False)
        region_title = delta_results.get("region_name", "North Zone" if self.region == "north" else "Central Zone")

        total_new = delta_results.get("total_newly_tripped", 0)
        total_rec = delta_results.get("total_recovered", 0)
        total_ongoing = delta_results.get("total_ongoing", 0)
        total_curr = delta_results.get("total_current_tripped", 0)

        lines = [
            f"⚡ *BBMP {region_title} — MCB Trip Interval Tracker*",
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
            lines.append(f"🚨 *NEW MCB Trips:* *{total_new}*  |  🟢 *Recovered:* *{total_rec}*  |  🟡 *Ongoing:* *{total_ongoing}*")
        elif total_rec > 0:
            lines.append(f"✅ *No New Trips*  |  🟢 *Recovered:* *{total_rec}*  |  🟡 *Ongoing:* *{total_ongoing}*")
        elif total_curr == 0:
            lines.append(f"✨ *ALL CLEAR:* No MCB Trips active across all {region_title} zones!")
        else:
            lines.append(f"ℹ️ *Total Active MCB Trips:* *{total_curr}* (No status changes in this interval)")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        # 1. SECTION: NEWLY TRIPPED PANELS (CRITICAL ALERT)
        all_new_panels = []
        for z_name, z_data in delta_results.get("zones", {}).items():
            for p in z_data.get("newly_tripped", []):
                p["zone_display"] = z_name
                all_new_panels.append(p)

        if all_new_panels:
            lines.append("🚨 *NEWLY TRIPPED PANELS IN THIS INTERVAL:*")
            for idx, p in enumerate(all_new_panels, 1):
                panel_id = p.get("label") or p.get("uid") or p.get("id") or "Unknown"
                device_name = p.get("name") or p.get("gateway_uid") or "-"
                zone = p.get("zone_display") or p.get("zone", "")
                ward = p.get("ward", "")
                loc = p.get("location") or "Location not specified"
                comm_status = p.get("comm_status", "Online")
                fault_str = p.get("fault_str", "MCB")
                last_comm = p.get("last_comm_at", "-")
                volts = p.get("voltages", {})
                v_str = f"R:{volts.get('r', 0)}V Y:{volts.get('y', 0)}V B:{volts.get('b', 0)}V"

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
                lines.append(f"     📍 *Zone:* {zone}  |  🏛️ *Ward:* {ward}")
                lines.append(f"     🗺️ *Lat, Long:* {maps_link}")
                lines.append(f"     🏠 *Location:* {loc}")
                lines.append(f"     ⚡ *Voltages:* `{v_str}`")
                lines.append(f"     ⚠️ *Trip Cause:* `{fault_str}`")
                lines.append(f"     📡 *Status:* {comm_status}  |  🕒 *Last Comm:* {last_comm}")
                lines.append("")
        elif not is_initial:
            lines.append("🟢 *New Trips:* 0 new MCB trips detected in this interval.")
            lines.append("")

        # 2. SECTION: ZONE BREAKDOWN SUMMARY
        lines.append("📊 *Zone Breakdown:*")
        for z_name, z_data in delta_results.get("zones", {}).items():
            c_cnt = z_data.get("current_count", 0)
            n_cnt = len(z_data.get("newly_tripped", []))
            r_cnt = len(z_data.get("recovered", []))
            badge = "🔴" if n_cnt > 0 else ("🟡" if c_cnt > 0 else "🟢")
            lines.append(f"  {badge} *{z_name}:* Active: *{c_cnt}* | New: *{n_cnt}* | Recovered: *{r_cnt}*")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"_⚡ *Schnell IoT BBMP {region_title} Smart Lighting Monitoring*_")
        return "\n".join(lines)

    def send_mcb_report(
        self,
        delta_results: Dict[str, Any],
        webhook_url_override: Optional[str] = None,
    ) -> bool:
        """Post the formatted delta report directly to Google Chat."""
        target_url = webhook_url_override or self.webhook_url
        if not target_url:
            logger.error("No Google Chat Webhook URL configured.")
            return False

        message_text = self.build_mcb_delta_report(delta_results)
        payload = {"text": message_text}

        max_retries = 3
        backoff_delays = [2, 4, 8]

        for attempt in range(max_retries):
            try:
                logger.info("Sending MCB interval alert to Google Chat...")
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

        logger.error(f"Failed to dispatch MCB report to Google Chat after {max_retries} attempts.")
        return False
