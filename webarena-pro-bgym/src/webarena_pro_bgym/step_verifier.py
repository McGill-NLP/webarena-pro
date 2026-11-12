"""BrowserGym/AgentLab adapter for core verifier step records."""

from __future__ import annotations

import time

from webarena_pro_core.eval.protocol import StepRecord, extract_first_string_arg
from webarena_pro_core.eval.registry import (
    dispatch_step_record,
    registered_step_verifiers,
)


def scale_bbox_to_screenshot(
    bbox: tuple[float, float, float, float] | None,
    extras: dict | None,
    screenshot,
) -> tuple[float, float, float, float] | None:
    """Rescale DOM bbox coordinates to match a screenshot array.

    BrowserGym extracts DOM bboxes scaled by `deviceScaleFactor`, while saved
    screenshots may be at a different pixel scale. If the root element
    advertises the DOM canvas size, scale the target bbox to land on the same
    element in the screenshot.
    """
    if bbox is None or screenshot is None or not extras:
        return bbox
    root = extras.get("0")
    if not isinstance(root, dict):
        return bbox
    root_bbox = root.get("bbox")
    if not root_bbox or len(root_bbox) < 4 or root_bbox[2] <= 0 or root_bbox[3] <= 0:
        return bbox
    try:
        sh, sw = screenshot.shape[:2]
    except (AttributeError, ValueError):
        return bbox
    sx = sw / root_bbox[2]
    sy = sh / root_bbox[3]
    if abs(sx - 1.0) < 0.01 and abs(sy - 1.0) < 0.01:
        return bbox
    return (bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy)


def dispatch_step(step_info_pre, action: str, step_info_post) -> None:
    """Build a core verifier ``StepRecord`` from BrowserGym step info."""
    if not registered_step_verifiers():
        return

    obs_pre = getattr(step_info_pre, "obs", None) or {}
    obs_post = getattr(step_info_post, "obs", None) or {}

    screenshot_before = obs_pre.get("screenshot")
    if screenshot_before is not None:
        screenshot_before = screenshot_before.copy()
    screenshot_after = obs_post.get("screenshot")
    if screenshot_after is not None:
        screenshot_after = screenshot_after.copy()

    bid = extract_first_string_arg(action)
    bbox: tuple[float, float, float, float] | None = None
    extras = obs_pre.get("extra_element_properties") or {}
    if bid is not None and bid in extras:
        raw_bbox = extras[bid].get("bbox")
        if raw_bbox is not None:
            bbox = tuple(raw_bbox)  # type: ignore[assignment]
    else:
        bid = None

    bbox = scale_bbox_to_screenshot(bbox, extras, screenshot_before)

    agent_info = getattr(step_info_pre, "agent_info", None) or {}
    agent_think = agent_info.get("think") if isinstance(agent_info, dict) else None

    record: StepRecord = {
        "step": getattr(step_info_post, "step", None),
        "task_name": getattr(step_info_post, "task_name", None),
        "exp_dir": getattr(step_info_post, "exp_dir", None),
        "goal": obs_pre.get("goal"),
        "url": obs_pre.get("url"),
        "action": action,
        "bid": bid,
        "bbox": bbox,
        "screenshot_before": screenshot_before,
        "screenshot_after": screenshot_after,
        "agent_think": agent_think,
        "is_final_step": bool(getattr(step_info_post, "is_done", False)),
        # Online path: stamp with wall-clock now. Replay tools can construct
        # StepRecord directly and override this field to preserve trace time.
        "timestamp": time.time(),
    }
    dispatch_step_record(record, validate=False)
