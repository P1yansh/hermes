#!/usr/bin/env python3
"""
CLI Multi-Account Google OAuth Authenticator for Hermes.
Iterates through config/accounts.json and authenticates each email inbox individually.
"""
import sys
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.connectors.google_live import GMAIL_SCOPES, CLASSROOM_SCOPES

def main():
    print("=" * 65)
    print("  HERMES // Multi-Account Google OAuth Authentication Wizard")
    print("=" * 65)

    creds_path = Path(settings.GOOGLE_CREDENTIALS_PATH)
    if not creds_path.is_absolute():
        creds_path = PROJECT_ROOT / creds_path

    if not creds_path.exists():
        print(f"\n[ERROR] Missing Google Cloud OAuth Client Secret file:")
        print(f"        {creds_path}")
        print("\nPlease download your desktop credentials JSON from Google Cloud Console")
        print(f"and save it to: {creds_path}\n")
        sys.exit(1)

    accounts_file = Path(settings.ACCOUNTS_CONFIG_PATH)
    if not accounts_file.is_absolute():
        accounts_file = PROJECT_ROOT / accounts_file

    if not accounts_file.exists():
        print(f"\n[ERROR] Missing accounts configuration manifest: {accounts_file}")
        sys.exit(1)

    with open(accounts_file, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    target_acc = sys.argv[1] if len(sys.argv) > 1 else None
    if target_acc:
        accounts = [a for a in accounts if a.get("id") == target_acc]
        if not accounts:
            print(f"[ERROR] No account with id '{target_acc}' found in {accounts_file.name}")
            sys.exit(1)

    print(f"\nLoaded {len(accounts)} configured account(s) to process:")
    for idx, acc in enumerate(accounts, 1):
        services = []
        if acc.get("enable_gmail"):
            services.append("Gmail")
        if acc.get("enable_classroom"):
            services.append("Google Classroom")
        print(f"  [{idx}] {acc.get('label')} ({acc.get('id')}) -> {', '.join(services)}")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("\n[ERROR] Missing google_auth_oauthlib. Run: uv sync")
        sys.exit(1)

    print("\nStarting authentication loop. Log in to the appropriate Google account for each step.\n")

    for idx, acc in enumerate(accounts, 1):
        acc_id = acc.get("id")
        label = acc.get("label", acc_id)
        token_rel = acc.get("token_file", f"tokens/token_{acc_id}.json")
        token_path = PROJECT_ROOT / token_rel
        token_path.parent.mkdir(parents=True, exist_ok=True)

        scopes = list(GMAIL_SCOPES)
        if acc.get("enable_classroom"):
            scopes.extend(CLASSROOM_SCOPES)

        print("-" * 65)
        print(f"Step {idx}/{len(accounts)}: Authenticating '{label}'")
        print(f"Target token: {token_rel}")
        print(f"Scopes: {len(scopes)} permission(s)")

        if token_path.exists():
            resp = input(f"Token file already exists for '{acc_id}'. Re-authenticate? [y/N]: ").strip().lower()
            if resp != "y":
                print(f"Skipping '{acc_id}' (using existing token).\n")
                continue

        input(f"Press [ENTER] to launch browser for '{label}'...")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w", encoding="utf-8") as tf:
                tf.write(creds.to_json())
            print(f"[SUCCESS] Token saved successfully -> {token_rel}\n")
        except Exception as e:
            print(f"[FAILED] Could not authenticate '{acc_id}': {e}\n")

    print("=" * 65)
    print("  All accounts processed. You can now run Hermes with DATA_SOURCE=live")
    print("=" * 65)

if __name__ == "__main__":
    main()
