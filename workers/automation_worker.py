# workers/automation_worker.py
import time
import random
import requests
import base64
import json
from PyQt6.QtCore import QThread, pyqtSignal
from config import WEBUI_API_URL

class AutomationWorker(QThread):
    """자동화 작업 워커"""
    progress_update = pyqtSignal(str)
    image_generated = pyqtSignal(bytes, dict)
    automation_finished = pyqtSignal(str)
    
    def __init__(self, main_window, settings, prompt_list, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.settings = settings
        self.prompt_list = prompt_list
        self.is_running = True
        
        if not self.settings['allow_duplicates']:
            self.prompt_deck = self.prompt_list.copy()
            random.shuffle(self.prompt_deck)
            
    def run(self):
        """자동화 실행"""
        generated_count = 0
        start_time = time.time()
        
        while self.is_running:
            # 종료 조건 체크
            if self.settings['termination_mode'] == 'timer':
                if time.time() - start_time >= self.settings['termination_limit']:
                    self.automation_finished.emit("타이머 시간이 다 되어 자동화를 종료합니다.")
                    break
            elif self.settings['termination_mode'] == 'count':
                if generated_count >= self.settings['termination_limit']:
                    self.automation_finished.emit("목표 생성 갯수에 도달하여 자동화를 종료합니다.")
                    break
            
            # 프롬프트 선택
            if self.settings['allow_duplicates']:
                if not self.prompt_list:
                    self.automation_finished.emit("오류: 프롬프트 목록이 비어있습니다.")
                    break
                current_bundle = random.choice(self.prompt_list)
            else:
                if not self.prompt_deck:
                    self.progress_update.emit("덱을 모두 소모하여 다시 섞습니다...")
                    self.prompt_deck = self.prompt_list.copy()
                    random.shuffle(self.prompt_deck)
                current_bundle = self.prompt_deck.pop()
            
            # 프롬프트 생성
            prompt_text, neg_prompt_text = self.main_window.get_prompts_from_bundle(
                current_bundle
            )
            
            # 반복 생성
            for i in range(self.settings['repeat_per_prompt']):
                if not self.is_running: 
                    break
                    
                self.progress_update.emit(
                    f"({generated_count + 1}) 생성 중... "
                    f"(반복 {i+1}/{self.settings['repeat_per_prompt']})"
                )
                
                try:
                    payload = self.main_window.prepare_payload(
                        prompt_text, neg_prompt_text
                    )
                    
                    response = requests.post(
                        url=f'{WEBUI_API_URL}/sdapi/v1/txt2img', 
                        json=payload, 
                        timeout=600
                    )
                    response.raise_for_status()
                    
                    r = response.json()
                    if 'images' in r and r['images']:
                        image_data = base64.b64decode(r['images'][0])
                        generation_info = json.loads(r.get('info', '{}'))
                        self.image_generated.emit(image_data, generation_info)
                        generated_count += 1
                    else: 
                        self.progress_update.emit(
                            f"API 오류: {r.get('detail', '알 수 없음')}"
                        )
                        
                except Exception as e:
                    self.progress_update.emit(f"API 요청 오류: {e}")
                    time.sleep(5)
                    
                time.sleep(self.settings['delay'])
        
        if self.is_running: 
            self.automation_finished.emit("자동화가 정상적으로 완료되었습니다.")
        
    def stop(self):
        """자동화 중지"""
        self.progress_update.emit("자동화를 중지하는 중...")
        self.is_running = False