"""Date editing regression against a disposable, seeded Notion container."""
import asyncio
import os
from playwright.async_api import async_playwright, expect


async def main():
    base = os.environ.get("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        login = await page.request.post(base + "/api/login", data={"email": "demo@webarena.local", "password": "password123"})
        assert login.ok, await login.text()
        rows_response = await page.request.get(base + "/api/databases/page_task_tracker/rows")
        assert rows_response.ok, await rows_response.text()
        row = (await rows_response.json())["rows"][0]
        await page.goto(base + "/app/page/" + row["pageId"])
        date = page.get_by_label("Due Date", exact=True)
        await expect(date).to_be_visible()
        values = []
        in_flight = 0
        max_in_flight = 0
        completed = asyncio.Event()

        async def slow_save(route):
            nonlocal in_flight, max_in_flight
            if route.request.method != "POST":
                return await route.continue_()
            payload = route.request.post_data_json
            values.append(payload["value"])
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            # A partial-year write must finish before a later edit is sent.
            await asyncio.sleep(0.3)
            response = await route.fetch()
            assert response.ok, await response.text()
            await route.fulfill(response=response)
            in_flight -= 1
            if payload["value"] == "2026-06-20":
                completed.set()

        await page.route("**/api/databases/*/cells", slow_save)
        await date.fill("2001-06-20")
        await expect(date).to_be_enabled()
        # Select the year segment using the native date input's keyboard UI.
        await date.click(position={"x": 8, "y": 8})
        await page.keyboard.press("ArrowRight")
        await page.keyboard.press("ArrowRight")
        for digit in "2026":
            await page.keyboard.press(digit)
            assert await date.evaluate("el => document.activeElement === el"), "Date input lost focus during save"
        await expect(date).to_have_value("2026-06-20")
        await asyncio.wait_for(completed.wait(), timeout=15)
        assert max_in_flight == 1, f"Overlapping writes: {max_in_flight}; {values}"
        await page.reload()
        await expect(page.get_by_label("Due Date", exact=True)).to_have_value("2026-06-20")
        if os.environ.get("SCREENSHOT_PATH"):
            await page.screenshot(path=os.environ["SCREENSHOT_PATH"])
        await page.unroute("**/api/databases/*/cells", slow_save)
        async with page.expect_response(lambda r: r.url.endswith("/cells") and r.request.method == "POST") as cleared:
            await page.get_by_label("Due Date", exact=True).fill("")
        assert (await cleared.value).ok
        await page.reload()
        await expect(page.get_by_label("Due Date", exact=True)).to_have_value("")
        login = await page.request.post(base + "/api/login", data={"email": "mina@webarena.local", "password": "password123"})
        assert login.ok, await login.text()
        await page.reload()
        await expect(page.get_by_label("Due Date", exact=True)).to_be_disabled()
        await browser.close()
    print("PASS: slow saves preserve keyboard focus and full year; ordered writes and clearing persist; viewers cannot edit")


if __name__ == "__main__":
    asyncio.run(main())
