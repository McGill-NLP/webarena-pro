"""Task loading and data-only evaluation must not initialize browser integrations."""
import subprocess
import sys


def test_core_data_evaluation_does_not_import_browser_or_media():
    subprocess.run([sys.executable, "-c", '''
import importlib.abc
import sys
class NoExecutionPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'playwright', 'webarena_pro_autologin', 'webarena_pro_media', 'webarena_pro_ui_evidence'}:
            raise ImportError('execution package intentionally unavailable: ' + fullname)
sys.meta_path.insert(0, NoExecutionPackages())
from webarena_pro_core.task import load_task_configs
from webarena_pro_core.website_metadata import deployed_website_url
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval.ui_evidence import build_ui_evidence_plan
assert not hasattr(EvalContext(), "page")
config = {"nodes": [{"id": "ui", "type": "ui_state", "eval_config": {"checks": []}}]}
assert not build_ui_evidence_plan(config).probes
assert DAGEvaluator(parse_eval_dag(config)).evaluate(EvalContext())[0] == 0
from webarena_pro_core import cli
assert len(load_task_configs(split='test')) == 300
assert deployed_website_url('x-lite')
# Loading tasks and evaluating evidence must not initialize browser helpers.
assert 'webarena_pro_core.autologin' not in sys.modules
assert 'webarena_pro_core.ui_evidence' not in sys.modules
# The bundled helpers themselves also support lazy browser imports.
from webarena_pro_core.autologin import sync_api as login_sync, async_api as login_async
from webarena_pro_core.ui_evidence import sync_api as evidence_sync, async_api as evidence_async
assert login_sync.AutoLogin and login_async.AutoLogin
assert evidence_sync.collect_ui_evidence(None, build_ui_evidence_plan(config)).status == 'unavailable'
assert evidence_async.collect_ui_evidence
try:
    cli._auto_login_started_sites({}, auth_dir=None, browser_name='chromium', headless=True, max_attempts=1)
except SystemExit as exc:
    assert 'Playwright, a Core dependency' in str(exc) and '`webarena-pro-core`' in str(exc)
else:
    raise AssertionError('Login must explain a missing browser dependency')
'''], check=True)
