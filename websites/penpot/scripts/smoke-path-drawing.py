#!/usr/bin/env python3
"""Exercise Path initialization and persistence on a disposable Penpot container.

Requires Playwright (and BrowserGym with --browsergym). Creates test files in
the seed admin's Drafts; use a disposable instance, never a user's working file.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:9001')
    parser.add_argument('--output', type=Path, default=Path('/tmp/penpot-path-smoke'))
    parser.add_argument('--browsergym', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def observe(page):
        if args.browsergym:
            from browsergym.core.observation import _post_extract, _pre_extract
            _pre_extract(page)
            _post_extract(page)

    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for activation in ('toolbar', 'keyboard'):
            # A new browser context has never generated a viewport pointer event.
            context = browser.new_context(viewport={'width': 1280, 'height': 900})
            page = context.new_page()
            errors = []
            saves = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda msg: errors.append(msg.text)
                    if ('TypeError:' in msg.text or 'ExceptionInfo' in msg.text) else None)
            page.on('response', lambda response: saves.append(response.status)
                    if '/update-file' in response.url else None)
            page.goto(args.url)
            page.get_by_placeholder('Email').fill('admin@penpot.local')
            page.get_by_placeholder('Password', exact=True).fill('Admin@Secure123')
            page.get_by_placeholder('Password', exact=True).press('Enter')
            page.get_by_role('button', name='+ New File', exact=True).click()
            tool = page.get_by_role('button', name='Path (P)', exact=True)
            expect(tool).to_be_visible()
            page.wait_for_timeout(1000)
            observe(page)
            if activation == 'toolbar':
                tool.click()
            else:
                page.keyboard.press('p')
            page.wait_for_timeout(300)
            observe(page)
            expect(page.get_by_text('Internal Error', exact=True)).to_have_count(0)
            expect(page.get_by_text('Something wrong has happened.', exact=True)).to_have_count(0)
            assert not errors, errors

            # A closed heart made of line segments, as in the reported task.
            # Allow pointer events to pass through Penpot's animation-frame stream
            # before mouse-down, just as in normal human/agent interactions.
            points = [(635, 390), (685, 335), (755, 350), (790, 425),
                      (635, 585), (480, 425), (515, 350), (585, 335), (635, 390)]
            for x, y in points:
                page.mouse.move(x, y)
                page.wait_for_timeout(100)
                page.mouse.click(x, y, delay=50)
                page.wait_for_timeout(100)
                observe(page)
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)
            page.keyboard.press('Escape')
            paths = page.locator('.fills > path[d]')
            expect(paths).to_have_count(1)
            path_data = paths.first.get_attribute('d')
            assert path_data and path_data.startswith('M') and path_data.count('L') >= 7, path_data
            assert 'NaN' not in path_data, path_data

            # Wait for the autosave request instead of treating a drawn preview
            # as success; reload must reproduce the exact saved path geometry.
            for _ in range(100):
                if 200 in saves:
                    break
                page.wait_for_timeout(100)
            assert 200 in saves, f'No successful update-file response: {saves}'
            page.reload()
            expect(tool).to_be_visible()
            expect(paths).to_have_count(1)
            expect(paths.first).to_have_attribute('d', path_data)
            expect(page.get_by_text('Internal Error', exact=True)).to_have_count(0)
            expect(page.get_by_text('Something wrong has happened.', exact=True)).to_have_count(0)
            assert not errors, errors
            page.screenshot(path=str(args.output / f'{activation}.png'))
            result = {'activation': activation, 'browsergym': args.browsergym,
                      'url': page.url, 'saved_path': path_data, 'save_statuses': saves,
                      'errors': errors, 'reload_matches': True}
            results.append(result)
            print(json.dumps(result), flush=True)
            context.close()
        browser.close()
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
