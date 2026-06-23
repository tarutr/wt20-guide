"""
export_feedback.py
Pulls feedback from Supabase submitted within the last N hours and, if there is
any, emails a JSON digest to the configured address. Sends nothing when empty.

Usage:
    python export_feedback.py --hours 24   --label daily
    python export_feedback.py --hours 168  --label weekly

Env vars required (from GitHub Secrets):
    SUPABASE_URL
    SUPABASE_SERVICE_KEY   (service_role — can read the feedback table)
    GMAIL_ADDRESS
    GMAIL_APP_PASSWORD
"""

import os
import sys
import json
import argparse
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import requests


def fetch_feedback(supabase_url: str, service_key: str, since_iso: str):
    """Fetch feedback rows created at or after since_iso, newest first."""
    url = f"{supabase_url}/rest/v1/feedback"
    params = {
        "select": "*",
        "created_at": f"gte.{since_iso}",
        "order": "created_at.desc",
    }
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if not resp.ok:
        # Surface the actual PostgREST error so failures are diagnosable in the logs.
        print(f"Supabase returned {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


def send_email(gmail_addr, app_password, subject, body_text, json_bytes, json_filename):
    msg = MIMEMultipart()
    msg["From"] = gmail_addr
    msg["To"] = gmail_addr
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    attachment = MIMEApplication(json_bytes, _subtype="json")
    attachment.add_header("Content-Disposition", "attachment", filename=json_filename)
    msg.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_addr, app_password)
        server.send_message(msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, required=True, help="Look-back window in hours")
    parser.add_argument("--label", type=str, required=True, help="daily or weekly (used in subject/filename)")
    args = parser.parse_args()

    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_KEY"]
    gmail_addr = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    # Clean, PostgREST-friendly UTC timestamp: 'YYYY-MM-DDTHH:MM:SSZ' (no microseconds, no +00:00 offset).
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = fetch_feedback(supabase_url, service_key, since_iso)

    if not rows:
        print(f"No feedback in the last {args.hours}h ({args.label}) — sending nothing.")
        return

    count = len(rows)
    json_text = json.dumps(rows, indent=2, ensure_ascii=False)
    json_bytes = json_text.encode("utf-8")
    date_str = now.strftime("%Y-%m-%d")
    json_filename = f"feedback_{args.label}_{date_str}.json"

    subject = f"WT20 Dashboard — {args.label} feedback digest ({count} new) — {date_str}"
    body = (
        f"{count} new feedback submission(s) in the last {args.hours} hours.\n\n"
        f"The full JSON is attached as {json_filename}.\n"
        f"You can upload it directly to an AI bot for analysis."
    )

    send_email(gmail_addr, app_password, subject, body, json_bytes, json_filename)
    print(f"Sent {args.label} digest with {count} item(s).")


if __name__ == "__main__":
    main()
