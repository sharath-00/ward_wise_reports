import os
import sys
import unittest

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from north_analyzer import NorthZonesAnalyzer
from north_client import NorthZonesThingsBoardClient
from north_notifier import NorthZonesNotifier
from main_north_zone import load_config


class TestNorthZonesReport(unittest.TestCase):
    def setUp(self):
        self.config = load_config("north_config.json")
        self.analyzer = NorthZonesAnalyzer(thresholds=self.config.get("alert_thresholds"))
        self.notifier = NorthZonesNotifier()

    def test_analyzer_single_panel_health_evaluation(self):
        import time
        now_ts = int(time.time() * 1000)
        # 1. Normal Online panel
        mock_online_panel = {
            "id": "mock-north-1",
            "name": "NORTH-001",
            "label": "LBL-N1",
            "ward": "W20",
            "zone": "Sarvagna Nagar",
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
            "id": "mock-north-2",
            "name": "NORTH-002",
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
            "id": "mock-north-3",
            "name": "NORTH-003",
            "attributes": {"lastActivityTime": now_ts, "phase": 1, "state": "INSTALLED"},
            "telemetry": {"rv": 0.0, "ri": 0.0, "rly": 0, "pkt": 8}
        }
        res_pkt8 = self.analyzer.analyze_single_panel(p_pkt8)
        self.assertFalse(res_pkt8["is_online"])
        self.assertTrue(res_pkt8["is_offline_pf"])
        self.assertFalse(res_pkt8["is_offline"])
        self.assertFalse(res_pkt8["is_power_failure"])

    def test_text_report_bold_generation(self):
        mock_reports = [
            {
                "zone_name": "Sarvagna Nagar",
                "generated_at": "12-Sep-2026 10:00 AM IST",
                "section1_overview": {
                    "total_panels": 761,
                    "online_panels": 720,
                    "offline_panels": 21,
                    "offline_pf_panels": 20,
                    "online_pct": 94.6,
                    "relay_on": 700,
                    "relay_off": 20,
                },
                "section2_issues": {
                    "low_voltage": 1,
                    "high_voltage": 0,
                    "power_failure": 12,
                    "mcb_trip": 2,
                    "panel_door_open": 3,
                },
            },
            {
                "zone_name": "Hebbal",
                "generated_at": "12-Sep-2026 10:00 AM IST",
                "section1_overview": {
                    "total_panels": 453,
                    "online_panels": 440,
                    "offline_panels": 8,
                    "offline_pf_panels": 5,
                    "online_pct": 97.1,
                    "relay_on": 430,
                    "relay_off": 10,
                },
                "section2_issues": {
                    "low_voltage": 0,
                    "high_voltage": 1,
                    "power_failure": 2,
                    "mcb_trip": 1,
                    "panel_door_open": 0,
                },
            },
            {
                "zone_name": "Pulakesi Nagar",
                "generated_at": "12-Sep-2026 10:00 AM IST",
                "section1_overview": {
                    "total_panels": 445,
                    "online_panels": 435,
                    "offline_panels": 6,
                    "offline_pf_panels": 4,
                    "online_pct": 97.8,
                    "relay_on": 420,
                    "relay_off": 15,
                },
                "section2_issues": {
                    "low_voltage": 0,
                    "high_voltage": 0,
                    "power_failure": 1,
                    "mcb_trip": 0,
                    "panel_door_open": 1,
                },
            },
        ]

        text = self.notifier.build_text_report(mock_reports)
        self.assertIn("⚡ *BBMP North Zone — CCMS Health Report*", text)
        self.assertIn("📍 *Sarvagna Nagar* — 🟢 *94.6% Online*", text)
        self.assertIn("📍 *Hebbal* — 🟢 *97.1% Online*", text)
        self.assertIn("📍 *Pulakesi Nagar* — 🟢 *97.8% Online*", text)
        self.assertIn("• *Total Panels:* 761", text)
        self.assertIn("• *Offline PF Panels:* 20", text)
        self.assertIn("🟡 *Low Voltage:* 1", text)
        self.assertIn("⚡ *Power Failure:* 12", text)
        self.assertIn("⚙️ *MCB Trip:* 2", text)
        self.assertIn("🚪 *Panel Door Open:* 3", text)
        self.assertIn("⚡ *Schnell IoT Smart Lighting CCMS Monitoring*", text)


if __name__ == "__main__":
    unittest.main()
