#!/usr/bin/env python
"""
Charge légère HTTP — smoke de montée en charge.

Usage :
  python scripts/load_smoke.py --base http://localhost/api/v1 --users 20 --requests 100

Authentifie avec group_admin puis martèle /health/ et /reporting/dashboard/.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def post_json(url: str, payload: dict, headers: dict | None = None) -> tuple[int, dict | list | str, float]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = body
            return resp.status, parsed, (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace"), (time.perf_counter() - t0) * 1000


def get(url: str, headers: dict | None = None) -> tuple[int, float]:
    req = urllib.request.Request(url, headers=headers or {})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
            return resp.status, (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as exc:
        return exc.code, (time.perf_counter() - t0) * 1000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost/api/v1")
    parser.add_argument("--username", default="group_admin")
    parser.add_argument("--password", default="FinFlow2026!")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--requests", type=int, default=50)
    args = parser.parse_args()

    status, body, _ = post_json(
        f"{args.base.rstrip('/')}/auth/token/",
        {"username": args.username, "password": args.password},
    )
    if status != 200 or not isinstance(body, dict) or "access" not in body:
        raise SystemExit(f"Login failed: {status} {body}")

    headers = {"Authorization": f"Bearer {body['access']}"}
    targets = [
        f"{args.base.rstrip('/')}/health/",
        f"{args.base.rstrip('/')}/reporting/dashboard/",
    ]

    latencies: list[float] = []
    errors = 0

    def one(i: int):
        url = targets[i % len(targets)]
        code, ms = get(url, headers=headers if "health" not in url else None)
        return code, ms

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futs = [pool.submit(one, i) for i in range(args.requests)]
        for fut in as_completed(futs):
            code, ms = fut.result()
            latencies.append(ms)
            if code >= 400:
                errors += 1

    latencies.sort()
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0
    print(
        json.dumps(
            {
                "requests": len(latencies),
                "errors": errors,
                "avg_ms": round(statistics.mean(latencies), 1) if latencies else 0,
                "p95_ms": round(p95, 1),
                "max_ms": round(max(latencies), 1) if latencies else 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
