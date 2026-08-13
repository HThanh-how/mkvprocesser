#!/usr/bin/env python3
"""Bang giao queue metadata active/passive, co ACK sau khi node dich da luu.

Vi du:
  handoff.py --source http://127.0.0.1:8800 --dest http://mac:8800 \
    --token-file /etc/mkvtools-handoff.token

Script khong copy media. Neu bat ky buoc nao loi, source khong xoa job va lan timer
sau se thu lai an toan nho ID on dinh/idempotent import.
"""
import argparse
import json
import pathlib
import urllib.request
from datetime import datetime


def call(url, token, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-MKV-Handoff-Token": token, "Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310 - URL do admin dat
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--start-hour", type=int)
    parser.add_argument("--stop-hour", type=int)
    args = parser.parse_args()
    if args.start_hour is not None and args.stop_hour is not None:
        hour = datetime.now().hour
        if args.start_hour < args.stop_hour:
            allowed = args.start_hour <= hour < args.stop_hour
        else:
            allowed = hour >= args.start_hour or hour < args.stop_hour
        if not allowed:
            print("handoff: ngoai khung gio")
            return
    token = pathlib.Path(args.token_file).read_text(encoding="utf-8").strip()
    if len(token) < 24:
        raise SystemExit("handoff token qua ngan")

    bundle = call(args.source.rstrip("/") + "/api/handoff/export", token)
    jobs = bundle.get("jobs") or []
    if not jobs:
        print("handoff: queue trong")
        return
    result = call(args.dest.rstrip("/") + "/api/handoff/import", token, bundle)
    accepted = result.get("accepted") or []
    if len(accepted) != len(jobs):
        raise SystemExit(f"handoff: dest chi xac nhan {len(accepted)}/{len(jobs)} job")
    ack = call(args.source.rstrip("/") + "/api/handoff/ack", token, {"ids": accepted})
    print(f"handoff: {len(accepted)} job, source removed {ack.get('removed', 0)}")


if __name__ == "__main__":
    main()
