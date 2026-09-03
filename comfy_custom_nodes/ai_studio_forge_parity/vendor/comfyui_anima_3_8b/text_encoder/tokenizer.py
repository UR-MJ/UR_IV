from __future__ import annotations

import os

import torch
from transformers import AutoTokenizer

import folder_paths
from comfy.text_encoders.anima import T5XXLTokenizer


class Qwen35Tokenizer:
    max_length = 1024
    pad_token_id = 151643

    def __init__(self, embedding_directory=None, tokenizer_data=None):
        del embedding_directory, tokenizer_data
        self.tokenizer = self._load_tokenizer()
        self.embedding_size = 1024
        self.embedding_key = "qwen35_4b"

    @staticmethod
    def _load_tokenizer():
        package_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        candidates = [os.path.join(package_dir, "qwen35_tokenizer")]
        for text_encoder_dir in folder_paths.get_folder_paths("text_encoders"):
            candidates.append(os.path.join(text_encoder_dir, "qwen35_tokenizer"))

        for candidate in candidates:
            if os.path.isfile(os.path.join(candidate, "tokenizer.json")):
                return AutoTokenizer.from_pretrained(
                    candidate,
                    trust_remote_code=False,
                    local_files_only=True,
                )

        try:
            return AutoTokenizer.from_pretrained(
                "Qwen/Qwen3.5-4B",
                trust_remote_code=False,
                local_files_only=True,
            )
        except OSError as error:
            raise FileNotFoundError(
                "Qwen3.5 tokenizer files were not found locally. Put tokenizer.json "
                "and its companion files in this extension's qwen35_tokenizer folder "
                "or in models/text_encoders/qwen35_tokenizer."
            ) from error

    def tokenize_with_weights(self, text, return_word_ids=False, **kwargs):
        del kwargs
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)
        if not token_ids:
            token_ids = [self.pad_token_id]
        token_ids = token_ids[:self.max_length]
        if return_word_ids:
            return [[(token_id, 1.0, index) for index, token_id in enumerate(token_ids)]]
        return [[(token_id, 1.0) for token_id in token_ids]]

    def untokenize(self, token_weight_pair):
        token_ids = [
            item[0] for item in token_weight_pair if item[0] != self.pad_token_id
        ]
        return self.tokenizer.decode(token_ids)

    def state_dict(self):
        return {}

    def decode(self, token_ids, **kwargs):
        if isinstance(token_ids, torch.Tensor):
            token_ids = token_ids.tolist()
        return self.tokenizer.decode(token_ids, **kwargs)


class AnimaQwen35Tokenizer:
    def __init__(self, embedding_directory=None, tokenizer_data=None):
        tokenizer_data = tokenizer_data or {}
        self.qwen35_4b = Qwen35Tokenizer(
            embedding_directory=embedding_directory,
            tokenizer_data=tokenizer_data,
        )
        self.t5xxl = T5XXLTokenizer(
            embedding_directory=embedding_directory,
            tokenizer_data=tokenizer_data,
        )

    def tokenize_with_weights(self, text, return_word_ids=False, **kwargs):
        qwen_tokens = self.qwen35_4b.tokenize_with_weights(
            text, return_word_ids, **kwargs
        )
        return {
            "qwen35_4b": qwen_tokens,
            "t5xxl": self.t5xxl.tokenize_with_weights(
                text, return_word_ids, **kwargs
            ),
        }

    def untokenize(self, token_weight_pair):
        return self.t5xxl.untokenize(token_weight_pair)

    def state_dict(self):
        return {}

    def decode(self, token_ids, **kwargs):
        return self.qwen35_4b.decode(token_ids, **kwargs)

