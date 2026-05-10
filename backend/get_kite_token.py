"""Generate a fresh Kite Connect access token and save it to .env.

Run this ONCE per trading day (Kite tokens expire ~7:30 AM IST every morning):

    cd backend
    python get_kite_token.py

It prints the login URL, asks you to paste the request_token from the
redirect URL, then writes KITE_ACCESS_TOKEN= back into backend/.env.
Restart the backend after this finishes.
"""
from __future__ import annotations

import os
import re
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from kiteconnect import KiteConnect

ENV_PATH = Path(__file__).parent / ".env"


def main() -> int:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("KITE_API_KEY", "").strip()
    api_secret = os.getenv("KITE_API_SECRET", "").strip()

    if not api_key or not api_secret:
        print("ERROR: KITE_API_KEY and KITE_API_SECRET must be set in backend/.env first.")
        return 1

    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()

    print()
    print("=" * 70)
    print("STEP 1 — Open this URL in your browser and log into Zerodha:")
    print()
    print(f"  {login_url}")
    print()
    print("STEP 2 — After login, you'll be redirected to a URL containing")
    print("  ?request_token=XXXXXXXX&action=login&status=success")
    print()
    print("STEP 3 — Paste the FULL redirect URL (or just the request_token) below.")
    print("=" * 70)
    print()

    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    raw = input("Paste redirect URL or request_token: ").strip()
    if not raw:
        print("ERROR: nothing pasted.")
        return 1

    m = re.search(r"request_token=([^&\s]+)", raw)
    request_token = m.group(1) if m else raw

    print(f"\nUsing request_token: {request_token[:8]}...{request_token[-4:]}")

    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
    except Exception as e:
        print(f"ERROR: generate_session failed: {e}")
        print("Common causes: stale request_token (older than ~3 minutes),")
        print("              wrong API secret, or no active Kite Connect subscription.")
        return 2

    access_token = data["access_token"]
    print(f"\nOK — got access_token: {access_token[:8]}...{access_token[-4:]}")

    # Patch .env
    text = ENV_PATH.read_text(encoding="utf-8")
    if re.search(r"^KITE_ACCESS_TOKEN=.*$", text, flags=re.M):
        text = re.sub(
            r"^KITE_ACCESS_TOKEN=.*$",
            f"KITE_ACCESS_TOKEN={access_token}",
            text, flags=re.M,
        )
    else:
        text = text.rstrip() + f"\nKITE_ACCESS_TOKEN={access_token}\n"
    ENV_PATH.write_text(text, encoding="utf-8")

    print(f"\nWrote KITE_ACCESS_TOKEN to {ENV_PATH}")
    print("Now RESTART the backend (stop + start) for it to pick up the new token.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
