import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional

logger = logging.getLogger("GoogleSpacesNotifier")


class GoogleSpacesNotifier:
    """
    Constructs and dispatches clean Google Chat Card v2 reports to Google Spaces.
    Supports single ward card or combined multi-ward card in a single request body.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        raw_url = webhook_url or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
        self.webhook_url = str(raw_url).strip() if raw_url else None

    def _create_ward_sections(self, report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create a unified, easy-to-read section for a ward with status badges and smart issue highlighting."""
        ward_name = report_data.get("zone_name", "BBMP Ward")
        sec1 = report_data.get("section1_overview", {})
        sec2 = report_data.get("section2_issues", {})

        total = sec1.get("total_panels", 0)
        online = sec1.get("online_panels", 0)
        offline = sec1.get("offline_panels", 0)
        offline_pf = sec1.get("offline_pf_panels", 0)
        online_pct = sec1.get("online_pct", 0.0)

        low_volt = sec2.get("low_voltage", 0)
        high_volt = sec2.get("high_voltage", 0)
        pf = sec2.get("power_failure", 0)
        mcb_trip = sec2.get("mcb_trip", 0)
        door_open = sec2.get("panel_door_open", 0)

        # Health badge indicator based on operational percentage
        if online_pct >= 90.0:
            status_badge = f"🟢 {online_pct}% Operational"
        elif online_pct >= 75.0:
            status_badge = f"🟡 {online_pct}% Needs Attention"
        else:
            status_badge = f"🔴 {online_pct}% Critical"

        all_issue_lines = [
            f"⚡ <b>Power Failure (0V):</b> <b>{pf}</b>",
            f"⚙️ <b>MCB Tripped:</b> <b>{mcb_trip}</b>",
            f"🚪 <b>Door Open / Tamper:</b> <b>{door_open}</b>",
            f"📉 <b>Low Voltage (&lt;180V):</b> <b>{low_volt}</b>",
            f"📈 <b>High Voltage (&gt;265V):</b> <b>{high_volt}</b>",
        ]

        issue_widgets = [
            {
                "decoratedText": {
                    "startIcon": {"knownIcon": "MEMBERSHIP"},
                    "topLabel": "⚠️ ISSUE BREAKDOWN",
                    "text": "<br>".join(all_issue_lines),
                }
            }
        ]

        return [
            {
                "header": f"📍 {ward_name}  •  {status_badge}",
                "widgets": [
                    {
                        "columns": {
                            "columnItems": [
                                {
                                    "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                                    "horizontalAlignment": "CENTER",
                                    "widgets": [
                                        {
                                            "decoratedText": {
                                                "topLabel": "TOTAL PANELS",
                                                "text": f"<b><font color=\"#1a73e8\">{total}</font></b>",
                                            }
                                        }
                                    ],
                                },
                                {
                                    "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                                    "horizontalAlignment": "CENTER",
                                    "widgets": [
                                        {
                                            "decoratedText": {
                                                "topLabel": "ONLINE PANELS",
                                                "text": f"<b><font color=\"#137333\">{online}</font></b> ({online_pct}%)",
                                            }
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                    {
                        "columns": {
                            "columnItems": [
                                {
                                    "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                                    "horizontalAlignment": "CENTER",
                                    "widgets": [
                                        {
                                            "decoratedText": {
                                                "topLabel": "OFFLINE PANELS",
                                                "text": f"<b><font color=\"#d93025\">{offline}</font></b>",
                                            }
                                        }
                                    ],
                                },
                                {
                                    "horizontalSizeStyle": "FILL_AVAILABLE_SPACE",
                                    "horizontalAlignment": "CENTER",
                                    "widgets": [
                                        {
                                            "decoratedText": {
                                                "topLabel": "OFFLINE (NO POWER)",
                                                "text": f"<b><font color=\"#ea8600\">{offline_pf}</font></b>",
                                            }
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                    *issue_widgets,
                ],
            }
        ]

    def build_combined_card_v2(self, all_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine all ward reports into a single unified Google Chat Card v2 request body."""
        all_sections = []
        generated_at = all_reports[0].get("generated_at", "") if all_reports else ""

        for report in all_reports:
            ward_sections = self._create_ward_sections(report)
            all_sections.extend(ward_sections)

        # Append clean common footer section
        all_sections.append({
            "widgets": [
                {
                    "decoratedText": {
                        "bottomLabel": f"Report generated at {generated_at} • Schnell IoT BBMP CCMS Monitoring",
                    }
                }
            ]
        })

        card_title = (
            "BBMP Central Zone • CCMS Health Report"
            if len(all_reports) > 1
            else f"BBMP Panel Report: {all_reports[0].get('zone_name')}"
        )
        card_subtitle = (
            "Live Status Summary • Shanthi Nagar (W167) & Shivaji Nagar (W118)"
            if len(all_reports) > 1
            else f"Live Status Summary • {generated_at}"
        )

        card_payload = {
            "cardsV2": [
                {
                    "cardId": f"bbmp-combined-{int(os.times().elapsed * 1000)}",
                    "card": {
                        "header": {
                            "title": card_title,
                            "subtitle": card_subtitle,
                            "imageUrl": "https://img.icons8.com/fluency/96/street-light.png",
                            "imageType": "SQUARE",
                        },
                        "sections": all_sections,
                    },
                }
            ]
        }
        return card_payload

    def build_markdown_fallback(self, all_reports: List[Dict[str, Any]]) -> str:
        """Construct clean markdown text displaying exact dashboard metrics and issue breakdown."""
        generated_at = all_reports[0].get("generated_at", "") if all_reports else ""
        lines = [
            "⚡ *BBMP Central Zone — CCMS Health Report*",
            f"🕒 _{generated_at}_\n",
        ]

        for r in all_reports:
            w_name = r.get("zone_name", "Ward")
            sec1 = r.get("section1_overview", {})
            sec2 = r.get("section2_issues", {})

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
                f"📍 *{w_name}* — {badge}",
                f"• *Total Panels:* {sec1.get('total_panels', 0)}  |  *Online Panels:* {sec1.get('online_panels', 0)}  |  *Offline Panels:* {sec1.get('offline_panels', 0)}",
                f"• *Offline PF Panels:* {sec1.get('offline_pf_panels', 0)}  |  *Relay Status:* 🟢 {sec1.get('relay_on', 0)} ON / 🔴 {sec1.get('relay_off', 0)} OFF",
                f"• ⚠️ *Issue Breakdown:*",
                f"   - 🟡 *Low Voltage:* {low_volt}",
                f"   - 🟠 *High Voltage:* {high_volt}",
                f"   - ⚡ *Power Failure:* {pf}",
                f"   - ⚙️ *MCB Trip:* {mcb_trip}",
                f"   - 🚪 *Panel Door Open:* {door_open}\n",
            ])

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("_⚡ Schnell IoT Smart Lighting CCMS Monitoring_")
        return "\n".join(lines)

    def send_combined_report(
        self,
        all_reports: List[Dict[str, Any]],
        webhook_url: Optional[str] = None,
        use_card: bool = False,
    ) -> bool:
        """Send all ward reports in a single unified message request body."""
        target_url = webhook_url or self.webhook_url
        if not target_url:
            logger.error("No Google Chat Webhook URL provided. Unable to send notification.")
            return False

        headers = {"Content-Type": "application/json; charset=UTF-8"}

        if use_card:
            payload = self.build_combined_card_v2(all_reports)
        else:
            payload = {"text": self.build_markdown_fallback(all_reports)}

        max_retries = 3
        backoff_delays = [2, 4, 8]

        for attempt in range(max_retries):
            try:
                resp = requests.post(target_url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 200:
                    logger.info("Successfully delivered report to Google Spaces.")
                    return True
                elif resp.status_code in (429, 500, 502, 503, 504):
                    wait_time = backoff_delays[attempt]
                    logger.warning(
                        f"Google Chat returned status {resp.status_code}. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})... Response: {resp.text}"
                    )
                    import time
                    time.sleep(wait_time)
                else:
                    logger.warning(
                        f"Send failed ({resp.status_code}): {resp.text}."
                    )
                    return False
            except Exception as e:
                wait_time = backoff_delays[attempt]
                logger.warning(f"Error posting combined message to Google Spaces: {e}. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                import time
                time.sleep(wait_time)

        logger.error(f"Failed to dispatch combined report to Google Spaces after {max_retries} attempts.")
        return False
