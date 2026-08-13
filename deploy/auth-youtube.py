#!/usr/bin/env python3
"""Tao token YouTube tren server headless qua SSH local port-forward 8089."""
import argparse
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from mkvtools.uploader import SCOPES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    creds = flow.run_local_server(
        host="localhost", bind_addr="0.0.0.0", port=8089, open_browser=False,
        authorization_prompt_message="Mo URL nay tren may dang SSH:\n{url}",
    )
    os.makedirs(os.path.dirname(args.token) or ".", exist_ok=True)
    with open(args.token, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    os.chmod(args.token, 0o600)
    print(f"Da luu token: {args.token}")


if __name__ == "__main__":
    main()
