from __future__ import annotations

import logging

import comfy.model_detection

logger = logging.getLogger(__name__)


def install_pro52_model_detection():
    current = comfy.model_detection.detect_unet_config
    if getattr(current, "_anima_qwen35_pro52_patch", False):
        return

    def detect_unet_config(state_dict, key_prefix, metadata=None):
        config = current(state_dict, key_prefix, metadata)
        if config is None or config.get("image_model") != "anima":
            return config

        block_prefix = f"{key_prefix}blocks."
        block_indices = []
        for key in state_dict:
            if not key.startswith(block_prefix):
                continue
            index = key[len(block_prefix):].split(".", 1)[0]
            if index.isdigit():
                block_indices.append(int(index))
        if block_indices:
            block_count = max(block_indices) + 1
            if config.get("num_blocks") != block_count:
                config["num_blocks"] = block_count
                logger.info("Detected %d Anima DiT blocks", block_count)
        return config

    detect_unet_config._anima_qwen35_pro52_patch = True
    comfy.model_detection.detect_unet_config = detect_unet_config

