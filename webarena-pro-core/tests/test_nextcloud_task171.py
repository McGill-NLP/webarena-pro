"""Task 171 creates /marketing and uses the execution date, not grading day."""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.task import WebArenaProTaskConfig

CONFIG = Path(__file__).parents[1] / 'src/webarena_pro_core/config'
TASK = next(t for t in json.loads((CONFIG / 'nextcloud.raw.json').read_text()) if t['task_id'] == '171')


def response(status, body=''):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    return result


@pytest.mark.parametrize('body,favorite,uppercase_only,expected', [
    ('date: 27/10/2026', True, False, 1),
    ('# Strategy\n\nUpdated date: 27/10/2026 for this strategy.', True, False, 1),
    ('date: 24/10/2026', True, False, .75),
    ('date: 27/10/2026', False, False, .75),
    ('date: 27/10/2026', True, True, 0),
    ('date: 32/10/2026', True, False, .75),
    ('date: 27/10/2026\ndate: 24/10/2026', True, False, .75),
    ('date: 27/10/20260', True, False, .75),
])
def test_real_dag_http_checks(monkeypatch, body, favorite, uppercase_only, expected):
    paths = []
    def send(self, spec, context):
        path = urlsplit(self._resolve_url(spec['url'], context)).path
        paths.append(path)
        assert path in {'/remote.php/dav/files/maya.patel/marketing', '/remote.php/dav/files/maya.patel/marketing/strategy.md'}
        if uppercase_only:
            return response(404)
        if spec.get('method') == 'PROPFIND':
            return response(207, f'<oc:favorite>{int(favorite)}</oc:favorite>')
        return response(200, body)
    monkeypatch.setattr(BackendStateEvaluator, '_send', send)
    def judge(*args):
        pytest.fail('A definitive backend result must not fall through to a judge')
    monkeypatch.setattr(llm_judge, '_JUDGE_HOOK', judge)
    score, _ = DAGEvaluator(parse_eval_dag(TASK['eval'])).evaluate(EvalContext(
        task_config=TASK, task_start_date=date(2026,10,27),
        last_action="click('favorite')",
    ))
    assert score == expected
    assert paths


@pytest.mark.parametrize('execution_date', [date(2024,2,29), date(2026,12,31), '2026-10-27'])
def test_date_check_accepts_persisted_execution_date(execution_date):
    parsed = date.fromisoformat(execution_date) if isinstance(execution_date,str) else execution_date
    check = TASK['eval']['nodes'][2]['eval_config']['strategies'][0]['config']['checks'][1]
    result, _ = BackendStateEvaluator()._run_check(check, response(200, 'date: '+parsed.strftime('%d/%m/%Y')), EvalContext(task_start_date=execution_date))
    assert result


@pytest.mark.parametrize('execution_date', [None, '', 'not-a-date'])
def test_missing_execution_date_is_inconclusive(monkeypatch, execution_date):
    monkeypatch.setattr(BackendStateEvaluator, '_send', lambda *args: response(200, 'date: 27/10/2026'))
    config = TASK['eval']['nodes'][2]['eval_config']['strategies'][0]['config']
    result = BackendStateEvaluator().evaluate(config, EvalContext(task_config=TASK, task_start_date=execution_date))
    assert result.inconclusive
    assert not result.passed


def test_task_loads_once_in_test_split():
    WebArenaProTaskConfig.from_raw_task(TASK, container_name='task171-test')
    assert sum(t['task_id']=='171' for p in CONFIG.glob('*.raw.json') for t in json.loads(p.read_text())) == 1
    assert not any(t['task_id']=='171' for t in json.loads((CONFIG/'splits/dev.json').read_text())['tasks'])
    assert '/marketing/strategy.md' in TASK['intent']
    assert 'Marketing' not in json.dumps(TASK)


def test_favorite_error_response_cannot_pass_from_its_text(monkeypatch):
    monkeypatch.setattr(BackendStateEvaluator, '_send', lambda *args: response(500, '<oc:favorite>1</oc:favorite>'))
    config = TASK['eval']['nodes'][3]['eval_config']['strategies'][0]['config']
    result = BackendStateEvaluator().evaluate(config, EvalContext(task_config=TASK))
    assert not result.passed
    assert result.inconclusive
    assert '500' in result.reason


@pytest.mark.parametrize('action', [
    "click('favorite')",
    "click('unfavorite')",
    "send_msg_to_user('Added /marketing/strategy.md to favorites')",
    None,
])
def test_favorite_action_alone_falls_through_to_judge(monkeypatch, action):
    def send(self, spec, context):
        if spec.get('method') == 'PROPFIND':
            raise requests.ConnectionError('Favorite state is unavailable')
        return response(200, 'date: 27/10/2026')

    judge_calls = []

    def judge(rubric, context, model):
        judge_calls.append(rubric)
        return 'fail', 'No evidence of the saved favorite state'

    monkeypatch.setattr(BackendStateEvaluator, '_send', send)
    monkeypatch.setattr(llm_judge, '_JUDGE_HOOK', judge)
    score, results = DAGEvaluator(parse_eval_dag(TASK['eval'])).evaluate(EvalContext(
        task_config=TASK, task_start_date=date(2026,10,27), last_action=action,
    ))

    assert score == .75
    assert 'decided_by=T2:llm_judge' in results['r4']['reason']
    assert 'T0:backend_state=INCONCLUSIVE' in results['r4']['reason']
    assert 'T1:ui_state=INCONCLUSIVE' in results['r4']['reason']
    assert judge_calls == ['strategy.md is added to favorites.']
