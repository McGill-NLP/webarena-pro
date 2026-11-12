"""Attach requested audio and video beside GenericAgent's current observation.

Importing this module installs WebArenaProMainPrompt in AgentLab. Media stays
out of textual history; per-agent action-set capabilities control attachments.
"""

from copy import deepcopy

from agentlab.agents.generic_agent import generic_agent as _ga_mod
from agentlab.agents.generic_agent.generic_agent_prompt import MainPrompt
from agentlab.llm.llm_utils import HumanMessage

from webarena_pro_bgym.agentlab_compat import count_prompt_tokens


def configure_media(agent_args) -> None:
    """Set per-agent prompt/action capabilities without changing shared presets."""
    from webarena_pro_bgym.benchmark.benchmark import WebArenaProActionSetArgs
    from webarena_pro_bgym.llm_configs import validate_audio_support, validate_video_support

    flags = getattr(agent_args, "flags", None)
    if flags is None or not isinstance(
        flags.action.action_set, WebArenaProActionSetArgs
    ):
        return
    flags = agent_args.flags = deepcopy(flags)
    model_args = agent_args.chat_model_args
    flags.action.action_set.audio_support = validate_audio_support(model_args)
    flags.action.action_set.vision_support = bool(model_args.vision_support)
    flags.action.action_set.video_support = validate_video_support(model_args)
    context = (getattr(model_args, "max_input_tokens", None)
               or getattr(model_args, "max_total_tokens", None) or 131_072)
    # Leave at least half of the context for browser state/history and output.
    flags.action.action_set.watch_token_budget = max(1, min(131_072, int(context) // 2))
    if not model_args.vision_support:
        flags.obs.use_screenshot = False
        flags.obs.use_som = False


_ABSTRACT_EXAMPLE_HEADER = """
# Abstract Example

Here is an abstract version of the answer with description of the content of
each tag. Make sure you follow this structure, but replace the content with your
answer:"""

_CONCRETE_EXAMPLE_HEADER = """
# Concrete Example

Here is a concrete example of how to format your answer.
Make sure to follow the template with proper tags:"""


class WebArenaProMainPrompt(MainPrompt):
    @property
    def _prompt(self):
        prompt = HumanMessage(self.instructions.prompt)

        # 1. Observation text: AXTree (with [media ...] and [FRAMES_RESULT ...]
        #    synthetic nodes), focused element, error, etc.
        prompt.add_text(self.obs.prompt)

        if "mouse_down" in self.action_prompt.action_set.action_set:
            prompt.add_text(
                "\n## Canvas coordinates\n"
                "Coordinate actions use pixels in the current page screenshot: "
                "(0, 0) is its top-left corner. BrowserGym maps screenshot scaling "
                "to viewport CSS pixels automatically. Choose points "
                "inside the visible viewport; scrolling changes the visible coordinates. "
                "To draw a continuous pencil stroke, use mouse_down(x, y), one or more "
                "mouse_move(x, y) actions, then mouse_up(x, y). The button stays held "
                "between these actions. To draw a closed path, select the Path tool, "
                "mouse_click each vertex, then mouse_click the first vertex again.\n"
            )

        # 2. Frames extracted by the most recent extract_frames() call,
        #    placed inline with the observation so the model reads them as
        #    "what I currently see (extracted from the page's video)".
        vision_support = getattr(
            self.flags.action.action_set,
            "vision_support",
            self.flags.obs.use_screenshot,
        )
        audio_support = getattr(self.flags.action.action_set, "audio_support", False)
        video_support = getattr(self.flags.action.action_set, "video_support", False)
        if audio_support:
            prompt.add_text(
                "\n## Audio input\n"
                "You can hear audio directly. For listening tasks, use "
                "listen(url, start_seconds, end_seconds) with a media URL from "
                "the observation. It attaches the actual sound to your next "
                "observation, including source timestamps. Request a short "
                "interval (at most 60 seconds) and listen to later intervals "
                "if needed. Prefer listen() for speech, lyrics, music, and "
                "vocal judgments; transcribe() is an optional text fallback.\n"
            )
        if video_support:
            prompt.add_text(
                "\n## Video input\n"
                "Use watch(url) to survey a video through timestamped images. "
                "Use watch(url, start_seconds, end_seconds, mode='detail', "
                "include_audio=True) to inspect an actual video clip with sound. "
                "Omit audio when unnecessary or unsupported. For long videos, "
                "start with an overview, then inspect relevant intervals. "
                "For movement, event order, or speech synchronized with video, "
                "inspect detail clips before answering; an overview alone cannot establish those facts. "
                "You can request longer intervals or mode='full' if they fit the "
                "budget. Errors explain how to reduce the request. "
                "Sparse sampling can miss events; it does not prove complete coverage. "
                "listen() supplies audio only, never video frames.\n"
            )
        frames = (self.obs.obs or {}).get("extracted_frames") or []
        if frames and not vision_support:
            prompt.add_text("Video frames omitted: this model has no vision support.")
            frames = []
        if frames:
            prompt.add_text(
                f"\n## Extracted Video Frames ({len(frames)} frames)\n"
                "Frames returned by your most recent extract_frames() call, "
                "in time order. They correspond to the [FRAMES_RESULT ...] "
                "marker shown in the AXTree above.\n"
            )
            for f in frames:
                ts = f.get("timestamp", 0.0)
                b64 = f.get("image_b64") or ""
                if not b64:
                    continue
                prompt.add_text(f"\nFrame at t={ts:.1f}s:")
                prompt.add_image(
                    f"data:image/jpeg;base64,{b64}",
                    detail=self.flags.obs.openai_vision_detail,
                )

        # Keep each requested clip's source, interval, audio and video together.
        # Only the current observation is attached, never the history's media.
        for clip in (self.obs.obs or {}).get("media_clips") or []:
            prompt.add_text(
                f"\n## Requested media: {clip['url']}\n"
                f"Source interval: {clip['start']}--{clip['end']} seconds.\n"
            )
            if clip.get("error"):
                prompt.add_text(f"Media error: {clip['error']}")
                continue
            if audio_support:
                prompt.add_text(
                    f"Actual audio: {clip['duration']:g}s, {clip['format']}, "
                    f"{clip['sample_rate']} Hz, {clip['channels']} channels. "
                    "Use the sound itself for music, language and vocal judgments.\n"
                )
                prompt.add_content(
                    "input_audio", {"data": clip["audio_b64"], "format": clip["format"]}
                )
            else:
                prompt.add_text(
                    "Audio omitted: this model has no audio support. Use transcribe() for speech."
                )

        for clip in (self.obs.obs or {}).get("video_clips") or []:
            prompt.add_text(
                f"\n## Requested video: {clip['url']}\n"
                f"Source interval: {clip['start']}--{clip['end']} seconds.\n"
            )
            if clip.get("error"):
                prompt.add_text(f"Video error: {clip['error']}")
                continue
            if not video_support:
                prompt.add_text("Video omitted: this model has no video support.")
                continue
            prompt.add_text(
                f"Mode: {clip['mode']}; representation: {clip['representation']}; "
                f"audio included: {clip['audio_included']}; "
                f"source duration: {clip['source_duration']} seconds.\n"
                "Clip playback time zero corresponds to the source interval's start. "
                "Use source timestamps when reporting events.\n"
            )
            prompt.add_text(
                f"Sampling: {clip.get('sampling', 'See reported sampling rate')}. "
                f"Encoded duration: {clip.get('encoded_duration', 'not applicable')}; "
                f"encoded frame count: {clip.get('encoded_frame_count', 'not applicable')}.\n"
            )
            if clip["representation"] == "video":
                if clip["audio_included"] and not audio_support:
                    prompt.add_text("Video omitted: its audio requires audio support. Rewatch without audio.")
                    continue
                prompt.add_content("input_video", {
                    "data": clip["video_b64"], "mime_type": "video/mp4",
                    "fps": clip["fps"], "duration": clip["duration"],
                    "audio_included": clip["audio_included"],
                    "estimated_tokens": clip["estimated_input_tokens"],
                })
            elif clip["representation"] == "sampled_frames":
                if not vision_support:
                    prompt.add_text("Overview omitted: this model has no image support. Request mode='detail'.")
                    continue
                prompt.add_text("This is a sparse visual overview with no audio; inspect detail intervals next.\n")
                for frame in clip["frames"]:
                    prompt.add_text(f"Overview image at source t={frame['timestamp']:.3f}s:")
                    prompt.add_image(
                        f"data:image/jpeg;base64,{frame['image_b64']}",
                        detail=self.flags.obs.openai_vision_detail,
                    )

        # 3. Rest of the prompt body.
        prompt.add_text(
            f"""\
{self.history.prompt}\
{self.action_prompt.prompt}\
{self.hints.prompt}\
{self.be_cautious.prompt}\
{self.think.prompt}\
{self.plan.prompt}\
{self.memory.prompt}\
{self.criticise.prompt}\
"""
        )

        if self.flags.use_abstract_example:
            prompt.add_text(
                f"{_ABSTRACT_EXAMPLE_HEADER}\n"
                f"{self.think.abstract_ex}"
                f"{self.plan.abstract_ex}"
                f"{self.memory.abstract_ex}"
                f"{self.criticise.abstract_ex}"
                f"{self.action_prompt.abstract_ex}"
            )

        if self.flags.use_concrete_example:
            prompt.add_text(
                f"{_CONCRETE_EXAMPLE_HEADER}\n"
                f"{self.think.concrete_ex}"
                f"{self.plan.concrete_ex}"
                f"{self.memory.concrete_ex}"
                f"{self.criticise.concrete_ex}"
                f"{self.action_prompt.concrete_ex}"
            )

        # 4. Page screenshot at the end (AgentLab convention).
        return self.obs.add_screenshot(prompt)


_ga_mod.MainPrompt = WebArenaProMainPrompt
# GenericAgent's prompt fitter has no token-counter injection point. Adapt only
# that accounting hook, never tiktoken.Encoding or text sent to the provider.
_ga_mod.dp.count_tokens = count_prompt_tokens
