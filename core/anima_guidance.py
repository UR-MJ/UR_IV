# core/anima_guidance.py
"""Anima Guidance Suite — alwayson_scripts 인자 빌더. 순수 함수(테스트 가능), Qt 의존 없음.

sam-extra(forge_sam3_extension v0.20.0)의 세 스크립트는 `process_before_every_sampling`에서
`args[i]`를 **위치(index)로만** 읽는다(`_arg(i, default)`). 따라서 순서가 곧 계약이고,
한 칸만 밀려도 조용히 엉뚱한 값이 들어간다. SAM3 Mask처럼 dict를 받아주지 않는다.

그래서 이 모듈은 스펙을 선언적으로 두고 그 순서대로만 배열을 만든다.
스펙 순서 = 확장 `ui()`의 `return [...]` 순서이며, `tests/test_anima_guidance.py`가
개수·순서·기본값을 고정한다. 확장을 업데이트하면 그 테스트가 먼저 깨지게 하는 게 목적.

주의: 확장은 **인덱스 안정성을 위해 새 인자를 뒤에 append**한다(주석으로 명시됨).
      중간에 끼워넣지 말 것.
"""

# 확장 스크립트 title() 값 = alwayson_scripts 키
SCRIPT_PERTURBATION = "Anima Perturbation Guidance"   # scripts/anima_safe_pag.py
SCRIPT_SKIMMED_CFG = "Anima Skimmed CFG"              # scripts/anima_skimmed_cfg.py
SCRIPT_DETAIL_DAEMON = "Anima Detail Daemon"          # scripts/anima_detail_daemon.py


# ── 값 강제 변환 ────────────────────────────────────────────────────────────
# 설정값은 Vue 위젯 프록시에서 오므로 대부분 문자열('true' / '0.75')이다.
# 확장이 잘못된 타입을 만나면 조용히 폴백하거나 전체가 죽으므로 여기서 확실히 맞춘다.

_FALSEY = ('0', 'false', 'no', 'off', 'none', '')


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in _FALSEY


def _as_float(value, default: float, lo: float, hi: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (float('inf'), float('-inf')):  # NaN/Inf
        return default
    return max(lo, min(hi, out))


def _as_int(value, default: int, lo: int, hi: int) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, out))


def _as_choice(value, default: str, choices: tuple) -> str:
    """대소문자/공백 무시하고 매칭, 실패 시 default. 반환은 항상 확장이 아는 표기."""
    raw = str(value if value is not None else '').strip().lower()
    for choice in choices:
        if choice.lower() == raw:
            return choice
    return default


def _as_text(value, default: str) -> str:
    if value is None:
        return default
    return str(value)


# ── 스펙 ────────────────────────────────────────────────────────────────────
# (key, kind, default, extra) — extra: 숫자는 (lo, hi), choice는 선택지 튜플
_B, _F, _I, _C, _T = 'bool', 'float', 'int', 'choice', 'text'

# scripts/anima_safe_pag.py — ui() return 순서 (v0.20.0 기준 56개)
PERTURBATION_SPEC = (
    # 0-4 : PAG/SEG 본체
    ('guid_enabled',            _B, False,  None),
    ('guid_attn_method',        _C, 'PAG',  ('PAG', 'SEG', 'None')),
    ('guid_scale',              _F, 4.0,    (0.0, 15.0)),
    ('guid_legacy_strength',    _F, 0.75,   (0.0, 1.0)),
    ('guid_block_indices',      _T, '18',   None),
    # 5-7 : SLG
    ('guid_slg_on',             _B, False,  None),
    ('guid_slg_scale',          _F, 3.0,    (0.0, 15.0)),
    ('guid_slg_blocks',         _T, '18',   None),
    # 8-11 : 공통 스케줄
    ('guid_start_percent',      _F, 0.0,    (0.0, 1.0)),
    ('guid_end_percent',        _F, 0.7,    (0.0, 1.0)),
    ('guid_rescale',            _F, 0.20,   (0.0, 1.0)),
    ('guid_auto_decay',         _B, False,  None),   # 확장에서 visible=False (자리 유지용)
    # 12-16 : APG
    ('guid_apg_enabled',        _B, False,  None),
    ('guid_apg_eta',            _F, 0.0,    (-10.0, 10.0)),
    ('guid_apg_norm',           _F, 15.0,   (0.0, 50.0)),
    ('guid_apg_momentum',       _F, 0.0,    (-1.0, 1.0)),
    ('guid_apg_autooff',        _B, True,   None),
    # 17-19 : Adaptive Guidance
    ('guid_adg_enabled',        _B, False,  None),
    ('guid_adg_start',          _F, 0.5,    (0.0, 1.0)),
    ('guid_adg_interval',       _I, 0,      (0, 10)),
    # 20-21 : legacy attn / SEG sigma
    ('guid_legacy_attn',        _B, False,  None),
    ('guid_seg_sigma',          _F, 100.0,  (0.0, 10000.0)),
    # 22-23 : legacy CFG base 라디오
    ('guid_cfg_mode',           _C, 'Preserve incoming',
     ('Preserve incoming', 'APG', 'CWM', 'SMC', 'SMC + CWM')),
    ('guid_experimental_stack', _B, False,  None),
    # 24-27 : CWM / SMC 파라미터
    ('guid_cwm_alpha_low',      _F, 0.30,   (-1.0, 1.0)),
    ('guid_cwm_alpha_high',     _F, 0.15,   (-1.0, 1.0)),
    ('guid_smc_lambda',         _F, 6.0,    (0.0, 10.0)),
    ('guid_smc_k',              _F, 0.20,   (0.0, 1.0)),
    # 28-30 : DCW
    ('guid_dcw_enabled',        _B, False,  None),
    ('guid_dcw_lambda_low',     _F, 0.10,   (-0.5, 0.5)),
    ('guid_dcw_lambda_high',    _F, 0.02,   (-0.5, 0.5)),
    # 31-34 : DAVE
    ('guid_dave_enabled',       _B, False,  None),
    ('guid_dave_strength',      _F, 0.30,   (0.0, 1.0)),
    ('guid_dave_tau',           _F, 0.10,   (0.0, 1.0)),
    ('guid_dave_blocks',        _T, '8-18', None),
    # 35-38 : CNS
    ('guid_cns_enabled',        _B, False,  None),
    ('guid_cns_strength',       _F, 1.0,    (0.0, 1.0)),
    ('guid_cns_gamma_power',    _F, 0.5,    (0.05, 2.0)),
    ('guid_cns_gamma_scale',    _F, 3.0,    (0.25, 25.0)),
    # 39-41 : v0.13 append (구버전 인덱스 보존 목적)
    ('guid_official_strength',  _F, 0.75,   (0.0, 1.0)),
    ('guid_head_indices',       _T, '',     None),
    ('guid_rescale_mode',       _C, 'full', ('full', 'partial')),
    # 42-43 : SMC/CWM 독립 토글 append
    ('guid_smc_enabled',        _B, False,  None),
    ('guid_cwm_enabled',        _B, False,  None),
    # 44-55 : v0.20 Modulation Guidance append
    ('guid_mod_enabled',        _B, False,  None),
    ('guid_mod_clip_model',     _T, '',     None),
    ('guid_mod_weight',         _F, 3.0,    (-20.0, 20.0)),
    ('guid_mod_start_layer',    _I, 0,      (0, 63)),
    ('guid_mod_end_layer',      _I, -1,     (-1, 63)),
    ('guid_mod_base_source',    _C, 'Main positive', ('Main positive', 'Custom')),
    ('guid_mod_base_prompt',    _T, '',     None),
    ('guid_mod_positive_prompt', _T, 'masterpiece, best quality, highres', None),
    ('guid_mod_negative_source', _C, 'Main negative', ('Main negative', 'Custom')),
    ('guid_mod_negative_prompt', _T, 'worst quality, low quality', None),
    ('guid_mod_adapter_mode',   _C, 'Auto-download official',
     ('Auto-download official', 'Local file')),
    ('guid_mod_adapter_path',   _T, '',     None),
)

# scripts/anima_skimmed_cfg.py — ui() return 순서 (7개)
SKIMMED_SPEC = (
    ('skim_enabled',                 _B, False, None),
    ('skim_skimming_cfg',            _F, 7.0,   (-1.0, 10.0)),
    ('skim_full_skim_negative',      _B, False, None),
    ('skim_disable_flipping_filter', _B, False, None),
    ('skim_start_percent',           _F, 0.0,   (0.0, 1.0)),
    ('skim_end_percent',             _F, 1.0,   (0.0, 1.0)),
    ('skim_flip_at',                 _F, 0.0,   (0.0, 1.0)),
)

# scripts/anima_detail_daemon.py — ui() return 순서 (13개)
DETAIL_DAEMON_SPEC = (
    ('dd_enabled',      _B, False,    None),
    ('dd_preset',       _C, 'Medium', ('Custom', 'Subtle', 'Medium', 'Strong')),
    ('dd_amount',       _F, 0.10,     (-1.0, 1.0)),
    ('dd_start',        _F, 0.2,      (0.0, 1.0)),
    ('dd_end',          _F, 0.8,      (0.0, 1.0)),
    ('dd_bias',         _F, 0.5,      (0.0, 1.0)),
    ('dd_exponent',     _F, 1.0,      (0.0, 10.0)),
    ('dd_start_offset', _F, 0.0,      (-1.0, 1.0)),
    ('dd_end_offset',   _F, 0.0,      (-1.0, 1.0)),
    ('dd_fade',         _F, 0.0,      (0.0, 1.0)),
    ('dd_multiplier',   _F, 1.0,      (0.0, 2.0)),
    ('dd_smooth',       _B, True,     None),
    ('dd_cfg_couple',   _B, True,     None),
)

SPECS = {
    SCRIPT_PERTURBATION: PERTURBATION_SPEC,
    SCRIPT_SKIMMED_CFG: SKIMMED_SPEC,
    SCRIPT_DETAIL_DAEMON: DETAIL_DAEMON_SPEC,
}

# 스크립트를 페이로드에 넣을지 결정하는 마스터 토글.
# 전부 꺼져 있으면 alwayson_scripts에 아예 넣지 않는다 — 확장을 건드리지 않아야
# "전부 끄면 Forge 결과 그대로"가 보장되고, 불필요한 hook 설치도 피한다.
_ACTIVATION_KEYS = {
    SCRIPT_PERTURBATION: (
        'guid_enabled', 'guid_slg_on', 'guid_apg_enabled', 'guid_adg_enabled',
        'guid_smc_enabled', 'guid_cwm_enabled', 'guid_dcw_enabled',
        'guid_dave_enabled', 'guid_cns_enabled', 'guid_mod_enabled',
        'guid_experimental_stack',
    ),
    SCRIPT_SKIMMED_CFG: ('skim_enabled',),
    SCRIPT_DETAIL_DAEMON: ('dd_enabled',),
}


def _coerce(kind, value, default, extra):
    if kind == _B:
        return _as_bool(value, default)
    if kind == _F:
        return _as_float(value, default, extra[0], extra[1])
    if kind == _I:
        return _as_int(value, default, extra[0], extra[1])
    if kind == _C:
        return _as_choice(value, default, extra)
    return _as_text(value, default)


def default_settings() -> dict:
    """모든 키의 기본값 dict — UI 초기화/리셋용."""
    out = {}
    for spec in SPECS.values():
        for key, kind, default, _extra in spec:
            out[key] = default
    return out


def build_args(script_title: str, settings=None) -> list:
    """스크립트 하나의 위치 인자 배열 생성. 스펙에 없는 키는 무시된다."""
    spec = SPECS.get(script_title)
    if spec is None:
        raise KeyError(f"알 수 없는 Anima 스크립트: {script_title!r}")
    settings = settings if isinstance(settings, dict) else {}
    return [_coerce(kind, settings.get(key), default, extra)
            for key, kind, default, extra in spec]


def is_script_active(script_title: str, settings=None) -> bool:
    """마스터 토글 중 하나라도 켜져 있는지."""
    settings = settings if isinstance(settings, dict) else {}
    return any(_as_bool(settings.get(key), False)
               for key in _ACTIVATION_KEYS.get(script_title, ()))


def build_alwayson(settings=None) -> dict:
    """켜져 있는 Anima 스크립트만 골라 alwayson_scripts 조각을 만든다.

    반환 예: {"Anima Skimmed CFG": {"args": [True, 7.0, False, False, 0.0, 1.0, 0.0]}}
    전부 꺼져 있으면 빈 dict.
    """
    settings = settings if isinstance(settings, dict) else {}
    out = {}
    for title in SPECS:
        if is_script_active(title, settings):
            out[title] = {"args": build_args(title, settings)}
    return out


def apply_to_payload(payload: dict, settings=None) -> dict:
    """payload['alwayson_scripts']에 Anima 스크립트를 병합하고 payload를 반환.

    이미 같은 키가 있으면 덮어쓰지 않는다(호출자가 명시 지정한 값 우선).
    """
    if not isinstance(payload, dict):
        return payload
    block = build_alwayson(settings)
    if not block:
        return payload
    scripts = payload.setdefault('alwayson_scripts', {})
    if not isinstance(scripts, dict):
        return payload
    for title, args in block.items():
        scripts.setdefault(title, args)
    return payload


def describe_active(settings=None) -> str:
    """로그/토스트용 짧은 요약. 예: 'PAG(4.0) + Skimmed CFG + Detail Daemon(Medium)'"""
    settings = settings if isinstance(settings, dict) else {}
    parts = []
    if _as_bool(settings.get('guid_enabled'), False):
        method = _as_choice(settings.get('guid_attn_method'), 'PAG', ('PAG', 'SEG', 'None'))
        if method != 'None':
            parts.append(f"{method}({_as_float(settings.get('guid_scale'), 4.0, 0.0, 15.0):g})")
    for key, label in (
        ('guid_slg_on', 'SLG'), ('guid_apg_enabled', 'APG'),
        ('guid_adg_enabled', 'Adaptive'), ('guid_smc_enabled', 'SMC'),
        ('guid_cwm_enabled', 'CWM'), ('guid_dcw_enabled', 'DCW'),
        ('guid_dave_enabled', 'DAVE'), ('guid_cns_enabled', 'CNS'),
        ('guid_mod_enabled', 'Modulation'), ('skim_enabled', 'Skimmed CFG'),
    ):
        if _as_bool(settings.get(key), False):
            parts.append(label)
    if _as_bool(settings.get('dd_enabled'), False):
        preset = _as_choice(settings.get('dd_preset'), 'Medium',
                            ('Custom', 'Subtle', 'Medium', 'Strong'))
        parts.append(f"Detail Daemon({preset})")
    return ' + '.join(parts)
