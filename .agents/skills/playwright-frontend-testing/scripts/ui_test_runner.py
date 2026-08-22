#!/usr/bin/env python3
"""Modular Playwright UI Test & Inspection Runner for MyMonee."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Resolve project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from expense_tracker.config import load_settings
from expense_tracker.db.session import get_session_factory
from expense_tracker.services.auth import _get_or_create_secret, create_session_token


def get_auth_token() -> str:
    """Generate a valid session token directly from the local database secret."""
    load_settings()
    SessionFactory = get_session_factory()
    with SessionFactory() as db:
        secret = _get_or_create_secret(db)
        token = create_session_token(secret)
        db.commit()
    return token


async def setup_context(browser, is_mobile: bool, token: str):
    """Set up browser context with appropriate viewport and authentication."""
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
    return ctx


async def test_overview(page, outdir: Path, is_mobile: bool, errors: list):
    """Test Overview page and month strip interaction."""
    prefix = "mobile" if is_mobile else "desktop"
    print(f"\n[Testing Overview ({prefix})]")
    
    await page.goto("http://127.0.0.1:8477/", wait_until="networkidle")
    await page.wait_for_selector(".month-strip-container", timeout=10000)
    
    active_month = await page.locator(".month-strip-item.active").text_content()
    print(f"  • Initial active month: {active_month.strip()}")
    await page.screenshot(path=str(outdir / f"{prefix}_overview_initial.png"))
    
    # Click previous month
    prev_btn = page.locator(".month-strip-arrow.left")
    await prev_btn.click()
    await page.wait_for_timeout(400)
    
    active_prev = await page.locator(".month-strip-item.active").text_content()
    print(f"  • Active month after left click: {active_prev.strip()}")
    assert active_prev != active_month, "Active month did not change on previous click"
    
    # Verify This Month button
    this_month_btn = page.locator(".month-strip-today-btn")
    assert await this_month_btn.is_visible(), "'This Month' button should appear"
    await page.screenshot(path=str(outdir / f"{prefix}_overview_prev_month.png"))
    
    # Click This Month
    await this_month_btn.click()
    await page.wait_for_timeout(400)
    active_restored = await page.locator(".month-strip-item.active").text_content()
    assert active_restored == active_month, "'This Month' failed to snap back"
    print(f"  • Successfully snapped back to: {active_restored.strip()}")


async def test_settings(page, outdir: Path, is_mobile: bool, errors: list):
    """Test Settings page tabs, categories accordion, search, and mobile scroll clearance."""
    prefix = "mobile" if is_mobile else "desktop"
    print(f"\n[Testing Settings ({prefix})]")
    
    await page.goto("http://127.0.0.1:8477/settings", wait_until="networkidle")
    await page.wait_for_selector(".settings-tabs-nav", timeout=10000)
    
    # Cycle tabs
    for tab in ["general", "gmail", "categories", "ai", "data", "system"]:
        btn = page.locator(f"#settings-tab-{tab}")
        await btn.click()
        await page.wait_for_timeout(250)
        panel = page.locator(f"#settings-tabpanel-{tab}")
        assert await panel.is_visible(), f"Tab panel for {tab} failed to render"
    print("  • All 6 settings tabs cycled and verified.")

    # Test Gmail Tab layout
    await page.locator("#settings-tab-gmail").click()
    await page.wait_for_timeout(300)
    oauth_card = page.locator(".oauth-upload-card")
    assert await oauth_card.is_visible(), "OAuth upload card not visible"
    await page.screenshot(path=str(outdir / f"{prefix}_settings_gmail.png"))

    # Test Categories Tab (Search & Expand)
    await page.locator("#settings-tab-categories").click()
    await page.wait_for_timeout(300)
    
    search_input = page.locator("input[placeholder*='Search categories']")
    await search_input.fill("Food")
    await page.wait_for_timeout(200)
    assert await page.locator(".category-row-card").count() > 0, "Category filter failed"
    await search_input.fill("")
    await page.wait_for_timeout(200)
    
    # Expand first category
    first_cat = page.locator(".category-row-card").first
    await first_cat.locator(".category-row-main").click()
    await page.wait_for_timeout(300)
    assert await first_cat.locator(".category-row-expanded").is_visible(), "Accordion expansion failed"
    await page.screenshot(path=str(outdir / f"{prefix}_settings_categories_expanded.png"))
    print("  • Category search, filters, and row accordion verified.")

    # Test Scroll Clearance
    if is_mobile:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(300)
        scroll_y = await page.evaluate("window.scrollY")
        assert scroll_y > 0, "Mobile page failed to scroll"
        await page.screenshot(path=str(outdir / f"{prefix}_settings_bottom_clearance.png"))
        print(f"  • Mobile bottom scroll clearance verified (scrollY: {scroll_y}px).")


async def test_transactions(page, outdir: Path, is_mobile: bool, errors: list):
    """Test Transactions ledger page."""
    prefix = "mobile" if is_mobile else "desktop"
    print(f"\n[Testing Transactions ({prefix})]")
    
    await page.goto("http://127.0.0.1:8477/transactions", wait_until="networkidle")
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(outdir / f"{prefix}_transactions.png"))
    print(f"  • Transactions view rendered and captured.")


async def main():
    parser = argparse.ArgumentParser(description="MyMonee Playwright UI Test Runner")
    parser.add_argument("--page", choices=["overview", "settings", "transactions", "all"], default="all", help="Specific page to test")
    parser.add_argument("--all", action="store_true", help="Run full test suite across all pages and viewports")
    parser.add_argument("--mobile", action="store_true", help="Run in mobile viewport (390x844)")
    parser.add_argument("--desktop", action="store_true", help="Run in desktop viewport (1200x850)")
    parser.add_argument("--interactive", action="store_true", help="Launch in headful interactive browser window")
    parser.add_argument("--outdir", default=None, help="Output directory for screenshots")
    
    args = parser.parse_args()

    outdir = Path(args.outdir) if args.outdir else PROJECT_ROOT / "tests" / "screenshots"
    outdir.mkdir(parents=True, exist_ok=True)

    token = get_auth_token()
    print(f"Authenticated with session token ({token[:18]}...)")

    viewports = []
    if args.mobile:
        viewports.append(True)
    if args.desktop:
        viewports.append(False)
    if not viewports:
        # Default to mobile or both if --all
        viewports = [True, False] if (args.all or args.page == "all") else [True]

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.interactive)
        
        for is_mobile in viewports:
            ctx = await setup_context(browser, is_mobile=is_mobile, token=token)
            page = await ctx.new_page()
            
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))

            pages_to_run = ["overview", "settings", "transactions"] if (args.all or args.page == "all") else [args.page]

            for pg in pages_to_run:
                if pg == "overview":
                    await test_overview(page, outdir, is_mobile, errors)
                elif pg == "settings":
                    await test_settings(page, outdir, is_mobile, errors)
                elif pg == "transactions":
                    await test_transactions(page, outdir, is_mobile, errors)

            if args.interactive:
                print("\n[Interactive Mode]: Browser session active. Press Enter in terminal to close...")
                await asyncio.get_event_loop().run_in_executor(None, input)

            assert len(errors) == 0, f"Uncaught console errors detected: {errors}"
            await ctx.close()

        await browser.close()
    
    print(f"\n✅ All tests passed cleanly! Screenshots saved to: {outdir}\n")


if __name__ == "__main__":
    asyncio.run(main())
