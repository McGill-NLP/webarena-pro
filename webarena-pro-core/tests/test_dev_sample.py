"""Reproducible Dev membership, complete evaluation coverage and prerequisite gates."""
import json
import random
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from webarena_pro_core.website_metadata import deployed_website_url
from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.task import WebArenaProTaskConfig

CONFIG = Path(__file__).parents[1] / 'src/webarena_pro_core/config'
DEV = json.loads((CONFIG / 'splits/dev.json').read_text())
MANIFEST = DEV['sampling']
TASKS = {task['task_id']: task for task in DEV['tasks']}
DAGS = {tid: task['eval'] for tid, task in TASKS.items()}


def test_sample_reproduces_and_all_dev_tasks_match_packaged_dags():
    selected_source_ids = {row['task_id'] for row in MANIFEST['sampled']}
    selected = {row['packaged_task_id'] for row in MANIFEST['sampled']}
    rng = random.Random(MANIFEST['seed'])
    reproduced = {
        tid for site in sorted(MANIFEST['website_targets'])
        for tid in rng.sample(MANIFEST['eligible_task_ids_by_site'][site],
                              MANIFEST['sampled_counts_by_site'][site])
    }
    overrides = MANIFEST['sampled_task_overrides']
    assert set(overrides) <= reproduced
    assert set(overrides.values()) <= set(MANIFEST['eligible_task_ids']) - reproduced
    assert not set(overrides) & selected_source_ids
    assert selected_source_ids == {overrides.get(tid, tid) for tid in reproduced}
    fixed = set(MANIFEST['fixed_dev_task_ids'])
    assert len(fixed) == 43 and len(selected) == len(selected_source_ids) == 57
    assert not fixed & selected_source_ids
    dev = DEV['tasks']
    assert len(dev) == len({t['task_id'] for t in dev}) == len(DAGS) == 100
    assert {t['task_id'] for t in dev} == set(DAGS)
    assert selected <= set(DAGS)
    assert len(set(DAGS) - selected) == len(fixed)
    packaged = {str(t['task_id']): t for p in CONFIG.glob('*.raw.json') for t in json.loads(p.read_text())}
    for task in dev:
        tid = task['task_id']
        assert tid not in packaged
        assert 'intent' not in DAGS[tid]
        dag = parse_eval_dag(DAGS[tid])
        assert len(DAGEvaluator(dag)._topological_sort()) == len(DAGS[tid]['nodes'])
    assert sum(len(DAGS[tid]['nodes']) for tid in selected) == 100
    for row in MANIFEST['sampled']:
        assert row['review_status'] == 'solved' and not row['review_flags']
        nodes = DAGS[row['packaged_task_id']]['nodes']
        rubrics = [r['text'] for r in row['source_eval']['rubrics']]
        for correction in row.get('evaluation_normalizations', []):
            index = correction['rubric_index']
            assert rubrics[index] == correction['source_rubric']
            assert correction['reason']
            rubrics[index] = correction['packaged_rubric']
        assert [n['eval_config']['rubric'] for n in nodes] == rubrics
        for node in nodes:
            judge = node['eval_config']['strategies'][-1]
            assert judge['type'] == 'llm_judge'
            reference = row['source_eval'].get('reference_answers', {}).get('exact_match')
            if reference:
                assert reference in judge['config']['rubric']


def test_dev_includes_task_421_and_retired_task_141_is_absent():
    packaged = {str(t['task_id']): t for p in CONFIG.glob('*.raw.json')
                for t in json.loads(p.read_text())}
    assert '141' not in set(packaged) | set(DAGS)
    assert '421' not in packaged
    task = next(task for task in DEV['tasks'] if task['task_id'] == '421')
    assert task['sites'] == ['mattermost']
    config = WebArenaProTaskConfig.from_raw_task(task, container_name='dev-task-421')
    assert config.start_url == deployed_website_url('mattermost')
    assert task in DEV['tasks']
    dag = DAGS[task['task_id']]
    assert len(dag['nodes']) == 1
    evaluation = dag['nodes'][0]['eval_config']
    assert evaluation['rubric'] == 'Correct if the answer is 203.0.113.0/24.'
    judge = evaluation['strategies'][-1]
    assert judge['type'] == 'llm_judge'
    assert 'The IP range was 203.0.113.0/24.' in judge['config']['rubric']


def test_domain_balance_and_media_priority():
    counts = Counter(t['sites'][0] for t in DEV['tasks'])
    assert dict(counts) == MANIFEST['website_targets']
    domains = {domain: sum(counts[site] for site in sites)
               for domain, sites in MANIFEST['domain_sites'].items()}
    assert domains == MANIFEST['domain_targets'] == {
        'Productivity': 10, 'Communication': 15, 'Analytics': 14,
        'Business ops.': 15, 'Design & media': 32, 'Travel': 14,
    }
    assert sum(domains.values()) == 100
    # The two preferred sites lead both primary counts and multisite coverage.
    memberships = Counter(site for task in DEV['tasks'] for site in task['sites'])
    for distribution in [counts, memberships]:
        assert {site for site, _ in distribution.most_common(2)} == {'acidwave', 'yt-lite'}
    pools = MANIFEST['eligible_task_ids_by_site']
    assert len({tid for ids in pools.values() for tid in ids}) == sum(map(len, pools.values())) == 89
    assert {tid for ids in pools.values() for tid in ids} == set(MANIFEST['eligible_task_ids'])


@pytest.mark.parametrize('task_date', [date(2026, 5, 3), date(2026, 10, 19), date(2026, 10, 22)])
def test_task_373_judge_uses_execution_date_and_relative_thursday(monkeypatch, task_date):
    dag = DAGS['373']
    prompts = []

    def judge(rubric, context, model):
        prompts.append(llm_judge.build_judge_messages(rubric, context))
        return 'fail', 'Prompt-only regression check; no LLM verdict'

    monkeypatch.setattr(llm_judge, '_JUDGE_HOOK', judge)
    DAGEvaluator(parse_eval_dag(dag)).evaluate(EvalContext(
        task_config=TASKS['373'],
        task_start_date=task_date,
    ))
    assert len(prompts) == 1
    for variant in ('regular', 'pruned'):
        text = str(prompts[0][variant])
        assert f'Task execution date: {task_date.isoformat()}' in text
        assert 'first Thursday strictly after the task execution date' in text
        assert 'Thursday seven days later' in text
        assert '09:00 to 11:00' in text
        assert 'same newly saved event' in text
        assert 'may 7' not in text.lower()


@pytest.mark.parametrize('task_id,rejected,called,score', [
    ('354', {'r1'}, {'r1'}, 0),
    ('354', {'r2'}, {'r1', 'r2'}, 1/3),
    ('354', set(), {'r1', 'r2', 'r3'}, 1),
    ('355', {'r2'}, {'r1', 'r2'}, 1/3),
    ('357', {'r1'}, {'r1'}, 0),
    ('399', {'r1'}, {'r1'}, 0),
    ('399', {'r3'}, {'r1', 'r2', 'r3', 'r4'}, 3/4),
    ('402', {'r2'}, {'r1', 'r2'}, 1/4),
    ('402', set(), {'r1', 'r2', 'r3', 'r4'}, 1),
    # Independent outcome criteria still earn partial credit.
    ('347', {'r1'}, {'r1', 'r2'}, 1/2),
    ('397', {'r2'}, {'r1', 'r2', 'r3'}, 2/3),
    ('353', {'r1'}, {'r1'}, 0),
    ('359', {'r2'}, {'r1', 'r2'}, 1/3),
    ('363', {'r1'}, {'r1'}, 0),
    ('383', {'r1'}, {'r1'}, 0),
    ('391', {'r1'}, {'r1'}, 0),
    ('391', {'r5'}, {'r1', 'r2', 'r3', 'r4', 'r5'}, 4/7),
    ('352', {'r2'}, {'r1', 'r2'}, 1/3),
])
def test_dev_dag_prerequisites_gate_credit(monkeypatch, task_id, rejected, called, score):
    dag = DAGS[task_id]
    ids = {n['eval_config']['strategies'][-1]['config']['rubric']: n['id'] for n in dag['nodes']}
    seen = set()
    def judge(rubric, context, model):
        node_id = ids[rubric]
        seen.add(node_id)
        return ('fail' if node_id in rejected else 'pass'), 'Scripted criterion result'
    monkeypatch.setattr(llm_judge, '_JUDGE_HOOK', judge)
    actual, _ = DAGEvaluator(parse_eval_dag(dag)).evaluate(EvalContext(task_config=TASKS[task_id]))
    assert actual == pytest.approx(score)
    assert seen == called
