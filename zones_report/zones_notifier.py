import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("ZonesNotifier")


class ZonesNotifier:
    """
    Formats and dispatches 4-Zone Telemetry Reports to Google Chat Spaces
    matching the exact BBMP Central Zone CCMS report format with bold region names and headings.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        raw_url = (
            webhook_url
            or os.getenv("ZONES_GOOGLE_CHAT_WEBHOOK_URL")
            or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
        )
        self.webhook_url = str(raw_url).strip() if raw_url else None

    def build_text_report(self, all_reports: List[Dict[str, Any]]) -> str:
        """
        Constructs clean report with bold region names and important headings:
        ⚡ *BBMP Central Zone — CCMS Health Report*
        🕒 *08-Sep-2026 05:00 PM IST*

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        📍 *Shanthi Nagar* — 🟢 *95.4% Online*
        • *Total Panels:* 152  |  *Online Panels:* 145  |  *Offline Panels:* 7
        • *Offline PF Panels:* 5
        • ⚠️ *Issue Breakdown:*
        🟡 *Low Voltage:* 0
        🟠 *High Voltage:* 0
        ⚡ *Power Failure:* 6
        ⚙️ *MCB Trip:* 1
        🚪 *Panel Door Open:* 2

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _⚡ *Schnell IoT Smart Lighting CCMS Monitoring*_
        """
        generated_at = all_reports[0].get("generated_at", "") if all_reports else ""
        lines = [
            "⚡ *BBMP Central Zone — CCMS Health Report*",
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
        """Send the aggregated zone report to Google Chat."""
        url = (
            webhook_url_override
            or os.getenv("ZONES_GOOGLE_CHAT_WEBHOOK_URL")
            or self.webhook_url
        )
        if not url:
            logger.error("No Google Chat Webhook URL configured.")
            return False

        headers = {"Content-Type": "application/json; charset=UTF-8"}
        text_message = self.build_text_report(all_reports)
        payload = {"text": text_message}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            if resp.status_code == 200:
                logger.info("Successfully dispatched 4-Zone report to Google Chat.")
                return True
            else:
                logger.error(f"Failed to send to Google Chat ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to post report to Google Chat: {e}")
            return False
