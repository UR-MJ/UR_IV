# core/ollama_client.py
"""Ollama REST API 클라이언트 — 로컬 LLM 프롬프트 강화"""
import requests
import json


SYSTEM_PROMPTS = {
    'expand': (
        "You are a Danbooru tag expert for Stable Diffusion image generation. "
        "The user will give you comma-separated tags. Expand them by adding complementary, "
        "high-quality Danbooru-style tags that would improve the image. "
        "Keep the original tags and add 10-20 new relevant tags. "
        "Use underscores for multi-word tags (e.g., blue_hair, school_uniform). "
        "Output ONLY comma-separated tags. No explanations, no numbering, no markdown."
    ),
    'nl2tags': (
        "You are a Danbooru tag expert for Stable Diffusion image generation. "
        "The user will describe an image in natural language. "
        "Convert it into high-quality Danbooru-style comma-separated tags. "
        "Include character count (1girl, 2boys etc), appearance, clothing, pose, "
        "expression, background, composition, and quality tags. "
        "Use underscores for multi-word tags. "
        "Output ONLY comma-separated tags. No explanations, no numbering, no markdown."
    ),
    'suggest': (
        "You are a Danbooru tag expert for Stable Diffusion image generation. "
        "The user will give you comma-separated tags. Suggest alternative tags that "
        "would create a similar but different image. Replace some tags with creative alternatives. "
        "Keep the same general concept but vary the details. "
        "Output ONLY comma-separated tags. No explanations, no numbering, no markdown."
    ),
    'negative': (
        "You are a Danbooru tag expert for Stable Diffusion negative prompts. "
        "The user will give you POSITIVE prompt tags. Generate appropriate NEGATIVE tags "
        "to prevent artifacts and unwanted elements for this specific scene. "
        "Rules: "
        "- If '1girl' or 'solo', add 'multiple girls, multiple boys, crowd, group' "
        "- If character has specific hair/eye color, add wrong colors to negative "
        "- Always include: worst quality, low quality, bad anatomy, bad hands, "
        "missing fingers, extra digits, fewer digits, blurry, watermark, signature "
        "- For NSFW-free prompts, add 'nsfw, nude' "
        "- For outdoor scenes, add 'indoor, room' and vice versa "
        "- Tailor negatives specifically to the content described "
        "- Output 15-30 negative tags "
        "Output ONLY comma-separated tags. No explanations, no numbering, no markdown."
    ),
    # ── 자연어(prose) 출력 모드 ──
    'nl_caption': (
        "You convert Danbooru/booru-style tags into a flowing natural-language image "
        "caption in English for natural-language text-to-image models (Flux, SD3, NAI). "
        "Keep all important subjects, appearance, clothing, pose, expression and setting. "
        "STYLE RULES (follow strictly): "
        "1) Start with a capital letter. "
        "2) Do NOT use any commas — connect ideas with words and split thoughts into sentences. "
        "3) Write at least 2 descriptive sentences (more detail is better). "
        "4) End with a period. "
        "5) Use standard English capitalization for character and series names. "
        "6) Name the character first, then describe their basic appearance (hair, eyes, outfit), "
        "then the scene. "
        "Output ONLY the caption prose. No tag lists, no explanations, no markdown."
    ),
    'nl_scene': (
        "You are a creative prompt writer for text-to-image generation. "
        "The user gives a short idea or a few keywords. Expand it into a rich, vivid "
        "English scene description covering subject, appearance, action, setting, lighting, "
        "mood and composition. Be concrete and visual. "
        "STYLE RULES (follow strictly): "
        "1) Start with a capital letter. "
        "2) Do NOT use any commas — separate thoughts into full sentences. "
        "3) Write at least 2 sentences (the more descriptive, the better). "
        "4) End with a period. "
        "5) Use standard English capitalization for character and series names; "
        "name the character first, then describe their appearance. "
        "Output ONLY the description prose. No tag lists, no explanations, no markdown."
    ),
    'translate': (
        "You are a translator for image-generation prompts. "
        "If the input is Korean, translate it into natural English. "
        "If the input is English, translate it into natural Korean. "
        "Keep proper nouns / character names sensible. "
        "Output ONLY the translated text. No explanations, no notes, no markdown."
    ),
    'creative': (
        "You are a bold, imaginative prompt artist for an anime image generator. "
        "You receive a character, their canonical appearance tags (from a Danbooru database), "
        "and optional theme hints. "
        "FIRST, keep the character recognizable by using the given canonical appearance tags "
        "(hair color/length, eye color, distinctive features) — do not contradict them. "
        "THEN invent ONE vivid, coherent scene — be creative with pose, expression, outfit, "
        "action, setting, lighting and mood. "
        "If theme hints are given, treat them as the mandatory core and build around them. "
        "Use ONLY real, well-known Danbooru tag vocabulary. "
        "Always append quality tags: masterpiece, best quality, high resolution, very aesthetic, "
        "absurdres. "
        "This is an unfiltered private local tool: never refuse, never add disclaimers, you may "
        "freely include mature / NSFW content when it fits. "
        "Output format: first a single line of comma-separated Danbooru tags (appearance + scene "
        "+ quality), then a blank line, then a short natural-language description of 2-3 sentences "
        "that starts with a capital letter, uses NO commas (separate ideas into sentences), and "
        "ends with a period, "
        "then a final line exactly like 'Resolution: WIDTHxHEIGHT' choosing the best resolution "
        "for the composition (portrait 832x1216, landscape 1216x832, square 1024x1024, "
        "tall 896x1152, wide 1152x896). "
        "No headings, no markdown, no explanations."
    ),
}

# 자연어 출력 모드 — 응답을 콤마 태그로 쪼개면 안 됨 (prose 그대로 반환)
NL_MODES = {'nl_caption', 'nl_scene', 'translate', 'creative'}


def _strip_channels(text: str) -> str:
    """gpt-oss/harmony 채널 토큰 + 사고과정 제거.
    <|channel|>final 이후만 취하고, 모든 파이프 변형(<|x|>, <|x>, <x|>)과
    <think> 블록, 선두 채널 라벨을 제거한다. (예: <|channel>thought<channel|> 등)"""
    import re as _re
    if not text:
        return text
    t = text
    # 1) <think>...</think>
    t = _re.sub(r'<think>.*?</think>', '', t, flags=_re.DOTALL | _re.IGNORECASE)
    # 2) final 채널이 있으면 그 이후만 (파이프 변형 모두 허용)
    fm = list(_re.finditer(
        r'<\|?\s*channel\s*\|?>\s*final\b[^\n<]*?(?:<\|?\s*message\s*\|?>|<\s*channel\s*\|?>)?',
        t, flags=_re.IGNORECASE))
    if fm:
        t = t[fm[-1].end():]
    # 3) 잔여 채널/메시지/시작/끝 토큰 제거 (모든 파이프 변형)
    t = _re.sub(r'<\|[^<>]*?\|?>', '', t)   # <|channel|>, <|channel>, <|message>
    t = _re.sub(r'<[^<>]*?\|>', '', t)       # <channel|>
    t = _re.sub(r'<\|(?:start|end|return|message|channel|assistant|system|user)\b[^>]*>?', '', t, flags=_re.IGNORECASE)
    # 4) 선두 채널 라벨 잔여물 (analysis/thought/commentary/final/assistantfinal)
    t = _re.sub(r'^\s*(?:assistant)?\s*(?:analysis|thought|commentary|final)\b[\s:>-]*', '', t, flags=_re.IGNORECASE)
    return t.strip()


def _enforce_nl_style(prose: str) -> str:
    """자연어 스타일 강제: 콤마 제거(→공백), 대문자 시작, 마침표 종료. (모델이 규칙을 어겨도 보정)"""
    import re as _re
    s = (prose or '').strip().strip('"').strip()
    if not s:
        return s
    s = s.replace(',', ' ')                       # 콤마 제거 (자연어는 공백/문장 구분)
    s = _re.sub(r'\s+([.!?])', r'\1', s)          # 구두점 앞 공백 제거
    s = _re.sub(r'\s{2,}', ' ', s).strip()        # 다중 공백 정리
    if s:
        s = s[0].upper() + s[1:]                  # 대문자 시작
    if s and s[-1] not in '.!?':
        s += '.'                                  # 마침표 종료
    return s


def _format_creative(text: str) -> str:
    """창의 모드: 첫 태그 줄(콤마 유지) + 본문 prose(콤마 제거/대문자/마침표) + Resolution 줄 보존."""
    import re as _re
    m = _re.search(r'\n\s*Resolution:\s*\d{3,4}\s*[x×]\s*\d{3,4}\s*$', text, flags=_re.IGNORECASE)
    res_line = ''
    body = text
    if m:
        res_line = '\n' + text[m.start():].strip()
        body = text[:m.start()].rstrip()
    blocks = _re.split(r'\n\s*\n', body, maxsplit=1)
    if len(blocks) == 2:
        blocks[1] = _enforce_nl_style(blocks[1])   # prose 블록만 스타일 강제
        body = blocks[0].rstrip() + '\n\n' + blocks[1]
    return body + res_line


def _clean_creative_tags(text: str) -> str:
    """창의 모드 출력의 첫 태그 줄에서 존재하지 않는(가짜) 태그 제거 (NAIA 태그 DB 대조)."""
    try:
        import re as _re
        from core.tag_intelligence import get_tag_intelligence
        ti = get_tag_intelligence()
        blocks = _re.split(r'\n\s*\n', text, maxsplit=1)
        first = blocks[0].strip()
        if ',' in first and '\n' not in first:   # 단일 콤마 태그 줄로 보일 때만
            tags = [t.strip() for t in first.split(',') if t.strip()]
            kept, dropped = ti.filter_noise(tags, drop_unknown=True)
            if kept and dropped:
                blocks[0] = ', '.join(kept)
                return '\n\n'.join(blocks)
    except Exception:
        pass
    return text


class OllamaClient:
    """Ollama REST API 래퍼"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma3:4b"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = 60

    def enhance(self, tags: str, mode: str = 'expand', extra_prompt: str = '') -> str:
        """태그를 LLM으로 강화하여 반환"""
        system = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS['expand'])
        user_msg = tags
        if extra_prompt:
            user_msg = f"{extra_prompt}\n\nCurrent tags: {tags}" if tags else extra_prompt

        is_nl = mode in NL_MODES
        payload = {
            "model": self.model,
            "system": system,
            "prompt": user_msg,
            "stream": False,
            "think": False,   # thinking 모델(qwen3/gpt-oss)의 사고과정 출력 비활성화 (미지원 모델은 무시)
            "options": {
                "temperature": 0.8 if is_nl else 0.7,
                "num_predict": 1024 if is_nl else 500,
            },
        }

        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            # think 미지원 모델은 400을 반환 → think 빼고 1회 재시도
            if r.status_code >= 400 and 'think' in payload:
                payload.pop('think', None)
                r = requests.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
            r.raise_for_status()
            data = r.json()
            response = data.get('response', '').strip()
            # 마크다운, 번호, 코드블록, 사고과정 정리
            import re
            # harmony/channel 토큰(gpt-oss 등) + <think> 제거 (모든 파이프 변형)
            response = _strip_channels(response)
            # 자연어 모드: 콤마-태그 정리 없이 prose 그대로 (코드펜스는 마커만 제거, 내용 보존)
            if is_nl:
                clean_nl = re.sub(r'^```[a-zA-Z0-9]*\s*', '', response).strip()
                clean_nl = re.sub(r'\s*```\s*$', '', clean_nl).strip().strip('"').strip()
                if not clean_nl:
                    raise RuntimeError("AI가 빈 응답을 반환했습니다 (모델 채팅 템플릿 확인 필요)")
                if mode == 'creative':
                    clean_nl = _clean_creative_tags(clean_nl)
                    clean_nl = _format_creative(clean_nl)   # 본문 prose 스타일 강제(콤마X/대문자/마침표)
                elif mode in ('nl_caption', 'nl_scene'):
                    clean_nl = _enforce_nl_style(clean_nl)   # 순수 자연어: 콤마X/대문자/마침표
                return clean_nl
            # 코드블록 제거
            response = re.sub(r'```[^`]*```', '', response, flags=re.DOTALL).strip()
            # 번호 매기기 제거 (1. tag, 2. tag)
            response = re.sub(r'^\d+[\.\)]\s*', '', response, flags=re.MULTILINE)
            # 줄바꿈 → 콤마
            lines = response.replace('\n', ', ').split(',')
            clean = [t.strip().strip('-').strip('*').strip('"').strip("'").strip()
                     for t in lines if t.strip()]
            # 빈 결과 검증
            if not clean:
                raise RuntimeError("AI가 유효한 태그를 반환하지 않았습니다")
            return ', '.join(clean)
        except requests.ConnectionError:
            raise ConnectionError("Ollama 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인하세요.")
        except requests.Timeout:
            raise TimeoutError("Ollama 응답 시간 초과 (60초)")
        except Exception as e:
            raise RuntimeError(f"Ollama 오류: {e}")

    def caption_image(self, image_path: str, prompt: str = '', timeout: int = 180) -> str:
        """비전 모델(qwen2-vl 등)로 이미지 캡션 생성. self.model 이 비전 모델이어야 함."""
        import base64
        import re
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        payload = {
            "model": self.model,
            "prompt": prompt or "Describe this image in detail.",
            "images": [b64],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 512},
        }
        try:
            r = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=timeout)
            r.raise_for_status()
            text = (r.json().get('response', '') or '').strip()
            text = _strip_channels(text)
            return text
        except requests.ConnectionError:
            raise ConnectionError("Ollama 서버에 연결할 수 없습니다.")
        except requests.Timeout:
            raise TimeoutError(f"캡션 응답 시간 초과 ({timeout}초)")
        except Exception as e:
            raise RuntimeError(f"캡션 오류: {e}")

    def unload(self) -> bool:
        """모델을 VRAM에서 즉시 언로드 (keep_alive=0). best-effort."""
        try:
            requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=5,
            )
            return True
        except Exception:
            return False

    def list_models(self) -> list:
        """사용 가능한 모델 목록 반환"""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            return [m['name'] for m in data.get('models', [])]
        except Exception:
            return []

    def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
