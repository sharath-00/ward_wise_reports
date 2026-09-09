import os
import sys
import json
import time
import unittest

curr_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(curr_dir)
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from mcb_analyzer import MCBAnalyzer
from mcb_state_manager import MCBStateManager
from mcb_notifier import MCBNotifier


class TestMCBIntervalTracker(unittest.TestCase):
    def setUp(self):
        self.analyzer = MCBAnalyzer()
        self.notifier = MCBNotifier()
        self.test_state_file = os.path.join(curr_dir, "test_state_temp.json")
        self.state_mgr = MCBStateManager(state_file_path=self.test_state_file)

    def tearDown(self):
        if os.path.exists(self.test_state_file):
            try:
                os.remove(self.test_state_file)
            except Exception:
                pass

    def test_mcb_trip_detection(self):
        now_ts = int(time.time() * 1000)

        # 1. Normal Panel (Relay ON, Voltage 230V, Current 5.2A) -> NOT tripped
        normal_panel = {
            "id": "dev-normal",
            "name": "PANEL-NORMAL",
            "label": "LBL-001",
            "attributes": {"state": "INSTALLED", "lastActivityTime": now_ts, "phase": 1},
            "telemetry": {"rv": 230.0, "ri": 5.2, "rly": 1},
        }
        res_normal = self.analyzer.evaluate_panel(normal_panel)
        self.assertFalse(res_normal["is_mcb_tripped"])

        # 2. MCB Tripped Panel (Relay ON, Voltage 230V, Current 0A) -> TRIPPED
        tripped_panel = {
            "id": "dev-tripped-1",
            "name": "PANEL-TRIPPED",
            "label": "LBL-002",
            "ward": "W167",
            "zone": "Shanthi Nagar",
            "location": "12, Main Road, Bangalore",
            "attributes": {"state": "INSTALLED", "lastActivityTime": now_ts, "phase": 1},
            "telemetry": {"rv": 235.0, "ri": 0.0, "rly": 1},
        }
        res_tripped = self.analyzer.evaluate_panel(tripped_panel)
        self.assertTrue(res_tripped["is_mcb_tripped"])

        # 3. Relay OFF Panel (Relay OFF, Voltage 230V, Current 0A) -> NOT tripped
        relay_off_panel = {
            "id": "dev-off",
            "name": "PANEL-OFF",
            "attributes": {"state": "INSTALLED", "lastActivityTime": now_ts, "phase": 1},
            "telemetry": {"rv": 230.0, "ri": 0.0, "rly": 0},
        }
        res_off = self.analyzer.evaluate_panel(relay_off_panel)
        self.assertFalse(res_off["is_mcb_tripped"])

        # 4. Power Failure Panel (Relay ON, Voltage 0V, Current 0A) -> NOT MCB trip (Grid Power Failure)
        pf_panel = {
            "id": "dev-pf",
            "name": "PANEL-PF",
            "attributes": {"state": "INSTALLED", "lastActivityTime": now_ts, "phase": 1},
            "telemetry": {"rv": 0.0, "ri": 0.0, "rly": 1},
        }
        res_pf = self.analyzer.evaluate_panel(pf_panel)
        self.assertFalse(res_pf["is_mcb_tripped"])

    def test_interval_delta_computation(self):
        # Initial Run (Baseline)
        empty_prev = {"last_run_timestamp": None, "zones": {}}
        mock_trips_t1 = {
            "Shanthi Nagar": [
                {
                    "id": "dev-1",
                    "name": "PANEL-01",
                    "label": "LBL-01",
                    "ward": "SNTR-W167",
                    "zone": "Shanthi Nagar",
                    "location": "Brigade Road",
                    "voltages": {"r": 230.0, "y": 0, "b": 0},
                }
            ],
            "Shivaji Nagar": [],
        }

        delta1 = self.state_mgr.compute_interval_deltas(mock_trips_t1, empty_prev)
        res1 = delta1["delta_analysis"]
        self.assertTrue(res1["is_initial_run"])
        self.assertEqual(res1["total_newly_tripped"], 1)
        self.assertEqual(res1["total_recovered"], 0)
        self.assertEqual(res1["total_ongoing"], 0)

        # Save snapshot
        self.state_mgr.save_current_state(delta1["new_state_snapshot"])

        # Second Run (T2):
        # - PANEL-01 is still tripped (ongoing)
        # - PANEL-02 is NEWLY tripped in Shivaji Nagar
        loaded_prev = self.state_mgr.load_previous_state()
        mock_trips_t2 = {
            "Shanthi Nagar": [
                {
                    "id": "dev-1",
                    "name": "PANEL-01",
                    "label": "LBL-01",
                    "ward": "SNTR-W167",
                    "zone": "Shanthi Nagar",
                    "location": "Brigade Road",
                    "voltages": {"r": 230.0, "y": 0, "b": 0},
                }
            ],
            "Shivaji Nagar": [
                {
                    "id": "dev-2",
                    "name": "PANEL-02",
                    "label": "LBL-02",
                    "ward": "SVJR-W118",
                    "zone": "Shivaji Nagar",
                    "location": "Cunningham Road",
                    "voltages": {"r": 235.0, "y": 0, "b": 0},
                }
            ],
        }

        delta2 = self.state_mgr.compute_interval_deltas(mock_trips_t2, loaded_prev)
        res2 = delta2["delta_analysis"]
        self.assertFalse(res2["is_initial_run"])
        self.assertEqual(res2["total_newly_tripped"], 1)  # PANEL-02
        self.assertEqual(res2["total_ongoing"], 1)        # PANEL-01
        self.assertEqual(res2["total_recovered"], 0)
        self.assertEqual(res2["zones"]["Shivaji Nagar"]["newly_tripped"][0]["name"], "PANEL-02")

        # Save snapshot
        self.state_mgr.save_current_state(delta2["new_state_snapshot"])

        # Third Run (T3):
        # - PANEL-01 RECOVERED (Current restored)
        # - PANEL-02 still ongoing
        loaded_prev_t2 = self.state_mgr.load_previous_state()
        mock_trips_t3 = {
            "Shanthi Nagar": [],  # PANEL-01 recovered!
            "Shivaji Nagar": [
                {
                    "id": "dev-2",
                    "name": "PANEL-02",
                    "label": "LBL-02",
                    "ward": "SVJR-W118",
                    "zone": "Shivaji Nagar",
                    "location": "Cunningham Road",
                    "voltages": {"r": 235.0, "y": 0, "b": 0},
                }
            ],
        }

        delta3 = self.state_mgr.compute_interval_deltas(mock_trips_t3, loaded_prev_t2)
        res3 = delta3["delta_analysis"]
        self.assertEqual(res3["total_recovered"], 1)      # PANEL-01 recovered
        self.assertEqual(res3["total_ongoing"], 1)        # PANEL-02 ongoing
        self.assertEqual(res3["total_newly_tripped"], 0)  # No new trips
        self.assertEqual(res3["zones"]["Shanthi Nagar"]["recovered"][0]["name"], "PANEL-01")

    def test_notifier_report_generation(self):
        mock_delta = {
            "evaluated_at_ist": "09-Sep-2026 08:00 PM IST",
            "previous_run_ist": "09-Sep-2026 07:00 PM IST",
            "interval_mins": 60.0,
            "is_initial_run": False,
            "total_newly_tripped": 1,
            "total_recovered": 1,
            "total_ongoing": 0,
            "total_current_tripped": 1,
            "zones": {
                "Shivaji Nagar": {
                    "current_count": 1,
                    "newly_tripped": [
                        {
                            "name": "SALSS004988",
                            "label": "SSC107SM04954",
                            "ward": "SVJR-W118",
                            "zone": "Shivaji Nagar",
                            "latitude": "12.98177",
                            "longitude": "77.62859",
                            "location": "26, Cunningham Rd, Vasanth Nagar",
                            "voltages": {"r": 234.1, "y": 0.0, "b": 0.0},
                        }
                    ],
                    "recovered": [],
                    "ongoing": [],
                },
                "Shanthi Nagar": {
                    "current_count": 0,
                    "newly_tripped": [],
                    "recovered": [
                        {
                            "name": "SALSS002788",
                            "label": "SSC107SM02960",
                            "ward": "SNTR-W167",
                            "zone": "Shanthi Nagar",
                            "latitude": "12.97224",
                            "longitude": "77.64694",
                            "location": "122, 1st Main Rd",
                            "total_trip_duration_mins": 60.0,
                        }
                    ],
                    "ongoing": [],
                },
            },
        }

        text = self.notifier.build_mcb_delta_report(mock_delta)
        self.assertIn("BBMP Central Zone — MCB Trip Interval Tracker", text)
        self.assertIn("NEW MCB Trips:* *1*", text)
        self.assertIn("Recovered:* *1*", text)
        # Verify Panel ID and Device Name
        self.assertIn("Panel ID:* `SSC107SM04954`", text)
        self.assertIn("Device Name:* `SALSS004988`", text)
        # Verify Zone and Ward
        self.assertIn("Zone:* Shivaji Nagar", text)
        self.assertIn("Ward:* SVJR-W118", text)
        # Verify Google Maps hyperlink with coordinates
        self.assertIn("https://www.google.com/maps?q=12.98177,77.62859|12.98177, 77.62859", text)
        self.assertIn("26, Cunningham Rd, Vasanth Nagar", text)
        self.assertIn("SALSS002788", text)
        self.assertIn("Restored to normal operation", text)


if __name__ == "__main__":
    unittest.main()
