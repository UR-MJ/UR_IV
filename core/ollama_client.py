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
        "You convert Danbooru/booru-style comma-separated tags into ONE flowing "
        "natural-language image caption in English. Describe the scene as a vivid "
        "prompt sentence (or two) suitable for natural-language text-to-image models "
        "(Flux, SD3, NAI). Keep all important subjects, appearance, clothing, pose, "
        "expression and setting. "
        "Output ONLY the caption prose. No tag lists, no explanations, no markdown."
    ),
    'nl_scene': (
        "You are a creative prompt writer for text-to-image generation. "
        "The user gives a short idea or a few keywords. Expand it into a rich, vivid "
        "English scene description (2-5 sentences) covering subject, appearance, action, "
        "setting, lighting, mood and composition. Be concrete and visual. "
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
        "+ quality), then a blank line, then a short natural-language description (2-3 sentences). "
        "No headings, no markdown, no explanations."
    ),
}

# 자연어 출력 모드 — 응답을 콤마 태그로 쪼개면 안 됨 (prose 그대로 반환)
NL_MODES = {'nl_caption', 'nl_scene', 'translate', 'creative'}


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
            r.raise_for_status()
            data = r.json()
            response = data.get('response', '').strip()
            # 마크다운, 번호, 코드블록, 사고과정(<think>) 정리
            import re
            # harmony/channel 형식 (gpt-oss 등): <|channel|>analysis<|message|>…<|channel|>final<|message|>답
            _hm = re.search(r'<\|channel\|>\s*final\s*<\|message\|>(.*)',
                            response, flags=re.DOTALL | re.IGNORECASE)
            if _hm:
                response = _hm.group(1)
            response = re.sub(r'<\|[^|>]*\|>', '', response).strip()   # 남은 <|...|> 마커 제거
            # <think>...</think> 블록 제거 (qwen3 등 thinking 모드)
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
            # 자연어 모드: 콤마-태그 정리 없이 prose 그대로 (코드펜스는 마커만 제거, 내용 보존)
            if is_nl:
                clean_nl = re.sub(r'^```[a-zA-Z0-9]*\s*', '', response).strip()
                clean_nl = re.sub(r'\s*```\s*$', '', clean_nl).strip().strip('"').strip()
                if not clean_nl:
                    raise RuntimeError("AI가 빈 응답을 반환했습니다 (모델 채팅 템플릿 확인 필요)")
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
