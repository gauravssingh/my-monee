"""Visual & Functional UI Audit for Sprint 3 (Data, Storage & Backups)."""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path("/Users/gauravsingh/.gemini/antigravity-cli/brain/c50d7540-0f2c-465d-9ad7-dbd3a6a78129/screenshots/storage")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Generate auth token
sys.path.insert(0, "/Users/gauravsingh/projects/expense-tracker/src")
from mymonee.config import load_settings
from mymonee.db.session import get_session_factory
from mymonee.services.auth import _get_or_create_secret, create_session_token

load_settings()
SessionFactory = get_session_factory()
with SessionFactory() as db:
    secret = _get_or_create_secret(db)
    token = create_session_token(secret)
    db.commit()

def run_audit():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Desktop Audit
        context_desktop = browser.new_context(viewport={"width": 1280, "height": 950})
        page_desktop = context_desktop.new_page()

        page_desktop.goto("http://127.0.0.1:8477/settings?tab=data")
        page_desktop.evaluate(f"localStorage.setItem('mymonee_auth_token', '{token}');")
        page_desktop.goto("http://127.0.0.1:8477/settings?tab=data")
        page_desktop.wait_for_load_state("networkidle")
        time.sleep(1)

        desktop_img = SCREENSHOT_DIR / "desktop_data_storage_settings.png"
        page_desktop.screenshot(path=str(desktop_img), full_page=True)
        print(f"  ✓ Captured Desktop Data Storage Settings: {desktop_img}")

        # 2. Mobile Audit
        context_mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            is_mobile=True,
            has_touch=True,
        )
        page_mobile = context_mobile.new_page()
        page_mobile.goto("http://127.0.0.1:8477/settings?tab=data")
        page_mobile.evaluate(f"localStorage.setItem('mymonee_auth_token', '{token}');")
        page_mobile.goto("http://127.0.0.1:8477/settings?tab=data")
        page_mobile.wait_for_load_state("networkidle")
        time.sleep(1)

        mobile_img = SCREENSHOT_DIR / "mobile_data_storage_settings.png"
        page_mobile.screenshot(path=str(mobile_img), full_page=True)
        print(f"  ✓ Captured Mobile Data Storage Settings: {mobile_img}")

        browser.close()

if __name__ == "__main__":
    run_audit()
