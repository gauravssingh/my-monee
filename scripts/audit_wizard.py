#!/usr/bin/env python3
"""Automated visual and interaction UI audit for the MyMonee Onboarding Wizard."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from playwright.async_api import async_playwright
from expense_tracker.config import load_settings
from expense_tracker.db.session import get_session_factory
from expense_tracker.services.auth import _get_or_create_secret, create_session_token


def get_auth_token() -> str:
    load_settings()
    SessionFactory = get_session_factory()
    with SessionFactory() as db:
        secret = _get_or_create_secret(db)
        token = create_session_token(secret)
        db.commit()
    return token


async def audit_wizard():
    outdir = Path("/Users/gauravsingh/.gemini/antigravity-cli/brain/c50d7540-0f2c-465d-9ad7-dbd3a6a78129/screenshots/wizard")
    outdir.mkdir(parents=True, exist_ok=True)

    token = get_auth_token()
    console_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for mode, is_mobile in [("desktop", False), ("mobile", True)]:
            print(f"\n==========================================")
            print(f"Auditing Onboarding Wizard ({mode.upper()})")
            print(f"==========================================")

            if is_mobile:
                ctx = await browser.new_context(
                    viewport={"width": 390, "height": 844},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                    has_touch=True,
                )
            else:
                ctx = await browser.new_context(
                    viewport={"width": 1200, "height": 850},
                )

            await ctx.add_init_script(f"""
                localStorage.setItem('mymonee_auth_token', '{token}');
            """)

            page = await ctx.new_page()
            page.on("console", lambda msg: console_errors.append(f"[{mode}] {msg.text}") if msg.type == "error" else None)

            # 1. Step 1: Welcome
            await page.goto("http://127.0.0.1:8477/onboarding", wait_until="networkidle")
            await page.wait_for_selector("h2", timeout=8000)
            await page.wait_for_timeout(500)
            p1 = outdir / f"{mode}_wizard_step1_welcome.png"
            await page.screenshot(path=str(p1), full_page=True)
            print(f"  ✓ Captured Step 1 Welcome: {p1}")

            # 2. Step 2: Accounts
            btn_next1 = page.locator("button:has-text('Get Started: Review Accounts')")
            await btn_next1.click()
            await page.wait_for_timeout(400)
            p2 = outdir / f"{mode}_wizard_step2_accounts.png"
            await page.screenshot(path=str(p2), full_page=True)
            print(f"  ✓ Captured Step 2 Accounts: {p2}")

            # 3. Step 3: Income
            btn_next2 = page.locator("button:has-text('Continue: Income & Salary')")
            await btn_next2.click()
            await page.wait_for_timeout(400)
            p3 = outdir / f"{mode}_wizard_step3_income.png"
            await page.screenshot(path=str(p3), full_page=True)
            print(f"  ✓ Captured Step 3 Income: {p3}")

            # 4. Step 4: Fixed Obligations
            btn_next3 = page.locator("button:has-text('Continue: Fixed Obligations')")
            await btn_next3.click()
            await page.wait_for_timeout(400)
            p4 = outdir / f"{mode}_wizard_step4_obligations.png"
            await page.screenshot(path=str(p4), full_page=True)
            print(f"  ✓ Captured Step 4 Fixed Obligations: {p4}")

            # 5. Step 5: Ready & Launch
            btn_next4 = page.locator("button:has-text('Continue: Review Blueprint')")
            await btn_next4.click()
            await page.wait_for_timeout(400)
            p5 = outdir / f"{mode}_wizard_step5_launch.png"
            await page.screenshot(path=str(p5), full_page=True)
            print(f"  ✓ Captured Step 5 Ready & Launch: {p5}")

            await ctx.close()

        await browser.close()

    print(f"\n==========================================")
    print(f"Console Errors Encountered: {len(console_errors)}")
    for err in console_errors:
        print(f"  ⚠ {err}")
    print(f"==========================================")


if __name__ == "__main__":
    asyncio.run(audit_wizard())
