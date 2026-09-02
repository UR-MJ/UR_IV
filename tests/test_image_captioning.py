"""Fast unit tests for the local Batch/Caption inference boundary."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from core.image_captioning import (
    CAFORMER_PAD_INTERPOLATION,
    CAFORMER_RESIZE_INTERPOLATION,
    TORIIGATE_BF16_MODEL,
    TORIIGATE_FACTUAL_SYSTEM_PROMPT,
    CAFormerOptions,
    CAFormerTagger,
    ImageCaptioningEngine,
    ModelDiscoveryError,
    ModelValidationError,
    RuntimeDependencyError,
    TagPrediction,
    build_torii_prompt,
    discover_caformer_model,
    preprocess_caformer_image,
    normalize_torii_caption,
    select_toriigate_model,
)
from core.ollama_client import OllamaClient


def _logit(probability: float) -> float:
    return math.log(probability / (1.0 - probability))


def _make_model_dir(root: Path, rows: list[tuple[str, int, float]] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "model.onnx").write_bytes(b"fake onnx")
    (root / "preprocess.json").write_text("{}", encoding="utf-8")
    rows = rows or [("1girl", 0, 0.35)]
    lines = ["name,category,best_threshold"]
    lines.extend(f"{name},{category},{threshold}" for name, category, threshold in rows)
    (root / "selected_tags.csv").write_text("\n".join(lines), encoding="utf-8")
    return root


def _make_image(path: Path, size: tuple[int, int] = (32, 32), color="red") -> Path:
    Image.new("RGB", size, color).save(path)
    return path


class _FakeInput:
    name = "image"


class _FakeOutput:
    def __init__(self, name, shape):
        self.name = name
        self.shape = shape


class _FakeSession:
    def __init__(self, probabilities: list[float]):
        self._output = np.asarray(
            [[_logit(probability) for probability in probabilities]], dtype=np.float32
        )
        self.feeds: list[dict[str, np.ndarray]] = []
        self.output_requests = []

    def get_inputs(self):
        return [_FakeInput()]

    def get_outputs(self):
        return [_FakeOutput("logits", self._output.shape)]

    def run(self, outputs, feed):
        self.feeds.append(feed)
        self.output_requests.append(outputs)
        return [self._output]


class _NamedMultiOutputSession:
    def __init__(self, outputs):
        self.outputs = [(name, np.asarray(value, dtype=np.float32)) for name, value in outputs]
        self.output_requests = []

    def get_inputs(self):
        return [_FakeInput()]

    def get_outputs(self):
        return [_FakeOutput(name, value.shape) for name, value in self.outputs]

    def run(self, requested, _feed):
        self.output_requests.append(requested)
        if requested is None:
            return [value for _, value in self.outputs]
        by_name = dict(self.outputs)
        return [by_name[name] for name in requested]


class _FakeTagger:
    def __init__(self, tags: list[TagPrediction]):
        self.tags = tags
        self.calls = []

    def tag_image(self, image_path, options=None):
        self.calls.append((Path(image_path), options))
        return list(self.tags)


class _FakeVisionClient:
    def __init__(self, models=None, response="natural caption"):
        self.model = "initial-model"
        self.base_url = "http://initial"
        self.models = list(models or [])
        self.response = response
        self.caption_calls = []

    def list_models(self):
        return list(self.models)

    def caption_image(self, image_path, prompt="", timeout=180, system_prompt=None):
        path = Path(image_path)
        with Image.open(path) as image:
            size = image.size
        self.caption_calls.append(
            {
                "path": path,
                "path_existed": path.exists(),
                "size": size,
                "prompt": prompt,
                "timeout": timeout,
                "model": self.model,
                "base_url": self.base_url,
                "system_prompt": system_prompt,
            }
        )
        return self.response


class CAFormerOptionsTests(unittest.TestCase):
    def test_vue_camel_case_options_and_nested_thresholds_are_supported(self):
        options = CAFormerOptions.from_mapping(
            {
                "includeRating": True,
                "includeCharacters": False,
                "thresholdMode": "category",
                "categoryThresholds": {
                    "general": 0.25,
                    "character": 0.55,
                    "rating": 0.75,
                },
            }
        )
        self.assertTrue(options.include_rating)
        self.assertFalse(options.include_characters)
        self.assertEqual(options.threshold_mode, "category")
        self.assertEqual(options.threshold_for("character"), 0.55)

    def test_invalid_threshold_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "best.*category"):
            CAFormerOptions(threshold_mode="global")
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            CAFormerOptions(general_threshold=1.1)


class CAFormerDiscoveryTests(unittest.TestCase):
    def test_discovers_complete_newest_hf_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "hub"
            old = cache / "models--animetimm--caformer_s18.dbv4-full" / "snapshots" / "old"
            new = cache / "models--animetimm--caformer_s18.dbv4-full" / "snapshots" / "new"
            _make_model_dir(old)
            _make_model_dir(new)
            old.touch()
            new.touch()

            found = discover_caformer_model(cache_roots=[cache])

            self.assertIn(found.name, {"old", "new"})
            self.assertEqual(set(path.name for path in found.iterdir()), {
                "model.onnx", "preprocess.json", "selected_tags.csv"
            })

    def test_explicit_incomplete_folder_reports_each_required_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "model.onnx").write_bytes(b"x")
            with self.assertRaises(ModelValidationError) as caught:
                discover_caformer_model(folder)
        self.assertIn("selected_tags.csv", str(caught.exception))
        self.assertIn("preprocess.json", str(caught.exception))

    def test_missing_cache_reports_search_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ModelDiscoveryError) as caught:
                discover_caformer_model(cache_roots=[Path(temp_dir)])
        self.assertIn("model.onnx", str(caught.exception))
        self.assertIn("selected_tags.csv", str(caught.exception))


class CAFormerInferenceTests(unittest.TestCase):
    def test_preprocess_interpolation_matches_preprocess_json(self):
        self.assertEqual(CAFORMER_PAD_INTERPOLATION, Image.Resampling.BILINEAR)
        self.assertEqual(CAFORMER_RESIZE_INTERPOLATION, Image.Resampling.BICUBIC)

    def test_preprocess_is_nchw_float32_with_white_square_padding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "wide.png"
            Image.new("RGBA", (1024, 512), (255, 0, 0, 255)).save(image_path)
            tensor = preprocess_caformer_image(image_path)

        self.assertEqual(tensor.shape, (1, 3, 384, 384))
        self.assertEqual(tensor.dtype, np.float32)
        # Red subject remains at the center; white padding occupies top/bottom.
        self.assertGreater(float(tensor[0, 0, 192, 192]), 2.0)
        self.assertLess(float(tensor[0, 1, 192, 192]), -1.5)
        self.assertGreater(float(tensor[0, 1, 0, 0]), 2.0)

    def test_best_and_category_thresholds_split_filter_and_sort_tags(self):
        rows = [
            ("general_high", 0, 0.60),
            ("character_tag", 4, 0.90),
            ("explicit", 9, 0.50),
            ("general_low", 0, 0.20),
        ]
        session = _FakeSession([0.80, 0.80, 0.90, 0.30])
        factory_calls = []

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = _make_model_dir(root / "model", rows)
            image_path = _make_image(root / "image.png")

            def factory(model_path):
                factory_calls.append(model_path)
                return session

            tagger = CAFormerTagger(model_dir, session_factory=factory)
            best = tagger.tag_image(image_path)
            category = tagger.tag_image(
                image_path,
                {
                    "includeRating": True,
                    "thresholdMode": "category",
                    "generalThreshold": 0.7,
                    "characterThreshold": 0.43,
                    "ratingThreshold": 0.95,
                },
            )

        self.assertEqual([tag.name for tag in best], ["general_high", "general_low"])
        self.assertEqual([tag.category for tag in best], ["general", "general"])
        self.assertEqual([tag.name for tag in category], ["general_high", "character_tag"])
        self.assertEqual(len(factory_calls), 1, "session must be lazy and cached per tagger")
        self.assertEqual(len(session.feeds), 2)
        self.assertEqual(session.feeds[0]["image"].shape, (1, 3, 384, 384))

    def test_rating_and_character_inclusion_are_independent(self):
        rows = [("general", 0, 0.1), ("character", 4, 0.1), ("rating", 9, 0.1)]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = _make_model_dir(root / "model", rows)
            image_path = _make_image(root / "image.png")
            tagger = CAFormerTagger(
                model_dir,
                session_factory=lambda _: _FakeSession([0.9, 0.9, 0.9]),
            )
            tags = tagger.tag_image(
                image_path,
                {"includeRating": True, "includeCharacters": False},
            )
        self.assertEqual([tag.name for tag in tags], ["general", "rating"])

    def test_output_metadata_count_must_match_model_logits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = _make_model_dir(root / "model")
            image_path = _make_image(root / "image.png")
            tagger = CAFormerTagger(
                model_dir,
                session_factory=lambda _: _FakeSession([0.9, 0.8]),
            )
            with self.assertRaisesRegex(ModelValidationError, "mismatch"):
                tagger.tag_image(image_path)

    def test_named_logits_are_selected_instead_of_first_embedding_output(self):
        rows = [("first", 0, 0.5), ("second", 0, 0.5)]
        session = _NamedMultiOutputSession(
            [
                ("embedding", np.zeros((1, 512))),
                ("logits", np.asarray([[_logit(0.9), _logit(0.1)]])),
                ("prediction", np.asarray([[0.1, 0.9]])),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = _make_model_dir(root / "model", rows)
            image_path = _make_image(root / "image.png")
            tagger = CAFormerTagger(model_dir, session_factory=lambda _: session)

            tags = tagger.tag_image(image_path)

        self.assertEqual([tag.name for tag in tags], ["first"])
        self.assertEqual(session.output_requests, [["logits"]])

    def test_prediction_fallback_is_already_probability_and_not_sigmoided(self):
        rows = [("above", 0, 0.75), ("below", 0, 0.75)]
        session = _NamedMultiOutputSession(
            [
                ("embedding", np.zeros((1, 512))),
                ("prediction", np.asarray([[0.8, 0.2]])),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = _make_model_dir(root / "model", rows)
            image_path = _make_image(root / "image.png")
            tagger = CAFormerTagger(model_dir, session_factory=lambda _: session)

            tags = tagger.tag_image(image_path)

        self.assertEqual([tag.name for tag in tags], ["above"])
        self.assertAlmostEqual(tags[0].score, 0.8, places=5)
        self.assertEqual(session.output_requests, [None])

    def test_missing_onnxruntime_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = _make_model_dir(root / "model")
            image_path = _make_image(root / "image.png")
            tagger = CAFormerTagger(model_dir)
            with mock.patch(
                "core.image_captioning.importlib.import_module",
                side_effect=ModuleNotFoundError("onnxruntime"),
            ):
                with self.assertRaises(RuntimeDependencyError) as caught:
                    tagger.tag_image(image_path)
        self.assertIn("onnxruntime-gpu", str(caught.exception))
        self.assertIn("onnxruntime", str(caught.exception))


class ToriiModelSelectionTests(unittest.TestCase):
    def test_exact_bf16_model_is_preferred_case_insensitively(self):
        exact_from_ollama = "hf.co/DraconicDragon/ToriiGate-0.5-GGUF:bf16"
        chosen = select_toriigate_model(
            ["gemma3:4b", "hf.co/example/ToriiGate:q4", exact_from_ollama]
        )
        self.assertEqual(chosen, exact_from_ollama)

    def test_exact_default_is_returned_when_torii_is_not_installed(self):
        self.assertEqual(select_toriigate_model(["gemma3:4b"]), TORIIGATE_BF16_MODEL)


class ToriiPromptTests(unittest.TestCase):
    def test_short_prompt_wraps_user_instruction_and_grounding_in_official_sections(self):
        prompt = build_torii_prompt(
            tags=[
                TagPrediction("blue_hair", 0.9, "general"),
                TagPrediction("1girl", 0.8, "general"),
            ],
            user_instruction="Focus on clothing details.",
        )

        self.assertTrue(prompt.startswith("# Captioning format:\n"))
        self.assertIn("quite short without long purple prose", prompt)
        self.assertIn("Do not use JSON, Markdown headings, lists, or key-value fields.", prompt)
        self.assertIn("# Additional instructions:\nFocus on clothing details.", prompt)
        self.assertIn("# Booru tags for the image\n[blue_hair 1girl]", prompt)
        self.assertTrue(
            prompt.endswith(
                "# Characters on picture:\nAvoid guessing names for characters."
            )
        )

    def test_json_string_leaves_are_recovered_in_insertion_order(self):
        response = """```json
        {
          "general": "A blue-haired woman stands beside a window",
          "characters": {"first": "The woman wears a black coat."},
          "details": ["Rain runs down the glass", {"background": "City lights glow outside"}],
          "count": 1
        }
        ```"""

        caption = normalize_torii_caption(response)

        self.assertEqual(
            caption,
            "A blue-haired woman stands beside a window. "
            "The woman wears a black coat. Rain runs down the glass. "
            "City lights glow outside.",
        )

    def test_plain_text_code_fence_is_removed_without_rewriting_prose(self):
        self.assertEqual(
            normalize_torii_caption("```\nA compact natural caption.\n```"),
            "A compact natural caption.",
        )

    def test_subjective_mood_conclusion_is_removed_but_visible_facts_remain(self):
        response = (
            "Two purple squares float over a white background. "
            "Both squares cast narrow gray shadows. "
            "The background is white, enhancing the subject's prominence. "
            "The overall style is minimalist. "
            "The composition has a modern abstract feel."
        )

        self.assertEqual(
            normalize_torii_caption(response),
            "Two purple squares float over a white background. "
            "Both squares cast narrow gray shadows. The background is white.",
        )


class ImageCaptioningEngineTests(unittest.TestCase):
    def test_caformer_mode_exposes_text_and_grouped_metadata(self):
        tags = [
            TagPrediction("1girl", 0.99, "general"),
            TagPrediction("some_character", 0.80, "character"),
        ]
        fake_tagger = _FakeTagger(tags)
        engine = ImageCaptioningEngine(caformer_tagger=fake_tagger)

        result = engine.caption_result("unused.png", "caformer")

        self.assertEqual(result.text, "1girl, some_character")
        self.assertEqual(result.tags, tuple(tags))
        self.assertEqual(result.tags_by_category["character"][0].name, "some_character")

    def test_torii_uses_exact_local_model_and_resizes_to_one_megapixel(self):
        fake_client = _FakeVisionClient(
            models=["gemma3:4b", TORIIGATE_BF16_MODEL],
            response="A precise natural caption.",
        )
        engine = ImageCaptioningEngine(ollama_client=fake_client)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "large.jpg", (2000, 1000))
            result = engine.caption_result(image_path, "torii", timeout=77)

        call = fake_client.caption_calls[0]
        self.assertEqual(result.text, "A precise natural caption.")
        self.assertEqual(call["model"], TORIIGATE_BF16_MODEL)
        self.assertLessEqual(call["size"][0] * call["size"][1], 1_000_000)
        self.assertEqual(call["timeout"], 77)
        self.assertTrue(call["prompt"].startswith("# Captioning format:\n"))
        self.assertIn("Do not use JSON", call["prompt"])
        self.assertIn("Avoid guessing names for characters.", call["prompt"])
        self.assertEqual(call["system_prompt"], TORIIGATE_FACTUAL_SYSTEM_PROMPT)
        self.assertIn("only directly visible facts", call["system_prompt"])
        self.assertIn("Do not infer or embellish mood", call["system_prompt"])
        self.assertTrue(call["path_existed"])
        self.assertFalse(call["path"].exists(), "temporary resized input must be cleaned")
        self.assertEqual(fake_client.model, "initial-model", "injected client state is restored")

    def test_generic_ollama_accepts_model_and_url_per_call(self):
        fake_client = _FakeVisionClient(response="generic caption")
        engine = ImageCaptioningEngine(ollama_client=fake_client)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "small.png")
            text = engine.caption(
                image_path,
                "ollama",
                ollama_model="qwen2-vl:7b",
                ollama_base_url="http://127.0.0.1:22334/",
                prompt="Focus on clothing.",
            )

        call = fake_client.caption_calls[0]
        self.assertEqual(text, "generic caption")
        self.assertEqual(call["model"], "qwen2-vl:7b")
        self.assertEqual(call["base_url"], "http://127.0.0.1:22334")
        self.assertEqual(call["prompt"], "Focus on clothing.")
        self.assertIsNone(call["system_prompt"], "generic Ollama must retain its default system")

    def test_small_exif_rotated_image_is_transposed_via_temporary_rgb_file(self):
        fake_client = _FakeVisionClient(response="oriented caption")
        engine = ImageCaptioningEngine(ollama_client=fake_client)
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "oriented.jpg"
            exif = Image.Exif()
            exif[274] = 6  # Rotate 90 degrees clockwise for display.
            Image.new("RGB", (40, 20), "blue").save(source_path, exif=exif)

            text = engine.caption(source_path, "ollama")

            call = fake_client.caption_calls[0]
            self.assertEqual(text, "oriented caption")
            self.assertEqual(call["size"], (20, 40))
            self.assertNotEqual(call["path"], source_path)
            self.assertTrue(call["path_existed"])
            self.assertFalse(call["path"].exists())
            self.assertTrue(source_path.exists())

    def test_combined_mode_grounds_torii_and_uses_configurable_separator(self):
        tags = [
            TagPrediction("blue_hair", 0.95, "general"),
            TagPrediction("1girl", 0.90, "general"),
        ]
        fake_tagger = _FakeTagger(tags)
        fake_client = _FakeVisionClient(models=[TORIIGATE_BF16_MODEL], response="Caption text.")
        engine = ImageCaptioningEngine(
            caformer_tagger=fake_tagger,
            ollama_client=fake_client,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "image.png")
            result = engine.caption_result(
                image_path,
                "combined",
                separator="\n--CAPTION--\n",
            )

        self.assertEqual(
            result.text,
            "blue_hair, 1girl\n--CAPTION--\nCaption text.",
        )
        self.assertIn(
            "# Booru tags for the image\n[blue_hair 1girl]",
            fake_client.caption_calls[0]["prompt"],
        )
        self.assertIn("Avoid guessing names for characters.", fake_client.caption_calls[0]["prompt"])
        self.assertEqual(
            fake_client.caption_calls[0]["system_prompt"],
            TORIIGATE_FACTUAL_SYSTEM_PROMPT,
        )

    def test_torii_mode_recovers_json_response_to_natural_text(self):
        fake_client = _FakeVisionClient(
            models=[TORIIGATE_BF16_MODEL],
            response='{"general":"A silver camera rests on a desk",'
            '"background":"A purple wall fills the background"}',
        )
        engine = ImageCaptioningEngine(ollama_client=fake_client)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "image.png")
            text = engine.caption(image_path, "torii")

        self.assertEqual(
            text,
            "A silver camera rests on a desk. A purple wall fills the background.",
        )

    def test_unknown_mode_is_rejected_before_any_inference(self):
        engine = ImageCaptioningEngine()
        with self.assertRaisesRegex(ValueError, "ollama, caformer, torii, combined"):
            engine.caption_result("unused.png", "unknown")

    def test_empty_ollama_caption_is_an_explicit_inference_error(self):
        fake_client = _FakeVisionClient(response="   ")
        engine = ImageCaptioningEngine(ollama_client=fake_client)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "image.png")
            with self.assertRaisesRegex(RuntimeError, "empty caption"):
                engine.caption(image_path, "ollama")


class OllamaCaptionSystemOverrideTests(unittest.TestCase):
    @staticmethod
    def _response(text="caption"):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": text}
        return response

    def test_optional_system_override_is_sent_to_ollama(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "image.png")
            with mock.patch(
                "core.ollama_client.requests.post",
                return_value=self._response("Visible factual caption."),
            ) as post:
                text = OllamaClient(model="vision:test").caption_image(
                    str(image_path),
                    system_prompt="Custom factual system.",
                )

        self.assertEqual(text, "Visible factual caption.")
        self.assertEqual(post.call_args.kwargs["json"]["system"], "Custom factual system.")

    def test_omitting_override_preserves_existing_generic_system(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = _make_image(Path(temp_dir) / "image.png")
            with mock.patch(
                "core.ollama_client.requests.post",
                return_value=self._response(),
            ) as post:
                OllamaClient(model="vision:test").caption_image(str(image_path))

        default_system = post.call_args.kwargs["json"]["system"]
        self.assertIn("lighting and mood", default_system)
        self.assertNotEqual(default_system, TORIIGATE_FACTUAL_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
