"""Deal layout regression check against a seeded Pipedrive container."""
import asyncio
import os
from playwright.async_api import async_playwright, expect


async def main():
    base = os.environ.get("BASE_URL", "http://127.0.0.1:4520").rstrip("/")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(base + "/login")
        await page.get_by_role("button", name="Sign in", exact=True).click()
        await page.wait_for_url("**/deals")
        add_deal = page.get_by_role("button", name="Add Deal", exact=True)
        await expect(add_deal).to_be_visible()
        box = await add_deal.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 1280, box
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Board overflows viewport"
        if os.environ.get("SCREENSHOT_PATH"):
            await page.screenshot(path=os.environ["SCREENSHOT_PATH"])
        await add_deal.click()
        await expect(page.get_by_role("dialog")).to_be_visible()
        await page.keyboard.press("Escape")
        await browser.close()
    print("PASS: Add Deal is reachable at 1280x720 and opens its dialog; the board stays within the viewport")


if __name__ == "__main__":
    asyncio.run(main())
