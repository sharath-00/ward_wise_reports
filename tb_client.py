import os
import sys
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("ThingsBoardClient")


class ThingsBoardClient:
    """
    ThingsBoard REST API Client dedicated to fetching panel telemetry
    and attributes for BBMP Shanthi Nagar (W167) and Shivaji Nagar (W118).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        raw_url = base_url or os.getenv("THINGSBOARD_BASE_URL", "https://schnelliot.in")
        self.base_url = str(raw_url).strip().rstrip("/") if raw_url else "https://schnelliot.in"
        raw_user = username or os.getenv("THINGSBOARD_USERNAME")
        self.username = str(raw_user).strip() if raw_user else None
        raw_pass = password or os.getenv("THINGSBOARD_PASSWORD")
        self.password = str(raw_pass).strip() if raw_pass else None
        self.token: Optional[str] = None
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def login(self) -> bool:
        """Authenticate with ThingsBoard using username and password."""
        if not self.username or not self.password:
            raise ValueError(
                "ThingsBoard username and password must be configured in .env."
            )

        url = f"{self.base_url}/api/auth/login"
        payload = {"username": self.username, "password": self.password}
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token")
                logger.info("Successfully authenticated with ThingsBoard API.")
                return True
            else:
                logger.error(f"Authentication failed ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Error connecting to ThingsBoard: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        if not self.token:
            if not self.login():
                raise ConnectionError("Failed to authenticate with ThingsBoard.")
        return {
            "X-Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _request(
        self, method: str, path: str, params: Optional[Dict] = None, json_data: Optional[Any] = None, retry: bool = True
    ) -> requests.Response:
        """Execute authenticated request with automatic retry on 401 token expiry."""
        url = f"{self.base_url}{path}"
        headers = self._get_headers()
        try:
            resp = self.session.request(
                method, url, headers=headers, params=params, json=json_data, timeout=25
            )
            if resp.status_code == 401 and retry:
                logger.warning("Token expired or unauthorized. Re-authenticating...")
                self.login()
                headers = self._get_headers()
                return self.session.request(
                    method, url, headers=headers, params=params, json=json_data, timeout=25
                )
            return resp
        except Exception as e:
            logger.error(f"HTTP request error for {url}: {e}")
            raise

    def get_device_attributes(self, device_id: str) -> Dict[str, Any]:
        """Fetch all server, client, and shared attributes for a device."""
        resp = self._request("GET", f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes")
        if resp.status_code == 200:
            attrs = {}
            for item in resp.json():
                attrs[item["key"]] = item["value"]
            return attrs
        return {}

    def get_latest_telemetry(self, device_id: str) -> Dict[str, Any]:
        """Fetch latest timeseries telemetry values for a device."""
        resp = self._request("GET", f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries")
        if resp.status_code == 200:
            ts = {}
            for k, v in resp.json().items():
                if v and len(v) > 0:
                    ts[k] = v[0].get("value")
            return ts
        return {}

    def fetch_panel_details(self, device_meta: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch live attributes and telemetry for a single panel."""
        dev_id = device_meta.get("id")
        dev_name = device_meta.get("name", "")
        dev_label = device_meta.get("label", "")
        ward_code = device_meta.get("ward", "")
        ward_name = device_meta.get("ward_name", "")
        zone = device_meta.get("zone", "")
        location = device_meta.get("location", "")

        attrs = self.get_device_attributes(dev_id)
        telemetry = self.get_latest_telemetry(dev_id)

        # Merge base location/zone if missing from attrs
        if not attrs.get("location") and location:
            attrs["location"] = location
        if not attrs.get("wardName") and ward_code:
            attrs["wardName"] = ward_code
        if not attrs.get("zoneName") and zone:
            attrs["zoneName"] = zone

        return {
            "id": dev_id,
            "name": dev_name,
            "label": dev_label,
            "ward_code": ward_code,
            "ward_name": ward_name,
            "zone": zone,
            "attributes": attrs,
            "telemetry": telemetry,
        }

    def load_ward_devices(self, inventory_file: str = "ward_devices.json") -> Dict[str, List[Dict[str, Any]]]:
        """Load the pre-indexed inventory for Ward 167 and Ward 118."""
        if not os.path.exists(inventory_file):
            logger.error(f"Ward inventory file not found: {inventory_file}")
            return {"SNTR-W167": [], "SVJR-W118": []}

        with open(inventory_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def fetch_panels_for_wards(
        self,
        ward_target: str = "all",
        inventory_file: str = "ward_devices.json",
        max_workers: int = 30,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch live data for panels in Shanthi Nagar (W167) and/or Shivaji Nagar (W118).
        `ward_target`: '167', '118', or 'all'
        """
        inventory = self.load_ward_devices(inventory_file)

        selected_wards = {}
        target_str = str(ward_target).strip().lower()

        if target_str in ("167", "w167", "sntr-w167", "shanthi", "shanthi nagar"):
            selected_wards["SNTR-W167"] = inventory.get("SNTR-W167", [])
        elif target_str in ("118", "w118", "svjr-w118", "shivaji", "shivaji nagar"):
            selected_wards["SVJR-W118"] = inventory.get("SVJR-W118", [])
        else:
            selected_wards = inventory

        results: Dict[str, List[Dict[str, Any]]] = {}

        for w_code, devices in selected_wards.items():
            logger.info(f"Fetching live telemetry for {len(devices)} panels in {w_code}...")
            panels_data = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_meta = {executor.submit(self.fetch_panel_details, d): d for d in devices}
                for future in as_completed(future_to_meta):
                    try:
                        pdata = future.result()
                        panels_data.append(pdata)
                    except Exception as e:
                        logger.error(f"Error fetching live data for panel: {e}")

            results[w_code] = panels_data

        return results
