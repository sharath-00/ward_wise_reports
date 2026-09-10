import os
import sys
import unittest
import tempfile
import time
from unittest.mock import MagicMock, patch

curr_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(curr_dir)
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from voltage_analyzer import VoltageAnalyzer
from voltage_state_manager import VoltageStateManager
from voltage_notifier import VoltageNotifier


class TestVoltageIntervalTracker(unittest.TestCase):

    def setUp(self):
        self.analyzer = VoltageAnalyzer()
        self.temp_state_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_state_file.close()
        self.state_mgr = VoltageStateManager(state_file_path=self.temp_state_file.name)
        self.notifier = VoltageNotifier(webhook_url="https://mock.webhook.local")

    def tearDown(self):
        if os.path.exists(self.temp_state_file.name):
            os.remove(self.temp_state_file.name)

    def test_voltage_analyzer_detection(self):
        now_ts = int(time.time() * 1000)

        # 1. Normal Panel (fault = 0)
        norm_panel = {
            "id": {"id": "DEV-NORM-01"},
            "name": "SALSS001",
            "label": "SSC001",
            "ward": "W100",
            "zone": "Shivaji Nagar",
            "attributes": {"state": "INSTALLED", "phase": 1, "lastActivityTime": now_ts},
            "telemetry": {"rv": 230.0, "yv": 0.0, "bv": 0.0, "ri": 10.0, "yi": 0.0, "bi": 0.0, "fault": 0},
        }
        res_norm = self.analyzer.evaluate_panel(norm_panel)
        self.assertFalse(res_norm["is_voltage_anomaly"])
        self.assertFalse(res_norm["is_low_voltage"])
        self.assertFalse(res_norm["is_high_voltage"])

        # 2. Low Voltage Panel (RVL - bit 0: 1 << 0 = 1)
        low_panel = {
            "id": {"id": "DEV-LOW-01"},
            "name": "SALSS002",
            "label": "SSC002",
            "ward": "W100",
            "zone": "Sarvagna Nagar",
            "attributes": {"state": "INSTALLED", "phase": 1, "lastActivityTime": now_ts},
            "telemetry": {"rv": 120.5, "yv": 0.0, "bv": 0.0, "ri": 0.0, "yi": 0.0, "bi": 0.0, "fault": 1 << 0},
        }
        res_low = self.analyzer.evaluate_panel(low_panel)
        self.assertTrue(res_low["is_voltage_anomaly"])
        self.assertTrue(res_low["is_low_voltage"])
        self.assertFalse(res_low["is_high_voltage"])
        self.assertEqual(res_low["anomaly_type"], "LOW_VOLTAGE")

        # 3. High Voltage Panel (RVH - bit 1: 1 << 1 = 2)
        high_panel = {
            "id": {"id": "DEV-HIGH-01"},
            "name": "SALSS003",
            "label": "SSC003",
            "ward": "W110",
            "zone": "CV Raman Nagar",
            "attributes": {"state": "INSTALLED", "phase": 1, "lastActivityTime": now_ts},
            "telemetry": {"rv": 290.0, "yv": 0.0, "bv": 0.0, "ri": 0.0, "yi": 0.0, "bi": 0.0, "fault": 1 << 1},
        }
        res_high = self.analyzer.evaluate_panel(high_panel)
        self.assertTrue(res_high["is_voltage_anomaly"])
        self.assertFalse(res_high["is_low_voltage"])
        self.assertTrue(res_high["is_high_voltage"])
        self.assertEqual(res_high["anomaly_type"], "HIGH_VOLTAGE")

        # 4. Power Failure (<30V) is NOT classified as Low Voltage
        pf_panel = {
            "id": {"id": "DEV-PF-01"},
            "name": "SALSS004",
            "label": "SSC004",
            "ward": "W100",
            "zone": "Shivaji Nagar",
            "attributes": {"state": "INSTALLED", "phase": 1, "lastActivityTime": now_ts},
            "telemetry": {"rv": 0.0, "yv": 0.0, "bv": 0.0, "ri": 0.0, "yi": 0.0, "bi": 0.0},
        }
        res_pf = self.analyzer.evaluate_panel(pf_panel)
        self.assertFalse(res_pf["is_voltage_anomaly"])
        self.assertTrue(res_pf["is_power_failure"])

    def test_state_manager_deltas(self):
        # Initial baseline
        panels_run1 = {
            "Sarvagna Nagar": [
                {"id": "DEV-01", "name": "PANEL-01", "is_low_voltage": True, "is_high_voltage": False, "anomaly_type": "LOW_VOLTAGE"},
            ]
        }
        res1 = self.state_mgr.compute_interval_deltas(panels_run1, self.state_mgr.load_previous_state())
        d1 = res1["delta_analysis"]
        s1 = res1["new_state_snapshot"]

        self.assertEqual(d1["total_newly_flagged"], 1)
        self.assertEqual(d1["total_new_low"], 1)
        self.assertEqual(d1["total_recovered"], 0)
        self.state_mgr.save_current_state(s1)

        # Next run: Panel 1 normalizes (recovers)
        panels_run2 = {
            "Sarvagna Nagar": []
        }
        res2 = self.state_mgr.compute_interval_deltas(panels_run2, self.state_mgr.load_previous_state())
        d2 = res2["delta_analysis"]

        self.assertEqual(d2["total_newly_flagged"], 0)
        self.assertEqual(d2["total_recovered"], 1)
        self.assertEqual(d2["zones"]["Sarvagna Nagar"]["recovered"][0]["name"], "PANEL-01")

    def test_notifier_formatting(self):
        mock_delta = {
            "evaluated_at_ist": "10-Sep-2026 05:00 PM IST",
            "previous_run_ist": "10-Sep-2026 04:45 PM IST",
            "interval_mins": 15.0,
            "is_initial_run": False,
            "total_newly_flagged": 1,
            "total_new_low": 1,
            "total_new_high": 0,
            "total_recovered": 1,
            "total_ongoing": 0,
            "total_current_low": 1,
            "total_current_high": 0,
            "total_current_anomalies": 1,
            "zones": {
                "Sarvagna Nagar": {
                    "current_count": 1,
                    "current_low_count": 1,
                    "current_high_count": 0,
                    "newly_flagged": [
                        {
                            "id": "DEV-01",
                            "name": "SALSS005825",
                            "label": "SSC107SM05740",
                            "zone": "Sarvagna Nagar",
                            "ward": "SN-W78",
                            "location": "Kadugondanahalli",
                            "latitude": "13.020",
                            "longitude": "77.620",
                            "is_low_voltage": True,
                            "is_high_voltage": False,
                            "voltages": {"r": 121.2, "y": 0.0, "b": 0.0},
                            "comm_status": "Online",
                            "last_comm_at": "10/09/2026, 04:59:00 PM",
                        }
                    ],
                    "recovered": [
                        {
                            "id": "DEV-02",
                            "name": "SALSS009999",
                            "label": "SSC107SM09999",
                        }
                    ],
                    "ongoing": [],
                }
            }
        }

        text = self.notifier.build_voltage_delta_report(mock_delta)
        self.assertIn("Voltage Anomaly (Low/High) Interval Tracker", text)
        self.assertIn("NEW Voltage Alerts:* *1*", text)
        self.assertIn("Normalized:* *1*", text)
        self.assertIn("LOW VOLTAGE", text)
        self.assertNotIn("(<180V)", text)
        self.assertNotIn("(>265V)", text)
        self.assertIn("SSC107SM05740", text)
        self.assertIn("SALSS005825", text)
        # Recovered detailed list should NOT be in text (counts only)
        self.assertNotIn("SALSS009999", text)


if __name__ == "__main__":
    unittest.main()
