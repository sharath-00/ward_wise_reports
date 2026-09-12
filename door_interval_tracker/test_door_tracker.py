import os
import sys
import time
import unittest
import tempfile
import json
from unittest.mock import MagicMock, patch

curr_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(curr_dir)
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from door_analyzer import DoorAnalyzer
from door_state_manager import DoorStateManager
from door_notifier import DoorNotifier


class TestDoorIntervalTracker(unittest.TestCase):

    def setUp(self):
        self.analyzer = DoorAnalyzer()
        self.temp_state_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_state_file.close()
        self.state_mgr = DoorStateManager(state_file_path=self.temp_state_file.name)
        self.notifier = DoorNotifier(webhook_url="https://mock.webhook.local")

    def tearDown(self):
        if os.path.exists(self.temp_state_file.name):
            os.remove(self.temp_state_file.name)

    def test_door_analyzer_detection(self):
        # 1. Normal panel (No door open, TPR bit 26 is 0)
        normal_panel = {
            "id": {"id": "DEV-NORM-001"},
            "name": "SALSS001001",
            "label": "SSC107SM01001",
            "ward": "W100",
            "zone": "Shivaji Nagar",
            "attributes": {"state": "INSTALLED", "phase": 3, "location": "Main Road"},
            "telemetry": {
                "rv": 230.0, "yv": 232.0, "bv": 231.0,
                "ri": 10.5, "yi": 11.0, "bi": 10.8,
                "rly": 1,
                "fault": 0,
                "faultLong": 0,
            }
        }
        res_norm = self.analyzer.evaluate_panel(normal_panel)
        self.assertFalse(res_norm["is_door_open"])

        # 2. Door Open panel (Bit 26: 1 << 26 = 67108864)
        door_open_panel = {
            "id": {"id": "DEV-DOOR-001"},
            "name": "SALSS002002",
            "label": "SSC107SM02002",
            "ward": "W118",
            "zone": "Shivaji Nagar",
            "attributes": {
                "state": "INSTALLED",
                "phase": 3,
                "location": "Cunningham Road",
                "latitude": "12.98177",
                "longitude": "77.62859",
                "lastActivityTime": int(time.time() * 1000),
            },
            "telemetry": {
                "rv": 230.0, "yv": 232.0, "bv": 231.0,
                "ri": 0.0, "yi": 0.0, "bi": 0.0,
                "rly": 0,
                "fault": 1 << 26, # TPR bit
                "faultLong": 0,
            }
        }
        res_door = self.analyzer.evaluate_panel(door_open_panel)
        self.assertTrue(res_door["is_door_open"])
        self.assertIn("TPR", res_door["fault_str"])

        # 3. Uncommissioned panel (INSTALLABLE) should NOT trigger
        door_uncommissioned = dict(door_open_panel)
        door_uncommissioned["attributes"] = {"state": "INSTALLABLE"}
        res_uncomm = self.analyzer.evaluate_panel(door_uncommissioned)
        self.assertFalse(res_uncomm["is_door_open"])

    def test_state_manager_delta_tracking(self):
        # Step 1: Initial Baseline Run
        panels_run1 = {
            "Shivaji Nagar": [
                {"id": "DEV-01", "name": "PANEL-01", "zone": "Shivaji Nagar", "ward": "W118"},
            ],
            "Shanthi Nagar": [],
        }
        res1 = self.state_mgr.compute_interval_deltas(panels_run1, self.state_mgr.load_previous_state())
        delta1 = res1["delta_analysis"]
        snapshot1 = res1["new_state_snapshot"]

        self.assertTrue(delta1["is_initial_run"])
        self.assertEqual(delta1["total_newly_opened"], 1)
        self.assertEqual(delta1["total_recovered"], 0)
        self.assertEqual(delta1["total_ongoing"], 0)
        self.assertEqual(delta1["total_current_open"], 1)

        self.state_mgr.save_current_state(snapshot1)

        # Step 2: Next Run with 1 new door open and 1 ongoing
        panels_run2 = {
            "Shivaji Nagar": [
                {"id": "DEV-01", "name": "PANEL-01", "zone": "Shivaji Nagar", "ward": "W118"}, # Ongoing
            ],
            "Shanthi Nagar": [
                {"id": "DEV-02", "name": "PANEL-02", "zone": "Shanthi Nagar", "ward": "W167"}, # Newly opened
            ],
        }
        res2 = self.state_mgr.compute_interval_deltas(panels_run2, self.state_mgr.load_previous_state())
        delta2 = res2["delta_analysis"]
        snapshot2 = res2["new_state_snapshot"]

        self.assertFalse(delta2["is_initial_run"])
        self.assertEqual(delta2["total_newly_opened"], 1)
        self.assertEqual(delta2["total_ongoing"], 1)
        self.assertEqual(delta2["total_recovered"], 0)
        self.assertEqual(delta2["total_current_open"], 2)

        self.state_mgr.save_current_state(snapshot2)

        # Step 3: Next Run where PANEL-01 closed (recovered)
        panels_run3 = {
            "Shivaji Nagar": [], # DEV-01 closed!
            "Shanthi Nagar": [
                {"id": "DEV-02", "name": "PANEL-02", "zone": "Shanthi Nagar", "ward": "W167"}, # Ongoing
            ],
        }
        res3 = self.state_mgr.compute_interval_deltas(panels_run3, self.state_mgr.load_previous_state())
        delta3 = res3["delta_analysis"]

        self.assertEqual(delta3["total_newly_opened"], 0)
        self.assertEqual(delta3["total_recovered"], 1) # DEV-01 closed
        self.assertEqual(delta3["total_ongoing"], 1)
        self.assertEqual(delta3["total_current_open"], 1)
        self.assertEqual(delta3["zones"]["Shivaji Nagar"]["recovered"][0]["name"], "PANEL-01")

    def test_door_notifier_formatting(self):
        mock_delta = {
            "evaluated_at_ist": "10-Sep-2026 03:45 PM IST",
            "previous_run_ist": "10-Sep-2026 03:30 PM IST",
            "interval_mins": 15.0,
            "is_initial_run": False,
            "total_newly_opened": 1,
            "total_recovered": 1,
            "total_ongoing": 0,
            "total_current_open": 1,
            "zones": {
                "Shivaji Nagar": {
                    "current_count": 1,
                    "newly_opened": [
                        {
                            "id": "DEV-001",
                            "name": "SALSS004988",
                            "label": "SSC107SM04954",
                            "ward": "SVJR-W118",
                            "zone": "Shivaji Nagar",
                            "latitude": "12.98177",
                            "longitude": "77.62859",
                            "location": "26, Cunningham Rd, Vasanth Nagar",
                            "voltages": {"r": 234.1, "y": 233.0, "b": 232.5},
                            "fault_str": "TPR",
                            "comm_status": "Online",
                            "last_comm_at": "10/09/2026, 03:44:00 PM",
                        }
                    ],
                    "recovered": [
                        {
                            "id": "DEV-002",
                            "name": "SALSS002788",
                            "label": "SSC107SM02960",
                            "ward": "SVJR-W119",
                            "zone": "Shivaji Nagar",
                            "total_open_duration_mins": 45.0,
                        }
                    ],
                    "ongoing": [],
                },
            },
        }

        text = self.notifier.build_door_delta_report(mock_delta)
        self.assertIn("BBMP Central Zone — Panel Door Open Interval Tracker", text)
        self.assertIn("NEW Door Opens:* *1*", text)
        self.assertIn("Closed/Recovered:* *1*", text)
        self.assertIn("Panel ID:* `SSC107SM04954`", text)
        self.assertIn("Device Name:* `SALSS004988`", text)
        self.assertIn("Zone:* Shivaji Nagar", text)
        self.assertIn("Ward:* SVJR-W118", text)
        self.assertIn("https://www.google.com/maps?q=12.98177,77.62859|12.98177, 77.62859", text)
        self.assertIn("26, Cunningham Rd, Vasanth Nagar", text)
        # Recovered/closed detailed list must NOT be present (counts only)
        self.assertNotIn("SALSS002788", text)


if __name__ == "__main__":
    unittest.main()
