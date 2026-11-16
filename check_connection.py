"""Webull OpenAPI connection check.

Reads APP_ID / APP_KEY / APP_SECRET from the environment and verifies, step by step:
  1. the three variables are present
  2. a signed request reaches the regional API host
  3. an access token is issued (needs one-time approval in the Webull app when 2FA is on)
  4. the account list can be read

Secrets are never printed. Usage:  python check_connection.py [--wait SECONDS]
Region defaults to jp; override with WEBULL_REGION (us, hk, jp, ...).
"""
import argparse
import logging
import os
import sys

from webull.core.client import ApiClient
from webull.core.exception.exceptions import ClientException, ServerException
from webull.core.http.initializer.config.config_operation import ConfigOperation
from webull.core.http.initializer.token.token_manager import TokenManager
from webull.trade.trade_client import TradeClient

TOKEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".webull_token")


def mask(value):
    return f"{value[:2]}…{value[-2:]} ({len(value)} chars)" if len(value) > 8 else f"({len(value)} chars)"


def step(n, title):
    print(f"\n[{n}/4] {title}")


def describe(err):
    if isinstance(err, ServerException):
        return f"HTTP {err.get_http_status()} {err.get_error_code()}: {err.get_error_msg()}"
    return f"{type(err).__name__}: {err}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=int, default=300, help="seconds to wait for app approval of the token")
    args = parser.parse_args()
    region = os.getenv("WEBULL_REGION", "jp")

    step(1, "Environment variables")
    env = {name: os.getenv(name, "").strip() for name in ("APP_ID", "APP_KEY", "APP_SECRET")}
    for name, value in env.items():
        shown = f"({len(value)} chars)" if name == "APP_SECRET" else mask(value)
        print(f"  {name}: {'OK ' + shown if value else 'MISSING'}")
    if not env["APP_KEY"] or not env["APP_SECRET"]:
        print("  -> APP_KEY and APP_SECRET are required.")
        return 1

    client = ApiClient(env["APP_KEY"], env["APP_SECRET"], region,
                       token_check_duration_seconds=max(args.wait, 1))
    client.set_stream_logger(log_level=logging.WARNING, stream=sys.stderr)
    client.set_token_dir(TOKEN_DIR)

    step(2, f"Signed request to region '{region}'")
    try:
        config = ConfigOperation(client).get_config().json()
    except (ClientException, ServerException) as err:
        print(f"  FAILED  {describe(err)}")
        return 1
    token_required = bool(config.get("token_check_enabled"))
    print(f"  OK  (token / 2FA required: {token_required})")

    step(3, "Access token")
    if token_required:
        print(f"  Requesting token. If prompted, approve it in the Webull app (waiting up to {args.wait}s)...")
        try:
            TokenManager(TOKEN_DIR).init_token(client)
        except (ClientException, ServerException) as err:
            print(f"  FAILED  {describe(err)}")
            print("  -> If the token is still PENDING, approve it in the Webull app and run this again.")
            return 1
        print("  OK  token is NORMAL (saved under .webull_token/)")
    else:
        print("  SKIPPED  not required for this app")

    step(4, "Account list")
    try:
        # Token is already set on the client; TradeClient re-validates it against the saved file.
        accounts = TradeClient(client).account_v2.get_account_list().json()
    except (ClientException, ServerException) as err:
        print(f"  FAILED  {describe(err)}")
        return 1
    for acct in accounts or []:
        acct_id = str(acct.get("account_id", ""))
        print(f"  account …{acct_id[-4:]}  type={acct.get('account_type')}  class={acct.get('account_class')}"
              f"  label={acct.get('account_label')}")
    print(f"  OK  {len(accounts or [])} account(s)")
    print("\nConnection check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
