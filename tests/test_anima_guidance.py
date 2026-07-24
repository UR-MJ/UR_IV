"""Anima Guidance Suite 인자 계약 회귀 테스트.

확장(sam-extra)의 세 스크립트는 args를 **위치(index)로만** 읽는다. 한 칸만 밀려도
조용히 엉뚱한 파라미터가 적용되고, 로그에도 안 남는다. 그래서 두 겹으로 막는다:

1) 리터럴 고정 — 아래 EXPECTED_* 가 core/anima_guidance 스펙과 일치하는지.
   (우리 쪽 스펙을 실수로 건드리면 여기서 깨짐)
2) 설치된 확장과 교차검증 — Forge 경로에 확장이 있으면 실제 `ui()`의 `return [...]`을
   파싱해 순서를 대조. 확장이 없으면 skip (다른 PC/CI에서도 테스트가 돌아야 하므로).
"""
import ast
import os
import unittest

from core.anima_guidance import (
    DETAIL_DAEMON_SPEC,
    PERTURBATION_SPEC,
    SCRIPT_DETAIL_DAEMON,
    SCRIPT_PERTURBATION,
    SCRIPT_SKIMMED_CFG,
    SKIMMED_SPEC,
    build_alwayson,
    build_args,
    default_settings,
    describe_active,
    is_script_active,
)

# 확장 소스 위치 (reference: Forge Neo 설치 경로)
_EXT_DIR = os.path.join('C:\\', 'sd-webui-forge-neo', 'extensions',
                        'forge_sam3_extension', 'scripts')

# ── 1) 리터럴 고정 ───────────────────────────────────────────────────────────
# 확장 varname 순서 그대로. 우리 키는 접두사만 다름(guid_/skim_/dd_).
EXPECTED_PERTURBATION = [
    'enabled', 'attn_method', 'scale', 'legacy_strength', 'block_indices',
    'slg_on', 'slg_scale', 'slg_blocks',
    'start_percent', 'end_percent', 'rescale', 'auto_decay',
    'apg_enabled', 'apg_eta', 'apg_norm', 'apg_momentum', 'apg_autooff',
    'adg_enabled', 'adg_start', 'adg_interval',
    'legacy_attn', 'seg_sigma',
    'cfg_mode', 'experimental_stack',
    'cwm_alpha_low', 'cwm_alpha_high', 'smc_lambda', 'smc_k',
    'dcw_enabled', 'dcw_lambda_low', 'dcw_lambda_high',
    'dave_enabled', 'dave_strength', 'dave_tau', 'dave_blocks',
    'cns_enabled', 'cns_strength', 'cns_gamma_power', 'cns_gamma_scale',
    'official_strength', 'head_indices', 'rescale_mode',
    'smc_enabled', 'cwm_enabled',
    'mod_enabled', 'mod_clip_model', 'mod_weight',
    'mod_start_layer', 'mod_end_layer',
    'mod_base_source', 'mod_base_prompt', 'mod_positive_prompt',
    'mod_negative_source', 'mod_negative_prompt',
    'mod_adapter_mode', 'mod_adapter_path',
]
EXPECTED_SKIMMED = [
    'enabled', 'skimming_cfg', 'full_skim_negative',
    'disable_flipping_filter', 'start_percent', 'end_percent', 'flip_at',
]
EXPECTED_DETAIL_DAEMON = [
    'enabled', 'preset', 'amount', 'start', 'end', 'bias', 'exponent',
    'start_offset', 'end_offset', 'fade', 'multiplier', 'smooth', 'cfg_couple',
]

_PREFIXES = {
    SCRIPT_PERTURBATION: ('guid_', PERTURBATION_SPEC, EXPECTED_PERTURBATION,
                          'anima_safe_pag.py'),
    SCRIPT_SKIMMED_CFG: ('skim_', SKIMMED_SPEC, EXPECTED_SKIMMED,
                         'anima_skimmed_cfg.py'),
    SCRIPT_DETAIL_DAEMON: ('dd_', DETAIL_DAEMON_SPEC, EXPECTED_DETAIL_DAEMON,
                           'anima_detail_daemon.py'),
}


class TestSpecOrder(unittest.TestCase):
    def test_spec_matches_expected_order(self):
        for title, (prefix, spec, expected, _f) in _PREFIXES.items():
            with self.subTest(script=title):
                got = [key[len(prefix):] for key, _k, _d, _e in spec]
                self.assertEqual(got, expected)

    def test_arg_counts(self):
        self.assertEqual(len(PERTURBATION_SPEC), 56)
        self.assertEqual(len(SKIMMED_SPEC), 7)
        self.assertEqual(len(DETAIL_DAEMON_SPEC), 13)

    def test_keys_are_globally_unique(self):
        keys = [k for spec in (PERTURBATION_SPEC, SKIMMED_SPEC, DETAIL_DAEMON_SPEC)
                for k, _kind, _d, _e in spec]
        self.assertEqual(len(keys), len(set(keys)))


class TestBuildArgs(unittest.TestCase):
    def test_defaults_roundtrip(self):
        # 빈 설정 → 전부 기본값, 길이는 스펙과 동일
        for title, (_p, spec, _e, _f) in _PREFIXES.items():
            with self.subTest(script=title):
                args = build_args(title, {})
                self.assertEqual(len(args), len(spec))
                self.assertEqual(args, [d for _k, _kind, d, _e2 in spec])

    def test_default_settings_produce_same_args(self):
        for title in _PREFIXES:
            with self.subTest(script=title):
                self.assertEqual(build_args(title, default_settings()),
                                 build_args(title, {}))

    def test_string_values_are_coerced(self):
        # Vue 위젯 프록시는 전부 문자열로 넘어온다
        args = build_args(SCRIPT_PERTURBATION, {
            'guid_enabled': 'true',
            'guid_scale': '6.5',
            'guid_adg_interval': '3',
            'guid_slg_on': 'false',
        })
        self.assertIs(args[0], True)
        self.assertEqual(args[2], 6.5)
        self.assertEqual(args[19], 3)
        self.assertIs(args[5], False)

    def test_out_of_range_is_clamped_not_dropped(self):
        args = build_args(SCRIPT_PERTURBATION, {'guid_scale': 999})
        self.assertEqual(args[2], 15.0)
        args = build_args(SCRIPT_PERTURBATION, {'guid_apg_eta': -50})
        self.assertEqual(args[13], -10.0)

    def test_garbage_falls_back_to_default(self):
        args = build_args(SCRIPT_DETAIL_DAEMON, {'dd_amount': 'abc'})
        self.assertEqual(args[2], 0.10)
        args = build_args(SCRIPT_DETAIL_DAEMON, {'dd_preset': 'nonsense'})
        self.assertEqual(args[1], 'Medium')

    def test_choice_is_case_insensitive_but_canonical(self):
        args = build_args(SCRIPT_PERTURBATION, {'guid_cfg_mode': 'smc + cwm'})
        self.assertEqual(args[22], 'SMC + CWM')
        args = build_args(SCRIPT_PERTURBATION, {'guid_attn_method': 'seg'})
        self.assertEqual(args[1], 'SEG')

    def test_unknown_script_raises(self):
        with self.assertRaises(KeyError):
            build_args('Nope', {})


class TestActivation(unittest.TestCase):
    def test_all_off_yields_empty_payload(self):
        self.assertEqual(build_alwayson({}), {})
        self.assertEqual(build_alwayson(default_settings()), {})

    def test_only_active_scripts_included(self):
        block = build_alwayson({'skim_enabled': True})
        self.assertEqual(list(block), [SCRIPT_SKIMMED_CFG])
        self.assertEqual(len(block[SCRIPT_SKIMMED_CFG]['args']), 7)

    def test_dave_alone_activates_perturbation_script(self):
        # DAVE는 PAG 본체 토글과 별개지만 같은 스크립트에 산다
        self.assertTrue(is_script_active(SCRIPT_PERTURBATION, {'guid_dave_enabled': True}))
        block = build_alwayson({'guid_dave_enabled': 'true'})
        self.assertIn(SCRIPT_PERTURBATION, block)
        self.assertIs(block[SCRIPT_PERTURBATION]['args'][31], True)

    def test_payload_shape_is_args_list(self):
        block = build_alwayson({'dd_enabled': True})
        self.assertEqual(set(block[SCRIPT_DETAIL_DAEMON]), {'args'})
        self.assertIsInstance(block[SCRIPT_DETAIL_DAEMON]['args'], list)

    def test_describe_active(self):
        text = describe_active({'guid_enabled': True, 'guid_attn_method': 'SEG',
                                'guid_scale': 5, 'skim_enabled': True})
        self.assertIn('SEG(5)', text)
        self.assertIn('Skimmed CFG', text)
        self.assertEqual(describe_active({}), '')


class TestApplyToPayload(unittest.TestCase):
    def test_merges_without_clobbering(self):
        from core.anima_guidance import apply_to_payload
        payload = {'alwayson_scripts': {'SAM3 Mask': {'args': [{}]}}}
        apply_to_payload(payload, {'dd_enabled': True})
        self.assertIn('SAM3 Mask', payload['alwayson_scripts'])
        self.assertIn(SCRIPT_DETAIL_DAEMON, payload['alwayson_scripts'])

    def test_existing_key_wins(self):
        from core.anima_guidance import apply_to_payload
        sentinel = {'args': ['keep-me']}
        payload = {'alwayson_scripts': {SCRIPT_DETAIL_DAEMON: sentinel}}
        apply_to_payload(payload, {'dd_enabled': True})
        self.assertEqual(payload['alwayson_scripts'][SCRIPT_DETAIL_DAEMON], sentinel)

    def test_creates_alwayson_key_when_missing(self):
        from core.anima_guidance import apply_to_payload
        payload = {}
        apply_to_payload(payload, {'skim_enabled': True})
        self.assertIn(SCRIPT_SKIMMED_CFG, payload['alwayson_scripts'])

    def test_noop_when_all_off(self):
        from core.anima_guidance import apply_to_payload
        payload = {}
        apply_to_payload(payload, {})
        self.assertEqual(payload, {})


# ── 2) 설치된 확장과 교차검증 ────────────────────────────────────────────────
def _parse_ui_return(source_path: str) -> list:
    """스크립트의 `def ui(self, is_img2img)` 안 마지막 `return [...]`에서 이름 순서 추출."""
    with open(source_path, 'r', encoding='utf-8') as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == 'ui'):
            continue
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, (ast.List, ast.Tuple)):
                names = [el.id for el in stmt.value.elts if isinstance(el, ast.Name)]
                if names:
                    return names
    return []


@unittest.skipUnless(os.path.isdir(_EXT_DIR),
                     f"sam-extra 확장 미설치 ({_EXT_DIR})")
class TestAgainstInstalledExtension(unittest.TestCase):
    """확장을 업데이트해 인자 순서가 바뀌면 여기서 먼저 깨진다."""

    def test_live_order_matches_spec(self):
        for title, (prefix, spec, _exp, filename) in _PREFIXES.items():
            path = os.path.join(_EXT_DIR, filename)
            if not os.path.exists(path):
                self.skipTest(f"{filename} 없음")
            with self.subTest(script=title):
                live = _parse_ui_return(path)
                ours = [key[len(prefix):] for key, _k, _d, _e in spec]
                self.assertEqual(
                    live, ours,
                    f"\n{filename}의 ui() 인자 순서가 core/anima_guidance.py 스펙과 다릅니다."
                    f"\n확장: {live}\n앱  : {ours}")

    def test_titles_match(self):
        import re
        expected_titles = {
            'anima_safe_pag.py': SCRIPT_PERTURBATION,
            'anima_skimmed_cfg.py': SCRIPT_SKIMMED_CFG,
            'anima_detail_daemon.py': SCRIPT_DETAIL_DAEMON,
        }
        for filename, title in expected_titles.items():
            path = os.path.join(_EXT_DIR, filename)
            if not os.path.exists(path):
                self.skipTest(f"{filename} 없음")
            with self.subTest(script=filename):
                with open(path, 'r', encoding='utf-8') as fh:
                    src = fh.read()
                match = re.search(r'def title\(self\):\s*\n\s*return\s+"([^"]+)"', src)
                self.assertIsNotNone(match, f"{filename}에서 title() 파싱 실패")
                self.assertEqual(match.group(1), title)


if __name__ == '__main__':
    unittest.main()
