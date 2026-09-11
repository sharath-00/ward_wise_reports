import os
import sys
import unittest

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from zones_analyzer import ZonesAnalyzer
from zones_client import ZonesThingsBoardClient
from zones_notifier import ZonesNotifier
from main_zones import load_config


class TestZonesReport(unittest.TestCase):
    def setUp(self):
        self.config = load_config("zones_config.json")
        self.analyzer = ZonesAnalyzer(thresholds=self.config.get("alert_thresholds"))
        self.notifier = ZonesNotifier()

    def test_analyzer_single_panel_health_evaluation(self):
        import time
        now_ts = int(time.time() * 1000)
        # 1. Normal Online panel
        mock_online_panel = {
            "id": "mock-dev-1",
            "name": "PANEL-001",
            "label": "LBL-001",
            "ward": "W167",
            "zone": "Shanthi Nagar",
            "attributes": {
                "lastActivityTime": now_ts,
                "phase": 1,
                "state": "INSTALLED",
            },
            "telemetry": {
                "rv": 230.0,
                "ri": 10.5,
                "rly": 1,
                "fault": 0,
            },
        }
        res = self.analyzer.analyze_single_panel(mock_online_panel)
        self.assertEqual(res["is_online"], True)
        self.assertEqual(res["is_power_failure"], False)
        self.assertEqual(res["is_mcb_tripped"], False)
        self.assertEqual(res["is_door_open"], False)

        # 2. Door Open panel (bit 26)
        mock_door_open_panel = {
            "id": "mock-dev-2",
            "name": "PANEL-002",
            "attributes": {
                "lastActivityTime": now_ts,
                "phase": 1,
                "state": "INSTALLED",
            },
            "telemetry": {
                "rv": 230.0,
                "ri": 5.0,
                "rly": 1,
                "fault": 1 << 26,
            },
        }
        res_door = self.analyzer.analyze_single_panel(mock_door_open_panel)
        self.assertTrue(res_door["is_door_open"])

        # 3. Offline PF via pkt == 8
        p_pkt8 = {
            "id": "mock-dev-3",
            "name": "PANEL-003",
            "attributes": {"lastActivityTime": now_ts, "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 0.0, "ri": 0.0, "rly": 0, "pkt": 8}
        }
        res_pkt8 = self.analyzer.analyze_single_panel(p_pkt8)
        self.assertFalse(res_pkt8["is_online"])
        self.assertTrue(res_pkt8["is_offline_pf"])
        self.assertFalse(res_pkt8["is_offline"])
        self.assertFalse(res_pkt8["is_power_failure"])

        # 4. Offline stale panel (5 hours ago) with 0V: Offline PF = True, Live Power Failure = False
        p_stale = {
            "id": "mock-dev-4",
            "name": "PANEL-004",
            "attributes": {"lastActivityTime": now_ts - (5 * 3600 * 1000), "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 0.0, "ri": 0.0, "rly": 0, "pkt": 0}
        }
        res_stale = self.analyzer.analyze_single_panel(p_stale)
        self.assertFalse(res_stale["is_online"])
        self.assertTrue(res_stale["is_offline_pf"])
        self.assertFalse(res_stale["is_offline"])
        self.assertFalse(res_stale["is_power_failure"])

    def test_text_report_bold_generation(self):
        mock_reports = [
            {
                "zone_name": "Shanthi Nagar",
                "generated_at": "08-Sep-2026 05:00 PM IST",
                "section1_overview": {
                    "total_panels": 152,
                    "online_panels": 145,
                    "offline_panels": 7,
                    "offline_pf_panels": 5,
                    "online_pct": 95.4,
                },
                "section2_issues": {
                    "low_voltage": 0,
                    "high_voltage": 0,
                    "power_failure": 6,
                    "mcb_trip": 1,
                    "panel_door_open": 2,
                },
            },
            {
                "zone_name": "Shivaji Nagar",
                "generated_at": "08-Sep-2026 05:00 PM IST",
                "section1_overview": {
                    "total_panels": 57,
                    "online_panels": 55,
                    "offline_panels": 2,
                    "offline_pf_panels": 0,
                    "online_pct": 96.5,
                },
                "section2_issues": {
                    "low_voltage": 0,
                    "high_voltage": 0,
                    "power_failure": 0,
                    "mcb_trip": 0,
                    "panel_door_open": 1,
                },
            },
        ]

        text = self.notifier.build_text_report(mock_reports)
        self.assertIn("⚡ *BBMP Central Zone — CCMS Health Report*", text)
        self.assertIn("📍 *Shanthi Nagar* — 🟢 *95.4% Online*", text)
        self.assertIn("📍 *Shivaji Nagar* — 🟢 *96.5% Online*", text)
        self.assertIn("• *Total Panels:* 152", text)
        self.assertIn("• *Offline PF Panels:* 5", text)
        self.assertIn("🟡 *Low Voltage:* 0", text)
        self.assertIn("⚡ *Power Failure:* 6", text)
        self.assertIn("⚙️ *MCB Trip:* 1", text)
        self.assertIn("🚪 *Panel Door Open:* 2", text)
        self.assertIn("⚡ *Schnell IoT Smart Lighting CCMS Monitoring*", text)


if __name__ == "__main__":
    unittest.main()
