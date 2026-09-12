import os
import sys
import json
import time
import argparse
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from tabulate import tabulate

# Force UTF-8 encoding on Windows console
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure imports from parent directory
curr_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(curr_dir)
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from door_analyzer import DoorAnalyzer
from door_state_manager import DoorStateManager
from door_notifier import DoorNotifier
from north_zone_report.north_client import NorthZonesThingsBoardClient
from zones_report.zones_client import ZonesThingsBoardClient

load_dotenv()
load_dotenv(os.path.join(parent_dir, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Door_Interval_Tracker")

CENTRAL_ZONES = [
    "CV Raman Nagar",
    "Shanthi Nagar",
    "Shivaji Nagar",
]

NORTH_ZONES = [
    "Sarvagna Nagar",
    "Hebbal",
    "Pulakesi Nagar",
]


def print_console_summary(delta_results: Dict[str, Any], region_name: str = "Central Zone"):
    """Print formatted console tables showing interval delta changes for door open events."""
    eval_time = delta_results.get("evaluated_at_ist", "")
    prev_time = delta_results.get("previous_run_ist", "Initial Baseline")
    interval = delta_results.get("interval_mins")
    is_initial = delta_results.get("is_initial_run", False)

    print("\n" + "=" * 78)
    print(f"🚪  BBMP {region_name.upper()} — PANEL DOOR OPEN INTERVAL TRACKER")
    print(f"🕒 Current Scan: {eval_time}")
    if not is_initial and interval:
        print(f"⏱️  Interval: Last {interval} minutes (Since {prev_time})")
    else:
        print("📌 Baseline Snapshot Initialized")
    print("=" * 78)

    overview_table = [
        ["🚨 Total Newly Opened in this Interval", delta_results["total_newly_opened"]],
        ["🟢 Total Closed/Recovered in this Interval", delta_results["total_recovered"]],
        ["🟡 Total Ongoing Open Panels", delta_results["total_ongoing"]],
        ["🚪 Total Currently Open Panels", delta_results["total_current_open"]],
    ]
    print("\n📊 INTERVAL SUMMARY")
    print(tabulate(overview_table, headers=["Metric", "Count"], tablefmt="fancy_grid"))

    # Zone breakdown table
    zone_table = []
    for z_name, z_data in delta_results.get("zones", {}).items():
        zone_table.append([
            z_name,
            z_data["current_count"],
            len(z_data["newly_opened"]),
            len(z_data["recovered"]),
            len(z_data["ongoing"]),
        ])

    print("\n🏙️  ZONE-WISE BREAKDOWN")
    print(tabulate(
        zone_table,
        headers=["Zone Name", "Active Open Doors", "🚨 Newly Opened", "🟢 Closed", "🟡 Ongoing"],
        tablefmt="fancy_grid",
    ))

    # Detail of newly opened panels
    all_new = []
    for z_name, z_data in delta_results.get("zones", {}).items():
        for p in z_data.get("newly_opened", []):
            volts = p.get("voltages", {})
            v_str = f"R:{volts.get('r')}V Y:{volts.get('y')}V B:{volts.get('b')}V"
            lat = str(p.get("latitude") or "").strip()
            lng = str(p.get("longitude") or "").strip()
            map_url = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else "-"
            all_new.append([
                p.get("label") or p.get("uid") or "-",
                p.get("name") or p.get("gateway_uid") or "-",
                z_name,
                p.get("ward") or "-",
                map_url,
                v_str,
                (p.get("location") or "")[:30] + "..." if len(p.get("location") or "") > 30 else (p.get("location") or "-"),
            ])

    if all_new:
        print("\n🚨 DETAILED LIST OF NEWLY OPENED DOOR PANELS")
        print(tabulate(
            all_new,
            headers=["Panel ID", "Device Name", "Zone", "Ward", "Google Maps", "Voltages", "Location"],
            tablefmt="fancy_grid",
        ))
    else:
        print("\n✅ No new door open events detected during this interval.")

    print("=" * 78 + "\n")


def execute_door_tracker(
    region: str = "central",
    zone_target: str = "all",
    send_to_chat: bool = False,
    send_only_on_change: bool = False,
    webhook_url_override: Optional[str] = None,
    state_file: Optional[str] = None,
    reset_state: bool = False,
) -> Dict[str, Any]:
    """
    Execute real-time door open discovery and interval delta tracking for Central / North Zones.
    """
    reg_clean = region.strip().lower()

    if reg_clean == "north":
        region_title = "North Zone"
        base_zones = NORTH_ZONES
        default_state_file = os.path.join(curr_dir, "door_state_north.json")
    elif reg_clean in ("all", "both"):
        region_title = "Central & North Zones"
        base_zones = CENTRAL_ZONES + NORTH_ZONES
        default_state_file = os.path.join(curr_dir, "door_state_all.json")
    else:
        region_title = "Central Zone"
        base_zones = CENTRAL_ZONES
        default_state_file = os.path.join(curr_dir, "door_state_central.json")

    actual_state_file = state_file or default_state_file
    state_mgr = DoorStateManager(state_file_path=actual_state_file)

    if reset_state:
        logger.info("Resetting Door state baseline snapshot...")
        state_mgr.save_current_state({"last_run_timestamp": None, "last_run_ist": None, "zones": {}})

    previous_state = state_mgr.load_previous_state()
    analyzer = DoorAnalyzer()

    zone_alias_map = {
        "cv_raman_nagar": "CV Raman Nagar",
        "cv_raman": "CV Raman Nagar",
        "cvr": "CV Raman Nagar",
        "shanthi_nagar": "Shanthi Nagar",
        "shanthi": "Shanthi Nagar",
        "sntr": "Shanthi Nagar",
        "shivaji_nagar": "Shivaji Nagar",
        "shivaji": "Shivaji Nagar",
        "svjr": "Shivaji Nagar",
        "sarvagna_nagar": "Sarvagna Nagar",
        "sarvagna": "Sarvagna Nagar",
        "srvr": "Sarvagna Nagar",
        "hebbal": "Hebbal",
        "hbl": "Hebbal",
        "pulakesi_nagar": "Pulakesi Nagar",
        "pulakesi": "Pulakesi Nagar",
        "pulakeshi_nagar": "Pulakesi Nagar",
        "pulakeshi": "Pulakesi Nagar",
    }

    target_str = str(zone_target).strip().lower().replace(" ", "_")
    if target_str in ("all", "*", ""):
        selected_zones = base_zones
    elif target_str in zone_alias_map:
        selected_zones = [zone_alias_map[target_str]]
    else:
        selected_zones = [z for z in (CENTRAL_ZONES + NORTH_ZONES) if target_str in z.lower().replace(" ", "_")]
        if not selected_zones:
            selected_zones = base_zones

    logger.info("Connecting to ThingsBoard API for live real-time query...")
    tb_client = NorthZonesThingsBoardClient() if any(z in NORTH_ZONES for z in selected_zones) else ZonesThingsBoardClient()
    if not tb_client.login():
        logger.error("Failed to authenticate with ThingsBoard API.")
        return {}

    current_zone_door_opens: Dict[str, List[Dict[str, Any]]] = {}

    for z_name in selected_zones:
        logger.info(f"Querying live panels for {z_name} in real-time...")
        live_panels = tb_client.fetch_panels_for_zone_realtime(z_name)
        open_panels = analyzer.filter_door_open_panels(live_panels)
        current_zone_door_opens[z_name] = open_panels
        logger.info(f"[{z_name}] Found {len(open_panels)} door open panels out of {len(live_panels)} live panels.")

    # Compute delta vs previous run
    results = state_mgr.compute_interval_deltas(
        current_zone_door_open=current_zone_door_opens,
        previous_state=previous_state,
    )

    delta_results = results["delta_analysis"]
    delta_results["region_name"] = region_title
    new_snapshot = results["new_state_snapshot"]

    # Print summary
    print_console_summary(delta_results, region_name=region_title)

    # Save updated snapshot
    state_mgr.save_current_state(new_snapshot)

    # Determine whether to send chat notification
    has_changes = (delta_results["total_newly_opened"] > 0) or (delta_results["total_recovered"] > 0)
    should_send = send_to_chat

    if send_only_on_change and not has_changes:
        logger.info("No newly opened or closed door panels in this interval. Skipping notification (--send-only-on-change active).")
        should_send = False

    if should_send:
        logger.info(f"Dispatching Door interval alert for {region_title} to Google Chat...")
        notifier = DoorNotifier(webhook_url=webhook_url_override, region=reg_clean)
        success = notifier.send_door_report(delta_results)
        if success:
            logger.info("Alert successfully dispatched to Google Chat.")
        else:
            logger.error("Failed to dispatch alert to Google Chat.")

    return delta_results


def main():
    parser = argparse.ArgumentParser(
        description="BBMP Panel Door Open Interval Tracker (Supports Central and North Zones)"
    )
    parser.add_argument(
        "--region",
        choices=["central", "north", "all"],
        default="central",
        help="Target Region ('central' [CV Raman, Shanthi, Shivaji], 'north' [Sarvagna, Hebbal, Pulakesi], 'all')",
    )
    parser.add_argument(
        "--zone",
        default="all",
        help="Target Zone ('all', 'cv_raman_nagar', 'shanthi_nagar', 'shivaji_nagar', 'sarvagna_nagar', 'hebbal', 'pulakesi_nagar')",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send formatted Google Chat Alert to webhook",
    )
    parser.add_argument(
        "--send-only-on-change",
        action="store_true",
        help="Only dispatch Google Chat alert if new door opens or closures occurred in this interval",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="Override Google Chat Webhook URL",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=None,
        help="Path to custom door state JSON file",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Clear historical state and re-initialize baseline snapshot",
    )

    args = parser.parse_args()

    execute_door_tracker(
        region=args.region,
        zone_target=args.zone,
        send_to_chat=args.send,
        send_only_on_change=args.send_only_on_change,
        webhook_url_override=args.webhook,
        state_file=args.state_file,
        reset_state=args.reset_state,
    )


if __name__ == "__main__":
    main()
