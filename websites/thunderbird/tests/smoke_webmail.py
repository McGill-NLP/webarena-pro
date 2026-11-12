"""Exercise filters on a disposable seeded container."""
import argparse
import json
from playwright.sync_api import sync_playwright, expect
from pathlib import Path
import uuid
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://localhost:8080')
parser.add_argument('--output',type=Path,default=Path('/tmp/thunderbird-smoke'))
args=parser.parse_args()
base=args.url.rstrip('/')
filter_name='Filter regression '+uuid.uuid4().hex[:8]
out=args.output;out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1280,'height':720})
 page.goto(base,wait_until='domcontentloaded')
 page.locator('[name=_user]').fill('alice@techcorp.local')
 page.locator('[name=_pass]').fill('User@Secure123');page.locator('[name=_pass]').press('Enter')
 expect(page.locator('#mailboxlist')).to_be_visible()
 page.goto(base+'/?_task=settings&_action=plugin.managesieve',wait_until='domcontentloaded')
 page.wait_for_timeout(1500)
 page.get_by_title('Add filter',exact=True).click()
 frame=page.frame_locator('iframe[name="filter-box"]')
 expect(frame.locator('input[name="_name"]')).to_be_visible()
 frame.locator('input[name="_name"]').fill(filter_name)
 frame.locator('[name="_rule_target[0][]"]').fill('Issue112 test')
 frame.locator('#action_type0').select_option('fileinto')
 frame.locator('#action_mailbox0').select_option('Work')
 frame.locator('button').filter(has_text='Save').click()
 expect(page.get_by_text(filter_name,exact=True)).to_be_visible()
 page.reload(wait_until='domcontentloaded')
 expect(page.get_by_text(filter_name,exact=True)).to_be_visible()
 page.screenshot(path=str(out/'filters-saved.png'))
 print('filter_saved_and_reloaded',True)
 result={'filter_saved_and_reloaded':True}
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
 b.close()
