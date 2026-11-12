"""Create a ticket on a disposable seeded container and verify its landing page."""
import argparse
import json,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://localhost:3000')
parser.add_argument('--output',type=Path,default=Path('/tmp/peppermint-new-smoke'))
args=parser.parse_args()
out=args.output;out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1280,'height':720})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(args.url)
 page.locator('#email').fill('admin@admin.com');page.locator('#password').fill('1234')
 page.get_by_role('button',name='Sign In',exact=True).click()
 page.wait_for_url(lambda u: '/auth/login' not in u)
 page.goto(args.url.rstrip('/')+'/new')
 expect(page.get_by_role('button',name='Create Ticket',exact=True)).to_be_visible()
 title='Issue112 regression '+uuid.uuid4().hex[:8]
 page.locator('input[name=title]').fill(title)
 page.locator('input[name=name]').fill('Regression User')
 page.locator('input[name=email]').fill('regression@example.com')
 page.locator('[contenteditable=true]').first.fill('Verify post-create navigation to the ticket list.')
 with page.expect_response(lambda r:'/api/v1/ticket/create' in r.url and r.request.method=='POST') as result:
  page.get_by_role('button',name='Create Ticket',exact=True).click()
 response=result.value;print('create',response.status,response.text())
 assert response.status==200 and response.json()['success'] is True
 page.wait_for_url(lambda u:u.endswith('/issues'))
 expect(page.get_by_text('404',exact=True)).to_have_count(0)
 expect(page.get_by_text(title,exact=True)).to_be_visible()
 page.screenshot(path=str(out/'created-ticket.png'))
 data={'create_status':response.status,'url':page.url,'ticket_title':title,'visible_in_list':True,'page_errors':errors}
 (out/'results.json').write_text(json.dumps(data,indent=2));print(json.dumps(data))
 b.close()
