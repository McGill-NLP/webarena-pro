#!/usr/bin/env python3
"""Verify the Penpot 2.14.1 text-entry workaround on a disposable container.

Creates a board and text in a new Drafts file, waits for a successful save that
contains the text, and reloads to verify persistence. Requires Playwright and
Chromium. It intentionally does not type until a contenteditable has focus.
"""
import argparse
import json
from pathlib import Path
import re

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:9001')
    parser.add_argument('--output', type=Path, default=Path('/tmp/penpot-text-smoke'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    text = 'Proposal regression text'
    errors, saves = [], []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: saves.append(response.status)
                if '/update-file' in response.url
                and text in (response.request.post_data or '') else None)
        page.goto(args.url)
        page.get_by_placeholder('Email').fill('admin@penpot.local')
        page.get_by_placeholder('Password', exact=True).fill('Admin@Secure123')
        page.get_by_placeholder('Password', exact=True).press('Enter')
        page.get_by_role('button', name='+ New File', exact=True).click()
        expect(page.get_by_role('button', name='Text (T)', exact=True)).to_be_visible()

        page.keyboard.press('b')
        page.mouse.move(450, 180)
        page.wait_for_timeout(100)
        page.mouse.down()
        page.mouse.move(850, 520, steps=20)
        page.mouse.up()
        page.wait_for_timeout(1000)
        page.get_by_role('button', name='Text (T)', exact=True).click()
        page.mouse.move(550, 300)
        page.wait_for_timeout(100)
        page.mouse.click(550, 300)
        page.wait_for_timeout(500)
        first_click_focused = page.evaluate('document.activeElement.isContentEditable')
        if not first_click_focused:
            page.mouse.click(550, 300)
        page.wait_for_function('document.activeElement.isContentEditable')
        page.keyboard.type(text, delay=100)
        expect(page.locator('[role="textbox"][contenteditable="true"]')).to_have_text(text)

        # Clicking outside commits the editor contents before waiting for save.
        page.mouse.click(900, 580)
        page.get_by_role('button', name='Move (V)', exact=True).click()
        for _ in range(200):
            if 200 in saves:
                break
            page.wait_for_timeout(100)
        assert 200 in saves, f'No successful save containing the text: {saves}'
        assert not errors, errors
        expect(page.get_by_text('Internal Error', exact=True)).to_have_count(0)
        page.reload()
        expect(page.get_by_role('button', name='Text (T)', exact=True)).to_be_visible()
        expect(page.locator('text').filter(has_text=re.compile('^' + re.escape(text) + '$'))).to_have_count(1, timeout=30000)
        assert not errors, errors
        page.screenshot(path=str(args.output / 'text-reloaded.png'))
        result = {'first_click_focused': first_click_focused,
                  'second_click_used': not first_click_focused,
                  'text_saved_and_reloaded': text, 'save_statuses': saves,
                  'errors': errors, 'url': page.url}
        (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        browser.close()


if __name__ == '__main__':
    main()
