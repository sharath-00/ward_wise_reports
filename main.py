import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from tabulate import tabulate

# Force UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tb_client import ThingsBoardClient
from analyzer import PanelAnalyzer
from google_spaces import GoogleSpacesNotifier

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BBMP_Ward_Report")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_console_report(report_data: Dict[str, Any]):
    """Display clean Section 1 and Section 2 summary tables in the terminal."""
    ward_name = report_data.get("zone_name", "BBMP Ward")
    sec1 = report_data.get("section1_overview", {})
    sec2 = report_data.get("section2_issues", {})
    generated_at = report_data.get("generated_at", "")

    print("\n" + "=" * 70)
    print(f"  BBMP PANEL HEALTH REPORT: {ward_name.upper()}")
    print(f"  Timestamp: {generated_at}")
    print("=" * 70)

    sec1_table = [
        ["Total Panels", sec1.get("total_panels", 0)],
        ["🟢 Online Panels", f"{sec1.get('online_panels', 0)} ({sec1.get('online_pct', 0)}%)"],
        ["🔴 Offline Panels", sec1.get("offline_panels", 0)],
        ["⚡ Offline PF Panels", sec1.get("offline_pf_panels", 0)],
    ]
    print("\n📍 SECTION 1: WARD OVERVIEW")
    print(tabulate(sec1_table, headers=["Metric", "Count"], tablefmt="fancy_grid"))

    sec2_table = [
        ["🟡 Low Voltage (< 180V)", sec2.get("low_voltage", 0)],
        ["🟠 High Voltage (> 265V)", sec2.get("high_voltage", 0)],
        ["⚡ Power Failure (0V)", sec2.get("power_failure", 0)],
        ["⚙️ MCB Trip", sec2.get("mcb_trip", 0)],
        ["🚪 Panel Door Open", sec2.get("panel_door_open", 0)],
    ]
    print("\n⚠️  SECTION 2: ISSUE BREAKDOWN")
    print(tabulate(sec2_table, headers=["Issue Type", "Count"], tablefmt="fancy_grid"))
    print("=" * 70 + "\n")


def execute_ward_reports(
    ward_target: str = "all",
    send_to_chat: bool = False,
    webhook_url_override: Optional[str] = None,
    config_path: str = "config.json",
) -> List[Dict[str, Any]]:
    """Fetch panel data, analyze health, print summary, and dispatch reports to Google Spaces."""
    config = load_config(config_path)
    thresholds = config.get("alert_thresholds", {})
    analyzer = PanelAnalyzer(thresholds=thresholds)

    logger.info("Connecting to ThingsBoard API...")
    tb_client = ThingsBoardClient()
    if not tb_client.login():
        logger.error("Failed to authenticate with ThingsBoard API.")
        return []

    # Fetch live data strictly for target wards (W167 / W118)
    ward_panels_map = tb_client.fetch_panels_for_wards(ward_target=ward_target)

    target_webhook = (
        webhook_url_override
        or os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
    )
    notifier = GoogleSpacesNotifier(webhook_url=target_webhook)

    ward_display_names = {
        "SNTR-W167": "Shanthi Nagar (Ward 167)",
        "SVJR-W118": "Shivaji Nagar (Ward 118)",
    }

    all_reports = []
    for w_code, panels in ward_panels_map.items():
        ward_title = ward_display_names.get(w_code, w_code)
        report_data = analyzer.generate_zone_report(zone_name=ward_title, panels=panels)
        print_console_report(report_data)
        all_reports.append(report_data)

        if send_to_chat:
            if not target_webhook:
                logger.warning(
                    "No GOOGLE_CHAT_WEBHOOK_URL configured in .env. Skipping send."
                )
            else:
                logger.info(f"Dispatching report for {ward_title} to Google Spaces...")
                success = notifier.send_report(report_data)
                if success:
                    logger.info(f"Report for {ward_title} successfully delivered to Google Spaces!")
                else:
                    logger.error(f"Failed to deliver report for {ward_title} to Google Spaces.")

    return all_reports


def run_scheduler(
    schedule_times: List[str],
    ward_target: str,
    send_to_chat: bool,
    config_path: str,
):
    """Run report continuously on schedule."""
    import schedule

    logger.info(f"Scheduling reports for Ward '{ward_target}' at daily times: {schedule_times}")

    for t in schedule_times:
        t_clean = t.strip()
        schedule.every().day.at(t_clean).do(
            execute_ward_reports,
            ward_target=ward_target,
            send_to_chat=send_to_chat,
            config_path=config_path,
        )

    # Run immediately once at startup
    execute_ward_reports(ward_target=ward_target, send_to_chat=send_to_chat, config_path=config_path)

    logger.info("Scheduler started. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch ThingsBoard panel data for Shanthi Nagar (W167) & Shivaji Nagar (W118) and send reports to Google Spaces."
    )
    parser.add_argument(
        "--ward",
        type=str,
        default="all",
        help="Target ward: '167' (Shanthi Nagar), '118' (Shivaji Nagar), or 'all' (both). Default: 'all'",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send formatted Card v2 report to Google Spaces webhook.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display report in console without sending to Google Spaces.",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="Override Google Chat Webhook URL.",
    )
    parser.add_argument(
        "--schedule",
        type=str,
        default=None,
        help="Comma-separated daily schedule times (24h format, e.g. '09:00,18:00').",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to config.json file.",
    )

    args = parser.parse_args()

    send_flag = args.send and not args.dry_run

    if args.schedule:
        times = args.schedule.split(",")
        run_scheduler(
            schedule_times=times,
            ward_target=args.ward,
            send_to_chat=send_flag,
            config_path=args.config,
        )
    else:
        execute_ward_reports(
            ward_target=args.ward,
            send_to_chat=send_flag,
            webhook_url_override=args.webhook,
            config_path=args.config,
        )


if __name__ == "__main__":
    main()
