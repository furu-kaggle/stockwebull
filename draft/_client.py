"""Shared Webull client setup for the draft scripts.

Reads APP_KEY / APP_SECRET from the environment. Region defaults to jp (WEBULL_REGION overrides).
The access token is cached in .webull_token/ at the repo root; run check_connection.py first
if it has not been approved in the Webull app yet.
"""
import logging
import os
import sys

from webull.core.client import ApiClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_DIR = os.path.join(REPO_ROOT, ".webull_token")


def make_client():
    client = ApiClient(os.environ["APP_KEY"], os.environ["APP_SECRET"], os.getenv("WEBULL_REGION", "jp"))
    # The SDK's ERROR logs dump request headers (app key, access token), so keep it at CRITICAL.
    client.set_stream_logger(log_level=logging.CRITICAL, stream=sys.stderr)
    client.set_token_dir(TOKEN_DIR)
    return client
