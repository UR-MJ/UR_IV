<template>
  <div class="app-container">
    <header class="app-header">
      <TabBar @tab-changed="onTabChanged" />
    </header>

    <main class="main-workspace">
      <!-- Left Panel -->
      <aside class="side-panel left" v-if="showLeftPanel">
        <div class="panel-scroll">
          <PromptPanel @toggle-extend="showExtendPanel = !showExtendPanel"
            @open-wildcard="openWildcardByName" />
          <!-- 워크플로우 프로파일 -->
          <div class="tool-card profile-card">
            <div class="profile-row">
              <label class="profile-label">프로파일</label>
              <CustomSelect :modelValue="''" @update:modelValue="loadWorkflowProfile"
                :options="profileNames"
                :placeholder="profileNames.length === 0 ? '(저장된 프로파일 없음)' : '선택하여 적용...'" />
              <button class="profile-mini-btn" @click="saveCurrentAsProfile" title="현재 세팅을 새 프로파일로 저장">+</button>
              <button class="profile-mini-btn" @click="showProfileManager = true; loadWorkflowProfilesList()" title="프로파일 관리 (삭제/이름변경)">⚙</button>
            </div>
          </div>

          <div class="tool-card">
            <label>Studio Tools</label>
            <div class="tool-grid">
              <button class="tool-btn" @click="syncLoraStack(); action('save_settings')">SAVE</button>
              <button class="tool-btn" @click="showPresetManager = true; loadPresetList()">PRESET</button>
              <button class="tool-btn" @click="showWeightManager = true">WEIGHT</button>
              <button class="tool-btn" @click="showWcManager = true">WILDCARD</button>
              <button class="tool-btn" @click="showInstantWcManager = true; loadInstantWcList()" title="JSON 기반 인라인 와일드카드 ($$name$$)">INSTANT WC</button>
              <button class="tool-btn" @click="showOrderManager = true; loadPromptOrder()" title="최종 프롬프트의 섹션 순서를 직접 지정">ORDER</button>
              <button class="tool-btn" @click="openAbTestModal()">A/B TEST</button>
              <button class="tool-btn" @click="showStatsModal = true; loadGenStats()">STATS</button>
              <button class="tool-btn" :class="{ 'tool-btn-on': condEnabled }" @click="showCondModal = true" :title="`태그 조건부 프롬프트 (IF→THEN) 관리 — 현재 ${condEnabled ? 'ON' : 'OFF'}`">조건부<span v-if="condEnabled" class="tool-dot"></span></button>
            </div>
          </div>

        </div>
        <div class="gen-footer">
          <div class="gen-actions">
            <button class="action-btn" :class="{ active: autoMode }" @click="autoMode = !autoMode; action('toggle_automation', { checked: autoMode })">
              {{ autoMode ? '🔄 AUTO ON' : '⏸ AUTO OFF' }}
            </button>
            <button class="action-btn highlight" @click="action('random_prompt')">🎲 RANDOM</button>
          </div>
          <!-- 자동화 설정 (AUTO ON일 때만) -->
          <div class="auto-settings" v-if="autoMode">
            <div class="auto-row">
              <label>{{ autoSettings.mode === 'unlimited' ? '무제한' : autoSettings.mode === 'count' ? '횟수' : '시간(분)' }}</label>
              <input v-if="autoSettings.mode !== 'unlimited'" type="number" v-model.number="autoSettings.limit" min="1" class="auto-input" />
              <span v-else class="auto-unlimited-mark">∞</span>
              <CustomSelect v-model="autoSettings.mode" :options="['count', 'timer', 'unlimited']" placeholder="모드" class="auto-select" />
            </div>
            <div class="auto-row">
              <label>반복</label>
              <input type="number" v-model.number="autoSettings.repeat" min="1" max="100" class="auto-input" />
              <label>대기(초)</label>
              <input type="number" v-model.number="autoSettings.delay" min="0" step="0.5" class="auto-input" />
            </div>
            <div class="auto-row">
              <label title="한 생성이 실패(서버 에러/타임아웃/OOM 등)했을 때 자동으로 다시 시도할 횟수.&#10;반복과 별개 — 반복은 같은 프롬프트로 N장 생성, 재시도는 실패 1회당 N번까지 다시 시도.&#10;지수 백오프(2s → 4s → 8s, 최대 30s)로 대기 후 재시도.&#10;&#10;예) 반복=3, 재시도=2:&#10;  · 2번째 시도가 실패하면 2초 대기 → 재시도 → 4초 → 재시도&#10;  · 두 재시도도 모두 실패 시 포기, 3번째 반복으로 진행">재시도</label>
              <input type="number" v-model.number="autoSettings.maxRetries" min="0" max="10" class="auto-input" />
            </div>
            <div class="auto-row">
              <label title="N회 generation마다 백엔드(WebUI/Forge)에 LoRA 캐시 정리 요청.&#10;Forge가 API 호출에서 LoRA patches를 누적시키는 버그 회피용.&#10;&#10;0 = 사용 안 함 (기본)&#10;5 = 매 5회마다 cleanup (LoRA 4개+SAM3 사용 시 권장)&#10;10 = 매 10회마다 (가벼운 워크플로우)&#10;&#10;cleanup은 ~1초 소요. OOM 발생 후 재시도 전엔 자동으로 full reload 실행됨.">cleanup 주기</label>
              <input type="number" v-model.number="autoSettings.cleanupEveryN" min="0" max="100" class="auto-input" />
            </div>
            <label class="auto-check"><input type="checkbox" v-model="autoSettings.allowDupes" /><span>중복 허용</span></label>
            <div class="auto-deck-pre" v-if="deckTotal > 0 && !isAutomating">
              🎴 덱 <strong>{{ deckRemaining }}</strong> / {{ deckTotal }} 남음 · {{ deckUsed }}개 사용<template v-if="deckAllowDup"> (중복·무한)</template>
            </div>
          </div>
          <!-- 자동화 상태 표시 -->
          <div class="auto-status" v-if="isAutomating">
            <div class="auto-status-bar">
              <span class="auto-pulse"></span>
              <span>자동화 진행 중 — {{ autoGenCount }}장 완료</span>
            </div>
            <div class="auto-status-sub deck-status" v-if="deckTotal > 0">
              🎴 덱
              <template v-if="deckAllowDup">{{ deckTotal }}개 (중복 허용 · 무한)</template>
              <template v-else><strong>{{ deckRemaining }}</strong> / {{ deckTotal }} 남음 · {{ deckUsed }}개 사용</template>
            </div>
            <div class="auto-status-sub auto-wait" v-if="autoWaiting && waitTotalMs > 0">
              <div class="wait-row"><span>⏳ 다음 생성까지 {{ waitSec }}s</span><span class="wait-pct">{{ Math.round(waitPct) }}%</span></div>
              <div class="wait-bar"><div class="wait-fill" :style="{ width: waitPct + '%' }"></div></div>
            </div>
            <div class="auto-status-sub" v-else-if="autoWaiting">대기 중...</div>
          </div>
          <div class="generate-row">
            <button class="btn-generate" :class="{ automating: isAutomating }" @click="doGenerate" :disabled="isGenerating && !isAutomating">
              {{ isAutomating ? '⏹ STOP AUTOMATION' : isGenerating ? 'GENERATING...' : autoMode ? '▶ START AUTOMATION' : 'GENERATE IMAGE' }}
            </button>
            <button v-if="isGenerating && !isAutomating" class="btn-cancel" @click="cancelGeneration" title="생성 취소">✕</button>
          </div>
          <div class="gen-eta" v-if="isGenerating && genEta">{{ genEta }}</div>
        </div>
      </aside>

      <!-- 반달 화살표 (좌측 패널 옆, 항상 표시) -->
      <div class="half-moon" v-if="showLeftPanel" @click="showExtendPanel = !showExtendPanel"
        :class="{ open: showExtendPanel }">
        <span>{{ showExtendPanel ? '◀' : '▶' }}</span>
      </div>

      <!-- Extended Panel backdrop (외부 클릭 시 닫기) -->
      <div class="extend-backdrop" v-if="showExtendPanel && showLeftPanel"
        @click="showExtendPanel = false"></div>

      <!-- Extended Panel — 뷰어 위에 오버레이 -->
      <transition name="slide">
        <aside class="extend-overlay" v-if="showExtendPanel && showLeftPanel" @click.stop>
          <div class="extend-header">
            <h3>ADVANCED SETTINGS</h3>
            <button class="close-btn" @click="showExtendPanel = false" title="닫기 (ESC)">✕</button>
          </div>
          <div class="extend-scroll">
            <!-- Parameters (기본) -->
            <div class="ext-card">
              <div class="ext-title">PARAMETERS</div>
              <div class="ext-field">
                <label>Resolution</label>
                <div class="ext-res-row">
                  <input type="number" v-model="storeWidgets.width_input" />
                  <span>×</span>
                  <input type="number" v-model="storeWidgets.height_input" />
                  <button class="ext-mini-btn" @click="action('swap_resolution')">↔</button>
                </div>
                <div class="ext-res-opts">
                  <label class="ext-check-sm"><input type="checkbox" v-model="randomResEnabled" /><span>랜덤</span></label>
                  <label class="ext-check-sm"><input type="checkbox" v-model="autoResEnabled" /><span>자동(Parquet)</span></label>
                  <label class="ext-check-sm hr-toggle" :class="{ active: highResEnabled }"
                    title="입력 해상도 × 배율로 처음부터 더 크게 생성 (hires.fix와 다른 단일 패스)&#10;&#10;⚠ SAM3 자동 검열과 동시 사용 시 VRAM OOM 위험&#10;⚠ 16GB GPU + 1.5× + SAM3 = inpaint 단계에서 메모리 부족&#10;⚠ 모델 학습 해상도(보통 1024±)를 크게 넘으면 이중 캐릭터/왜곡 가능&#10;&#10;권장: 1.5× 단독 사용 또는 SAM3 단독 사용 (둘 중 하나)">
                    <input type="checkbox" v-model="highResEnabled" />
                    <span>고해상도 {{ highResFactor.toFixed(2) }}×<span v-if="highResEnabled" class="hr-warn">⚠</span></span>
                  </label>
                </div>
                <!-- 고해상도 미리보기 + 배율 슬라이더 -->
                <div v-if="highResEnabled" class="hr-preview">
                  <div class="hr-row">
                    <span class="hr-label">배율</span>
                    <input type="range" min="1.1" max="2.5" step="0.05" v-model.number="highResFactor"
                      class="hr-slider" />
                    <span class="hr-val">{{ highResFactor.toFixed(2) }}×</span>
                  </div>
                  <div class="hr-result">
                    실제 생성: <strong>{{ hrActualW }}×{{ hrActualH }}</strong>
                    <span class="hr-note">(8 배수 정렬)</span>
                  </div>
                  <div class="hr-warn-banner">
                    ⚠ SAM3·ADetailer 등 후처리 동시 사용 시 VRAM OOM 위험.
                    16GB GPU + 1.5× = 한계.
                  </div>
                </div>
                <!-- 랜덤 해상도 편집기 -->
                <div v-if="randomResEnabled" class="rand-res-editor">
                  <div class="rand-res-list">
                    <div v-for="(r, i) in randomResList" :key="i" class="rand-res-item">
                      <span class="rand-res-val">{{ r[0] }}×{{ r[1] }}</span>
                      <span class="rand-res-desc">{{ r[2] }}</span>
                      <button class="rand-res-del" @click="removeRandomRes(i)">✕</button>
                    </div>
                    <div v-if="!randomResList.length" class="rand-res-empty">해상도를 추가하세요</div>
                  </div>
                  <div class="rand-res-add">
                    <input type="number" v-model.number="newResW" placeholder="W" class="rand-res-input" />
                    <span>×</span>
                    <input type="number" v-model.number="newResH" placeholder="H" class="rand-res-input" />
                    <button class="rand-res-btn" @click="addRandomRes">+</button>
                  </div>
                </div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Sampler</label>
                  <CustomSelect v-model="storeWidgets.sampler_combo" :options="samplerItems" placeholder="Sampler..." />
                </div>
                <div class="ext-field"><label>Scheduler</label>
                  <CustomSelect v-model="storeWidgets.scheduler_combo" :options="schedulerItems" placeholder="Scheduler..." />
                </div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Steps</label><input type="number" v-model="storeWidgets.steps_input" min="1" max="150" /></div>
                <div class="ext-field"><label>CFG</label><input type="number" v-model="storeWidgets.cfg_input" step="0.5" /></div>
                <div class="ext-field"><label>Shift</label><input type="number" v-model="storeWidgets.shift_input" step="0.5" min="0" max="24" title="0이면 미사용 (Distilled CFG Scale)" /></div>
                <div class="ext-field"><label>Seed</label><input type="text" v-model="storeWidgets.seed_input" /></div>
              </div>
            </div>

            <!-- Hires.fix -->
            <details class="ext-card">
              <summary class="ext-title">HIRES.FIX</summary>
              <label class="ext-check-row"><input type="checkbox" v-model="hires_enabled" /><span>Hires.fix 활성화</span></label>
              <div class="ext-field">
                <label>Upscaler</label>
                <CustomSelect v-model="storeWidgets.upscaler_combo" :options="upscalerItems" placeholder="Upscaler..." />
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Steps</label><input type="number" v-model="storeWidgets.hires_steps_input" /></div>
                <div class="ext-field"><label>Denoise</label><input type="number" v-model="storeWidgets.hires_denoising_input" step="0.05" /></div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Scale</label><input type="number" v-model="storeWidgets.hires_scale_input" step="0.1" min="1" /></div>
                <div class="ext-field"><label>CFG (0=off)</label><input type="number" v-model="storeWidgets.hires_cfg_input" step="0.5" /></div>
              </div>
              <div class="ext-field"><label>Checkpoint</label>
                <CustomSelect v-model="storeWidgets.hires_checkpoint_combo" :options="hiresCheckpointItems" placeholder="Use same checkpoint" /></div>
              <div class="ext-row">
                <div class="ext-field"><label>Sampler</label>
                  <CustomSelect v-model="storeWidgets.hires_sampler_combo" :options="hiresSamplerItems" placeholder="Use same sampler" /></div>
                <div class="ext-field"><label>Scheduler</label>
                  <CustomSelect v-model="storeWidgets.hires_scheduler_combo" :options="hiresSchedulerItems" placeholder="Use same scheduler" /></div>
              </div>
              <div class="ext-field"><label>Hires Prompt (비우면 메인 사용)</label>
                <input type="text" v-model="storeWidgets.hires_prompt_text" placeholder="비워두면 메인 프롬프트 사용" /></div>
              <div class="ext-field"><label>Hires Negative Prompt</label>
                <input type="text" v-model="storeWidgets.hires_neg_prompt_text" placeholder="비워두면 메인 네거티브 사용" /></div>
            </details>

            <details class="ext-card" open>
              <summary class="ext-title">PROMPT FILTERS</summary>
              <!-- Rating 토글 -->
              <div class="ext-sub-title">RATING FILTER</div>
              <div class="rating-toggle-row">
                <button v-for="r in ratingFilters" :key="r.key" class="rating-toggle"
                  :class="{ active: r.on }" @click="r.on = !r.on; saveRatingFilter()">{{ r.label }}</button>
              </div>
              <div class="ext-toggle-grid">
                <label class="ext-check-row"><input type="checkbox" v-model="removeCharacter" /><span>캐릭터 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="removeCharacterFeatures" /><span>캐릭터 특징 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="removeCopyright" /><span>작품 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="removeArtist" /><span>작가 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="removeMeta" /><span>메타 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="removeCensorship" /><span>검열 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="removeText" /><span>텍스트 제거</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="autoCharFeatures" /><span>특징 자동 추가</span></label>
                <label class="ext-check-row"><input type="checkbox" v-model="autoRemoveCharFeatures" /><span title="closed eyes 있으면 눈색 특징 생략, 머리 길이 충돌 시 생략">특징 auto remove</span></label>
              </div>
              <div v-if="autoRemoveCharFeatures" class="char-ovr-row">
                <button class="char-ovr-btn" @click="openCharOverrideModal()">⚙ override 설정 (머리길이 / 눈색)</button>
              </div>
            </details>

            <!-- ADetailer -->
            <details class="ext-card">
              <summary class="ext-title">ADETAILER</summary>
              <label class="ext-check-row"><input type="checkbox" v-model="ad_enabled" /><span>ADetailer 활성화</span></label>
              <!-- Slot 1 -->
              <div class="ext-sub-title">Slot 1</div>
              <label class="ext-check-row"><input type="checkbox" v-model="ad_s1_enabled" /><span>Slot 1 활성화</span></label>
              <div class="ext-field"><label>Model</label>
                <CustomSelect v-model="storeWidgets._ad_s1_model" :options="adModelItems" placeholder="AD Model..." /></div>
              <div class="ext-field"><label>Prompt</label>
                <input type="text" v-model="storeWidgets._ad_s1_prompt" placeholder="ADetailer prompt..." /></div>
              <div class="ext-field"><label>Negative Prompt</label>
                <input type="text" v-model="storeWidgets._ad_s1_neg" placeholder="AD negative..." /></div>
              <div class="ext-row">
                <div class="ext-field"><label>Confidence</label><input type="number" v-model="storeWidgets._ad_s1_confidence" step="0.05" min="0" max="1" /></div>
                <div class="ext-field"><label>Denoise</label><input type="number" v-model="storeWidgets._ad_s1_denoise" step="0.05" min="0" max="1" /></div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Mask Blur</label><input type="number" v-model="storeWidgets._ad_s1_mask_blur" min="0" /></div>
                <div class="ext-field"><label>Padding</label><input type="number" v-model="storeWidgets._ad_s1_padding" min="0" /></div>
                <div class="ext-field"><label>Dilate/Erode</label><input type="number" v-model="storeWidgets._ad_s1_dilate_erode" /></div>
              </div>
              <div class="ext-field"><label>Mask Merge</label>
                <CustomSelect v-model="storeWidgets._ad_s1_mask_merge" :options="['None', 'Merge', 'Merge and Invert']" placeholder="None" /></div>
              <!-- Separate settings -->
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s1_use_inp_size" true-value="true" false-value="false" /><span>별도 Inpaint 크기</span></label>
              <div class="ext-row" v-if="storeWidgets._ad_s1_use_inp_size === 'true'">
                <div class="ext-field"><label>Width</label><input type="number" v-model="storeWidgets._ad_s1_inp_w" /></div>
                <div class="ext-field"><label>Height</label><input type="number" v-model="storeWidgets._ad_s1_inp_h" /></div>
              </div>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s1_use_steps" true-value="true" false-value="false" /><span>별도 Steps</span></label>
              <div class="ext-row" v-if="storeWidgets._ad_s1_use_steps === 'true'">
                <div class="ext-field"><label>Steps</label><input type="number" v-model="storeWidgets._ad_s1_steps" min="1" /></div>
              </div>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s1_use_cfg" true-value="true" false-value="false" /><span>별도 CFG</span></label>
              <div class="ext-row" v-if="storeWidgets._ad_s1_use_cfg === 'true'">
                <div class="ext-field"><label>CFG</label><input type="number" v-model="storeWidgets._ad_s1_cfg" step="0.5" /></div>
              </div>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s1_use_sampler" true-value="true" false-value="false" /><span>별도 Sampler</span></label>
              <div class="ext-row" v-if="storeWidgets._ad_s1_use_sampler === 'true'">
                <div class="ext-field"><label>Sampler</label>
                  <CustomSelect v-model="storeWidgets._ad_s1_sampler" :options="samplerItems" placeholder="Sampler" /></div>
                <div class="ext-field"><label>Scheduler</label>
                  <CustomSelect v-model="storeWidgets._ad_s1_scheduler" :options="schedulerItems" placeholder="Scheduler" /></div>
              </div>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s1_use_ckpt" true-value="true" false-value="false" /><span>별도 Checkpoint</span></label>
              <div class="ext-field" v-if="storeWidgets._ad_s1_use_ckpt === 'true'"><label>Checkpoint</label>
                <CustomSelect v-model="storeWidgets._ad_s1_ckpt" :options="adCheckpointItems" placeholder="Use same checkpoint" /></div>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s1_use_vae" true-value="true" false-value="false" /><span>별도 VAE</span></label>
              <div class="ext-field" v-if="storeWidgets._ad_s1_use_vae === 'true'"><label>VAE</label>
                <CustomSelect v-model="storeWidgets._ad_s1_vae" :options="adVaeItems" placeholder="Use same VAE" /></div>

              <!-- Slot 2 -->
              <details class="ext-sub">
                <summary>Slot 2</summary>
                <label class="ext-check-row"><input type="checkbox" v-model="ad_s2_enabled" /><span>Slot 2 활성화</span></label>
                <div class="ext-field"><label>Model</label>
                  <CustomSelect v-model="storeWidgets._ad_s2_model" :options="adModelItems" placeholder="AD Model..." /></div>
                <div class="ext-field"><label>Prompt</label>
                  <input type="text" v-model="storeWidgets._ad_s2_prompt" placeholder="Slot 2 prompt..." /></div>
                <div class="ext-field"><label>Negative Prompt</label>
                  <input type="text" v-model="storeWidgets._ad_s2_neg" placeholder="AD negative..." /></div>
                <div class="ext-row">
                  <div class="ext-field"><label>Confidence</label><input type="number" v-model="storeWidgets._ad_s2_confidence" step="0.05" min="0" max="1" /></div>
                  <div class="ext-field"><label>Denoise</label><input type="number" v-model="storeWidgets._ad_s2_denoise" step="0.05" min="0" max="1" /></div>
                </div>
                <div class="ext-row">
                  <div class="ext-field"><label>Mask Blur</label><input type="number" v-model="storeWidgets._ad_s2_mask_blur" min="0" /></div>
                  <div class="ext-field"><label>Padding</label><input type="number" v-model="storeWidgets._ad_s2_padding" min="0" /></div>
                  <div class="ext-field"><label>Dilate/Erode</label><input type="number" v-model="storeWidgets._ad_s2_dilate_erode" /></div>
                </div>
                <div class="ext-field"><label>Mask Merge</label>
                  <CustomSelect v-model="storeWidgets._ad_s2_mask_merge" :options="['None', 'Merge', 'Merge and Invert']" placeholder="None" /></div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s2_use_inp_size" true-value="true" false-value="false" /><span>별도 Inpaint 크기</span></label>
                <div class="ext-row" v-if="storeWidgets._ad_s2_use_inp_size === 'true'">
                  <div class="ext-field"><label>Width</label><input type="number" v-model="storeWidgets._ad_s2_inp_w" /></div>
                  <div class="ext-field"><label>Height</label><input type="number" v-model="storeWidgets._ad_s2_inp_h" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s2_use_steps" true-value="true" false-value="false" /><span>별도 Steps</span></label>
                <div class="ext-row" v-if="storeWidgets._ad_s2_use_steps === 'true'">
                  <div class="ext-field"><label>Steps</label><input type="number" v-model="storeWidgets._ad_s2_steps" min="1" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s2_use_cfg" true-value="true" false-value="false" /><span>별도 CFG</span></label>
                <div class="ext-row" v-if="storeWidgets._ad_s2_use_cfg === 'true'">
                  <div class="ext-field"><label>CFG</label><input type="number" v-model="storeWidgets._ad_s2_cfg" step="0.5" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s2_use_sampler" true-value="true" false-value="false" /><span>별도 Sampler</span></label>
                <div class="ext-row" v-if="storeWidgets._ad_s2_use_sampler === 'true'">
                  <div class="ext-field"><label>Sampler</label>
                    <CustomSelect v-model="storeWidgets._ad_s2_sampler" :options="samplerItems" placeholder="Sampler" /></div>
                  <div class="ext-field"><label>Scheduler</label>
                    <CustomSelect v-model="storeWidgets._ad_s2_scheduler" :options="schedulerItems" placeholder="Scheduler" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s2_use_ckpt" true-value="true" false-value="false" /><span>별도 Checkpoint</span></label>
                <div class="ext-field" v-if="storeWidgets._ad_s2_use_ckpt === 'true'"><label>Checkpoint</label>
                  <CustomSelect v-model="storeWidgets._ad_s2_ckpt" :options="adCheckpointItems" placeholder="Use same checkpoint" /></div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._ad_s2_use_vae" true-value="true" false-value="false" /><span>별도 VAE</span></label>
                <div class="ext-field" v-if="storeWidgets._ad_s2_use_vae === 'true'"><label>VAE</label>
                  <CustomSelect v-model="storeWidgets._ad_s2_vae" :options="adVaeItems" placeholder="Use same VAE" /></div>
              </details>
            </details>

            <!-- SAM3 Mask — Forge Neo SAM3 확장과 1:1 -->
            <details class="ext-card">
              <summary class="ext-title">SAM3 Mask</summary>
              <label class="ext-check-row"><input type="checkbox" v-model="sam3_enabled" /><span>Enable SAM3</span></label>

              <div class="ext-field"><label>SAM3 Detect Prompt</label>
                <input type="text" v-model="storeWidgets._sam3_detect_prompt" placeholder="face" /></div>
              <div class="ext-field"><label>SAM3 Exclude Prompt</label>
                <input type="text" v-model="storeWidgets._sam3_exclude_prompt" placeholder="메인 마스크에서 검출+제외. 예: 'face, eyes' 보호" /></div>
              <div class="ext-field"><label>SAM3 Inpaint Prompt</label>
                <input type="text" v-model="storeWidgets._sam3_inpaint_prompt" placeholder="비워두면 메인 프롬프트 사용" /></div>
              <div class="ext-field"><label>SAM3 Negative Prompt</label>
                <input type="text" v-model="storeWidgets._sam3_neg_prompt" placeholder="비워두면 메인 네거티브 사용" /></div>

              <div class="ext-row">
                <div class="ext-field"><label>SAM3 Mode</label>
                  <CustomSelect v-model="storeWidgets._sam3_mode" :options="['Inpaint', 'Mask only']" placeholder="Inpaint" /></div>
                <div class="ext-field"><label>Mask Processing</label>
                  <CustomSelect v-model="storeWidgets._sam3_mask_mode" :options="['Individual', 'Combined']" placeholder="Individual" /></div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>SAM3 Threshold</label><input type="number" v-model="storeWidgets._sam3_threshold" step="0.01" min="0" max="1" /></div>
                <div class="ext-field"><label>Mask Dilation (px)</label><input type="number" v-model="storeWidgets._sam3_mask_dilation" min="0" /></div>
              </div>
              <div class="ext-row">
                <label class="ext-check-row" style="flex:1" title="머리카락 가닥 등을 감싸 마스크를 채움"><input type="checkbox" v-model="storeWidgets._sam3_mask_hull" true-value="true" false-value="false" /><span>Convex Hull (wrap strands)</span></label>
                <div class="ext-field"><label>Outline expand (edge-aware, px)</label><input type="number" v-model="storeWidgets._sam3_mask_outline_px" min="0" /></div>
              </div>
              <div class="ext-field"><label>SAM3 Checkpoint</label>
                <CustomSelect v-model="storeWidgets._sam3_checkpoint" :options="sam3CheckpointItems" placeholder="sam3.pt" /></div>
              <div class="ext-field">
                <label>SAM3 Device (검출 연산 장치)</label>
                <CustomSelect v-model="storeWidgets._sam3_device" :options="sam3DeviceItems" placeholder="cuda" />
                <div class="ext-note">cuda 권장 — auto는 CPU로 떨어져 검출이 느려질 수 있음</div>
              </div>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_preview_overlay" true-value="true" false-value="false" /><span>Replace output with overlay preview</span></label>
              <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_save_artifacts" true-value="true" false-value="false" /><span>Save mask/overlay artifacts</span></label>
              <label class="ext-check-row" title="검출 직후 SAM3(~3.5GB) VRAM 회수 — 16GB GPU 권장"><input type="checkbox" v-model="storeWidgets._sam3_unload_after" true-value="true" false-value="false" /><span>Unload SAM3 from VRAM after detection (~3.5GB)</span></label>

              <!-- 인페인트 하위 섹션 -->
              <details class="ext-card" open style="margin-top:8px">
                <summary class="ext-title">인페인트</summary>
                <div class="ext-row">
                  <div class="ext-field"><label>Denoising Strength</label><input type="number" v-model="storeWidgets._sam3_denoise" step="0.01" min="0" max="1" /></div>
                  <div class="ext-field"><label>Mask Blur</label><input type="number" v-model="storeWidgets._sam3_mask_blur" min="0" /></div>
                </div>
                <div class="ext-row">
                  <div class="ext-field"><label>Masked content (init for masked area)</label>
                    <CustomSelect v-model="storeWidgets._sam3_inpainting_fill" :options="sam3FillItems" placeholder="original" /></div>
                  <div class="ext-field"><label>Inpaint padding</label><input type="number" v-model="storeWidgets._sam3_padding" min="0" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_inpaint_only_masked" true-value="true" false-value="false" /><span>마스크된 영역만</span></label>

                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_use_inp_size" true-value="true" false-value="false" /><span>Use separate inpaint width/height</span></label>
                <div class="ext-row" v-if="storeWidgets._sam3_use_inp_size === 'true'">
                  <div class="ext-field"><label>Inpaint Width</label><input type="number" v-model="storeWidgets._sam3_inp_w" /></div>
                  <div class="ext-field"><label>Inpaint Height</label><input type="number" v-model="storeWidgets._sam3_inp_h" /></div>
                </div>

                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_use_steps" true-value="true" false-value="false" /><span>별도의 단계 사용</span></label>
                <div class="ext-row" v-if="storeWidgets._sam3_use_steps === 'true'">
                  <div class="ext-field"><label>단계</label><input type="number" v-model="storeWidgets._sam3_steps" min="1" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_use_cfg" true-value="true" false-value="false" /><span>별도의 CFG 스케일 사용</span></label>
                <div class="ext-row" v-if="storeWidgets._sam3_use_cfg === 'true'">
                  <div class="ext-field"><label>CFG 스케일</label><input type="number" v-model="storeWidgets._sam3_cfg" step="0.5" /></div>
                </div>
                <label class="ext-check-row" title="OFF면 base 생성의 sampler 상속&#10;ON이고 'Use same sampler' 이외면 SAM3 단계에서 override"><input type="checkbox" v-model="storeWidgets._sam3_use_sampler" true-value="true" false-value="false" /><span>별도의 샘플러 사용</span></label>
                <div class="ext-field" v-if="storeWidgets._sam3_use_sampler === 'true'"><label>샘플러</label>
                  <CustomSelect v-model="storeWidgets._sam3_sampler" :options="['Use same sampler', ...samplerItems]" placeholder="Use same sampler" /></div>
                <label class="ext-check-row" title="OFF면 base 생성의 scheduler 상속"><input type="checkbox" v-model="storeWidgets._sam3_use_scheduler" true-value="true" false-value="false" /><span>Use separate scheduler</span></label>
                <div class="ext-field" v-if="storeWidgets._sam3_use_scheduler === 'true'"><label>Scheduler</label>
                  <CustomSelect v-model="storeWidgets._sam3_scheduler" :options="['Use same scheduler', ...schedulerItems]" placeholder="Use same scheduler" /></div>

                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_use_seed" true-value="true" false-value="false" /><span>Use specified seed (instead of parent's)</span></label>
                <div class="ext-field" v-if="storeWidgets._sam3_use_seed === 'true'"><label>Seed (-1 = random)</label>
                  <input type="number" v-model="storeWidgets._sam3_seed" /></div>

                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_use_noise_mul" true-value="true" false-value="false" /><span>Use noise multiplier</span></label>
                <div class="ext-row" v-if="storeWidgets._sam3_use_noise_mul === 'true'">
                  <div class="ext-field"><label>Noise Multiplier</label><input type="number" v-model="storeWidgets._sam3_noise_mul" step="0.01" min="0" max="2" /></div>
                </div>
                <label class="ext-check-row"><input type="checkbox" v-model="storeWidgets._sam3_restore_face" true-value="true" false-value="false" /><span>Restore face</span></label>
              </details>
            </details>

            <!-- NegPiP 상시 적용 / 조건부 프롬프트는 STUDIO TOOLS '조건부' 모달로 이동 -->

            <!-- LoRA Stack -->
            <div class="ext-card">
              <div class="ext-title">LoRA STACK
                <span v-if="loraStack.length" class="lora-tools">
                  <button class="lora-tool-btn" @click="toggleAllLoras(!allLorasOn)" :title="allLorasOn ? '전체 끄기' : '전체 켜기'">{{ allLorasOn ? '전체 OFF' : '전체 ON' }}</button>
                  <button class="lora-tool-btn" @click="insertAllTriggers" title="활성 LoRA 트리거 워드를 메인 프롬프트에 일괄 삽입">트리거 삽입</button>
                </span>
              </div>
              <div class="lora-empty" v-if="loraStack.length === 0">
                LoRA 매니저에서 추가하세요
              </div>
              <div v-for="(lora, i) in loraStack" :key="i" class="lora-block">
                <label class="lora-check"><input type="checkbox" v-model="lora.enabled" /></label>
                <div class="lora-info-col">
                  <div class="lora-name">{{ lora.name }}</div>
                  <div class="lora-triggers" v-if="lora.triggerWords && lora.triggerWords.length">
                    <button v-for="tw in lora.triggerWords" :key="tw" class="trigger-chip"
                      @click="insertTriggerWord(tw)" :title="'클릭하여 프롬프트에 삽입'">{{ tw }}</button>
                  </div>
                </div>
                <input type="range" min="-100" max="200" v-model.number="lora.weight" class="lora-slider" />
                <span class="lora-weight">{{ (lora.weight / 100).toFixed(2) }}</span>
                <button class="lora-remove" @click="loraStack.splice(i, 1)">✕</button>
              </div>
              <button class="ext-add-btn" @click="showLoraModal = true">+ ADD LoRA</button>
              <!-- LoRA 세트 저장/불러오기 -->
              <div class="lora-sets">
                <input v-model="loraSetName" class="lora-set-input" placeholder="세트 이름" />
                <button class="lora-tool-btn" @click="saveLoraSet" :disabled="!loraStack.length || !loraSetName.trim()" title="현재 스택을 세트로 저장">저장</button>
                <select v-model="loraSetSel" class="lora-set-sel">
                  <option value="">불러오기…</option>
                  <option v-for="n in loraSetNames" :key="n" :value="n">{{ n }}</option>
                </select>
                <button class="lora-tool-btn" @click="loadLoraSet" :disabled="!loraSetSel" title="선택 세트를 스택에 적용">적용</button>
                <button class="lora-tool-btn" @click="deleteLoraSet" :disabled="!loraSetSel" title="세트 삭제">✕</button>
              </div>
            </div>
          </div>
        </aside>
      </transition>

      <!-- Center: Viewport + EXIF Bar -->
      <section class="viewport-area">
        <div class="viewport-main">
          <router-view v-slot="{ Component, route }">
            <keep-alive>
              <component :is="Component"
                :key="route.name"
                :image-url="currentImage"
                :resolution="resolution"
                :seed="seed"
                :status="status"
              />
            </keep-alive>
          </router-view>
        </div>
        <!-- EXIF Info Bar (Positive / Negative / Parameters 3탭) -->
        <div class="exif-bar" v-if="showLeftPanel && currentImage">
          <div class="exif-tabs">
            <button v-for="tab in exifTabs" :key="tab.id" class="exif-tab"
              :class="{ active: activeExifTab === tab.id }" @click="activeExifTab = tab.id">
              {{ tab.label }}
            </button>
          </div>
          <div class="exif-content" v-if="activeExifTab !== 'params'">{{ exifContent }}</div>
          <div class="exif-params" v-else-if="currentExif.params">
            <div class="param-line" v-if="currentExif.params.generation"><span class="pl">GEN</span>{{ currentExif.params.generation }}</div>
            <div class="param-line" v-if="currentExif.params.core"><span class="pl">CORE</span>{{ currentExif.params.core }}</div>
            <div class="param-line" v-if="currentExif.params.model"><span class="pl">MODEL</span>{{ currentExif.params.model }}</div>
            <div class="param-line" v-if="currentExif.params.hires"><span class="pl">HIRES</span>{{ currentExif.params.hires }}</div>
            <div class="param-line" v-if="currentExif.params.extensions"><span class="pl">EXT</span>{{ currentExif.params.extensions }}</div>
            <div class="param-line other" v-if="currentExif.params.other"><span class="pl">ETC</span>{{ currentExif.params.other }}</div>
          </div>
          <div class="exif-content" v-else>{{ currentExif.params_line || currentExif.raw || 'No parameters' }}</div>
        </div>
      </section>

      <!-- Right: History -->
      <aside class="side-panel right" v-if="showLeftPanel">
        <div class="hist-header">
          <h3>HISTORY</h3>
          <span class="count-badge">{{ historyImages.length }}</span>
        </div>
        <button class="hist-nav-btn" @click="histPage = Math.max(0, histPage - 1)" :disabled="histPage <= 0">▲</button>
        <div class="hist-scroll">
          <div v-for="img in visibleHistory" :key="img" class="hist-card"
            @click="selectHistoryImage(img)"
            @contextmenu.prevent="showHistoryMenu($event, img)"
            :class="{ selected: currentImage === img, blink: historyBlink && currentImage === img }"
            draggable="true" @dragstart="onDragStart($event, img)"
          >
            <img :key="historyImageSrc(img)" :src="historyImageSrc(img)" loading="lazy" />
          </div>
        </div>
        <button class="hist-nav-btn" @click="histPage++" :disabled="(histPage + 1) * histPerPage >= historyImages.length">▼</button>

        <transition name="pop">
          <div v-if="ctxMenu.show" class="modern-ctx-menu" :style="ctxMenuStyle">
            <div class="ctx-item" @click="ctxAddFavorite">⭐ ADD TO FAVORITES</div>
            <div class="ctx-item" @click="ctxSendI2I">🖼️ SEND TO I2I</div>
            <div class="ctx-item" @click="ctxSendInpaint">🎨 SEND TO INPAINT</div>
            <div class="ctx-item" @click="ctxSendEditor">✏️ SEND TO EDITOR</div>
            <div class="ctx-item" @click="ctxCompare('before')">🔍 COMPARE (BEFORE)</div>
            <div class="ctx-item" @click="ctxCompare('after')">🔍 COMPARE (AFTER)</div>
            <div class="ctx-item" @click="ctxRunAdetailer">🎯 ADETAILER</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item" @click="ctxPullPrompt">📥 프롬프트 당겨오기</div>
            <div class="ctx-item" @click="ctxAddToQueue">➕ 다음 큐에 추가</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item" @click="ctxCopyPath">📋 COPY PATH</div>
            <div class="ctx-item delete" @click="ctxDelete">🗑️ DELETE</div>
          </div>
        </transition>
      </aside>
    </main>

    <div class="global-progress" v-if="isGenerating">
      <div class="progress-fill" :style="{ width: progressVal + '%' }"></div>
    </div>

    <QueuePanel />

    <!-- VRAM 게이지 (하단 고정) — 클릭으로 상세 메모리 정보 + 권장사항 -->
    <div class="vram-bar" v-if="vramInfo.total > 0" @click="onVramClick" :title="vramTooltip">
      <div class="vram-fill" :style="{ width: vramInfo.pct + '%' }" :class="vramClass"></div>
      <span class="vram-text">
        VRAM {{ vramInfo.used }}GB / {{ vramInfo.total }}GB ({{ vramInfo.pct }}%)
        <span v-if="vramClass === 'critical'" class="vram-warn">⚠ 위험</span>
        <span v-else-if="vramClass === 'warn'" class="vram-warn">▲ 주의</span>
      </span>
    </div>

    <!-- Preset Manager Modal -->
    <transition name="fade">
      <div v-if="showPresetManager" class="pm-overlay" @click.self="showPresetManager = false">
        <div class="pm-modal">
          <div class="pm-header">
            <h3>PRESET MANAGER</h3>
            <button class="close-btn" @click="showPresetManager = false">✕</button>
          </div>
          <div class="pm-body">
            <div class="pm-list">
              <div v-for="p in presetList" :key="p" class="pm-item"
                :class="{ active: selectedPreset === p }" @click="selectedPreset = p; loadPresetPreview(p)">
                {{ p }}
              </div>
              <div v-if="presetList.length === 0" class="pm-empty">저장된 프리셋 없음</div>
            </div>
            <div class="pm-preview">
              <div v-if="presetPreview" class="pm-detail">
                <div class="pm-field" v-for="(val, key) in presetPreview" :key="key">
                  <span class="pm-key">{{ key }}</span>
                  <span class="pm-val">{{ typeof val === 'string' ? val.substring(0, 100) : val }}</span>
                </div>
              </div>
              <div v-else class="pm-empty">프리셋을 선택하세요</div>
            </div>
          </div>
          <div class="pm-footer">
            <button class="pm-btn" @click="loadSelectedPreset" :disabled="!selectedPreset">📂 LOAD</button>
            <button class="pm-btn" @click="deleteSelectedPreset" :disabled="!selectedPreset">🗑 DELETE</button>
            <div class="pm-spacer"></div>
            <button class="pm-btn accent" @click="saveNewPreset">💾 SAVE CURRENT</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 캐릭터 특징 프리셋 / A/B 테스트 / override 모달 (Vue) -->
    <CharacterPresetModal v-if="uiModals.charPreset" @close="closeCharPresetModal" />
    <ABTestModal v-if="uiModals.abTest" @close="closeAbTestModal" />
    <CharFeatureOverrideModal v-if="uiModals.charOverride" @close="closeCharOverrideModal" />
    <LoraManagerModal v-if="showLoraModal" @close="showLoraModal = false" @add="onLoraAdd" />
    <CondPromptModal v-if="showCondModal" v-model:preventDupe="extWidgets.cond_prevent_dupe" @close="showCondModal = false" />

    <!-- Weight Manager Modal -->
    <transition name="fade">
      <div v-if="showWeightManager" class="wm-overlay" @click.self="showWeightManager = false">
        <div class="wm-modal">
          <div class="wm-header">
            <h3>GLOBAL TAG WEIGHTS</h3>
            <span class="wm-desc">등록된 태그는 어디서든 자동으로 지정 가중치가 적용됩니다</span>
            <button class="close-btn" @click="showWeightManager = false">✕</button>
          </div>
          <div class="wm-body">
            <div v-for="(w, i) in globalWeights" :key="i" class="wm-row">
              <input v-model="w.tag" placeholder="태그명..." class="wm-tag-input" />
              <input type="range" min="50" max="200" v-model.number="w.weight" class="wm-slider" />
              <span class="wm-val">{{ (w.weight / 100).toFixed(2) }}</span>
              <button class="wm-rm" @click="globalWeights.splice(i, 1)">✕</button>
            </div>
            <button class="wm-add" @click="globalWeights.push({ tag: '', weight: 100 })">+ ADD TAG WEIGHT</button>
          </div>
          <div class="wm-footer">
            <button class="wm-save" @click="saveGlobalWeights">💾 SAVE</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Wildcard Manager Modal -->
    <transition name="fade">
      <div v-if="showWcManager" class="wc-overlay" @click.self="showWcManager = false">
        <div class="wc-modal">
          <div class="wc-modal-header">
            <h3>WILDCARD MANAGER</h3>
            <span class="wc-path">wildcards/</span>
            <button class="wc-new-btn" @click="createNewWildcard">+ NEW</button>
            <button class="close-btn" @click="showWcManager = false">✕</button>
          </div>
          <div class="wc-modal-body">
            <!-- 파일 목록 -->
            <div class="wc-sidebar">
              <div v-for="wc in wildcards" :key="wc.name" class="wc-file-item"
                :class="{ active: selectedWc === wc.name }" @click="selectWildcard(wc.name)">
                <span class="wc-fname" @dblclick.stop="renameWildcard(wc.name)">{{ wc.name }}</span>
                <span class="wc-file-count">{{ wc.tags.length }}</span>
                <button class="wc-del" @click.stop="deleteWildcard(wc.name)">✕</button>
              </div>
            </div>
            <!-- 편집 영역 -->
            <div class="wc-content">
              <template v-if="selectedWcData">
                <div class="wc-content-header">
                  <!-- 파일명 인라인 편집 -->
                  <h4 v-if="!wcRenaming" @dblclick="startWcRename">{{ selectedWc }}</h4>
                  <input v-else v-model="wcNewName" class="wc-rename-input" @blur="finishWcRename" @keydown.enter="finishWcRename" ref="wcRenameRef" />
                  <span class="wc-syntax">문법: <code>{{'__' + selectedWc + '__'}}</code></span>
                </div>
                <!-- 블록 편집 -->
                <div class="wc-blocks">
                  <div v-for="(line, li) in wcEditLines" :key="li" class="wc-block-row">
                    <span class="wc-block-idx">{{ li + 1 }}</span>
                    <input v-model="wcEditLines[li]" class="wc-block-input" @keydown.enter="addWcLine(li)" />
                    <button class="wc-block-rm" @click="wcEditLines.splice(li, 1)">✕</button>
                  </div>
                  <button class="wc-add-line" @click="wcEditLines.push('')">+ 줄 추가</button>
                </div>
                <!-- 하단: 삽입 + 저장 -->
                <div class="wc-bottom-bar">
                  <CustomSelect v-model="wcInsertTarget" :options="['main', 'prefix', 'suffix', 'clipboard']" placeholder="삽입 위치" class="wc-insert-sel" />
                  <button class="wc-use-btn" @click="useWcSyntax">USE</button>
                  <div class="wc-spacer"></div>
                  <button class="wc-save-btn" @click="saveCurrentWildcard">💾 SAVE</button>
                </div>
              </template>
              <div v-else class="wc-empty">좌측에서 와일드카드를 선택하거나 NEW를 클릭하세요</div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 워크플로우 프로파일 관리 모달 -->
    <transition name="fade">
      <div v-if="showProfileManager" class="wc-overlay" @click.self="showProfileManager = false">
        <div class="wc-modal" style="max-width: 520px;">
          <div class="wc-modal-header">
            <h3>워크플로우 프로파일</h3>
            <span class="wc-path">config/profiles/*.json</span>
            <button class="close-btn" @click="showProfileManager = false">✕</button>
          </div>
          <div class="order-modal-body">
            <div v-if="workflowProfiles.length === 0" class="wc-empty" style="padding: 20px;">
              저장된 프로파일이 없습니다.<br/>
              <small style="color: var(--text-muted)">상단의 + 버튼으로 현재 세팅을 저장하세요.</small>
            </div>
            <div v-else class="order-list">
              <div v-for="prof in workflowProfiles" :key="prof.name" class="profile-item">
                <div class="profile-info">
                  <div class="profile-name">{{ prof.name }}</div>
                  <div class="profile-meta">{{ prof.model || '모델 미지정' }}{{ prof.vae ? ' · VAE: ' + prof.vae : '' }}</div>
                </div>
                <button class="order-btn" @click="loadWorkflowProfile(prof.name)" title="적용">▶</button>
                <button class="order-btn" @click="renameWorkflowProfile(prof.name)" title="이름 변경">✏</button>
                <button class="order-btn" @click="deleteWorkflowProfile(prof.name)" title="삭제" style="color: #f87171;">✕</button>
              </div>
            </div>
            <div class="order-actions">
              <button class="order-save" @click="saveCurrentAsProfile">+ 현재 세팅 저장</button>
              <div style="flex: 1;"></div>
              <button class="order-cancel" @click="showProfileManager = false">닫기</button>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 프롬프트 섹션 순서 매니저 모달 -->
    <transition name="fade">
      <div v-if="showOrderManager" class="wc-overlay" @click.self="showOrderManager = false">
        <div class="wc-modal" style="max-width: 540px;">
          <div class="wc-modal-header">
            <h3>프롬프트 섹션 순서</h3>
            <span class="wc-path">생성 시 합쳐지는 순서를 ↑/↓로 조정. 저장 시 즉시 반영</span>
            <button class="close-btn" @click="showOrderManager = false">✕</button>
          </div>
          <div class="order-modal-body">
            <div class="order-list">
              <div v-for="(sec, i) in promptOrderList" :key="sec.key" class="order-item">
                <span class="order-num">{{ i + 1 }}</span>
                <span class="order-label">{{ sec.label }}</span>
                <button class="order-btn" :disabled="i === 0" @click="moveOrderUp(i)" title="위로">↑</button>
                <button class="order-btn" :disabled="i === promptOrderList.length - 1" @click="moveOrderDown(i)" title="아래로">↓</button>
              </div>
            </div>
            <div class="order-preview">
              <span class="order-preview-label">미리보기:</span>
              <code class="order-preview-text">{{ promptOrderList.map(s => s.label).join(' → ') }}</code>
            </div>
            <div class="order-actions">
              <button class="order-reset" @click="resetPromptOrder">↺ 기본값 복원</button>
              <div style="flex: 1;"></div>
              <button class="order-cancel" @click="showOrderManager = false">취소</button>
              <button class="order-save" @click="saveOrderAndClose">💾 저장 & 적용</button>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- PR 8: INSTANT WILDCARD Manager Modal -->
    <transition name="fade">
      <div v-if="showInstantWcManager" class="wc-overlay" @click.self="showInstantWcManager = false">
        <div class="wc-modal">
          <div class="wc-modal-header">
            <h3>INSTANT WILDCARD MANAGER</h3>
            <span class="wc-path">save/instant_wildcards.json &nbsp;·&nbsp; 문법: <code>$$name$$</code></span>
            <button class="wc-new-btn" @click="createNewInstantWc">+ NEW</button>
            <button class="close-btn" @click="showInstantWcManager = false">✕</button>
          </div>
          <div class="wc-modal-body">
            <!-- 이름 목록 -->
            <div class="wc-sidebar">
              <div v-for="iw in instantWildcards" :key="iw.name" class="wc-file-item"
                :class="{ active: selectedInstantWc === iw.name }" @click="selectInstantWc(iw.name)">
                <span class="wc-fname">{{ iw.name }}</span>
                <span class="wc-file-count">{{ iw.lines.length }}</span>
                <button class="wc-del" @click.stop="deleteInstantWc(iw.name)">✕</button>
              </div>
              <div v-if="instantWildcards.length === 0" class="wc-empty" style="padding: 12px; font-size: 11px;">
                와일드카드가 없습니다. + NEW로 추가하세요.
              </div>
            </div>
            <!-- 편집 영역 -->
            <div class="wc-content">
              <template v-if="selectedInstantWcData">
                <div class="wc-content-header">
                  <h4>{{ selectedInstantWc }}</h4>
                  <span class="wc-syntax">사용: <code>{{'$$' + selectedInstantWc + '$$'}}</code> ·
                    가중치: <code>{100}:tag</code></span>
                </div>
                <div class="wc-blocks">
                  <div v-for="(line, li) in iwEditLines" :key="li" class="wc-block-row">
                    <span class="wc-block-idx">{{ li + 1 }}</span>
                    <input v-model="iwEditLines[li]" class="wc-block-input"
                      :placeholder="li === 0 ? '예: happy 또는 {100}:happy (가중치)' : ''"
                      @keydown.enter="iwEditLines.push('')" />
                    <button class="wc-block-rm" @click="iwEditLines.splice(li, 1)">✕</button>
                  </div>
                  <button class="wc-add-line" @click="iwEditLines.push('')">+ 줄 추가</button>
                </div>
                <div class="wc-bottom-bar">
                  <span style="font-size: 11px; color: var(--text-muted); margin-right: auto;">
                    💡 <b>$$name$$</b>을 프롬프트에 넣으면 생성 시 라인 중 하나를 뽑아 치환합니다.
                  </span>
                  <button class="wc-save-btn" @click="saveCurrentInstantWc">💾 SAVE</button>
                </div>
              </template>
              <div v-else class="wc-empty">좌측에서 선택하거나 NEW를 클릭하세요</div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Generation Stats Modal -->
    <transition name="fade">
      <div v-if="showStatsModal" class="stats-overlay" @click.self="showStatsModal = false">
        <div class="stats-modal">
          <div class="stats-header">
            <h3>GENERATION STATISTICS</h3>
            <button class="close-btn" @click="showStatsModal = false">X</button>
          </div>
          <div class="stats-body" v-if="genStats.total > 0">
            <div class="stats-cards">
              <div class="stat-card">
                <div class="stat-val">{{ genStats.total }}</div>
                <div class="stat-label">Total</div>
              </div>
              <div class="stat-card accent">
                <div class="stat-val">{{ genStats.success_rate }}%</div>
                <div class="stat-label">Success</div>
              </div>
              <div class="stat-card">
                <div class="stat-val">{{ genStats.avg_time }}s</div>
                <div class="stat-label">Avg Time</div>
              </div>
              <div class="stat-card">
                <div class="stat-val">{{ formatTime(genStats.total_time) }}</div>
                <div class="stat-label">Total Time</div>
              </div>
            </div>

            <div class="stats-section" v-if="genStats.daily && genStats.daily.length">
              <h4>DAILY GENERATIONS (30 days)</h4>
              <div class="daily-chart">
                <div v-for="d in genStats.daily" :key="d.date" class="daily-bar-wrap"
                  :title="d.date + ': ' + d.count + '장'">
                  <div class="daily-bar" :style="{ height: genStats.daily_max ? (d.count / genStats.daily_max * 100) + '%' : '0%' }"></div>
                </div>
              </div>
              <div class="daily-labels">
                <span>30일 전</span><span>오늘</span>
              </div>
            </div>

            <div class="stats-two-col">
              <div class="stats-section" v-if="genStats.top_models && genStats.top_models.length">
                <h4>TOP MODELS</h4>
                <div v-for="m in genStats.top_models" :key="m.name" class="stats-bar-row">
                  <span class="bar-name">{{ m.name }}</span>
                  <div class="bar-track"><div class="bar-fill" :style="{ width: (m.count / genStats.total * 100) + '%' }"></div></div>
                  <span class="bar-count">{{ m.count }}</span>
                </div>
              </div>
              <div class="stats-section" v-if="genStats.top_resolutions && genStats.top_resolutions.length">
                <h4>TOP RESOLUTIONS</h4>
                <div v-for="r in genStats.top_resolutions" :key="r.res" class="stats-bar-row">
                  <span class="bar-name">{{ r.res }}</span>
                  <div class="bar-track"><div class="bar-fill" :style="{ width: (r.count / genStats.total * 100) + '%' }"></div></div>
                  <span class="bar-count">{{ r.count }}</span>
                </div>
              </div>
            </div>

            <div class="stats-section" v-if="genStats.recent && genStats.recent.length">
              <h4>RECENT GENERATIONS</h4>
              <div class="recent-table">
                <div v-for="r in genStats.recent" :key="r.timestamp" class="recent-row">
                  <span class="r-time">{{ r.timestamp?.slice(5, 16).replace('T', ' ') }}</span>
                  <span class="r-status" :class="r.success ? 'ok' : 'fail'">{{ r.success ? 'OK' : 'FAIL' }}</span>
                  <span class="r-dur">{{ r.duration_sec }}s</span>
                  <span class="r-res">{{ r.width }}x{{ r.height }}</span>
                  <span class="r-model">{{ (r.model || '').split('/').pop()?.slice(0, 20) }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="stats-body stats-empty" v-else>
            <div class="stats-empty-msg">아직 생성 기록이 없습니다</div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Global Toast Notifications -->
    <!-- 알림 벨 + 히스토리 패널 -->
    <button class="notif-bell" @click.stop="toggleNotifPanel" title="알림 기록">
      🔔<span v-if="unread > 0" class="notif-badge">{{ unread > 9 ? '9+' : unread }}</span>
    </button>
    <div v-if="showNotifPanel" class="notif-overlay" @click="showNotifPanel = false"></div>
    <transition name="fade">
      <div v-if="showNotifPanel" class="notif-panel" @click.stop>
        <div class="notif-head">
          <span>알림 기록</span>
          <button v-if="toastHistory.length" class="notif-clear" @click="clearNotifHistory">모두 지우기</button>
        </div>
        <div class="notif-list">
          <div v-for="n in toastHistory" :key="n.id" class="notif-item" :class="n.type">
            <span class="notif-ico">{{ n.type === 'error' ? '⚠' : n.type === 'success' ? '✓' : n.type === 'warning' ? '⚠' : 'ℹ' }}</span>
            <span class="notif-msg">{{ n.msg }}</span>
            <span class="notif-time">{{ relTime(n.ts) }}</span>
          </div>
          <div v-if="toastHistory.length === 0" class="notif-empty">알림 없음</div>
        </div>
      </div>
    </transition>

    <Teleport to="body">
      <div class="toast-container" :class="{ 'toast-multi': toasts.length > 1 }">
        <button v-if="toasts.length > 1" class="toast-clear-all" @click="clearAllToasts" title="모두 닫기">
          모두 닫기 ({{ toasts.length }})
        </button>
        <transition-group name="toast" tag="div" class="toast-stack">
          <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">
            <span class="toast-icon">{{ t.type === 'error' ? '⚠' : t.type === 'success' ? '✓' : 'ℹ' }}</span>
            <span class="toast-msg">{{ t.msg }}</span>
            <span v-if="t.count > 1" class="toast-count">×{{ t.count }}</span>
            <button class="toast-close" @click.stop="removeToast(t.id)" title="닫기">✕</button>
          </div>
        </transition-group>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { initBridge, onBackendEvent, getBackend } from './bridge.js'
import { requestAction, useWidgetStore } from './stores/widgetStore.js'

const wStore = useWidgetStore()
const storeWidgets = wStore.widgets
const samplerItems = computed(() => wStore.getProperty('sampler_combo', 'items') || [])
const schedulerItems = computed(() => wStore.getProperty('scheduler_combo', 'items') || [])
const upscalerItems = computed(() => wStore.getProperty('upscaler_combo', 'items') || [])
const sam3CheckpointItems = computed(() => wStore.getProperty('_sam3_checkpoint', 'items') || ['sam3.pt'])
const sam3DeviceItems = ['cuda', 'auto', 'cpu']
const sam3FillItems = ['fill', 'original', 'latent noise', 'latent nothing']
const adModelItems = ref([])
// ADetailer 슬롯 별도 Checkpoint/VAE 목록 (s1/s2 동일하게 Python이 채움)
const adCheckpointItems = computed(() => wStore.getProperty('_ad_s1_ckpt', 'items') || ['Use same checkpoint'])
const adVaeItems = computed(() => wStore.getProperty('_ad_s1_vae', 'items') || ['Use same VAE'])
// Hires 전용 Checkpoint/Sampler/Scheduler (Python이 'Use same ...' 접두 포함해 채움)
const hiresCheckpointItems = computed(() => wStore.getProperty('hires_checkpoint_combo', 'items') || ['Use same checkpoint'])
const hiresSamplerItems = computed(() => wStore.getProperty('hires_sampler_combo', 'items') || ['Use same sampler'])
const hiresSchedulerItems = computed(() => wStore.getProperty('hires_scheduler_combo', 'items') || ['Use same scheduler'])

// Hires/ADetailer 체크박스 (proxy 연동)
const randomResEnabled = computed({ get: () => storeWidgets.random_res_check === 'true', set: v => { storeWidgets.random_res_check = v ? 'true' : 'false'; if (v) loadRandomResList() } })
const autoResEnabled = computed({ get: () => storeWidgets.auto_res_check === 'true', set: v => { storeWidgets.auto_res_check = v ? 'true' : 'false' } })

// 고해상도 모드 — 생성 시점에 width/height × factor 적용 (Python이 처리)
// 입력 해상도는 그대로 유지 (UI에 보이는 값은 base, 실제 생성만 확대)
const highResEnabled = ref(localStorage.getItem('highRes.enabled') === 'true')
const highResFactor = ref(parseFloat(localStorage.getItem('highRes.factor') || '1.5') || 1.5)
// 미리보기 — 8 배수 정렬된 실제 생성 해상도
const hrActualW = computed(() => {
  const w = parseInt(storeWidgets.width_input || 0) || 0
  return Math.max(8, Math.floor((w * highResFactor.value) / 8) * 8)
})
const hrActualH = computed(() => {
  const h = parseInt(storeWidgets.height_input || 0) || 0
  return Math.max(8, Math.floor((h * highResFactor.value) / 8) * 8)
})
// 토글/배율 변경 시 즉시 Python으로 동기화 + localStorage 영속
function _syncHighRes() {
  try {
    localStorage.setItem('highRes.enabled', highResEnabled.value ? 'true' : 'false')
    localStorage.setItem('highRes.factor', String(highResFactor.value))
  } catch {}
  requestAction('set_high_res_factor', {
    enabled: highResEnabled.value,
    factor: highResFactor.value,
  })
}
watch(highResEnabled, _syncHighRes)
watch(highResFactor, _syncHighRes)
// 앱 시작 직후 한 번 — Python이 옛 상태 갖고 있을 수 있어 동기화
setTimeout(_syncHighRes, 400)

// 랜덤 해상도 관리
const randomResList = ref([])
const newResW = ref(832)
const newResH = ref(1216)
async function loadRandomResList() {
  const bk = await getBackend()
  if (bk.getRandomResolutions) {
    bk.getRandomResolutions((json) => {
      try { randomResList.value = JSON.parse(json) } catch {}
    })
  }
}
function addRandomRes() {
  const w = Math.round((newResW.value || 832) / 8) * 8
  const h = Math.round((newResH.value || 1216) / 8) * 8
  if (w < 256 || h < 256) return
  randomResList.value.push([w, h, `${w}x${h}`])
  requestAction('set_random_resolutions', { list: randomResList.value })
}
function removeRandomRes(i) {
  randomResList.value.splice(i, 1)
  requestAction('set_random_resolutions', { list: randomResList.value })
}
const negpipEnabled = computed({ get: () => storeWidgets.negpip_group === 'true', set: v => { storeWidgets.negpip_group = v ? 'true' : 'false' } })

const hires_enabled = computed({ get: () => storeWidgets.hires_options_group === 'true', set: v => { storeWidgets.hires_options_group = v ? 'true' : 'false' } })
// Rating 필터
const ratingFilters = reactive([
  { key: 'g', label: 'G', on: true },
  { key: 's', label: 'S', on: true },
  { key: 'q', label: 'Q', on: false },
  { key: 'e', label: 'E', on: false },
])
// localStorage에서 복원
try {
  const saved = JSON.parse(window.localStorage.getItem('ratingFilter') || '[]')
  if (saved.length === 4) saved.forEach((v, i) => { ratingFilters[i].on = v })
} catch {}
function saveUiPrefs(payload) {
  requestAction('save_ui_prefs', payload)
}
function saveRatingFilter() {
  window.localStorage.setItem('ratingFilter', JSON.stringify(ratingFilters.map(r => r.on)))
  saveUiPrefs({ ratingFilter: ratingFilters.map(r => r.on) })
  // Python에 전달
  requestAction('set_rating_filter', { ratings: ratingFilters.filter(r => r.on).map(r => r.key) })
}

const removeArtist = computed({ get: () => storeWidgets.chk_remove_artist === 'true', set: v => { storeWidgets.chk_remove_artist = v ? 'true' : 'false' } })
const removeCopyright = computed({ get: () => storeWidgets.chk_remove_copyright === 'true', set: v => { storeWidgets.chk_remove_copyright = v ? 'true' : 'false' } })
const removeCharacter = computed({ get: () => storeWidgets.chk_remove_character === 'true', set: v => { storeWidgets.chk_remove_character = v ? 'true' : 'false' } })
const removeCharacterFeatures = computed({ get: () => storeWidgets.chk_remove_character_features === 'true', set: v => { storeWidgets.chk_remove_character_features = v ? 'true' : 'false' } })
const removeMeta = computed({ get: () => storeWidgets.chk_remove_meta === 'true', set: v => { storeWidgets.chk_remove_meta = v ? 'true' : 'false' } })
const removeCensorship = computed({ get: () => storeWidgets.chk_remove_censorship === 'true', set: v => { storeWidgets.chk_remove_censorship = v ? 'true' : 'false' } })
const removeText = computed({ get: () => storeWidgets.chk_remove_text === 'true', set: v => { storeWidgets.chk_remove_text = v ? 'true' : 'false' } })
const autoCharFeatures = computed({ get: () => storeWidgets.chk_auto_char_features === 'true', set: v => { storeWidgets.chk_auto_char_features = v ? 'true' : 'false' } })
const autoRemoveCharFeatures = computed({ get: () => storeWidgets.chk_auto_remove_char_features === 'true', set: v => { storeWidgets.chk_auto_remove_char_features = v ? 'true' : 'false' } })
const ad_enabled = computed({ get: () => storeWidgets.adetailer_group === 'true', set: v => { storeWidgets.adetailer_group = v ? 'true' : 'false' } })
const sam3_enabled = computed({ get: () => storeWidgets.sam3_group === 'true', set: v => { storeWidgets.sam3_group = v ? 'true' : 'false' } })
const ad_s1_enabled = computed({ get: () => storeWidgets.ad_slot1_group === 'true', set: v => { storeWidgets.ad_slot1_group = v ? 'true' : 'false' } })
const ad_s2_enabled = computed({ get: () => storeWidgets.ad_slot2_group === 'true', set: v => { storeWidgets.ad_slot2_group = v ? 'true' : 'false' } })
import PromptPanel from './components/PromptPanel.vue'
import CustomSelect from './components/CustomSelect.vue'
import TabBar from './components/TabBar.vue'
import QueuePanel from './components/QueuePanel.vue'
import CharacterPresetModal from './components/CharacterPresetModal.vue'
import ABTestModal from './components/ABTestModal.vue'
import CharFeatureOverrideModal from './components/CharFeatureOverrideModal.vue'
import LoraManagerModal from './components/LoraManagerModal.vue'
import CondPromptModal from './components/CondPromptModal.vue'
import { loadCondRules, condEnabled } from './composables/condRules.js'
import { uiModals, closeCharPresetModal, openAbTestModal, closeAbTestModal,
         openCharOverrideModal, closeCharOverrideModal } from './composables/uiModals.js'

const currentImage = ref('')
const imageVersions = reactive({})
// HISTORY 선택 이미지 테두리 깜빡임 (Settings에서 on/off)
const historyBlink = ref(window.localStorage.getItem('historyBlinkSelected') !== 'false')
const resolution = ref('')
const seed = ref('')
const status = ref('')
const isGenerating = ref(false)
const progressVal = ref(0)
const genStartTime = ref(0)
const genEta = ref('')
const showLeftPanel = ref(true)
const showExtendPanel = ref(false)
const historyImages = ref([])
const histPage = ref(0)
const histPerPage = 5

// EXIF
const activeExifTab = ref('positive')
const exifTabs = [
  { id: 'positive', label: 'Positive' },
  { id: 'negative', label: 'Negative' },
  { id: 'params', label: 'Parameters' },
]
const currentExif = ref({ prompt: '', negative: '', raw: '' })
const exifContent = computed(() => {
  if (activeExifTab.value === 'positive') return currentExif.value.prompt || 'No EXIF data'
  if (activeExifTab.value === 'negative') return currentExif.value.negative || ''
  return currentExif.value.raw || ''
})

const autoMode = ref(false)
const isAutomating = ref(false)
const autoGenCount = ref(0)
const autoWaiting = ref(false)
const deckRemaining = ref(0)
const deckTotal = ref(0)
const deckUsed = ref(0)
const deckAllowDup = ref(false)
// 자동화 대기 카운트다운 (다음 생성까지) — Search % 바 느낌
const waitRemainingMs = ref(0)
const waitTotalMs = ref(0)
const waitSec = computed(() => (waitRemainingMs.value / 1000).toFixed(1))
const waitPct = computed(() => {
  if (waitTotalMs.value <= 0) return 0
  const elapsed = waitTotalMs.value - waitRemainingMs.value
  return Math.max(0, Math.min(100, (elapsed / waitTotalMs.value) * 100))
})
const vramInfo = ref({ used: 0, total: 0, pct: 0 })
const vramClass = computed(() => vramInfo.value.pct > 90 ? 'critical' : vramInfo.value.pct > 70 ? 'warn' : 'ok')
const vramTooltip = computed(() => {
  const v = vramInfo.value
  if (!v.total) return ''
  const free = (v.total - v.used).toFixed(1)
  let msg = `사용: ${v.used}GB / 전체: ${v.total}GB (여유: ${free}GB)`
  if (vramClass.value === 'critical') msg += '\n⚠ VRAM 부족 — 해상도/배치 크기를 줄이거나 모델 unload 권장'
  else if (vramClass.value === 'warn') msg += '\n▲ 70% 초과 — 추가 작업 시 OOM 가능성'
  msg += '\n\n클릭하여 백엔드 모델 unload 요청'
  return msg
})
function onVramClick() {
  // 백엔드에 unload 요청 — 사용자가 명시적으로 메모리 정리하고 싶을 때
  if (vramClass.value === 'critical') {
    if (!confirm(`VRAM 사용량이 ${vramInfo.value.pct}%입니다. 백엔드에서 모델을 unload 할까요?`)) return
  }
  requestAction('unload_model_request', {})
  requestAction('show_toast', { type: 'info', msg: '백엔드에 모델 unload 요청 전송됨' })
}
const autoSettings = reactive({ mode: 'count', limit: 10, repeat: 1, delay: 1.0, allowDupes: false, maxRetries: 2, cleanupEveryN: 0 })

function syncAutomationSettings() {
  const limit = Number(autoSettings.limit)
  const repeat = Number(autoSettings.repeat)
  const delay = Number(autoSettings.delay)
  const maxRetries = Number(autoSettings.maxRetries)
  const cleanupEveryN = Number(autoSettings.cleanupEveryN)

  action('set_automation_settings', {
    mode: autoSettings.mode,
    limit: Number.isFinite(limit) && limit > 0 ? limit : 10,
    repeat: Number.isFinite(repeat) && repeat > 0 ? repeat : 1,
    delay: Number.isFinite(delay) && delay >= 0 ? delay : 1,
    allowDupes: !!autoSettings.allowDupes,
    maxRetries: Number.isFinite(maxRetries) && maxRetries >= 0 ? maxRetries : 2,
    cleanupEveryN: Number.isFinite(cleanupEveryN) && cleanupEveryN >= 0 ? cleanupEveryN : 0,
  })
}

// PR 9: 서버 → Vue 푸시 중에는 watch가 다시 서버로 보내지 않도록 가드
let _applyingAutoFromServer = false

watch(autoSettings, () => {
  if (_applyingAutoFromServer) return
  syncAutomationSettings()
}, { deep: true })

// Toast 알림 시스템
const toasts = ref([])
let toastId = 0
const MAX_TOASTS = 5

// 알림(토스트) 히스토리 — 🔔 버튼으로 사라진 토스트 다시 보기
const toastHistory = ref([])
const showNotifPanel = ref(false)
const unread = ref(0)
const MAX_HISTORY = 40
function toggleNotifPanel() { showNotifPanel.value = !showNotifPanel.value; if (showNotifPanel.value) unread.value = 0 }
function clearNotifHistory() { toastHistory.value = [] }
function relTime(ts) {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return `${s}초 전`
  const m = Math.floor(s / 60); if (m < 60) return `${m}분 전`
  const h = Math.floor(m / 60); if (h < 24) return `${h}시간 전`
  return `${Math.floor(h / 24)}일 전`
}

function addToast(type, msg) {
  const id = toastId++
  // 같은 메시지가 직전에 있으면 카운터만 증가 (스팸 방지)
  const last = toasts.value[toasts.value.length - 1]
  if (last && last.type === type && last.msg === msg) {
    last.count = (last.count || 1) + 1
    last._ts = Date.now()  // 타이머 리셋
    // 기존 타이머 취소 + 새로 설정
    if (last._timer) clearTimeout(last._timer)
    last._timer = setTimeout(() => removeToast(last.id), 3000)
    return
  }
  const toast = { id, type, msg, count: 1, _ts: Date.now() }
  toasts.value.push(toast)
  toast._timer = setTimeout(() => removeToast(id), 3000)
  // 스택 초과분 — 가장 오래된 것부터 제거 (화면엔 최대 5개)
  while (toasts.value.length > MAX_TOASTS) {
    const oldest = toasts.value.shift()
    if (oldest._timer) clearTimeout(oldest._timer)
  }
  // 알림 기록에 누적 (사라진 토스트도 🔔에서 다시 볼 수 있게)
  toastHistory.value.unshift({ id, type, msg, ts: Date.now() })
  if (toastHistory.value.length > MAX_HISTORY) toastHistory.value.length = MAX_HISTORY
  if (!showNotifPanel.value) unread.value++
}
function removeToast(id) {
  const t = toasts.value.find(x => x.id === id)
  if (t && t._timer) clearTimeout(t._timer)
  toasts.value = toasts.value.filter(t => t.id !== id)
}
function clearAllToasts() {
  toasts.value.forEach(t => { if (t._timer) clearTimeout(t._timer) })
  toasts.value = []
}

// Extended panel state (NegPiP/조건부만 로컬)
const extWidgets = reactive({
  negpip_enabled: false,
  cond_prevent_dupe: true,
  cond_pos_on: false, cond_neg_on: false,
  cond_pos_rules: '', cond_neg_rules: '',
})
const loraStack = reactive([])

// LoRA localStorage 복원
try {
  const saved = JSON.parse(window.localStorage.getItem('loraStack') || '[]')
  if (Array.isArray(saved)) saved.forEach(l => loraStack.push(l))
} catch {}

let _loraInitialized = false
function _saveLoraStack() {
  try { window.localStorage.setItem('loraStack', JSON.stringify(loraStack)) } catch {}
  // 초기화 완료 전 빈 배열로 덮어쓰기 방지, 이후에는 빈 배열도 정상 저장
  if (!_loraInitialized && loraStack.length === 0) return
  _loraInitialized = true
  saveUiPrefs({ loraStack: loraStack.map(l => ({ ...l })) })
}

function syncLoraStack() {
  requestAction('set_lora_stack', {
    entries: loraStack.map(l => ({
      name: l.name || '',
      weight: Number.isFinite(Number(l.weight)) ? Number(l.weight) / 100 : 0.8,
      enabled: l.enabled !== false,
      triggerWords: Array.isArray(l.triggerWords) ? l.triggerWords : [],
    })),
  })
}

// LoRA 추가 함수 (Python에서 호출)
function addLoraToStack(name, weight, triggerWords = []) {
  const existing = loraStack.find(l => l.name === name)
  if (existing) {
    existing.weight = Math.round(weight * 100); existing.enabled = true
    if (triggerWords.length) existing.triggerWords = triggerWords
  }
  else loraStack.push({ name, weight: Math.round(weight * 100), enabled: true, triggerWords })
  _saveLoraStack()
}

// LoRA 변경 감시 → 자동 저장 (복원 중에는 무시)
let _loraRestoring = false
watch(loraStack, () => {
  if (_loraRestoring) return
  _saveLoraStack()
  syncLoraStack()
}, { deep: true })
function insertTriggerWord(tw) {
  const cur = storeWidgets.main_prompt_text || ''
  if (!cur.toLowerCase().includes(tw.toLowerCase())) {
    storeWidgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tw + ', ' : tw + ', '
    addToast('info', `트리거 워드 삽입: ${tw}`)
  } else {
    addToast('info', `이미 포함된 태그: ${tw}`)
  }
}

// LoRA 빠른 컨트롤 — 전체 on/off + 트리거 일괄삽입
const allLorasOn = computed(() => loraStack.length > 0 && loraStack.every(l => l.enabled))
function toggleAllLoras(on) { loraStack.forEach(l => { l.enabled = on }) }
function insertAllTriggers() {
  const tws = []
  for (const l of loraStack) {
    if (l.enabled && Array.isArray(l.triggerWords)) {
      for (const tw of l.triggerWords) if (tw && !tws.includes(tw)) tws.push(tw)
    }
  }
  if (!tws.length) { addToast('info', '활성 LoRA의 트리거 워드가 없습니다'); return }
  let cur = (storeWidgets.main_prompt_text || '').trim()
  const lower = cur.toLowerCase()
  const add = tws.filter(tw => !lower.includes(tw.toLowerCase()))
  if (!add.length) { addToast('info', '트리거가 이미 모두 포함됨'); return }
  storeWidgets.main_prompt_text = cur ? (cur.replace(/,?\s*$/, '') + ', ' + add.join(', ')) : add.join(', ')
  addToast('success', `트리거 ${add.length}개 삽입`)
}
// LoRA 매니저(Vue 모달)
const showLoraModal = ref(false)
const showCondModal = ref(false)   // 조건부 프롬프트 모달
function onLoraAdd(p) {
  addLoraToStack(p.name, typeof p.weight === 'number' ? p.weight : 1.0, p.triggerWords || [])
  addToast('success', `LoRA 추가: ${p.name}`)
}
// LoRA 세트 저장/불러오기 (localStorage 'loraSets')
const loraSets = ref({})
try { const s = JSON.parse(window.localStorage.getItem('loraSets') || '{}'); if (s && typeof s === 'object') loraSets.value = s } catch {}
const loraSetName = ref('')
const loraSetSel = ref('')
const loraSetNames = computed(() => Object.keys(loraSets.value))
function _persistLoraSets() { try { window.localStorage.setItem('loraSets', JSON.stringify(loraSets.value)) } catch {} }
function saveLoraSet() {
  const name = loraSetName.value.trim()
  if (!name || !loraStack.length) return
  loraSets.value = { ...loraSets.value, [name]: loraStack.map(l => ({ ...l })) }
  _persistLoraSets()
  loraSetSel.value = name; loraSetName.value = ''
  addToast('success', `LoRA 세트 저장: ${name} (${loraStack.length}개)`)
}
function loadLoraSet() {
  const set = loraSets.value[loraSetSel.value]
  if (!Array.isArray(set)) return
  loraStack.splice(0, loraStack.length, ...set.map(l => ({ ...l })))
  _saveLoraStack(); syncLoraStack()
  addToast('success', `세트 적용: ${loraSetSel.value} (${set.length}개)`)
}
function deleteLoraSet() {
  const n = loraSetSel.value
  if (!n) return
  const cp = { ...loraSets.value }; delete cp[n]
  loraSets.value = cp; _persistLoraSets(); loraSetSel.value = ''
  addToast('info', `세트 삭제: ${n}`)
}

// History pagination
const visibleHistory = computed(() => {
  const start = histPage.value * histPerPage
  return historyImages.value.slice(start, start + histPerPage)
})

// Context menu (화면 밖 방지)
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })
const ctxMenuStyle = computed(() => {
  // menuH는 실제 메뉴 높이(항목 13행 ≈ 400px) 이상으로 잡아야 하단 flip이
  // 충분히 동작. 250이면 항목 추가 후 실제 높이보다 작아 하단 잘림 발생했음.
  const menuW = 210, menuH = 420
  let x = ctxMenu.value.x, y = ctxMenu.value.y
  if (x + menuW > window.innerWidth) x = window.innerWidth - menuW - 10
  if (y + menuH > window.innerHeight) y = window.innerHeight - menuH - 10
  if (x < 0) x = 10
  if (y < 8) y = 8
  return { top: y + 'px', left: x + 'px' }
})

const wildcards = ref([])
const showPresetManager = ref(false)
const presetList = ref([])
const selectedPreset = ref('')
const presetPreview = ref(null)

async function loadPresetList() {
  const bk = await getBackend()
  if (bk.getPresetList) bk.getPresetList((json) => { try { presetList.value = JSON.parse(json) } catch {} })
}
async function loadPresetPreview(name) {
  const bk = await getBackend()
  if (bk.getPresetData) bk.getPresetData(name, (json) => { try { presetPreview.value = JSON.parse(json) } catch {} })
}
function loadSelectedPreset() {
  if (!selectedPreset.value) return
  action('load_preset_by_name', { name: selectedPreset.value })
  showPresetManager.value = false
}
function deleteSelectedPreset() {
  if (!selectedPreset.value || !confirm(`"${selectedPreset.value}" 삭제?`)) return
  action('delete_preset', { name: selectedPreset.value })
  presetList.value = presetList.value.filter(p => p !== selectedPreset.value)
  selectedPreset.value = ''; presetPreview.value = null
}
function saveNewPreset() {
  const name = prompt('프리셋 이름:')
  if (!name) return
  action('save_preset_by_name', { name })
  presetList.value.push(name)
  addToast('success', `프리셋 "${name}" 저장됨`)
}

const showWeightManager = ref(false)
const globalWeights = reactive([])  // [{tag, weight}]

function saveGlobalWeights() {
  const valid = globalWeights.filter(w => w.tag.trim())
  action('save_global_weights', { weights: valid })
  showWeightManager.value = false
}

// 프롬프트에 글로벌 가중치 적용
function applyGlobalWeights(text) {
  if (!globalWeights.length) return text
  let result = text
  for (const w of globalWeights) {
    if (!w.tag.trim()) continue
    const tag = w.tag.trim()
    const weight = (w.weight / 100).toFixed(2)
    if (weight === '1.00') continue
    // 이미 가중치가 있으면 교체, 없으면 추가
    const regex = new RegExp(`\\(${tag.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}:[\\d.]+\\)`, 'gi')
    if (regex.test(result)) {
      result = result.replace(regex, `(${tag}:${weight})`)
    } else {
      const plain = new RegExp(`(?<![:(])\\b${tag.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}\\b(?![:\\)])`, 'gi')
      result = result.replace(plain, `(${tag}:${weight})`)
    }
  }
  return result
}
// Generation Stats
const showStatsModal = ref(false)
const genStats = reactive({ total: 0, success: 0, fail: 0, success_rate: 0, avg_time: 0, total_time: 0, daily: [], daily_max: 0, top_models: [], top_resolutions: [], recent: [] })
async function loadGenStats() {
  const bk = await getBackend()
  if (bk.getGenStats) {
    bk.getGenStats((json) => {
      try { Object.assign(genStats, JSON.parse(json)) } catch {}
    })
  }
}
function formatTime(sec) {
  if (!sec) return '0s'
  if (sec < 60) return sec + 's'
  if (sec < 3600) return Math.floor(sec / 60) + 'm ' + Math.round(sec % 60) + 's'
  return Math.floor(sec / 3600) + 'h ' + Math.floor((sec % 3600) / 60) + 'm'
}

const showWcManager = ref(false)
const selectedWc = ref('')
const selectedWcData = computed(() => wildcards.value.find(w => w.name === selectedWc.value) || null)
const wcEditLines = ref([])
const wcInsertTarget = ref('main')

// 워크플로우 프로파일
const showProfileManager = ref(false)
const workflowProfiles = ref([])  // [{name, created_at, model, vae}]
const profileNames = computed(() => workflowProfiles.value.map(p => p.name))

function loadWorkflowProfilesList() {
  action('workflow_profile_list', {})
}
function loadWorkflowProfile(name) {
  if (!name) return
  action('workflow_profile_load', { name })
}
function saveCurrentAsProfile() {
  const name = window.prompt('프로파일 이름 (예: ANIMA Pony, Flux 표준):', '')
  if (!name || !name.trim()) return
  // 이미 있으면 덮어쓰기 확인
  const existing = workflowProfiles.value.find(p => p.name === name.trim())
  if (existing && !window.confirm(`'${name}' 이미 존재합니다. 덮어쓸까요?`)) return
  action('workflow_profile_save', { name: name.trim() })
}
function deleteWorkflowProfile(name) {
  if (!window.confirm(`'${name}' 삭제할까요?`)) return
  action('workflow_profile_delete', { name })
  workflowProfiles.value = workflowProfiles.value.filter(p => p.name !== name)
}
function renameWorkflowProfile(oldName) {
  const newName = window.prompt(`'${oldName}' → 새 이름:`, oldName)
  if (!newName || !newName.trim() || newName.trim() === oldName) return
  action('workflow_profile_rename', { old: oldName, new: newName.trim() })
}

// 프롬프트 섹션 순서 매니저
const showOrderManager = ref(false)
const promptOrderList = ref([])  // [{key, label}, ...]

function loadPromptOrder() {
  action('prompt_order_list', {})
}
function moveOrderUp(i) {
  if (i <= 0) return
  const arr = [...promptOrderList.value]
  ;[arr[i - 1], arr[i]] = [arr[i], arr[i - 1]]
  promptOrderList.value = arr
}
function moveOrderDown(i) {
  if (i >= promptOrderList.value.length - 1) return
  const arr = [...promptOrderList.value]
  ;[arr[i], arr[i + 1]] = [arr[i + 1], arr[i]]
  promptOrderList.value = arr
}
function saveOrderAndClose() {
  const order = promptOrderList.value.map(s => s.key)
  action('prompt_order_save', { order })
  showOrderManager.value = false
  addToast('success', '프롬프트 순서 저장됨')
}
function resetPromptOrder() {
  if (!window.confirm('기본 순서(인물수 → 캐릭터 → 작품 → 작가 → 선행 → 메인 → 후행)로 복원할까요?')) return
  action('prompt_order_reset', {})
  addToast('info', '기본 순서로 복원')
}

// PR 8: Instant Wildcards 상태
const showInstantWcManager = ref(false)
const instantWildcards = ref([])  // [{name, lines}]
const selectedInstantWc = ref('')
const selectedInstantWcData = computed(() =>
  instantWildcards.value.find(w => w.name === selectedInstantWc.value) || null
)
const iwEditLines = ref([])

function selectInstantWc(name) {
  selectedInstantWc.value = name
  const iw = instantWildcards.value.find(w => w.name === name)
  iwEditLines.value = iw ? [...iw.lines] : []
}

function loadInstantWcList() {
  action('instant_wildcards_list', {})
}

function createNewInstantWc() {
  const name = window.prompt('새 인스턴트 와일드카드 이름 (영숫자/_/.만):', '')
  if (!name || !/^[\w./]+$/.test(name)) return
  if (instantWildcards.value.find(w => w.name === name)) {
    addToast('error', '이미 존재함')
    return
  }
  instantWildcards.value.push({ name, lines: [''] })
  selectedInstantWc.value = name
  iwEditLines.value = ['']
  action('instant_wildcards_save', { name, lines: [''] })
}

function saveCurrentInstantWc() {
  if (!selectedInstantWc.value) return
  const lines = iwEditLines.value.filter(l => l !== undefined)
  action('instant_wildcards_save', { name: selectedInstantWc.value, lines })
  // 로컬 미러
  const iw = instantWildcards.value.find(w => w.name === selectedInstantWc.value)
  if (iw) iw.lines = lines
  addToast('success', `인스턴트 와일드카드 저장: $$${selectedInstantWc.value}$$`)
}

function deleteInstantWc(name) {
  if (!window.confirm(`'${name}' 삭제할까요?`)) return
  action('instant_wildcards_delete', { name })
  instantWildcards.value = instantWildcards.value.filter(w => w.name !== name)
  if (selectedInstantWc.value === name) {
    selectedInstantWc.value = ''
    iwEditLines.value = []
  }
}

function selectWildcard(name) {
  selectedWc.value = name
  const wc = wildcards.value.find(w => w.name === name)
  wcEditLines.value = wc ? [...wc.tags] : []
}

async function saveCurrentWildcard() {
  if (!selectedWc.value) return
  const bk = await getBackend()
  const content = wcEditLines.value.join('\n')
  bk.saveWildcard(selectedWc.value + '.txt', content, (json) => {
    try { const r = JSON.parse(json); if (r.ok) addToast('success', '와일드카드 저장됨') } catch {}
  })
  // 로컬 업데이트
  const wc = wildcards.value.find(w => w.name === selectedWc.value)
  if (wc) wc.tags = wcEditLines.value.filter(l => l.trim())
}

async function createNewWildcard() {
  const name = prompt('새 와일드카드 이름:')
  if (!name) return
  const bk = await getBackend()
  bk.saveWildcard(name + '.txt', '', () => {
    wildcards.value.push({ name, file: name + '.txt', tags: [] })
    selectedWc.value = name; wcEditLines.value = []
  })
}

async function deleteWildcard(name) {
  if (!confirm(`"${name}" 와일드카드를 삭제할까요?`)) return
  const bk = await getBackend()
  bk.deleteWildcard(name, () => {
    wildcards.value = wildcards.value.filter(w => w.name !== name)
    if (selectedWc.value === name) { selectedWc.value = ''; wcEditLines.value = [] }
  })
}

async function renameWildcard(oldName) {
  const newName = prompt('새 이름:', oldName)
  if (!newName || newName === oldName) return
  const bk = await getBackend()
  bk.renameWildcard(oldName, newName, () => {
    const wc = wildcards.value.find(w => w.name === oldName)
    if (wc) { wc.name = newName; wc.file = newName + '.txt' }
    if (selectedWc.value === oldName) selectedWc.value = newName
  })
}

const wcRenaming = ref(false)
const wcNewName = ref('')
const wcRenameRef = ref(null)

function startWcRename() {
  wcRenaming.value = true
  wcNewName.value = selectedWc.value
  nextTick(() => { if (wcRenameRef.value) wcRenameRef.value.focus() })
}

async function finishWcRename() {
  wcRenaming.value = false
  const newName = wcNewName.value.trim()
  if (!newName || newName === selectedWc.value) return
  const bk = await getBackend()
  bk.renameWildcard(selectedWc.value, newName, () => {
    const wc = wildcards.value.find(w => w.name === selectedWc.value)
    if (wc) { wc.name = newName; wc.file = newName + '.txt' }
    selectedWc.value = newName
    addToast('success', '이름 변경됨')
  })
}

// USE = 와일드카드 사용 문법 삽입 (__name__)
function useWcSyntax() {
  if (!selectedWc.value) return
  const syntax = `__${selectedWc.value}__`
  if (wcInsertTarget.value === 'clipboard') {
    navigator.clipboard?.writeText(syntax)
    addToast('info', '문법 복사됨: ' + syntax)
  } else {
    const targetMap = { main: 'main_prompt_text', prefix: 'prefix_prompt_text', suffix: 'suffix_prompt_text' }
    const key = targetMap[wcInsertTarget.value] || 'main_prompt_text'
    const cur = storeWidgets[key] || ''
    storeWidgets[key] = cur ? cur.replace(/,?\s*$/, '') + ', ' + syntax + ', ' : syntax + ', '
    addToast('success', syntax + ' 삽입됨')
  }
}

function addWcLine(afterIdx) { wcEditLines.value.splice(afterIdx + 1, 0, '') }

function openWildcardByName(name) {
  showWcManager.value = true
  selectWildcard(name)
}

function action(name, payload = {}) { requestAction(name, payload) }

function insertWildcardTag(tag) {
  const cur = storeWidgets.main_prompt_text || ''
  storeWidgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tag + ', ' : tag + ', '
}

function doGenerate() {
  // 자동화 중이면 중지
  if (isAutomating.value) {
    action('stop_automation')
    isAutomating.value = false
    autoWaiting.value = false
    return
  }
  // 글로벌 가중치 적용
  if (globalWeights.length > 0) {
    const cur = storeWidgets.main_prompt_text || ''
    const weighted = applyGlobalWeights(cur)
    if (weighted !== cur) storeWidgets.main_prompt_text = weighted
  }
  // LoRA Stack
  const activeLoras = loraStack.filter(l => l.enabled)
  if (activeLoras.length > 0) {
    const loraText = activeLoras.map(l => `<lora:${l.name}:${(l.weight/100).toFixed(2)}>`).join(', ')
    requestAction('set_lora_text', { lora_text: loraText })
  }
  syncAutomationSettings()
  genStartTime.value = Date.now()
  genEta.value = ''
  action('generate')
}

function cancelGeneration() {
  action('cancel_generation')
  // 취소는 backend가 imageGenerated/error를 안 쏠 수 있으므로 즉시 상태 복구
  isGenerating.value = false
  genEta.value = ''
}

function showHistoryMenu(e, path) { ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, path } }
function hideCtxMenu() { ctxMenu.value.show = false }
const ctxAddFavorite = () => { action('add_favorite', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxSendI2I = () => { action('send_to_i2i', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxSendInpaint = () => { action('send_to_inpaint', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxSendEditor = () => { action('send_to_editor', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxCompare = (slot) => { action('send_to_compare', { path: ctxMenu.value.path, slot }); hideCtxMenu() }
const ctxRunAdetailer = () => { action('run_adetailer_single', { path: ctxMenu.value.path, settings: { ad_model: 'face_yolov8n.pt', ad_confidence: 0.3, ad_denoise: 0.4 } }); hideCtxMenu() }
const ctxCopyPath = () => { navigator.clipboard?.writeText(ctxMenu.value.path); hideCtxMenu() }
const ctxPullPrompt = () => { action('pull_prompt_from_image', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxAddToQueue = () => { action('add_image_to_queue', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxDelete = () => {
  const path = ctxMenu.value.path
  action('delete_image', { path })
  // 히스토리에서 즉시 제거
  const idx = historyImages.value.indexOf(path)
  if (idx >= 0) historyImages.value.splice(idx, 1)
  // 현재 보고 있는 이미지였으면 다음 이미지로
  if (currentImage.value === path) {
    currentImage.value = historyImages.value[0] || ''
  }
  hideCtxMenu()
}

async function selectHistoryImage(path) {
  // (선택 시엔 이미지 내용이 안 바뀌므로 cache-bust 하지 않음 — 매 선택마다 썸네일이
  //  재로드되어 점멸하던 버그 수정. 재생성 시 cache-bust는 imageGenerated 핸들러가 처리.)
  currentImage.value = path
  const img = new Image()
  img.onload = () => { resolution.value = `${img.naturalWidth} × ${img.naturalHeight}` }
  img.src = historyImageSrc(path)
  // EXIF 로드
  const backend = await getBackend()
  if (backend.getImageExif) {
    backend.getImageExif(path, (json) => {
      try {
        const d = JSON.parse(json)
        currentExif.value = { prompt: d.prompt || '', negative: d.negative || '', raw: d.raw || '', params: d.params || null, params_line: d.params_line || '' }
      } catch {}
    })
  }
}

function historyImageSrc(path) {
  if (!path) return ''
  return `file:///${path}?t=${imageVersions[path] || 0}`
}

// History 키보드 상하 네비게이션 — 전역 ↑/↓로 이전/다음 이미지 선택.
// 선택이 없으면 첫 이미지부터. 페이지 경계를 넘으면 histPage도 따라 이동.
function navigateHistory(dir) {
  const list = historyImages.value
  if (!list.length) return
  let idx = list.indexOf(currentImage.value)
  if (idx < 0) idx = 0
  else idx = Math.min(list.length - 1, Math.max(0, idx + dir))
  histPage.value = Math.floor(idx / histPerPage)
  selectHistoryImage(list[idx])
}

// 최상단(top=최신)/최하단(bottom=가장 오래됨)으로 바로 이동 (Shift+화살표 등)
function navigateHistoryEdge(edge) {
  const list = historyImages.value
  if (!list.length) return
  const idx = edge === 'top' ? 0 : list.length - 1
  histPage.value = Math.floor(idx / histPerPage)
  selectHistoryImage(list[idx])
}

// 드래그 앤 드롭 지원
function onDragStart(e, path) {
  e.dataTransfer.setData('text/plain', path)
  e.dataTransfer.effectAllowed = 'copy'
}

function onTabChanged(tabName) {
  showLeftPanel.value = ['t2i', 'i2i', 'inpaint'].includes(tabName)
  showExtendPanel.value = false
  hideCtxMenu()
}

async function loadHistory() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages('', (json) => {
      try {
        const arr = JSON.parse(json)  // 무제한 — 생성/저장한 만큼 전부 표시
        historyImages.value = arr
        // localStorage 캐시 갱신 (다음 시작 시 즉시 표시용)
        try { localStorage.setItem('historyImagesCache', JSON.stringify(arr.slice(0, 50))) } catch {}
      } catch {}
    })
  }
}
// 생성된 이미지 추가될 때마다 캐시 동기화
watch(historyImages, (arr) => {
  try { localStorage.setItem('historyImagesCache', JSON.stringify(arr.slice(0, 50))) } catch {}
}, { deep: false })

import { useRouter } from 'vue-router'
const router = useRouter()

// UI 크기 — Chromium zoom 으로 전역 확대 (폰트/아이콘/패딩 비례)
// 변경 시 즉시 반영, localStorage 영속, 다른 탭(Settings)에서 변경하면 storage event로 동기화
const _applyUiScale = (val) => {
  const n = parseFloat(val)
  const scale = (!isNaN(n) && n >= 0.7 && n <= 2.0) ? n : 1.0
  try { document.documentElement.style.zoom = String(scale) } catch {}
}
_applyUiScale(localStorage.getItem('ui.scale') || '1.0')

onMounted(async () => {
  await initBridge()
  storeWidgets.negpip_group = 'true'   // NegPiP 상시 적용 (UI 토글 제거)
  loadCondRules()                      // 조건부 프롬프트 규칙 로드 (모달/Search 공유)
  // Settings 등 다른 곳에서 ui.scale 변경 시 즉시 반영
  window.addEventListener('storage', (e) => {
    if (e.key === 'ui.scale') _applyUiScale(e.newValue)
  })
  // 같은 창에서의 변경 (Settings 슬라이더)도 즉시 — 커스텀 이벤트
  window.addEventListener('uiScaleChanged', (e) => _applyUiScale(e.detail?.value))
  // HISTORY 선택 깜빡임 토글 — Settings에서 변경 시 즉시 반영
  window.addEventListener('historyBlinkChanged', (e) => { historyBlink.value = !!e.detail?.value })
  // localStorage 캐시로 즉시 표시 (응답 빠르게), 그 후 backend에서 최신 가져옴
  try {
    const cached = localStorage.getItem('historyImagesCache')
    if (cached) {
      const arr = JSON.parse(cached)
      if (Array.isArray(arr) && arr.length > 0) historyImages.value = arr
    }
  } catch {}
  // 시작 시 히스토리 자동 로드 — 사용자가 F5 안 눌러도 이전 이미지들 보이게
  loadHistory()
  document.addEventListener('click', hideCtxMenu)
  document.addEventListener('wheel', (e) => { if (e.ctrlKey) e.preventDefault() }, { passive: false })
  // 브라우저 기본 우클릭 메뉴 전역 차단
  document.addEventListener('contextmenu', (e) => { e.preventDefault() })
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'g') { e.preventDefault(); doGenerate() }
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); action('save_settings') }
    if (e.key === 'F5') { e.preventDefault(); loadHistory() }
    // Ctrl+Tab / Ctrl+Shift+Tab — 다음/이전 탭 탐색
    if (e.ctrlKey && e.key === 'Tab') {
      e.preventDefault()
      try { window.dispatchEvent(new CustomEvent('tabBarNavigate', { detail: { direction: e.shiftKey ? -1 : 1 } })) } catch {}
    }
    // ESC — 열려있는 오버레이/모달을 최상위 우선순위로 닫기
    if (e.key === 'Escape') {
      // 1) 최상위 모달이 있으면 그것부터 (z-index 2000)
      if (showPresetManager.value)    { showPresetManager.value = false; return }
      if (showWeightManager.value)    { showWeightManager.value = false; return }
      if (showWcManager.value)        { showWcManager.value = false; return }
      if (showOrderManager.value)     { showOrderManager.value = false; return }
      if (showProfileManager.value)   { showProfileManager.value = false; return }
      if (showInstantWcManager.value) { showInstantWcManager.value = false; return }
      if (showStatsModal.value)       { showStatsModal.value = false; return }
      // 2) 확장 패널 오버레이 (z-index 50)
      if (showExtendPanel.value)      { showExtendPanel.value = false; return }
    }
    // History ↑/↓ 네비게이션 — 입력 필드/모달 포커스 중이 아닐 때만
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const ae = document.activeElement
      const tag = (ae?.tagName || '').toLowerCase()
      const editable = tag === 'input' || tag === 'textarea' || tag === 'select' || ae?.isContentEditable
      const anyModal = showExtendPanel.value || showPresetManager.value || showWeightManager.value
        || showWcManager.value || showOrderManager.value || showProfileManager.value
        || showInstantWcManager.value || showStatsModal.value
      if (!editable && !anyModal && historyImages.value.length) {
        e.preventDefault()
        // 설정된 보조키(기본 Shift) + 화살표 → 최상단/최하단으로 바로 점프
        const mod = localStorage.getItem('historyJumpModifier') || 'shiftKey'
        if (e[mod]) {
          navigateHistoryEdge(e.key === 'ArrowDown' ? 'bottom' : 'top')
        } else {
          navigateHistory(e.key === 'ArrowDown' ? 1 : -1)
        }
      }
    }
  })

  // 초기 rating 필터 전달
  requestAction('set_rating_filter', { ratings: ratingFilters.filter(r => r.on).map(r => r.key) })

  // 워크플로우 프로파일 목록 미리 로드 (드롭다운에 즉시 보이도록)
  setTimeout(loadWorkflowProfilesList, 800)

  onBackendEvent('tabChanged', (tabId) => {
    const targetPath = tabId === 't2i' ? '/' : `/${tabId}`
    router.push(targetPath)
    onTabChanged(tabId)
  })

  onBackendEvent('imageGenerated', async (data) => {
    const parsed = JSON.parse(data)
    if (parsed.path) imageVersions[parsed.path] = Date.now()
    isGenerating.value = false
    genEta.value = ''
    status.value = ''
    // History에서 옛 이미지를 보던 중(브라우징)이면 뷰를 뺏지 않음 — '최신'(또는
    // 미선택)을 보고 있을 때만 새 이미지로 따라간다. 새 이미지는 History 맨 앞에
    // 추가되어 t2i 결과 목록에 표시됨. (선택 중이던 이미지/위치는 그대로 유지)
    const wasViewingLatest = !currentImage.value || currentImage.value === historyImages.value[0]
    if (parsed.path) {
      historyImages.value.unshift(parsed.path)  // 무제한 — 갯수 캡 제거
      if (wasViewingLatest) {
        histPage.value = 0
      } else {
        // 보던 옛 이미지를 계속 보여주도록 그 이미지가 있는 페이지로 유지
        const ci = historyImages.value.indexOf(currentImage.value)
        if (ci >= 0) histPage.value = Math.floor(ci / histPerPage)
      }
    }
    if (wasViewingLatest && parsed.path) {
      currentImage.value = parsed.path
      resolution.value = `${parsed.width} × ${parsed.height}`
      seed.value = String(parsed.seed)
      // 생성 직후 EXIF 자동 로드 (추종 중일 때만 현재 EXIF 갱신)
      const bk = await getBackend()
      if (bk.getImageExif) {
        bk.getImageExif(parsed.path, (json) => {
          try {
            const d = JSON.parse(json)
            currentExif.value = { prompt: d.prompt || '', negative: d.negative || '', raw: d.raw || '', params: d.params || null, params_line: d.params_line || '' }
          } catch {}
        })
      }
    }
  })
  onBackendEvent('generationStarted', () => { isGenerating.value = true; autoWaiting.value = false; progressVal.value = 0; genStartTime.value = Date.now(); genEta.value = '' })
  onBackendEvent('automationStatus', (json) => {
    try {
      const d = JSON.parse(json)
      isAutomating.value = d.running || false
      autoGenCount.value = d.count || 0
      autoWaiting.value = d.waiting || false
      deckRemaining.value = d.deck_remaining || 0
      deckTotal.value = d.deck_total || 0
      deckUsed.value = d.deck_used || 0
      deckAllowDup.value = d.allow_duplicates || false
      waitRemainingMs.value = d.wait_remaining_ms || 0
      waitTotalMs.value = d.wait_total_ms || 0
      if (!d.running) { isGenerating.value = false }
    } catch {}
  })
  // 워크플로우 프로파일 목록 수신
  onBackendEvent('workflowProfilesList', (json) => {
    try {
      const arr = JSON.parse(json)
      if (Array.isArray(arr)) workflowProfiles.value = arr
    } catch {}
  })
  // 프롬프트 섹션 순서 수신
  onBackendEvent('promptOrderLoaded', (json) => {
    try {
      const arr = JSON.parse(json)
      if (Array.isArray(arr)) promptOrderList.value = arr
    } catch {}
  })
  // PR 8: 인스턴트 와일드카드 목록 수신
  onBackendEvent('instantWildcardsList', (json) => {
    try {
      const arr = JSON.parse(json)
      if (Array.isArray(arr)) instantWildcards.value = arr
    } catch {}
  })
  // PR 9: 백엔드가 모드별 자동화 설정을 푸시 (시작 시 + 백엔드 모드 전환 시)
  onBackendEvent('automationSettingsLoaded', (json) => {
    try {
      const d = JSON.parse(json)
      _applyingAutoFromServer = true  // watch에서 다시 서버로 보내는 루프 방지
      if (typeof d.mode === 'string') autoSettings.mode = d.mode
      if (typeof d.limit === 'number') autoSettings.limit = d.limit
      if (typeof d.repeat === 'number') autoSettings.repeat = d.repeat
      if (typeof d.delay === 'number') autoSettings.delay = d.delay
      if (typeof d.allowDupes === 'boolean') autoSettings.allowDupes = d.allowDupes
      if (typeof d.maxRetries === 'number') autoSettings.maxRetries = d.maxRetries
      // watch 콜백이 큐잉 처리되도록 microtask 끝난 후 가드 해제
      Promise.resolve().then(() => { _applyingAutoFromServer = false })
    } catch {}
  })
  onBackendEvent('generationProgress', (step, total) => {
    progressVal.value = Math.round(step / total * 100)
    status.value = `Generating... ${step}/${total}`
    // 간단 ETA: 시작 시각 기준
    if (step > 0 && genStartTime.value) {
      const elapsed = (Date.now() - genStartTime.value) / 1000
      const remaining = Math.max(0, elapsed / step * (total - step))
      genEta.value = remaining >= 60
        ? `ETA ${Math.floor(remaining / 60)}m${String(Math.floor(remaining % 60)).padStart(2, '0')}s`
        : `ETA ${remaining.toFixed(0)}s`
    }
  })
  onBackendEvent('generationError', (msg) => { isGenerating.value = false; genEta.value = ''; status.value = `Error: ${msg}` })

  // 글로벌 가중치 로드
  onBackendEvent('globalWeightsLoaded', (json) => {
    try { const d = JSON.parse(json); globalWeights.splice(0); d.forEach(w => globalWeights.push(w)) } catch {}
  })

  // 랜덤 해상도 로드
  loadRandomResList()

  // ADetailer 모델 로드
  const _bk = await getBackend()
  syncAutomationSettings()
  if (_bk.getADetailerModels) _bk.getADetailerModels((json) => { try { adModelItems.value = JSON.parse(json) } catch {} })

  // 와일드카드 로드
  if (_bk.getWildcardTree) _bk.getWildcardTree((json) => { try { wildcards.value = JSON.parse(json) } catch {} })

  // VRAM 실시간 업데이트
  onBackendEvent('vramUpdated', (json) => { try { vramInfo.value = JSON.parse(json) } catch {} })

  // Global Toast 알림 (Python → Vue)
  onBackendEvent('showNotification', (type, msg) => { addToast(type, msg) })

  onBackendEvent('uiPrefsLoaded', (json) => {
    try {
      const prefs = JSON.parse(json)
      if (Array.isArray(prefs.ratingFilter) && prefs.ratingFilter.length === ratingFilters.length) {
        prefs.ratingFilter.forEach((v, i) => { ratingFilters[i].on = !!v })
        window.localStorage.setItem('ratingFilter', JSON.stringify(prefs.ratingFilter))
        requestAction('set_rating_filter', { ratings: ratingFilters.filter(r => r.on).map(r => r.key) })
      }
      if (Array.isArray(prefs.loraStack)) {
        _loraRestoring = true
        loraStack.splice(0, loraStack.length, ...prefs.loraStack.map(l => ({ ...l })))
        window.localStorage.setItem('loraStack', JSON.stringify(prefs.loraStack))
        nextTick(() => { _loraRestoring = false; _loraInitialized = true })
      }
      // tabOrder 복원 (Settings 탭 미방문 시에도 적용)
      if (Array.isArray(prefs.tabOrder) && prefs.tabOrder.length > 0) {
        window.localStorage.setItem('tabOrder', JSON.stringify(prefs.tabOrder))
      }
    } catch {}
  })

  // 에러도 Toast로 표시
  onBackendEvent('generationError', (msg) => { addToast('error', msg) })

  // LoRA 추가 이벤트 (Python lora_manager → Vue)
  onBackendEvent('loraInserted', (json) => {
    try {
      const d = JSON.parse(json)
      addLoraToStack(d.name, d.weight || 0.8, d.trigger_words || [])
      showExtendPanel.value = true
    } catch {}
  })

  onBackendEvent('loraStackLoaded', (json) => {
    try {
      const entries = JSON.parse(json)
      if (!Array.isArray(entries)) return
      _loraRestoring = true
      loraStack.splice(0, loraStack.length, ...entries.map(entry => ({
        name: entry.name || '',
        weight: Number.isFinite(Number(entry.weight)) ? Math.round(Number(entry.weight) * 100) : 80,
        enabled: entry.enabled !== false,
        triggerWords: Array.isArray(entry.triggerWords) ? entry.triggerWords : [],
      })))
      // localStorage만 업데이트, ui_prefs 재저장 안 함 (루프 방지)
      try { window.localStorage.setItem('loraStack', JSON.stringify(loraStack)) } catch {}
      nextTick(() => { _loraRestoring = false; _loraInitialized = true })
    } catch {}
  })

  syncLoraStack()
})
</script>

<style scoped>
.app-container { width: 100%; height: 100vh; display: flex; flex-direction: column; background: var(--bg-primary); }
.app-header { height: 60px; display: flex; align-items: center; justify-content: center; background: var(--bg-primary); border-bottom: 1px solid var(--border); z-index: 100; }
.main-workspace { flex: 1; display: flex; overflow: hidden; position: relative; }

.side-panel { width: 360px; display: flex; flex-direction: column; background: var(--bg-secondary); border-right: 1px solid var(--border); z-index: 10; }
.side-panel.right { width: 220px; border-right: none; border-left: 1px solid var(--border); }
.panel-scroll { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }

/* 반달 화살표 */
.half-moon {
  position: absolute; left: 360px; top: 50%; transform: translateY(-50%);
  width: 20px; height: 60px; background: var(--bg-secondary);
  border: 1px solid var(--border); border-left: none;
  border-radius: 0 30px 30px 0; cursor: pointer; z-index: 10;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); font-size: 10px; transition: all 0.2s;
}
.half-moon:hover { background: var(--bg-card); color: var(--accent); width: 24px; }
.half-moon.open { background: var(--accent-dim); color: var(--accent); left: 680px; }

/* Extended Panel Backdrop — 외부 클릭으로 닫기 */
.extend-backdrop {
  /* 왼쪽 패널(360px)은 덮지 않음 — inset:0이면 왼쪽 checkpoint/프롬프트 영역까지
     가려 wheel을 가로채 스크롤이 동결됐음. left:360부터 덮어 왼쪽 패널은 ADVANCED가
     열린 상태에서도 스크롤/조작 가능. 오버레이(360~680)는 위(z-index 50)라 클릭이
     오버레이로 가고, 그 바깥(680~)을 클릭하면 닫힘. */
  position: absolute; left: 360px; right: 0; top: 0; bottom: 0; background: transparent;
  z-index: 45; cursor: pointer;
}
/* Extended Panel Overlay */
.extend-overlay {
  position: absolute; left: 360px; top: 0; bottom: 0; width: 440px;
  background: var(--bg-secondary); border-right: 1px solid var(--border);
  z-index: 50; display: flex; flex-direction: column;
  box-shadow: 8px 0 32px rgba(0,0,0,0.5);
}
.extend-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.extend-header h3 { font-size: 11px; letter-spacing: 2px; color: var(--text-muted); }
.close-btn { background: none; border: none; color: var(--text-muted); font-size: 16px; cursor: pointer; }
.close-btn:hover { color: #f87171; }
.extend-scroll { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }

.ext-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 12px; }
.ext-title { font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: 1px; margin-bottom: 10px; cursor: pointer; }
.ext-field { margin-bottom: 8px; }
.ext-field label { font-size: 9px; color: var(--text-muted); font-weight: 700; display: block; margin-bottom: 3px; }
.ext-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.rating-toggle-row { display: flex; gap: 4px; margin-bottom: 8px; }
.rating-toggle {
  flex: 1; padding: 4px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text-muted); font-size: 10px; font-weight: 900;
  cursor: pointer; text-align: center; transition: var(--transition);
}
.rating-toggle.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.ext-toggle-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; }
.char-ovr-row { margin-top: 6px; }
.char-ovr-btn { width: 100%; padding: 6px 10px; background: var(--accent-dim); border: 1px solid var(--accent); border-radius: var(--radius-base); color: var(--accent); font-size: 10px; font-weight: 700; cursor: pointer; }
.char-ovr-btn:hover { background: rgba(250,204,21,0.18); }
.ext-sub { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.ext-sub summary { font-size: 10px; color: var(--text-secondary); cursor: pointer; }
.ext-sub-title { font-size: 10px; font-weight: 800; color: var(--accent); letter-spacing: 1px; margin: 8px 0 4px; }

/* LoRA block */
.lora-block { display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: var(--bg-button); border-radius: 6px; margin-bottom: 4px; }
.lora-info-col { flex: 1; min-width: 0; }
.lora-name { font-size: 11px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lora-triggers { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
.trigger-chip {
  padding: 1px 6px; font-size: 9px; font-weight: 700; color: var(--accent);
  background: var(--accent-dim); border: 1px solid rgba(250, 204, 21, 0.15);
  border-radius: 4px; cursor: pointer; transition: var(--transition);
}
.trigger-chip:hover { background: rgba(250, 204, 21, 0.2); border-color: var(--accent); }
.lora-slider { width: 60px; accent-color: var(--accent); }
.lora-weight { font-size: 10px; color: var(--accent); min-width: 30px; text-align: right; font-family: monospace; }
.lora-remove { background: none; border: none; color: #f87171; cursor: pointer; font-size: 12px; }
.lora-tools { float: right; display: inline-flex; gap: 4px; }
.lora-tool-btn { background: var(--bg-button); border: 1px solid var(--border); border-radius: 5px; color: var(--text-secondary); font-size: 9px; font-weight: 700; padding: 2px 7px; cursor: pointer; }
.lora-tool-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.lora-tool-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.lora-sets { display: flex; gap: 4px; margin-top: 6px; align-items: center; }
.lora-set-input { width: 70px; flex-shrink: 0; background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 4px 6px; color: var(--text-primary); font-size: 10px; }
.lora-set-sel { flex: 1; min-width: 0; background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 4px; color: var(--text-primary); font-size: 10px; }
.ext-add-btn { width: 100%; padding: 8px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; margin-top: 4px; }
.ext-res-row { display: flex; align-items: center; gap: 6px; }
.ext-res-row input { text-align: center; flex: 1; }
.ext-res-row span { color: var(--text-muted); }
.ext-mini-btn { width: 32px; height: 32px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); cursor: pointer; flex-shrink: 0; }
.ext-res-opts { display: flex; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
.ext-check-sm { display: flex; align-items: center; gap: 3px; font-size: 9px; color: var(--text-muted); cursor: pointer; white-space: nowrap; }
.ext-check-sm input { width: 12px; height: 12px; margin: 0; }
/* 고해상도 토글 — 활성 시 골드 강조 */
.hr-toggle.active { color: var(--accent); font-weight: 700; }
.hr-toggle.active span { text-shadow: 0 0 4px rgba(250, 204, 21, 0.3); }

/* 고해상도 미리보기 박스 */
.hr-preview {
  margin-top: 8px; padding: 8px 10px;
  background: var(--accent-dim); border: 1px solid rgba(250, 204, 21, 0.3);
  border-radius: 6px; display: flex; flex-direction: column; gap: 6px;
}
.hr-row { display: flex; align-items: center; gap: 8px; }
.hr-label { font-size: 9px; font-weight: 800; color: var(--accent); letter-spacing: 1px; min-width: 26px; }
.hr-slider { flex: 1; accent-color: var(--accent); cursor: pointer; height: 4px; }
.hr-val {
  font-family: 'Consolas', monospace; font-size: 10px; font-weight: 800;
  color: var(--accent); min-width: 36px; text-align: right;
}
.hr-result {
  font-size: 10px; color: var(--text-secondary);
  font-family: 'Consolas', monospace;
}
.hr-result strong { color: var(--accent); font-weight: 900; font-size: 11px; }
.hr-note { color: var(--text-muted); font-size: 9px; margin-left: 4px; }
.hr-warn { color: #fb923c; margin-left: 4px; font-weight: 900; }
.hr-warn-banner {
  margin-top: 4px; padding: 6px 8px;
  background: rgba(251, 146, 60, 0.08);
  border: 1px solid rgba(251, 146, 60, 0.3);
  border-radius: 4px;
  font-size: 9.5px; line-height: 1.5;
  color: #fb923c;
}

/* 랜덤 해상도 편집기 */
.rand-res-editor { margin-top: 6px; border: 1px solid var(--border); border-radius: 6px; padding: 6px; background: rgba(0,0,0,0.15); }
.rand-res-list { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.rand-res-item { display: flex; align-items: center; gap: 4px; padding: 2px 6px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; font-size: 10px; }
.rand-res-val { color: var(--text-primary); font-weight: 700; font-family: monospace; }
.rand-res-desc { color: var(--text-muted); font-size: 9px; }
.rand-res-del { background: none; border: none; color: #f87171; cursor: pointer; font-size: 10px; padding: 0 2px; }
.rand-res-empty { font-size: 9px; color: var(--text-muted); padding: 4px; }
.rand-res-add { display: flex; align-items: center; gap: 4px; }
.rand-res-add span { color: var(--text-muted); font-size: 10px; }
.rand-res-input { width: 50px; padding: 3px 4px; font-size: 10px; text-align: center; }
.rand-res-btn { width: 24px; height: 24px; background: var(--accent); border: none; border-radius: 4px; color: #000; font-weight: 900; cursor: pointer; font-size: 14px; }
.ext-check-row { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-secondary); cursor: pointer; margin-bottom: 4px; white-space: nowrap; }
.ext-check-row input[type="checkbox"] { flex-shrink: 0; margin: 0; }
.ext-check-row span { overflow: hidden; text-overflow: ellipsis; }
.ext-check-row input[type="checkbox"] { accent-color: var(--accent); }
.ext-hint { font-size: 10px; color: var(--text-muted); margin-top: 4px; }
.cond-textarea { min-height: 60px; font-size: 11px; line-height: 1.6; font-family: 'Consolas', monospace; }
.cond-block { margin-top: 6px; }
.cond-toggle-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.cond-toggle { padding: 2px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-button); color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer; }
.cond-toggle.on { background: rgba(74,222,128,0.15); border-color: #4ade80; color: #4ade80; }
.lora-check { flex-shrink: 0; }
.lora-check input { accent-color: var(--accent); }
.lora-empty { font-size: 11px; color: var(--text-muted); text-align: center; padding: 12px; }

.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease, opacity 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(-20px); opacity: 0; }

/* Tool Card */
.tool-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 16px; }
.tool-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.tool-btn { position: relative; padding: 8px 4px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; transition: var(--transition); }
.tool-btn-on { color: #4ade80; border-color: #4ade80; box-shadow: 0 0 0 1px rgba(74,222,128,0.25) inset; }
.tool-dot { position: absolute; top: 3px; right: 4px; width: 6px; height: 6px; border-radius: 50%; background: #4ade80; box-shadow: 0 0 5px #4ade80; }
.tool-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }
.tool-btn.highlight { color: var(--accent); border-color: var(--accent-dim); }

/* Preset Manager */
.pm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.pm-modal { width: 650px; height: 450px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.pm-header { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.pm-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); flex: 1; }
.pm-body { flex: 1; display: flex; overflow: hidden; }
.pm-list { width: 180px; overflow-y: auto; border-right: 1px solid var(--border); padding: 8px; }
.pm-item { padding: 7px 10px; font-size: 11px; color: var(--text-secondary); cursor: pointer; border-radius: 4px; margin-bottom: 2px; }
.pm-item:hover { background: var(--bg-input); }
.pm-item.active { background: var(--accent-dim); color: var(--accent); }
.pm-preview { flex: 1; overflow-y: auto; padding: 12px; }
.pm-detail { display: flex; flex-direction: column; gap: 4px; }
.pm-field { display: flex; gap: 8px; font-size: 10px; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 3px 0; }
.pm-key { color: var(--accent); font-weight: 700; min-width: 100px; }
.pm-val { color: var(--text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pm-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); }
.pm-footer { display: flex; align-items: center; gap: 6px; padding: 10px 16px; border-top: 1px solid var(--border); }
.pm-btn { padding: 6px 14px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }
.pm-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pm-btn:disabled { opacity: 0.3; }
.pm-btn.accent { background: var(--accent); color: #000; border: none; }
.pm-spacer { flex: 1; }

/* Weight Manager */
.wm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.wm-modal { width: 500px; max-height: 500px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.wm-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.wm-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); }
.wm-desc { font-size: 9px; color: var(--text-muted); flex: 1; }
.wm-body { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
.wm-row { display: flex; align-items: center; gap: 6px; }
.wm-tag-input { flex: 1; padding: 5px 8px; font-size: 11px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); }
.wm-slider { width: 100px; accent-color: var(--accent); }
.wm-val { font-size: 11px; color: var(--accent); min-width: 35px; text-align: right; font-family: monospace; }
.wm-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 14px; }
.wm-add { width: 100%; padding: 6px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 4px; color: var(--text-muted); font-size: 10px; cursor: pointer; }
.wm-footer { padding: 10px 16px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; }
.wm-save { padding: 7px 20px; background: var(--accent); border: none; border-radius: 6px; color: #000; font-size: 11px; font-weight: 800; cursor: pointer; }

/* Generation Stats Modal */
.stats-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.stats-modal { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 16px; width: 640px; max-height: 85vh; overflow-y: auto; }
.stats-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px; border-bottom: 1px solid var(--border); }
.stats-header h3 { font-size: 13px; font-weight: 900; letter-spacing: 2px; color: var(--text-primary); }
.stats-body { padding: 24px; display: flex; flex-direction: column; gap: 24px; }
.stats-empty { display: flex; align-items: center; justify-content: center; min-height: 200px; }
.stats-empty-msg { color: var(--text-muted); font-size: 14px; }

.stats-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat-card { background: var(--bg-input); border: 1px solid var(--border); border-radius: 12px; padding: 16px; text-align: center; }
.stat-card.accent { border-color: var(--accent-dim); }
.stat-val { font-size: 28px; font-weight: 900; color: var(--text-primary); font-family: monospace; }
.stat-card.accent .stat-val { color: var(--accent); }
.stat-label { font-size: 9px; font-weight: 800; color: var(--text-muted); letter-spacing: 1.5px; margin-top: 4px; }

.stats-section h4 { font-size: 10px; font-weight: 900; color: var(--text-muted); letter-spacing: 1.5px; margin-bottom: 12px; }
.stats-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }

.daily-chart { display: flex; align-items: flex-end; gap: 2px; height: 80px; padding: 0 2px; }
.daily-bar-wrap { flex: 1; height: 100%; display: flex; align-items: flex-end; }
.daily-bar { width: 100%; background: var(--accent); border-radius: 2px 2px 0 0; min-height: 1px; transition: height 0.3s; }
.daily-labels { display: flex; justify-content: space-between; margin-top: 4px; font-size: 9px; color: var(--text-muted); }

.stats-bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.bar-name { font-size: 11px; color: var(--text-secondary); min-width: 80px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; height: 6px; background: var(--bg-button); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.bar-count { font-size: 10px; color: var(--text-muted); min-width: 30px; text-align: right; font-family: monospace; }

.recent-table { display: flex; flex-direction: column; gap: 4px; }
.recent-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: var(--bg-input); border-radius: 6px; font-size: 11px; }
.r-time { color: var(--text-muted); min-width: 80px; font-family: monospace; }
.r-status { font-weight: 800; font-size: 10px; min-width: 30px; }
.r-status.ok { color: #4ade80; }
.r-status.fail { color: #f87171; }
.r-dur { color: var(--accent); min-width: 40px; font-family: monospace; }
.r-res { color: var(--text-secondary); min-width: 70px; }
.r-model { color: var(--text-muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Wildcard Manager Modal */
.wc-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.wc-modal { width: 700px; height: 500px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.wc-modal-header { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.wc-modal-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); }
.wc-path { font-size: 10px; color: var(--text-muted); font-family: monospace; flex: 1; }
.wc-modal-body { flex: 1; display: flex; overflow: hidden; }
.wc-sidebar { width: 180px; overflow-y: auto; border-right: 1px solid var(--border); padding: 8px; }
.wc-file-item { padding: 6px 10px; font-size: 11px; color: var(--text-secondary); cursor: pointer; border-radius: 4px; display: flex; justify-content: space-between; }
.wc-file-item:hover { background: var(--bg-input); }
.wc-file-item.active { background: var(--accent-dim); color: var(--accent); }
.wc-file-count { font-size: 9px; color: var(--text-muted); }
.wc-content { flex: 1; overflow-y: auto; padding: 16px; }
.wc-content-header { margin-bottom: 12px; }
.wc-content-header h4 { font-size: 14px; color: var(--text-primary); }
.wc-content-header span { font-size: 10px; color: var(--text-muted); }
.wc-content-header code { background: var(--bg-input); padding: 2px 6px; border-radius: 3px; font-size: 10px; color: var(--accent); }
.wc-new-btn { padding: 4px 12px; background: var(--accent); border: none; border-radius: 4px; color: #000; font-size: 10px; font-weight: 800; cursor: pointer; }
.wc-fname { flex: 1; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.wc-del { background: none; border: none; color: #f87171; cursor: pointer; font-size: 11px; opacity: 0; transition: 0.15s; }
.wc-file-item:hover .wc-del { opacity: 1; }
.wc-syntax { font-size: 10px; color: var(--text-muted); }
.wc-syntax code { background: var(--bg-input); padding: 1px 6px; border-radius: 3px; color: var(--accent); }
.wc-copy-btn { padding: 2px 8px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 3px; color: var(--text-secondary); font-size: 9px; cursor: pointer; }
.wc-blocks { display: flex; flex-direction: column; gap: 3px; max-height: 300px; overflow-y: auto; }
.wc-block-row { display: flex; align-items: center; gap: 4px; }
.wc-block-idx { font-size: 9px; color: var(--text-muted); min-width: 20px; text-align: right; font-family: monospace; }
.wc-block-input { flex: 1; padding: 4px 8px; font-size: 11px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 3px; color: var(--text-primary); }
.wc-block-use { padding: 2px 6px; background: var(--accent-dim); border: 1px solid var(--accent); border-radius: 3px; color: var(--accent); font-size: 9px; font-weight: 700; cursor: pointer; }
.wc-block-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 12px; }
.wc-add-line { width: 100%; padding: 4px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 3px; color: var(--text-muted); font-size: 9px; cursor: pointer; margin-top: 4px; }
.wc-rename-input { font-size: 14px; background: var(--bg-input); border: 1px solid var(--accent); border-radius: 4px; color: var(--text-primary); padding: 2px 8px; width: 200px; }
.wc-bottom-bar { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.wc-insert-sel { padding: 4px 8px; font-size: 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); }
.wc-use-btn { padding: 5px 16px; background: var(--accent); border: none; border-radius: 4px; color: #000; font-size: 10px; font-weight: 800; cursor: pointer; }
.wc-spacer { flex: 1; }
.wc-save-btn { padding: 5px 14px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }
.wc-save-btn:hover { border-color: var(--accent); color: var(--accent); }
.wc-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 13px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.gen-footer { padding: 12px 16px; background: var(--bg-card); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
.gen-actions { display: flex; gap: 6px; }
.action-btn { flex: 1; padding: 7px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; transition: var(--transition); }
.action-btn.active { border-color: #4ade80; color: #4ade80; background: rgba(74,222,128,0.05); }
.action-btn.highlight { border-color: var(--accent-dim); color: var(--accent); }
.action-btn:hover { border-color: var(--text-muted); }
.auto-settings { display: flex; flex-direction: column; gap: 4px; padding: 8px; background: rgba(74,222,128,0.03); border: 1px solid rgba(74,222,128,0.1); border-radius: 8px; }
.auto-row { display: flex; align-items: center; gap: 4px; }
.auto-row label { font-size: 9px; color: var(--text-muted); font-weight: 700; min-width: 32px; }
.auto-input { width: 50px; padding: 4px 6px; font-size: 11px; text-align: center; }
.auto-unlimited-mark { display: inline-block; width: 50px; padding: 4px 6px; font-size: 14px;
  color: var(--accent); text-align: center; font-weight: bold; }

/* 워크플로우 프로파일 */
.profile-card { background: rgba(96,165,250,0.04); border: 1px solid rgba(96,165,250,0.15);
  border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.profile-row { display: flex; align-items: center; gap: 6px; }
.profile-label { font-size: 10px; color: #60a5fa; font-weight: 700; flex-shrink: 0;
  letter-spacing: 0.5px; }
.profile-row :deep(.csel) { flex: 1; }
.profile-mini-btn { width: 24px; height: 24px; flex-shrink: 0; cursor: pointer;
  background: rgba(96,165,250,0.15); color: #93c5fd;
  border: 1px solid rgba(96,165,250,0.3); border-radius: 4px; font-weight: bold; }
.profile-mini-btn:hover { background: rgba(96,165,250,0.3); border-color: #60a5fa; color: #fff; }
.profile-item { display: flex; align-items: center; gap: 6px; padding: 8px 10px;
  background: rgba(255,255,255,0.04); border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.08); }
.profile-item:hover { background: rgba(96,165,250,0.08); }
.profile-info { flex: 1; min-width: 0; }
.profile-name { font-size: 13px; font-weight: 600; color: var(--text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.profile-meta { font-size: 10px; color: var(--text-muted); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 프롬프트 순서 모달 */
.order-modal-body { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.order-list { display: flex; flex-direction: column; gap: 4px;
  background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px; padding: 8px; }
.order-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  background: rgba(255,255,255,0.04); border-radius: 4px;
  transition: background 0.15s; }
.order-item:hover { background: rgba(96,165,250,0.08); }
.order-num { width: 22px; height: 22px; display: inline-flex; align-items: center;
  justify-content: center; background: rgba(96,165,250,0.2); color: #93c5fd;
  border-radius: 50%; font-size: 11px; font-weight: bold; }
.order-label { flex: 1; font-size: 13px; color: var(--text-primary); }
.order-btn { width: 28px; height: 28px; font-size: 13px; cursor: pointer;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 4px; color: var(--text-primary); }
.order-btn:hover:not(:disabled) { background: rgba(96,165,250,0.15);
  border-color: #60a5fa; color: #93c5fd; }
.order-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.order-preview { padding: 8px 10px; background: rgba(255,255,255,0.03);
  border-left: 2px solid #60a5fa; border-radius: 0 4px 4px 0; }
.order-preview-label { font-size: 10px; color: var(--text-muted); margin-right: 6px; }
.order-preview-text { font-size: 11px; color: #93c5fd; font-family: Consolas, monospace; }
.order-actions { display: flex; gap: 8px; align-items: center; padding-top: 6px;
  border-top: 1px solid rgba(255,255,255,0.08); }
.order-reset, .order-cancel, .order-save { padding: 6px 14px; border-radius: 4px;
  font-size: 12px; cursor: pointer; font-weight: 600; }
.order-reset { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  color: var(--text-muted); }
.order-cancel { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  color: var(--text-primary); }
.order-save { background: #2563eb; border: 1px solid #3b82f6; color: white; }
.order-save:hover { background: #3b82f6; }
.auto-select { min-width: 90px; padding: 4px; font-size: 10px; }

/* 자동화 상태 */
.auto-status { padding: 8px 12px; background: rgba(250, 204, 21, 0.05); border: 1px solid var(--accent-dim); border-radius: 8px; margin-bottom: 8px; }
.auto-deck-pre { margin-top: 8px; font-size: 11px; color: var(--text-muted); padding: 6px 10px; background: rgba(250,204,21,0.05); border: 1px solid var(--accent-dim); border-radius: 6px; }
.auto-deck-pre strong { color: var(--accent); font-weight: 900; }
.auto-status-bar { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--accent); font-weight: 700; }
.auto-status-sub { font-size: 10px; color: var(--text-muted); margin-top: 4px; }
.auto-wait .wait-row { display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--text-muted); margin-bottom: 3px; }
.auto-wait .wait-pct { color: var(--accent); font-weight: 700; }
.auto-wait .wait-bar { height: 5px; background: rgba(255,255,255,0.07); border-radius: 3px; overflow: hidden; }
.auto-wait .wait-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.12s linear; }
.auto-pulse { width: 8px; height: 8px; background: var(--accent); border-radius: 50%; animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.generate-row { display: flex; gap: 6px; align-items: stretch; }
.btn-cancel { width: 50px; height: 50px; background: transparent; border: 2px solid #f87171; border-radius: var(--radius-pill); color: #f87171; font-size: 18px; font-weight: 700; cursor: pointer; transition: var(--transition); }
.btn-cancel:hover { background: #f87171; color: #fff; }
.gen-eta { margin-top: 6px; font-size: 11px; color: var(--muted); text-align: center; letter-spacing: 0.5px; }
.auto-check { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-secondary); cursor: pointer; }
.auto-check input { accent-color: #4ade80; }
.btn-generate { width: 100%; height: 50px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 800; font-size: 14px; letter-spacing: 1px; cursor: pointer; transition: var(--transition); }
.btn-generate:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-2px); box-shadow: 0 8px 24px rgba(250, 204, 21, 0.3); }
.btn-generate:disabled { opacity: 0.5; cursor: wait; }
.btn-generate.automating { background: #f87171; color: #fff; }
.btn-generate.automating:hover:not(:disabled) { background: #ef4444; box-shadow: 0 8px 24px rgba(248, 113, 113, 0.3); }

/* Viewport */
.viewport-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #050505; }
.viewport-main { flex: 1; position: relative; overflow: hidden; }

/* EXIF Bar */
.exif-bar { flex-shrink: 0; background: #0D0D0D; border-top: 1px solid var(--border); }
.exif-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
.exif-tab { flex: 1; padding: 6px; background: transparent; border: none; color: var(--text-muted); font-size: 10px; font-weight: 700; cursor: pointer; text-align: center; border-bottom: 2px solid transparent; }
.exif-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.exif-content { padding: 6px 12px; font-size: 11px; color: var(--text-secondary); max-height: 80px; overflow-y: auto; line-height: 1.5; font-family: 'Consolas', monospace; white-space: pre-wrap; word-break: break-all; }
.exif-params { padding: 4px 12px; max-height: 80px; overflow-y: auto; }
.exif-params .param-line { display: flex; align-items: baseline; gap: 6px; padding: 2px 0; font-size: 10px; color: var(--text-secondary); font-family: 'Consolas', monospace; }
.exif-params .pl { font-size: 8px; font-weight: 900; color: var(--accent); letter-spacing: 1px; min-width: 40px; flex-shrink: 0; }
.exif-params .param-line.other { color: var(--text-muted); }

/* History */
.hist-header { padding: 16px; display: flex; justify-content: space-between; align-items: center; }
.hist-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); }
.count-badge { background: var(--border); padding: 2px 8px; border-radius: 10px; font-size: 10px; color: var(--text-secondary); }
.hist-nav-btn { width: 100%; padding: 4px; background: #131313; border: none; color: #484848; font-size: 12px; cursor: pointer; flex-shrink: 0; }
.hist-nav-btn:hover { background: #1A1A1A; color: #E8E8E8; }
.hist-nav-btn:disabled { opacity: 0.3; cursor: default; }
.hist-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 8px; }
/* flex:1 1 0 — 5개 카드가 컬럼 높이를 균등 분배 → 모든 간격(8px)이 일정.
   기존 aspect-ratio:1(정사각)은 5개가 컬럼을 못 채워 하단에 큰 빈 공간이 남아
   간격이 불균일해 보였음. */
.hist-card { position: relative; flex: 1 1 0; min-height: 0; border-radius: var(--radius-card); overflow: hidden; border: 2px solid transparent; cursor: pointer; transition: border-color 0.15s; }
.hist-card:hover { border-color: #333; }
.hist-card.selected { border-color: var(--accent); box-shadow: 0 0 12px var(--accent-dim); }
.hist-card.selected.blink { animation: histBlink 1s ease-in-out infinite; }
@keyframes histBlink {
  0%, 100% { border-color: var(--accent); box-shadow: 0 0 6px var(--accent-dim); }
  50% { border-color: #fff; box-shadow: 0 0 20px var(--accent); }
}
.hist-card img { width: 100%; height: 100%; object-fit: cover; display: block; }

/* Context Menu */
.modern-ctx-menu { position: fixed; background: #181818; border: 1px solid #222; border-radius: 10px; padding: 6px; z-index: 1000; min-width: 200px; box-shadow: 0 12px 32px rgba(0,0,0,0.8); max-height: calc(100vh - 16px); overflow-y: auto; }
.ctx-item { padding: 10px 14px; font-size: 11px; font-weight: 600; color: #909090; cursor: pointer; border-radius: 6px; transition: var(--transition); }
.ctx-item:hover { background: #252525; color: #FFF; }
.ctx-item.delete { color: #f87171; }
.ctx-item.delete:hover { background: rgba(248, 113, 113, 0.1); }
.ctx-separator { height: 1px; background: #222; margin: 4px 0; }

.pop-enter-active { animation: pop 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
@keyframes pop { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }

/* VRAM Bar */
.vram-warn { color: #fbbf24; font-weight: 900; margin-left: 6px; }
.vram-bar { cursor: pointer; }
.vram-bar:hover .vram-fill { filter: brightness(1.15); }
.vram-bar {
  position: fixed; bottom: 0; left: 0; right: 0; height: 22px;
  background: #080808; border-top: 1px solid var(--border); z-index: 500;
  display: flex; align-items: center;
}
.vram-fill { height: 100%; transition: width 1s ease; }
.vram-fill.ok { background: rgba(74,222,128,0.4); }
.vram-fill.warn { background: rgba(251,191,36,0.5); }
.vram-fill.critical { background: rgba(248,113,113,0.6); }
.vram-text {
  position: absolute; left: 50%; transform: translateX(-50%);
  font-size: 11px; font-weight: 800; color: #B0B0B0; letter-spacing: 0.5px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.8);
}

.global-progress { position: fixed; top: 0; left: 0; width: 100%; height: 3px; background: transparent; z-index: 1000; }
.progress-fill { height: 100%; background: var(--accent); transition: width 0.3s ease; }

/* Toast Notifications */
.toast-container {
  position: fixed; top: 70px; right: 20px; z-index: 99999;
  display: flex; flex-direction: column; gap: 6px; pointer-events: none;
  max-width: 400px;
}
.toast-stack { display: flex; flex-direction: column; gap: 6px; pointer-events: auto; }
.toast-clear-all {
  align-self: flex-end; padding: 3px 10px; font-size: 10px; font-weight: 600;
  background: rgba(0,0,0,0.6); color: #fff; border: 1px solid rgba(255,255,255,0.2);
  border-radius: 4px; cursor: pointer; pointer-events: auto; backdrop-filter: blur(8px);
}
.toast-clear-all:hover { background: rgba(248,113,113,0.5); border-color: #f87171; }
.toast {
  display: flex; align-items: center; gap: 8px;
  padding: 11px 13px 11px 15px; border-radius: 9px; font-size: 13px; font-weight: 600;
  color: #FFF; pointer-events: auto; min-width: 240px; max-width: 400px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4); backdrop-filter: blur(8px);
  word-break: break-word; line-height: 1.45;
}
.toast.success { background: rgba(74, 222, 128, 0.92); color: #000; }
.toast.error { background: rgba(248, 113, 113, 0.92); color: #FFF; }
.toast.info { background: rgba(96, 165, 250, 0.92); color: #FFF; }
.toast.warning { background: rgba(251, 191, 36, 0.92); color: #000; }
.toast-icon { font-size: 16px; flex-shrink: 0; }

/* 알림 벨 + 히스토리 패널 */
.notif-bell { position: fixed; top: 14px; right: 18px; z-index: 2003; width: 34px; height: 34px; border-radius: 50%; background: var(--bg-button); border: 1px solid var(--border); color: var(--text-secondary); font-size: 15px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.notif-bell:hover { border-color: var(--accent); color: var(--accent); }
.notif-badge { position: absolute; top: -4px; right: -4px; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px; background: #f87171; color: #fff; font-size: 9px; font-weight: 800; display: flex; align-items: center; justify-content: center; }
.notif-overlay { position: fixed; inset: 0; z-index: 2002; }
.notif-panel { position: fixed; top: 54px; right: 18px; z-index: 2003; width: 330px; max-height: 60vh; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 12px 32px rgba(0,0,0,0.6); display: flex; flex-direction: column; overflow: hidden; }
.notif-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 12px; font-weight: 800; color: var(--text-secondary); letter-spacing: 1px; }
.notif-clear { background: none; border: none; color: #f87171; font-size: 10px; font-weight: 700; cursor: pointer; }
.notif-list { overflow-y: auto; padding: 6px; }
.notif-item { display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; border-radius: 6px; font-size: 12px; color: var(--text-primary); }
.notif-item:hover { background: var(--bg-button); }
.notif-ico { flex-shrink: 0; }
.notif-item.error .notif-ico { color: #f87171; }
.notif-item.success .notif-ico { color: #4ade80; }
.notif-item.info .notif-ico { color: #60a5fa; }
.notif-item.warning .notif-ico { color: #fbbf24; }
.notif-msg { flex: 1; word-break: break-word; line-height: 1.4; }
.notif-time { flex-shrink: 0; font-size: 9px; color: var(--text-muted); white-space: nowrap; }
.notif-empty { padding: 24px; text-align: center; color: var(--text-muted); font-size: 12px; }
.toast-msg { flex: 1; }
.toast-count {
  background: rgba(0,0,0,0.25); padding: 1px 6px; border-radius: 8px;
  font-size: 10px; flex-shrink: 0;
}
.toast-close {
  width: 18px; height: 18px; padding: 0; flex-shrink: 0;
  background: rgba(0,0,0,0.2); border: none; border-radius: 50%;
  color: inherit; font-size: 10px; cursor: pointer; opacity: 0.7;
}
.toast-close:hover { opacity: 1; background: rgba(0,0,0,0.4); }
.toast-enter-active { animation: slideIn 0.25s ease; }
.toast-leave-active { animation: slideOut 0.25s ease; }
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideOut { from { opacity: 1; max-height: 60px; } to { transform: translateX(100%); opacity: 0; max-height: 0; padding: 0; margin: 0; } }
</style>
