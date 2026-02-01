# ui/generator_webui.py
"""
WebUI API 연결 및 정보 로드 로직
"""
import requests
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer

from config import WEBUI_API_URL
from workers.generation_worker import WebUIInfoWorker

class WebUIMixin:
    """WebUI 연결 관련 로직을 담당하는 Mixin"""
    
    def load_webui_info(self):
        """WebUI 정보 로드"""
        self.viewer_label.setText("WebUI 정보를 불러오는 중...")
        self.btn_generate.setEnabled(False)
        self.btn_random_prompt.setEnabled(False)
        
        self.info_worker = WebUIInfoWorker()
        self.info_worker.info_ready.connect(self.on_webui_info_loaded)
        self.info_worker.error_occurred.connect(self.on_webui_info_error)
        self.info_worker.start()
    
    def on_webui_info_loaded(self, info):
        """WebUI 정보 로드 완료"""
        # 모델
        models = info.get('models', [])
        self.model_combo.clear()
        self.model_combo.addItems(models)
        
        # 샘플러
        samplers = info.get('samplers', [])
        self.sampler_combo.clear()
        self.sampler_combo.addItems(samplers)
        
        # 스케줄러
        schedulers = info.get('schedulers', ['Automatic'])
        self.scheduler_combo.clear()
        self.scheduler_combo.addItems(schedulers)
        
        # 업스케일러
        upscalers = info.get('upscalers', [])
        self.upscaler_combo.clear()
        self.upscaler_combo.addItems(upscalers)
        
        # VAE
        vae_list = info.get('vae', ["Use same VAE"])
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['vae_combo'].clear()
            slot_widgets['vae_combo'].addItems(vae_list)
        
        # Checkpoint
        checkpoints = info.get('checkpoints', ["Use same checkpoint"])
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['checkpoint_combo'].clear()
            slot_widgets['checkpoint_combo'].addItems(checkpoints)
        
        # ADetailer 샘플러/스케줄러
        for slot_widgets in [self.s1_widgets, self.s2_widgets]:
            slot_widgets['sampler_combo'].clear()
            slot_widgets['sampler_combo'].addItems(["Use same sampler"] + samplers)
            slot_widgets['scheduler_combo'].clear()
            slot_widgets['scheduler_combo'].addItems(schedulers)
        
        # 저장된 설정 불러오기
        self.load_settings()
        
        # UI 활성화
        self.btn_generate.setEnabled(True)
        self.viewer_label.setText("✅ WebUI 연결 완료!\n생성 버튼을 눌러 시작하세요.")
        self.show_status(
            f"✅ WebUI 연결 성공 | 모델: {len(models)}개 | 샘플러: {len(samplers)}개"
        )
        
        # 검색 기능 활성화
        if self.filtered_results:
            self.btn_random_prompt.setEnabled(True)
    
    def on_webui_info_error(self, error_msg):
        """WebUI 정보 로드 실패"""
        self.viewer_label.setText(
            f"❌ WebUI 연결 실패\n\n{error_msg}\n\n"
            f"현재 URL: {WEBUI_API_URL}\n\n"
            f"설정 탭에서 API 주소를 확인하세요."
        )
        self.show_status(f"❌ WebUI 연결 실패: {error_msg}")
        
        QMessageBox.critical(
            self, "연결 실패", 
            f"WebUI API 연결에 실패했습니다.\n\n"
            f"오류: {error_msg}\n\n"
            f"현재 URL: {WEBUI_API_URL}\n\n"
            f"1. WebUI가 실행 중인지 확인하세요.\n"
            f"2. API 주소가 올바른지 확인하세요.\n"
            f"3. 방화벽 설정을 확인하세요."
        )
    
    def retry_connection(self, new_url=None):
        """연결 재시도"""
        if new_url:
            import config
            config.WEBUI_API_URL = new_url.strip()
            
        QTimer.singleShot(500, self.load_webui_info)
    
    def check_webui_connection(self):
        """WebUI 연결 상태 확인"""
        try:
            response = requests.get(
                f'{WEBUI_API_URL}/sdapi/v1/options', 
                timeout=3
            )
            response.raise_for_status()
            return True
        except Exception:
            return False