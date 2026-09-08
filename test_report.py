import unittest
from analyzer import PanelAnalyzer
from google_spaces import GoogleSpacesNotifier
from tb_client import ThingsBoardClient
from main import load_config


class TestWardReport(unittest.TestCase):
    def setUp(self):
        self.config = load_config("config.json")
        self.analyzer = PanelAnalyzer(thresholds=self.config.get("alert_thresholds"))
        self.notifier = GoogleSpacesNotifier()

    def test_tb_client_inventory_load(self):
        client = ThingsBoardClient()
        inventory = client.load_ward_devices("ward_devices.json")
        self.assertIn("SNTR-W167", inventory)
        self.assertIn("SVJR-W118", inventory)
        self.assertEqual(len(inventory["SNTR-W167"]), 152)
        self.assertEqual(len(inventory["SVJR-W118"]), 57)

    def test_tb_client_login(self):
        client = ThingsBoardClient()
        logged_in = client.login()
        self.assertTrue(logged_in, "ThingsBoard login should succeed with credentials")


if __name__ == "__main__":
    unittest.main()
