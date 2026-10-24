"""Smoke test for Ops API - starts uvicorn, tests key endpoints, then terminates.

Run with: python -X utf8 dev/smoke.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx


def main():
    """Run smoke tests."""
    # Load .env for SERVICE_KEY and SEED_PASSWORD
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        print("FAIL: .env file not found")
        return 1
    
    env_vars = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            env_vars[key.strip()] = val.strip()
    
    service_key = env_vars.get("SERVICE_KEY")
    seed_password = env_vars.get("SEED_PASSWORD")
    
    if not service_key:
        print("FAIL: SERVICE_KEY not found in .env")
        return 1
    if not seed_password:
        print("FAIL: SEED_PASSWORD not found in .env")
        return 1
    
    # Start uvicorn
    ops_api_dir = Path(__file__).parent.parent
    python_exe = sys.executable
    cmd = [
        python_exe, "-X", "utf8", "-m", "uvicorn",
        "resolvix_ops.app:app",
        "--port", "8100",
        "--loop", "asyncio",
        "--workers", "1"
    ]
    
    print(f"Starting uvicorn: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=ops_api_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )
    
    base_url = "http://localhost:8100"
    client = httpx.Client(timeout=10.0, follow_redirects=False)
    
    try:
        # Poll /healthz until 200 (max 15s)
        print("Polling /healthz...")
        start = time.time()
        healthz_ok = False
        while time.time() - start < 15:
            try:
                resp = client.get(f"{base_url}/healthz")
                if resp.status_code == 200:
                    healthz_ok = True
                    print("PASS: GET /healthz returned 200")
                    break
            except httpx.ConnectError:
                pass
            time.sleep(0.5)
        
        if not healthz_ok:
            print("FAIL: GET /healthz did not return 200 within 15s")
            return 1
        
        # GET /v1/departments with X-Service-Key
        print("Testing GET /v1/departments...")
        resp = client.get(f"{base_url}/v1/departments", headers={"X-Service-Key": service_key})
        if resp.status_code == 200:
            data = resp.json()
            if "departments" in data:
                print(f"PASS: GET /v1/departments returned 200 with {len(data['departments'])} departments")
            else:
                print("FAIL: GET /v1/departments returned 200 but no 'departments' key")
                return 1
        else:
            print(f"FAIL: GET /v1/departments returned {resp.status_code}")
            return 1
        
        # POST /v1/auth/login as admin@demo
        print("Testing POST /v1/auth/login...")
        resp = client.post(
            f"{base_url}/v1/auth/login",
            json={"email": "admin@demo", "password": seed_password}
        )
        if resp.status_code == 200:
            # Check for session cookie
            cookies = resp.cookies
            if "resolvix_session" in cookies:
                print("PASS: POST /v1/auth/login returned 200 with session cookie")
                session_cookie = cookies["resolvix_session"]
            else:
                print("FAIL: POST /v1/auth/login returned 200 but no session cookie")
                return 1
        else:
            print(f"FAIL: POST /v1/auth/login returned {resp.status_code}")
            return 1
        
        # GET /v1/auth/me with session cookie
        print("Testing GET /v1/auth/me...")
        resp = client.get(
            f"{base_url}/v1/auth/me",
            cookies={"resolvix_session": session_cookie}
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("email") == "admin@demo" and data.get("role") == "admin":
                print("PASS: GET /v1/auth/me returned 200 with correct user")
            else:
                print(f"FAIL: GET /v1/auth/me returned unexpected data: {data}")
                return 1
        else:
            print(f"FAIL: GET /v1/auth/me returned {resp.status_code}")
            return 1
        
        print("\nAll smoke tests passed!")
        return 0
    
    finally:
        # Terminate uvicorn
        print("\nTerminating uvicorn...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Killing uvicorn (timeout)...")
            proc.kill()
            proc.wait()
        client.close()


if __name__ == "__main__":
    sys.exit(main())
