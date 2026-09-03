from .loader import AnimaQwen35Loader
from .patches import install_pro52_model_detection
from .prompt import AnimaQwen35UnifiedPrompt
from .v2 import Anima38BV2Loader, Anima38BV2Prompt

install_pro52_model_detection()

NODE_CLASS_MAPPINGS = {
    "AnimaQwen35Loader": AnimaQwen35Loader,
    "AnimaQwen35UnifiedPrompt": AnimaQwen35UnifiedPrompt,
    "Anima38BV2Loader": Anima38BV2Loader,
    "Anima38BV2Prompt": Anima38BV2Prompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AnimaQwen35Loader": "Load Qwen3.5 4B (Anima)",
    "AnimaQwen35UnifiedPrompt": "Qwen3.5 Unified Prompt (Anima)",
    "Anima38BV2Loader": "anima.3-8B-v2",
    "Anima38BV2Prompt": "anima.3-8B-v2 Prompt",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
