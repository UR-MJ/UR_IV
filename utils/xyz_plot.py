# utils/xyz_plot.py
"""
XYZ Plot 시스템
- 프롬프트/설정 변형 조합 생성
- 대기열 연동
"""
from typing import List, Dict, Any, Optional
from itertools import product
from enum import Enum
import re


class AxisType(Enum):
    """축 타입"""
    NONE = "없음"
    PROMPT_SR = "프롬프트 S/R"
    PROMPT_REPLACE = "프롬프트 단어 교체"
    PROMPT_ADD = "프롬프트 단어 추가"
    PROMPT_REMOVE = "프롬프트 단어 제거"
    PROMPT_ORDER = "프롬프트 순서 변경"
    WILDCARD = "와일드카드 전개"
    CFG_SCALE = "CFG Scale"
    STEPS = "Steps"
    SAMPLER = "Sampler"
    SCHEDULER = "Scheduler"
    SEED = "Seed"
    WIDTH = "Width"
    HEIGHT = "Height"
    DENOISE = "Denoising Strength"


class AxisConfig:
    """축 설정"""
    
    def __init__(self, axis_type: AxisType = AxisType.NONE):
        self.axis_type = axis_type
        self.values: List[Any] = []
        
        # 프롬프트 변형용
        self.target_word: str = ""  # 교체/제거 대상
        self.insert_position: str = "end"  # 추가 위치: start, end, after:tag, before:tag
    
    def set_values_from_string(self, values_str: str):
        """문자열에서 값 파싱"""
        if not values_str.strip():
            self.values = []
            return
        
        axis_type = self.axis_type
        
        # 숫자 타입들
        if axis_type in [AxisType.CFG_SCALE, AxisType.DENOISE]:
            self.values = self._parse_float_values(values_str)
        elif axis_type in [AxisType.STEPS, AxisType.SEED, AxisType.WIDTH, AxisType.HEIGHT]:
            self.values = self._parse_int_values(values_str)
        else:
            # 문자열 타입 (쉼표 구분)
            self.values = [v.strip() for v in values_str.split(',') if v.strip()]
    
    def _parse_float_values(self, values_str: str) -> List[float]:
        """실수 값 파싱 (범위 지원: 5-9:0.5)"""
        result = []
        
        for part in values_str.split(','):
            part = part.strip()
            if not part:
                continue
            
            # 범위 패턴: 5-9:0.5 (5부터 9까지 0.5 간격)
            range_match = re.match(r'^([\d.]+)-([\d.]+)(?::([\d.]+))?$', part)
            if range_match:
                start = float(range_match.group(1))
                end = float(range_match.group(2))
                step = float(range_match.group(3)) if range_match.group(3) else 1.0
                
                current = start
                while current <= end + 0.0001:  # 부동소수점 오차 보정
                    result.append(round(current, 2))
                    current += step
            else:
                try:
                    result.append(float(part))
                except ValueError:
                    print(f"⚠️ XYZ Plot: 실수 변환 실패 - '{part}' (무시됨)")
        
        return result
    
    def _parse_int_values(self, values_str: str) -> List[int]:
        """정수 값 파싱 (범위 지원: 20-40:5)"""
        result = []
        
        for part in values_str.split(','):
            part = part.strip()
            if not part:
                continue
            
            # 범위 패턴: 20-40:5
            range_match = re.match(r'^(\d+)-(\d+)(?::(\d+))?$', part)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                step = int(range_match.group(3)) if range_match.group(3) else 1
                
                result.extend(range(start, end + 1, step))
            else:
                try:
                    result.append(int(part))
                except ValueError:
                    print(f"⚠️ XYZ Plot: 정수 변환 실패 - '{part}' (무시됨)")
        
        return result
    
    def get_value_count(self) -> int:
        """값 개수"""
        return len(self.values) if self.values else 1


class XYZPlotGenerator:
    """XYZ Plot 조합 생성기"""
    
    def __init__(self):
        self.base_payload: Dict[str, Any] = {}
        self.x_axis = AxisConfig()
        self.y_axis = AxisConfig()
        self.z_axis = AxisConfig()
    
    def set_base_payload(self, payload: Dict[str, Any]):
        """기본 payload 설정"""
        self.base_payload = payload.copy()
    
    def set_axis(self, axis: str, config: AxisConfig):
        """축 설정"""
        if axis.lower() == 'x':
            self.x_axis = config
        elif axis.lower() == 'y':
            self.y_axis = config
        elif axis.lower() == 'z':
            self.z_axis = config
    
    def get_total_count(self) -> int:
        """총 조합 수"""
        x_count = self.x_axis.get_value_count()
        y_count = self.y_axis.get_value_count()
        z_count = self.z_axis.get_value_count()
        return x_count * y_count * z_count
    
    def generate_all(self) -> List[Dict[str, Any]]:
        """모든 조합 생성"""
        results = []
        
        # 각 축의 값들
        x_values = self.x_axis.values if self.x_axis.values else [None]
        y_values = self.y_axis.values if self.y_axis.values else [None]
        z_values = self.z_axis.values if self.z_axis.values else [None]
        
        # 모든 조합
        for x_val, y_val, z_val in product(x_values, y_values, z_values):
            payload = self.base_payload.copy()
            
            # 각 축 적용
            if x_val is not None:
                payload = self._apply_axis_value(payload, self.x_axis, x_val)
            if y_val is not None:
                payload = self._apply_axis_value(payload, self.y_axis, y_val)
            if z_val is not None:
                payload = self._apply_axis_value(payload, self.z_axis, z_val)
            
            # 변형 정보 추가 (디버깅/표시용)
            payload['_xyz_info'] = {
                'x': x_val,
                'y': y_val,
                'z': z_val,
                'x_type': self.x_axis.axis_type.value,
                'y_type': self.y_axis.axis_type.value,
                'z_type': self.z_axis.axis_type.value,
            }
            
            results.append(payload)
        
        return results
    
    def _apply_axis_value(self, payload: Dict[str, Any], 
                          config: AxisConfig, value: Any) -> Dict[str, Any]:
        """축 값을 payload에 적용"""
        axis_type = config.axis_type
        
        if axis_type == AxisType.NONE:
            return payload

        # Prompt S/R: target_word가 검색어, value가 대체어 (첫 번째 값은 원본 유지)
        elif axis_type == AxisType.PROMPT_SR:
            prompt = payload.get('prompt', '')
            search_text = config.target_word
            replace_text = str(value)
            if search_text and search_text != replace_text:
                payload['prompt'] = prompt.replace(search_text, replace_text)
            return payload

        # 프롬프트 변형
        elif axis_type == AxisType.PROMPT_REPLACE:
            payload['prompt'] = self._replace_word(
                payload.get('prompt', ''), 
                config.target_word, 
                str(value)
            )
        
        elif axis_type == AxisType.PROMPT_ADD:
            payload['prompt'] = self._add_word(
                payload.get('prompt', ''),
                str(value),
                config.insert_position
            )
        
        elif axis_type == AxisType.PROMPT_REMOVE:
            payload['prompt'] = self._remove_word(
                payload.get('prompt', ''),
                str(value)
            )
        
        elif axis_type == AxisType.PROMPT_ORDER:
            payload['prompt'] = self._change_order(
                payload.get('prompt', ''),
                str(value)
            )
        
        # 설정 변형
        elif axis_type == AxisType.CFG_SCALE:
            payload['cfg_scale'] = float(value)
        
        elif axis_type == AxisType.STEPS:
            payload['steps'] = int(value)
        
        elif axis_type == AxisType.SAMPLER:
            payload['sampler_name'] = str(value)
        
        elif axis_type == AxisType.SCHEDULER:
            payload['scheduler'] = str(value)
        
        elif axis_type == AxisType.SEED:
            payload['seed'] = int(value)
        
        elif axis_type == AxisType.WIDTH:
            payload['width'] = int(value)
        
        elif axis_type == AxisType.HEIGHT:
            payload['height'] = int(value)
        
        elif axis_type == AxisType.DENOISE:
            payload['denoising_strength'] = float(value)
        
        return payload
    
    def _replace_word(self, prompt: str, target: str, replacement: str) -> str:
        """단어 교체"""
        if not target:
            return prompt
        return prompt.replace(target, replacement)
    
    def _add_word(self, prompt: str, word: str, position: str) -> str:
        """단어 추가"""
        tags = [t.strip() for t in prompt.split(',') if t.strip()]
        
        if position == "start":
            tags.insert(0, word)
        elif position == "end":
            tags.append(word)
        elif position.startswith("after:"):
            target = position[6:].strip()
            for i, tag in enumerate(tags):
                if target.lower() in tag.lower():
                    tags.insert(i + 1, word)
                    break
            else:
                tags.append(word)  # 못 찾으면 끝에 추가
        elif position.startswith("before:"):
            target = position[7:].strip()
            for i, tag in enumerate(tags):
                if target.lower() in tag.lower():
                    tags.insert(i, word)
                    break
            else:
                tags.insert(0, word)  # 못 찾으면 앞에 추가
        
        return ', '.join(tags)
    
    def _remove_word(self, prompt: str, word: str) -> str:
        """단어 제거"""
        tags = [t.strip() for t in prompt.split(',') if t.strip()]
        tags = [t for t in tags if word.lower() not in t.lower()]
        return ', '.join(tags)
    
    def _change_order(self, prompt: str, order_type: str) -> str:
        """순서 변경"""
        import random
        
        tags = [t.strip() for t in prompt.split(',') if t.strip()]
        
        if order_type == "reverse":
            tags = tags[::-1]
        elif order_type == "shuffle":
            random.shuffle(tags)
        elif order_type == "alphabetical":
            tags = sorted(tags)
        # "original"은 그대로
        
        return ', '.join(tags)
    
    def generate_preview(self, max_items: int = 10) -> List[Dict[str, str]]:
        """미리보기용 요약 생성"""
        all_payloads = self.generate_all()
        
        previews = []
        for i, payload in enumerate(all_payloads[:max_items]):
            xyz_info = payload.get('_xyz_info', {})
            preview = {
                'index': i + 1,
                'x': str(xyz_info.get('x', '-')),
                'y': str(xyz_info.get('y', '-')),
                'z': str(xyz_info.get('z', '-')),
                'prompt_preview': payload.get('prompt', '')[:50] + '...',
            }
            previews.append(preview)
        
        if len(all_payloads) > max_items:
            previews.append({
                'index': '...',
                'x': '...',
                'y': '...',
                'z': '...',
                'prompt_preview': f'외 {len(all_payloads) - max_items}개',
            })
        
        return previews