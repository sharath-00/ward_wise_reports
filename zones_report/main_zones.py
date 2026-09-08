import os
import sys
import json
import time
import argparse
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from tabulate import tabulate

# Force UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure parent and local directory are importable
curr_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(curr_dir)
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from zones_analyzer import ZonesAnalyzer
from zones_client import ZonesThingsBoardClient
from zones_notifier import ZonesNotifier

load_dotenv()
load_dotenv(os.path.join(parent_dir, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BBMP_4Zones_Report")


def load_config(config_path: str = "zones_config.json") -> Dict[str, Any]:
    resolved = config_path
    if not os.path.isabs(resolved):
        c1 = os.path.join(curr_dir, config_path)
        c2 = os.path.join(os.getcwd(), config_path)
        if os.path.exists(c1):
            resolved = c1
        elif os.path.exists(c2):
            resolved = c2

    if not os.path.exists(resolved):
        logger.warning(f"Config file not found at {resolved}, using default thresholds.")
        return {}
    with open(resolved, "r", encoding="utf-8") as f:
        return json.load(f)


def print_console_summary(zone_report: Dict[str, Any]):
    """Print clean formatted tables in console matching Section 1 & Section 2."""
    z_name = zone_report["zone_name"]
    sec1 = zone_report["section1_overview"]
    sec2 = zone_report["section2_issues"]

    print("\n" + "=" * 70)
    print(f"🏙️  ZONE: {z_name.upper()} | Operational: {sec1['online_pct']}%")
    print(f"🕒 Generated: {zone_report['generated_at']}")
    print("=" * 70)

    sec1_table = [
        ["Total Panels", sec1["total_panels"]],
        ["🟢 Online Panels", f"{sec1['online_panels']} ({sec1['online_pct']}%)"],
        ["🔴 Offline Panels", sec1["offline_panels"]],
        ["🔌 Offline (Power Failure)", sec1["offline_pf_panels"]],
        ["⚡ Relay Status", f"🟢 {sec1.get('relay_on', 0)} ON / 🔴 {sec1.get('relay_off', 0)} OFF"],
    ]
    print("\n📊 SECTION 1: OVERVIEW")
    print(tabulate(sec1_table, headers=["Metric", "Value"], tablefmt="fancy_grid"))

    sec2_table = [
        ["🟡 Low Voltage", sec2.get("low_voltage", 0)],
        ["🟠 High Voltage", sec2.get("high_voltage", 0)],
        ["⚡ Power Failure", sec2.get("power_failure", 0)],
        ["⚙️ MCB Trip", sec2.get("mcb_trip", 0)],
        ["🚪 Panel Door Open", sec2.get("panel_door_open", 0)],
    ]
    print("\n⚠️  SECTION 2: ISSUE BREAKDOWN")
    print(tabulate(sec2_table, headers=["Issue Type", "Count"], tablefmt="fancy_grid"))
    print("=" * 70 + "\n")


def execute_zones_report(
    zone_target: str = "all",
    send_to_chat: bool = False,
    webhook_url_override: Optional[str] = None,
    config_path: str = "zones_config.json",
    inventory_path: str = "zones_inventory.json",
) -> List[Dict[str, Any]]:
    """Fetch live panel telemetry for the 4 zones, compute metrics, print, and optionally send to Google Chat."""
    config = load_config(config_path)
    thresholds = config.get("alert_thresholds", {})
    analyzer = ZonesAnalyzer(thresholds=thresholds)

    logger.info("Connecting to ThingsBoard API...")
    tb_client = ZonesThingsBoardClient()
    if not tb_client.login():
        logger.error("Failed to authenticate with ThingsBoard API.")
        return []

    logger.info(f"Fetching live panel telemetry for zone target: '{zone_target}'...")
    zones_panels = tb_client.fetch_panels_for_zones(
        zone_target=zone_target, inventory_file=inventory_path
    )

    zone_reports = []
    for z_name, panels in zones_panels.items():
        report = analyzer.generate_zone_report(zone_display_name=z_name, panels=panels)
        zone_reports.append(report)
        print_console_summary(report)

    if send_to_chat and zone_reports:
        logger.info("Dispatching reports to Google Spaces...")
        notifier = ZonesNotifier(webhook_url=webhook_url_override)
        success = notifier.send_report(zone_reports)
        if success:
            logger.info("Report dispatched to Google Chat successfully.")
        else:
            logger.error("Failed to dispatch report to Google Chat.")

    return zone_reports


def main():
    parser = argparse.ArgumentParser(
        description="BBMP Central Zone 4-Zone Telemetry Report (CV Raman Nagar, Sarvagna Nagar, Shanthi Nagar, Shivaji Nagar)"
    )
    parser.add_argument(
        "--zone",
        choices=[
            "all",
            "cv_raman_nagar",
            "sarvagna_nagar",
            "shanthi_nagar",
            "shivaji_nagar",
        ],
        default="all",
        help="Target Zone ('all', 'cv_raman_nagar', 'sarvagna_nagar', 'shanthi_nagar', 'shivaji_nagar')",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send formatted Google Chat Card v2 to webhook",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="Override Google Chat Space Webhook URL",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="zones_config.json",
        help="Path to zones configuration JSON",
    )
    parser.add_argument(
        "--inventory",
        type=str,
        default="zones_inventory.json",
        help="Path to 4 zones inventory JSON",
    )

    args = parser.parse_args()

    execute_zones_report(
        zone_target=args.zone,
        send_to_chat=args.send,
        webhook_url_override=args.webhook,
        config_path=args.config,
        inventory_path=args.inventory,
    )


if __name__ == "__main__":
    main()
