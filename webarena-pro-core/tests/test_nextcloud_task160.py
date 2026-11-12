"""The prompted Markdown filename is the one whose saved content is graded."""
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import requests

from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.task import WebArenaProTaskConfig

CONFIG = Path(__file__).parents[1] / 'src/webarena_pro_core/config'
TASK = next(t for t in json.loads((CONFIG/'nextcloud.raw.json').read_text()) if t['task_id']=='160')


@pytest.mark.parametrize('files,expected', [
    ({'Client Meeting Update.md': 'The client meeting moved to next Thursday.'}, 1),
    ({'Client Meeting Update.md': 'The client meeting moved to next Friday.'}, 2 / 3),
    ({'Client Meeting Update': 'The client meeting moved to next Thursday.'}, 1 / 3),
    ({'New text file.md': 'The client meeting moved to next Thursday.'}, 1 / 3),
    ({}, 1 / 3),
])
def test_real_dag_grades_prompted_file_and_its_contents(monkeypatch, files, expected):
    requests_seen=[]
    def send(self, spec, context):
        path=unquote(urlsplit(self._resolve_url(spec['url'], context)).path)
        name=path.removeprefix('/remote.php/dav/files/maya.patel/')
        requests_seen.append(name)
        result=requests.Response(); result.status_code=200 if name in files else 404
        result._content=files.get(name,'Not found').encode()
        return result
    monkeypatch.setattr(BackendStateEvaluator,'_send',send)
    monkeypatch.setattr(llm_judge,'_JUDGE_HOOK',lambda *args: pytest.fail('Definitive saved-file result must not escalate'))
    context=EvalContext(task_config=TASK,last_action='click Project Alpha')
    score,_=DAGEvaluator(parse_eval_dag(TASK['eval'])).evaluate(context)
    assert score==pytest.approx(expected)
    assert set(requests_seen)=={'Client Meeting Update.md'}


def test_task_load_split_and_identity_consistency():
    WebArenaProTaskConfig.from_raw_task(TASK,container_name='task160-test')
    assert sum(t['task_id']=='160' for p in CONFIG.glob('*.raw.json') for t in json.loads(p.read_text()))==1
    assert not any(t['task_id']=='160' for t in json.loads((CONFIG/'splits/dev.json').read_text())['tasks'])
    assert 'Client Meeting Update.md' in TASK['intent']
    for node in TASK['eval']['nodes'][1:]:
        for strategy in node['eval_config']['strategies']:
            config=strategy['config']
            if strategy['type']=='backend_state': assert config['params']['path']=='Client Meeting Update.md'
            elif node['id']=='r2': assert 'Client Meeting Update.md' in config['rubric']
            else: assert config['rubric']==node['eval_config']['rubric']
