import json
import shutil

import pytest

from webarena_pro_core.splits import CONFIG_DIR, load_split_tasks, task_ids_for_split
from webarena_pro_core.task import load_raw_tasks, load_task_configs


def test_packaged_dev_and_test_partition_active_tasks():
    dev, test = task_ids_for_split("dev"), task_ids_for_split("test")
    active = {str(t["task_id"]) for p in CONFIG_DIR.glob("*.raw.json")
              for t in json.loads(p.read_text())}
    assert len(dev) == 100
    assert len(test) == 300
    assert {f"{task_id:03d}" for task_id in [*range(300, 346), *range(403, 421)]} <= test
    assert not dev & test
    assert test == active
    assert len(dev | test) == 400
    assert {"421", "422"} <= dev
    assert not {"141", "384"} & (dev | test)
    for split, expected in [("dev", dev), ("test", test)]:
        tasks = load_task_configs(split=split)
        assert {task.task_id for task in tasks} == expected
        assert len(tasks) == len(expected)
        assert all(task.evaluation["nodes"] for task in tasks)
        assert all(task.evaluation["scoring"] == "partial" for task in tasks)
    assert {task.task_id for task in load_task_configs()} == test


@pytest.mark.parametrize("bundle", [False, True])
def test_incomplete_dev_task_is_rejected(tmp_path, bundle):
    with pytest.raises(ValueError, match="Unknown task split"):
        task_ids_for_split("typo")
    (tmp_path / "splits").mkdir()
    (tmp_path / "demo.raw.json").write_text('[{"task_id":"001"}]')
    tasks = [{"task_id": "002"}]
    payload = {"sampling": {}, "tasks": tasks} if bundle else tasks
    (tmp_path / "splits/dev.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="intent and a tiered DAG"):
        task_ids_for_split("dev", tmp_path)


@pytest.mark.parametrize("split", ["dev", "test"])
def test_splits_load_independently(tmp_path, split):
    if split == "dev":
        (tmp_path / "splits").mkdir()
        shutil.copyfile(CONFIG_DIR / "splits/dev.json", tmp_path / "splits/dev.json")
        expected = task_ids_for_split("dev")
    else:
        shutil.copyfile(CONFIG_DIR / "nextcloud.raw.json", tmp_path / "nextcloud.raw.json")
        expected = {task["task_id"] for task in load_raw_tasks(tmp_path / "nextcloud.raw.json")}
    tasks = load_split_tasks(split, tmp_path)
    assert {task["task_id"] for task in tasks} == expected
    assert all(task["eval"]["nodes"] for task in tasks)
    assert all("sampling" not in task for task in tasks)
    configs = load_task_configs("nextcloud", config_dir=tmp_path, split=split)
    assert configs and all(task.website == "nextcloud" for task in configs)


def test_dev_rejects_duplicate_task_ids(tmp_path):
    (tmp_path / "splits").mkdir()
    task = {"task_id": "001", "intent": "Example", "eval": {"nodes": [{}]}}
    (tmp_path / "splits/dev.json").write_text(json.dumps([task, task]))
    with pytest.raises(ValueError, match="unique task IDs"):
        load_split_tasks("dev", tmp_path)


@pytest.mark.parametrize("tasks", [None, {}, "invalid", [None]])
def test_bundle_requires_task_objects(tmp_path, tasks):
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps({"sampling": {}, "tasks": tasks}))
    with pytest.raises(ValueError, match="Expected list|not an object"):
        load_raw_tasks(path)
