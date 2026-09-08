import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("GoogleSpacesNotifier")


class GoogleSpacesNotifier:
    """
    Constructs and dispatches clean Google Chat Card v2 reports to Google Spaces.
    Section 1: Ward Overview (Total Panels, Online Panels, Offline Panels, Offline PF Panels)
    Section 2: Issue Breakdown (Low Voltage, High Voltage, Power Failure, MCB Trip, Panel Door Open)
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")

    def build_card_v2(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Construct a clean, elegant Google Chat Card v2 layout."""
        ward_name = report_data.get("zone_name", "BBMP Ward")
        sec1 = report_data.get("section1_overview", {})
        sec2 = report_data.get("section2_issues", {})
        generated_at = report_data.get("generated_at", "")

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

        sections = [
            # SECTION 1: 4 Metric Cards
            {
                "header": f"📍 {ward_name}",
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
                                                "text": f"<b><font color=\"#c5221f\">{offline}</font></b>",
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
                                                "topLabel": "OFFLINE PF PANELS",
                                                "text": f"<b><font color=\"#b06000\">{offline_pf}</font></b>",
                                            }
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                ],
            },
            # SECTION 2: Issue Breakdown
            {
                "header": "⚠️ Issue Breakdown",
                "widgets": [
                    {
                        "decoratedText": {
                            "startIcon": {
                                "knownIcon": "MEMBERSHIP"
                            },
                            "topLabel": "VOLTAGE ANOMALIES",
                            "text": f"<b>Low Voltage:</b> {low_volt} &nbsp;&nbsp;|&nbsp;&nbsp; <b>High Voltage:</b> {high_volt}",
                        }
                    },
                    {
                        "decoratedText": {
                            "startIcon": {
                                "knownIcon": "CLOCK"
                            },
                            "topLabel": "SUPPLY & TRIPPING",
                            "text": f"<b>Power Failure:</b> {pf} &nbsp;&nbsp;|&nbsp;&nbsp; <b>MCB Trip:</b> {mcb_trip}",
                        }
                    },
                    {
                        "decoratedText": {
                            "startIcon": {
                                "knownIcon": "DESCRIPTION"
                            },
                            "topLabel": "PHYSICAL TAMPER / SECURITY",
                            "text": f"<b>Panel Door Open:</b> {door_open}",
                        }
                    },
                    {
                        "decoratedText": {
                            "bottomLabel": f"Report generated at {generated_at}",
                        }
                    },
                ],
            },
        ]

        card_payload = {
            "cardsV2": [
                {
                    "cardId": f"bbmp-ward-{int(os.times().elapsed * 1000)}",
                    "card": {
                        "header": {
                            "title": f"BBMP Panel Report: {ward_name}",
                            "subtitle": "Schnell IoT CCMS & Smart Lighting Health Summary",
                            "imageUrl": "https://img.icons8.com/fluency/96/street-light.png",
                            "imageType": "SQUARE",
                        },
                        "sections": sections,
                    },
                }
            ]
        }
        return card_payload

    def build_markdown_fallback(self, report_data: Dict[str, Any]) -> str:
        """Construct clean formatted markdown text for fallback."""
        ward_name = report_data.get("zone_name", "BBMP Ward")
        sec1 = report_data.get("section1_overview", {})
        sec2 = report_data.get("section2_issues", {})
        generated_at = report_data.get("generated_at", "")

        lines = [
            f"*{ward_name} - Panel Health Report*",
            f"🕒 _Generated: {generated_at}_\n",
            f"📊 *Ward Overview:*",
            f"• *Total Panels:* {sec1.get('total_panels', 0)}",
            f"• *Online Panels:* {sec1.get('online_panels', 0)} ({sec1.get('online_pct', 0)}%)",
            f"• *Offline Panels:* {sec1.get('offline_panels', 0)}",
            f"• *Offline PF Panels:* {sec1.get('offline_pf_panels', 0)}\n",
            f"⚠️ *Issue Breakdown:*",
            f"• *Low Voltage:* {sec2.get('low_voltage', 0)}",
            f"• *High Voltage:* {sec2.get('high_voltage', 0)}",
            f"• *Power Failure:* {sec2.get('power_failure', 0)}",
            f"• *MCB Trip:* {sec2.get('mcb_trip', 0)}",
            f"• *Panel Door Open:* {sec2.get('panel_door_open', 0)}",
        ]
        return "\n".join(lines)

    def send_report(
        self,
        report_data: Dict[str, Any],
        webhook_url: Optional[str] = None,
        use_card: bool = True,
    ) -> bool:
        """Send the panel report to Google Spaces."""
        target_url = webhook_url or self.webhook_url
        if not target_url:
            logger.error("No Google Chat Webhook URL provided. Unable to send notification.")
            return False

        headers = {"Content-Type": "application/json; charset=UTF-8"}

        if use_card:
            payload = self.build_card_v2(report_data)
        else:
            payload = {"text": self.build_markdown_fallback(report_data)}

        try:
            resp = requests.post(target_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                logger.info("Successfully sent panel report to Google Spaces.")
                return True
            else:
                logger.warning(
                    f"Card v2 send failed ({resp.status_code}): {resp.text}. Retrying with plain text..."
                )
                fallback_payload = {"text": self.build_markdown_fallback(report_data)}
                fb_resp = requests.post(
                    target_url, json=fallback_payload, headers=headers, timeout=15
                )
                if fb_resp.status_code == 200:
                    logger.info("Successfully sent fallback text report to Google Spaces.")
                    return True
                else:
                    logger.error(
                        f"Fallback send also failed ({fb_resp.status_code}): {fb_resp.text}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Failed to post message to Google Spaces: {e}")
            return False
