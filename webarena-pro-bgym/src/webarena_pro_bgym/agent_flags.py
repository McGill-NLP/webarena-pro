from __future__ import annotations

from agentlab.agents.generic_agent.agent_configs import FLAGS_GPT_4o

# Side-effect import: patches MainPrompt so extract_frames() output is
# attached as image_url content blocks for VLM agents.
import webarena_pro_bgym.agent  # noqa: F401


FLAGS_VISION = FLAGS_GPT_4o.copy()
FLAGS_VISION.obs.use_think_history = True # To remember audio transcriptions
FLAGS_VISION.obs.use_screenshot = True
FLAGS_VISION.obs.use_som = True
