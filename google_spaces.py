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
        self.webhook_url = webhook_url or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")

    def _create_ward_sections(self, report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create Section 1 (Overview) and Section 2 (Issues) for a given ward report."""
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

        return [
            # Section 1: Overview
            {
                "header": f"📍 {ward_name} — Overview",
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
            # Section 2: Issues
            {
                "header": f"⚠️ {ward_name} — Issue Breakdown",
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
                            "topLabel": "SECURITY & TAMPER",
                            "text": f"<b>Panel Door Open:</b> {door_open}",
                        }
                    },
                ],
            },
        ]

    def build_combined_card_v2(self, all_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine all ward reports into a single unified Google Chat Card v2 request body."""
        all_sections = []
        generated_at = all_reports[0].get("generated_at", "") if all_reports else ""

        for report in all_reports:
            ward_sections = self._create_ward_sections(report)
            all_sections.extend(ward_sections)

        # Append common footer section
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
            "BBMP Panel Health Report"
            if len(all_reports) > 1
            else f"BBMP Panel Report: {all_reports[0].get('zone_name')}"
        )
        card_subtitle = (
            "Shanthi Nagar (Ward 167) & Shivaji Nagar (Ward 118)"
            if len(all_reports) > 1
            else "Schnell IoT CCMS & Smart Lighting Health Summary"
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
        """Construct fallback formatted markdown text for chat."""
        lines = ["*BBMP Panel Health Report*"]
        generated_at = all_reports[0].get("generated_at", "") if all_reports else ""
        lines.append(f"🕒 _Generated: {generated_at}_\n")

        for r in all_reports:
            w_name = r.get("zone_name", "Ward")
            sec1 = r.get("section1_overview", {})
            sec2 = r.get("section2_issues", {})

            lines.extend([
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📍 *{w_name}*",
                f"• *Total Panels:* {sec1.get('total_panels', 0)}",
                f"• *Online Panels:* {sec1.get('online_panels', 0)} ({sec1.get('online_pct', 0)}%)",
                f"• *Offline Panels:* {sec1.get('offline_panels', 0)}",
                f"• *Offline PF Panels:* {sec1.get('offline_pf_panels', 0)}",
                f"• *Low Voltage:* {sec2.get('low_voltage', 0)}",
                f"• *High Voltage:* {sec2.get('high_voltage', 0)}",
                f"• *Power Failure:* {sec2.get('power_failure', 0)}",
                f"• *MCB Trip:* {sec2.get('mcb_trip', 0)}",
                f"• *Panel Door Open:* {sec2.get('panel_door_open', 0)}\n",
            ])

        return "\n".join(lines)

    def send_combined_report(
        self,
        all_reports: List[Dict[str, Any]],
        webhook_url: Optional[str] = None,
        use_card: bool = True,
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

        try:
            resp = requests.post(target_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                logger.info("Successfully delivered unified combined report to Google Spaces.")
                return True
            else:
                logger.warning(
                    f"Card v2 send failed ({resp.status_code}): {resp.text}. Retrying with plain text..."
                )
                fallback_payload = {"text": self.build_markdown_fallback(all_reports)}
                fb_resp = requests.post(
                    target_url, json=fallback_payload, headers=headers, timeout=15
                )
                if fb_resp.status_code == 200:
                    logger.info("Successfully sent fallback text report to Google Spaces.")
                    return True
                else:
                    logger.error(f"Fallback send failed ({fb_resp.status_code}): {fb_resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to post combined message to Google Spaces: {e}")
            return False
