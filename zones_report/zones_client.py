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
logger = logging.getLogger("ZonesThingsBoardClient")


class ZonesThingsBoardClient:
    """
    ThingsBoard REST API Client dedicated to fetching live panel telemetry
    and attributes for the 4 BBMP zones:
    - CV Raman Nagar
    - Sarvagna Nagar
    - Shanthi Nagar
    - Shivaji Nagar
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
        for attempt in range(1, 6):
            try:
                resp = self.session.post(url, json=payload, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    self.token = data.get("token")
                    logger.info("Successfully authenticated with ThingsBoard API.")
                    return True
                else:
                    logger.warning(f"Auth attempt {attempt} failed ({resp.status_code}): {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"Auth attempt {attempt} error: {e}")
            time.sleep(2.0 * attempt)

        logger.error("Failed to authenticate with ThingsBoard after 5 attempts.")
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
        ward = device_meta.get("ward", "")
        zone = device_meta.get("zone", "")
        location = device_meta.get("location", "")

        attrs = self.get_device_attributes(dev_id)
        telemetry = self.get_latest_telemetry(dev_id)

        # Merge base metadata if missing from live attributes
        if not attrs.get("location") and location:
            attrs["location"] = location
        if not attrs.get("wardName") and ward:
            attrs["wardName"] = ward
        if not attrs.get("zoneName") and zone:
            attrs["zoneName"] = zone

        return {
            "id": dev_id,
            "name": dev_name,
            "label": dev_label,
            "ward": ward,
            "zone": zone,
            "attributes": attrs,
            "telemetry": telemetry,
        }

    def fetch_panels_for_zone_realtime(self, zone_display_name: str) -> List[Dict[str, Any]]:
        """
        Dynamically query ThingsBoard in real time for all panels in a zone
        without relying on static inventory files.
        """
        # Normalize zone key for query (e.g. CVRamanNagar, SarvagnaNagar, ShanthiNagar, ShivajiNagar)
        norm_key = zone_display_name.replace(" ", "")

        query_payload = {
            "entityFilter": {"type": "entityType", "entityType": "DEVICE"},
            "pageLink": {"pageSize": 1000, "page": 0, "dynamic": True},
            "entityFields": [
                {"type": "ENTITY_FIELD", "key": "name"},
                {"type": "ENTITY_FIELD", "key": "label"}
            ],
            "latestValues": [
                {"type": "SERVER_ATTRIBUTE", "key": "wardName"},
                {"type": "SERVER_ATTRIBUTE", "key": "zoneName"},
                {"type": "SERVER_ATTRIBUTE", "key": "state"},
                {"type": "SERVER_ATTRIBUTE", "key": "location"},
                {"type": "SERVER_ATTRIBUTE", "key": "latitude"},
                {"type": "SERVER_ATTRIBUTE", "key": "longitude"},
                {"type": "SERVER_ATTRIBUTE", "key": "slatitude"},
                {"type": "SERVER_ATTRIBUTE", "key": "slongitude"},
                {"type": "CLIENT_ATTRIBUTE", "key": "latitude"},
                {"type": "CLIENT_ATTRIBUTE", "key": "longitude"},
                {"type": "SHARED_ATTRIBUTE", "key": "latitude"},
                {"type": "SHARED_ATTRIBUTE", "key": "longitude"},
                {"type": "SERVER_ATTRIBUTE", "key": "phase"},
                {"type": "SERVER_ATTRIBUTE", "key": "active"},
                {"type": "SERVER_ATTRIBUTE", "key": "pkt"},
                {"type": "SERVER_ATTRIBUTE", "key": "lastActivityTime"},
                {"type": "TIME_SERIES", "key": "pkt"},
                {"type": "TIME_SERIES", "key": "systime"},
                {"type": "TIME_SERIES", "key": "rv"},
                {"type": "TIME_SERIES", "key": "yv"},
                {"type": "TIME_SERIES", "key": "bv"},
                {"type": "TIME_SERIES", "key": "ri"},
                {"type": "TIME_SERIES", "key": "yi"},
                {"type": "TIME_SERIES", "key": "bi"},
                {"type": "TIME_SERIES", "key": "rly"},
                {"type": "TIME_SERIES", "key": "fault"},
                {"type": "TIME_SERIES", "key": "faultLong"}
            ],
            "keyFilters": [
                {
                    "key": {"type": "SERVER_ATTRIBUTE", "key": "zoneName"},
                    "valueType": "STRING",
                    "predicate": {
                        "type": "STRING",
                        "operation": "EQUAL",
                        "value": {"defaultValue": norm_key},
                        "ignoreCase": True
                    }
                }
            ]
        }

        try:
            resp = self._request("POST", "/api/entitiesQuery/find", json_data=query_payload)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", [])
                panels = []
                for item in items:
                    entity_id = item.get("entityId", {}).get("id")
                    latest = item.get("latest", {})
                    fields = latest.get("ENTITY_FIELD", {})
                    server_attrs = latest.get("SERVER_ATTRIBUTE", {})
                    client_attrs = latest.get("CLIENT_ATTRIBUTE", {})
                    shared_attrs = latest.get("SHARED_ATTRIBUTE", {})
                    timeseries = latest.get("TIME_SERIES", {})

                    dev_name = fields.get("name", {}).get("value", "")
                    dev_label = fields.get("label", {}).get("value", "")

                    attrs = {}
                    for attr_group in (shared_attrs, server_attrs, client_attrs):
                        for k, v in attr_group.items():
                            if v and v.get("value") not in (None, ""):
                                attrs[k] = v.get("value")

                    if "lastActivityTime" in attrs:
                        try:
                            attrs["lastActivityTime"] = int(attrs["lastActivityTime"])
                        except (ValueError, TypeError):
                            pass

                    telemetry = {k: v.get("value") for k, v in timeseries.items() if v}

                    panels.append({
                        "id": entity_id,
                        "name": dev_name,
                        "label": dev_label,
                        "ward": attrs.get("wardName", ""),
                        "ward_name": attrs.get("wardName", ""),
                        "zone": zone_display_name,
                        "attributes": attrs,
                        "telemetry": telemetry,
                    })
                logger.info(f"Live real-time query discovered {len(panels)} panels for {zone_display_name}.")
                return panels
        except Exception as e:
            logger.error(f"Error querying live panels for zone {zone_display_name}: {e}")

        return []

    def load_zones_inventory(
        self, inventory_file: str = "zones_inventory.json"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Load fallback inventory if offline."""
        resolved_path = inventory_file
        if not os.path.isabs(resolved_path):
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            cand1 = os.path.join(curr_dir, inventory_file)
            cand2 = os.path.join(os.getcwd(), inventory_file)
            if os.path.exists(cand1):
                resolved_path = cand1
            elif os.path.exists(cand2):
                resolved_path = cand2

        if not os.path.exists(resolved_path):
            return {
                "CV Raman Nagar": [],
                "Sarvagna Nagar": [],
                "Shanthi Nagar": [],
                "Shivaji Nagar": [],
            }

        with open(resolved_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def fetch_panels_for_zones(
        self,
        zone_target: str = "all",
        inventory_file: str = "zones_inventory.json",
        max_workers: int = 35,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch live data for panels in specified zone(s) or 'all'.
        Queries ThingsBoard dynamically in real time to capture newly added devices automatically.
        """
        all_zones = [
            "CV Raman Nagar",
            "Sarvagna Nagar",
            "Shanthi Nagar",
            "Shivaji Nagar",
        ]

        target_str = str(zone_target).strip().lower().replace(" ", "_").replace(".", "")

        zone_alias_map = {
            "cv_raman_nagar": "CV Raman Nagar",
            "cv_raman": "CV Raman Nagar",
            "cvr": "CV Raman Nagar",
            "c_v_raman_nagar": "CV Raman Nagar",
            "sarvagna_nagar": "Sarvagna Nagar",
            "sarvagna": "Sarvagna Nagar",
            "srvr": "Sarvagna Nagar",
            "sarvagnanagar": "Sarvagna Nagar",
            "shanthi_nagar": "Shanthi Nagar",
            "shanthi": "Shanthi Nagar",
            "sntr": "Shanthi Nagar",
            "shanthinagar": "Shanthi Nagar",
            "167": "Shanthi Nagar",
            "shivaji_nagar": "Shivaji Nagar",
            "shivaji": "Shivaji Nagar",
            "svjr": "Shivaji Nagar",
            "shivajinagar": "Shivaji Nagar",
            "118": "Shivaji Nagar",
        }

        if target_str in ("all", "*", ""):
            selected_zone_names = all_zones
        elif target_str in zone_alias_map:
            selected_zone_names = [zone_alias_map[target_str]]
        else:
            selected_zone_names = [
                z for z in all_zones if target_str in z.lower().replace(" ", "_")
            ]
            if not selected_zone_names:
                selected_zone_names = all_zones

        results: Dict[str, List[Dict[str, Any]]] = {}

        for z_name in selected_zone_names:
            logger.info(f"Fetching real-time live panels for {z_name} from ThingsBoard API...")
            live_panels = self.fetch_panels_for_zone_realtime(z_name)

            if live_panels:
                results[z_name] = live_panels
            else:
                # Fallback to local inventory if dynamic query was empty/failed
                logger.warning(f"Falling back to {inventory_file} for {z_name}...")
                inventory = self.load_zones_inventory(inventory_file)
                devices = inventory.get(z_name, [])
                panels_data = []
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_meta = {executor.submit(self.fetch_panel_details, d): d for d in devices}
                    for future in as_completed(future_to_meta):
                        try:
                            pdata = future.result()
                            panels_data.append(pdata)
                        except Exception as e:
                            logger.error(f"Error fetching live data for panel: {e}")
                results[z_name] = panels_data

        return results
