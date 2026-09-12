import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("NorthZonesNotifier")


class NorthZonesNotifier:
    """
    Formats and dispatches North Zone Telemetry Reports to Google Chat Spaces
    matching the exact BBMP CCMS report format with bold region names and headings.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        raw_url = (
            webhook_url
            or os.getenv("NORTH_ZONE_TELEMETRY_CHAT_WEBHOOK_URL")
            or os.getenv("NORTH_ZONE_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("ZONES_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
        )
        self.webhook_url = str(raw_url).strip() if raw_url else None

    def build_text_report(self, all_reports: List[Dict[str, Any]]) -> str:
        """
        Constructs clean report with bold region names and important headings:
        ⚡ *BBMP North Zone — CCMS Health Report*
        🕒 *08-Sep-2026 05:00 PM IST*

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        📍 *Sarvagna Nagar* — 🟢 *95.4% Online*
        • *Total Panels:* 761  |  *Online Panels:* 725  |  *Offline Panels:* 36
        • *Offline PF Panels:* 20  |  *Relay Status:* 🟢 700 ON / 🔴 25 OFF
        • ⚠️ *Issue Breakdown:*
        🟡 *Low Voltage:* 2
        🟠 *High Voltage:* 0
        ⚡ *Power Failure:* 15
        ⚙️ *MCB Trip:* 3
        🚪 *Panel Door Open:* 5

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _⚡ *Schnell IoT Smart Lighting CCMS Monitoring*_
        """
        generated_at = all_reports[0].get("generated_at", "") if all_reports else ""
        lines = [
            "⚡ *BBMP North Zone — CCMS Health Report*",
            f"🕒 *{generated_at}*\n",
        ]

        for r in all_reports:
            z_name = r.get("zone_name", "Zone")
            sec1 = r.get("section1_overview", {})
            sec2 = r.get("section2_issues", {})

            total = sec1.get("total_panels", 0)
            online = sec1.get("online_panels", 0)
            offline = sec1.get("offline_panels", 0)
            offline_pf = sec1.get("offline_pf_panels", 0)
            online_pct = sec1.get("online_pct", 0.0)

            if online_pct >= 90.0:
                badge = f"🟢 *{online_pct}% Online*"
            elif online_pct >= 75.0:
                badge = f"🟡 *{online_pct}% Online*"
            else:
                badge = f"🔴 *{online_pct}% Online*"

            low_volt = sec2.get("low_voltage", 0)
            high_volt = sec2.get("high_voltage", 0)
            pf = sec2.get("power_failure", 0)
            mcb_trip = sec2.get("mcb_trip", 0)
            door_open = sec2.get("panel_door_open", 0)

            lines.extend([
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📍 *{z_name}* — {badge}",
                f"• *Total Panels:* {total}  |  *Online Panels:* {online}  |  *Offline Panels:* {offline}",
                f"• *Offline PF Panels:* {offline_pf}  |  *Relay Status:* 🟢 {sec1.get('relay_on', 0)} ON / 🔴 {sec1.get('relay_off', 0)} OFF",
                "• ⚠️ *Issue Breakdown:*",
                f"🟡 *Low Voltage:* {low_volt}",
                f"🟠 *High Voltage:* {high_volt}",
                f"⚡ *Power Failure:* {pf}",
                f"⚙️ *MCB Trip:* {mcb_trip}",
                f"🚪 *Panel Door Open:* {door_open}\n",
            ])

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("_⚡ *Schnell IoT Smart Lighting CCMS Monitoring*_")
        return "\n".join(lines)

    def send_report(
        self,
        all_reports: List[Dict[str, Any]],
        webhook_url_override: Optional[str] = None,
    ) -> bool:
        """Send the aggregated North Zone report to Google Chat with automatic retry on transient errors."""
        import time

        url = (
            webhook_url_override
            or os.getenv("NORTH_ZONE_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("ZONES_GOOGLE_CHAT_WEBHOOK_URL")
            or self.webhook_url
        )
        if not url:
            logger.error("No Google Chat Webhook URL configured.")
            return False

        headers = {"Content-Type": "application/json; charset=UTF-8"}
        text_message = self.build_text_report(all_reports)
        payload = {"text": text_message}

        max_retries = 3
        backoff_delays = [2, 4, 8]

        for attempt in range(max_retries):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 200:
                    logger.info("Successfully dispatched North Zone report to Google Chat.")
                    return True
                elif resp.status_code in (429, 500, 502, 503, 504):
                    wait_time = backoff_delays[attempt]
                    logger.warning(
                        f"Google Chat returned status {resp.status_code}. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})... Response: {resp.text}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to send to Google Chat ({resp.status_code}): {resp.text}")
                    return False
            except Exception as e:
                wait_time = backoff_delays[attempt]
                logger.warning(f"Error posting to Google Chat: {e}. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)

        logger.error(f"Failed to dispatch North Zone report to Google Chat after {max_retries} attempts.")
        return False
