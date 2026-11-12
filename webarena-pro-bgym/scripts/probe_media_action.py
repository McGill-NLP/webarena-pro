"""Opt-in live action/observation/provider probe using a benchmark task's media.

This explicitly invokes the selected action. It is a function integration test,
not an autonomous benchmark episode and never reports a task reward. Supply a
media URL actually discovered on the task's website, with the site already up.
Requires GEMINI_API_KEY and makes a paid generation request.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--split", default="dev", choices=("dev", "test"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--action", choices=("listen", "watch"), required=True)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, default=30)
    parser.add_argument("--include-audio", action="store_true")
    parser.add_argument("--agent-model", default="gemini/gemini-3.5-flash-omni")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("--output already exists; preserve previous evidence with a new path")

    from webarena_pro_bgym.benchmark import env
    from webarena_pro_bgym.benchmark.benchmark import WebArenaProActionSetArgs
    from webarena_pro_bgym.llm_configs import WEBARENA_PRO_CHAT_MODEL_ARGS_DICT
    from webarena_pro_core.splits import load_split_tasks
    from webarena_pro_media.sync_api import clear_media_cache

    task = next(t for t in load_split_tasks(args.split)
                if str(t["task_id"]).zfill(3) == args.task.zfill(3))
    model_args = WEBARENA_PRO_CHAT_MODEL_ARGS_DICT[args.agent_model]
    if not getattr(model_args, "video_support", False):
        parser.error("Use an explicit Gemini omni preset for this native adapter probe")
    actions = WebArenaProActionSetArgs(subsets=("custom",), audio_support=model_args.audio_support,
                                     video_support=model_args.video_support).make_action_set()
    action = f"{args.action}({args.url!r}, {args.start!r}, {args.end!r}"
    if args.action == "watch":
        action += f", mode='detail', include_audio={args.include_audio!r}"
    action += ")"
    record = {"probe_type": "explicit_action_integration", "autonomous_episode": False,
              "task_id": task["task_id"], "split": args.split, "sites": task["sites"],
              "intent": task["intent"], "action": action, "agent_model": args.agent_model,
              "requested_model": model_args.model_name}
    model = None
    try:
        exec(actions.to_python_code(action), {"page": None, "DEMO_MODE": False})
        obs = {}
        if args.action == "watch":
            env.WebArenaProBrowserEnv._inject_watch_results_into_axtree(None, obs)
            clip = obs["video_clips"][0]
        else:
            env.WebArenaProBrowserEnv._inject_listen_results_into_axtree(None, obs)
            clip = obs["media_clips"][0]
        record["observation"] = {k: v for k, v in clip.items() if not k.endswith("_b64") and k != "frames"}
        if clip.get("error"):
            raise RuntimeError(clip["error"])
        content = [{"type": "text", "text": (
            f"Task: {task['intent']}\nThe supplied excerpt covers source seconds "
            f"{clip['start']}--{clip['end']}. Clip playback time zero is source "
            f"{clip['start']}. Answer from the supplied evidence and state any "
            "limitations of this excerpt."
        )}]
        if args.action == "watch":
            content.append({"type": "input_video", "input_video": {
                "data": clip["video_b64"], "mime_type": "video/mp4", "fps": clip["fps"],
                "duration": clip["duration"], "audio_included": clip["audio_included"],
                "estimated_tokens": clip["estimated_input_tokens"],
            }})
            raw = base64.b64decode(clip["video_b64"])
        else:
            assert not clip["frames"]
            content.append({"type": "input_audio", "input_audio": {"data": clip["audio_b64"], "format": "wav"}})
            raw = base64.b64decode(clip["audio_b64"])
        record["attachment"] = {"mime_type": clip["mime_type"], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        model = model_args.make_model()
        response = model([{"role": "user", "content": content}])
        record.update(delivery_verified=True, response=response["content"],
                      provider=model.last_response_metadata)
    except Exception as error:
        record.update(delivery_verified=False, error_type=type(error).__name__, error=str(error))
        raise
    finally:
        clear_media_cache()
        if model is not None:
            model.native_client.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"task": task["task_id"], "delivery_verified": True,
                      "served_model": record["provider"]["served_model"]}))


if __name__ == "__main__":
    main()
