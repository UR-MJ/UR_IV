# workers/generation_worker.py
import requests
import base64
import json
from PyQt6.QtCore import QThread, pyqtSignal
from config import WEBUI_API_URL

class WebUIInfoWorker(QThread):
    """WebUI 정보 로드 워커"""
    info_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def run(self):
        """WebUI API에서 모델, 샘플러 등 정보 가져오기"""
        info = {
            'models': [], 
            'samplers': [], 
            'schedulers': [], 
            'upscalers': [], 
            'options': {}, 
            'vae': ["Use same VAE"], 
            'checkpoints': []
        }
        
        try:
            headers = {"accept": "application/json"}
            timeout = 5
            
            # 모델 목록
            try:
                res = requests.get(
                    f'{WEBUI_API_URL}/sdapi/v1/sd-models', 
                    headers=headers, 
                    timeout=timeout
                )
                res.raise_for_status()
                sd_models = res.json()
                
                if isinstance(sd_models, list):
                    info['models'] = [m.get('title', '') for m in sd_models]
                    info['checkpoints'] = ["Use same checkpoint"] + [
                        m.get('model_name', '') for m in sd_models
                    ]
            except Exception as e:
                raise Exception(f"모델 목록 로드 실패: {e}")

            # 샘플러
            try:
                r = requests.get(
                    f'{WEBUI_API_URL}/sdapi/v1/samplers', 
                    headers=headers, 
                    timeout=timeout
                ).json()
                info['samplers'] = [s.get('name', '') for s in r] if isinstance(r, list) else []
            except Exception:
                pass

            # 스케줄러
            try:
                r = requests.get(
                    f'{WEBUI_API_URL}/sdapi/v1/schedulers', 
                    headers=headers, 
                    timeout=timeout
                ).json()
                info['schedulers'] = (
                    [s.get('name', '') for s in r] if isinstance(r, list) else ["Automatic"]
                )
            except Exception:
                pass
            
            # 업스케일러
            try:
                r = requests.get(
                    f'{WEBUI_API_URL}/sdapi/v1/upscalers', 
                    headers=headers, 
                    timeout=timeout
                ).json()
                info['upscalers'] = [u.get('name', '') for u in r] if isinstance(r, list) else []
            except Exception:
                pass

            # VAE 목록
            try:
                r = requests.get(
                    f'{WEBUI_API_URL}/sdapi/v1/sd-vae', 
                    headers=headers, 
                    timeout=timeout
                ).json()
                if isinstance(r, list):
                    info['vae'] = ["Use same VAE"] + [v.get('model_name', '') for v in r]
            except Exception:
                pass 

            # 옵션
            try:
                info['options'] = requests.get(
                    f'{WEBUI_API_URL}/sdapi/v1/options', 
                    headers=headers, 
                    timeout=timeout
                ).json()
            except Exception:
                pass
            
            self.info_ready.emit(info)

        except Exception as e:
            self.error_occurred.emit(str(e))


class GenerationFlowWorker(QThread):
    """이미지 생성 워커"""
    finished = pyqtSignal(object, dict)
    
    def __init__(self, model_name, payload):
        super().__init__()
        self.model_name = model_name
        self.payload = payload
        
    def run(self):
        """모델 변경 후 이미지 생성"""
        try:
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            
            # 현재 모델 확인
            current_options = requests.get(
                url=f'{WEBUI_API_URL}/sdapi/v1/options', 
                headers=headers, 
                timeout=10
            ).json()
            
            # 모델 변경 필요 시
            if current_options.get('sd_model_checkpoint') != self.model_name:
                requests.post(
                    url=f'{WEBUI_API_URL}/sdapi/v1/options', 
                    json={'sd_model_checkpoint': self.model_name}, 
                    headers=headers, 
                    timeout=60
                )
                
            # 이미지 생성
            response = requests.post(
                url=f'{WEBUI_API_URL}/sdapi/v1/txt2img', 
                json=self.payload, 
                headers=headers, 
                timeout=600
            )
            response.raise_for_status()
            
            r = response.json()
            if 'images' in r and r['images']:
                image_data = base64.b64decode(r['images'][0])
                generation_info = json.loads(r.get('info', '{}'))
                self.finished.emit(image_data, generation_info)
            else: 
                self.finished.emit(
                    f"API 응답에 이미지가 없습니다: {r.get('detail', '알 수 없는 오류')}", 
                    {}
                )
                
        except requests.exceptions.RequestException as e:
            self.finished.emit(f"API 요청 실패: {e}", {})
        except Exception as e:
            self.finished.emit(f"이미지 생성 중 오류: {e}", {})


class Img2ImgFlowWorker(QThread):
    """img2img / inpaint 생성 워커"""
    finished = pyqtSignal(object, dict)

    def __init__(self, model_name, payload):
        super().__init__()
        self.model_name = model_name
        self.payload = payload

    def run(self):
        try:
            headers = {"accept": "application/json", "Content-Type": "application/json"}

            # 현재 모델 확인 및 변경
            current_options = requests.get(
                url=f'{WEBUI_API_URL}/sdapi/v1/options',
                headers=headers,
                timeout=10
            ).json()

            if current_options.get('sd_model_checkpoint') != self.model_name:
                requests.post(
                    url=f'{WEBUI_API_URL}/sdapi/v1/options',
                    json={'sd_model_checkpoint': self.model_name},
                    headers=headers,
                    timeout=60
                )

            # img2img 생성
            response = requests.post(
                url=f'{WEBUI_API_URL}/sdapi/v1/img2img',
                json=self.payload,
                headers=headers,
                timeout=600
            )
            response.raise_for_status()

            r = response.json()
            if 'images' in r and r['images']:
                image_data = base64.b64decode(r['images'][0])
                generation_info = json.loads(r.get('info', '{}'))
                self.finished.emit(image_data, generation_info)
            else:
                self.finished.emit(
                    f"API 응답에 이미지가 없습니다: {r.get('detail', '알 수 없는 오류')}",
                    {}
                )

        except requests.exceptions.RequestException as e:
            self.finished.emit(f"API 요청 실패: {e}", {})
        except Exception as e:
            self.finished.emit(f"img2img 생성 중 오류: {e}", {})