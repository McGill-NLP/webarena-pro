"""Create a native Harbor fixture: prepare_smoke.py OUTPUT, then harbor run -p OUTPUT -a oracle."""

import sys
from pathlib import Path

import yaml
from webarena_pro_core.task import WebArenaProTaskConfig
from webarena_pro_mcp.media_policy import MediaSettings

from webarena_pro_harbor.export import export_tasks, write

# Full Chromium can preconnect without sending a request. Serve other sockets
# concurrently so an idle preconnection cannot block the guarded navigation.
FIXTURE_SERVER = """from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
saved = False
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global saved
        if self.path == '/save': saved = True
        text = 'Saved' if saved else 'Ready'
        body = ('<html><title>Harbor fixture</title><button onclick="fetch(\\\'/save\\\').then(()=>location.reload())">Save</button><p>'+text+'</p></html>').encode()
        self.send_response(200)
        self.send_header('Content-Type','text/html')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
ThreadingHTTPServer(('0.0.0.0',8000), Handler).serve_forever()
"""

SOLUTION = """import json, re, socket, urllib.request
try:
    socket.getaddrinfo('jobportal', 8000)
except socket.gaierror:
    pass
else:
    raise AssertionError('Website backend is accessible to the agent')
seq = 0
def rpc(method, params):
    global seq
    seq += 1
    request = urllib.request.Request('http://webarena:8000/mcp',
        data=json.dumps({'jsonrpc':'2.0','id':seq,'method':method,'params':params}).encode(),
        headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream',
                 'MCP-Protocol-Version':'2025-11-25'})
    with urllib.request.urlopen(request, timeout=120) as response:
        result=json.load(response)
    assert 'error' not in result, result
    return result['result']
rpc('initialize', {'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'harbor-smoke','version':'1'}})
names={t['name'] for t in rpc('tools/list', {})['tools']}
assert 'webarena_submit' in names and 'browser_evaluate' not in names
def call(name, arguments):
    return rpc('tools/call', {'name':name,'arguments':arguments})
assert call('browser_tabs', {'action':'close'}).get('isError')
assert not call('browser_tabs', {'action':'new', 'url':'http://jobportal:8000'}).get('isError')
assert not call('browser_tabs', {'action':'close'}).get('isError')
text='\\n'.join(p.get('text','') for p in call('browser_snapshot', {})['content'])
assert 'Ready' in text and 'Saved' not in text, text
ref=re.search(r'button "Save" \\[ref=([^\\]]+)\\]',text).group(1)
assert not call('browser_click', {'target':ref}).get('isError')
text='\\n'.join(p.get('text','') for p in call('browser_snapshot', {})['content'])
assert 'Saved' in text, text
assert call('browser_navigate', {'url':'http://jobportal:8000/api/eval/state'}).get('isError')
assert not call('webarena_submit', {'answer':'42'}).get('isError')
assert call('browser_snapshot', {}).get('isError')
print('Browser interaction, isolation, submission, and terminal behavior passed.')
"""


def prepare(output, runtime_image="webarena-pro-harbor:issue167"):
    task = WebArenaProTaskConfig.from_raw_task(
        {
            "task_id": "smoke",
            "intent": "Click Save and submit the answer 42.",
            "sites": ["jobportal"],
            "eval": {
                "nodes": [
                    {"id": "answer", "type": "answer_match", "eval_config": {"exact_match": "42"}}
                ]
            },
        },
        container_name="fixture",
    )
    export_tasks(
        [task], output, split="dev", runtime_image=runtime_image, media=MediaSettings(enabled=False)
    )
    root = Path(output) / "webarena-pro-dev-smoke"
    env = root / "environment"
    config = yaml.safe_load((env / "docker-compose.yaml").read_text())
    config["services"]["jobportal"] = {"build": {"context": "./fixture"}, "networks": ["websites"]}
    write(env / "docker-compose.yaml", yaml.safe_dump(config, sort_keys=False))
    write(
        env / "fixture/Dockerfile",
        'FROM python:3.12-slim-bookworm\nCOPY server.py /server.py\nCMD ["python", "/server.py"]\n',
    )
    write(env / "fixture/server.py", FIXTURE_SERVER)
    write(root / "solution/solve.sh", "#!/bin/sh\nset -eu\npython3 /solution/solve.py\n")
    write(root / "solution/solve.py", SOLUTION)
    return root


if __name__ == "__main__":
    print(prepare(sys.argv[1]))
