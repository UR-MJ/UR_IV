<template>
  <div class="settings-workspace" @keydown.ctrl.f.prevent="focusSearch">
    <!-- Left: Sub-navigation -->
    <aside class="settings-nav">
      <div class="nav-header">환경설정</div>
      <div class="settings-search-wrap">
        <input ref="searchInputRef" v-model="settingsSearch" class="settings-search"
          placeholder="설정 검색 (Ctrl+F)" />
        <button v-if="settingsSearch" class="search-clear" @click="settingsSearch = ''" title="지우기"><Icon name="close" /></button>
      </div>
      <button v-for="tab in filteredSubTabs" :key="tab.id"
        class="nav-item" :class="{ active: currentTab === tab.id }"
        @click="currentTab = tab.id"
      >
        <Icon :name="tab.icon" size="16" />
        <span class="label">{{ tab.label }}</span>
      </button>
      <div v-if="settingsSearch && filteredSubTabs.length === 0" class="nav-empty">
        검색 결과 없음
      </div>
    </aside>

    <!-- Right: Content Area -->
    <main class="settings-body">
      <div class="settings-content">
        <!-- 1. General & Backend -->
        <div v-show="currentTab === 'general'" class="section-fade">
          <div class="glass-card">
            <label>시스템 상태</label>
            <div class="info-row">
              <span class="desc">코어 버전</span>
              <span class="val-badge">v2.0.0 PRO</span>
            </div>
            <div class="info-row mt-12">
              <span class="desc">API 오케스트레이터</span>
              <button class="btn-pill" :disabled="generationApiWebMode" @click="act('show_api_manager')">백엔드 관리</button>
            </div>
          </div>
        </div>

        <!-- 2. Network & API -->
        <div v-show="currentTab === 'api'" class="section-fade generation-api-section">
          <div class="hint-banner generation-api-security">
            <strong>인증 생성 게이트웨이</strong>
            로컬 앱이 인증 token이 필요한 생성 API를 제공하고, 미리 등록한 Forge/WebUI·ComfyUI로 작업을 중계합니다.
            외부 요청은 임의 URL을 지정할 수 없으며, 기본값은 <b>127.0.0.1 / OFF</b>입니다.
          </div>
          <div v-if="generationApiReadOnlyReason" class="hint-banner generation-api-readonly">
            <strong>읽기 전용</strong> {{ generationApiReadOnlyReason }}
          </div>

          <section class="glass-card generation-api-card">
            <header class="generation-api-header">
              <div>
                <div class="generation-api-eyebrow">수신 서버</div>
                <h2>이 앱을 생성 API로 사용</h2>
              </div>
              <div class="generation-api-badges">
                <span class="generation-api-badge" :class="{ on: generationApi.running }">
                  {{ generationApi.running ? 'RUNNING' : 'STOPPED' }}
                </span>
                <span class="generation-api-badge" :class="{ on: generationApi.enabled }">
                  {{ generationApi.enabled ? 'AUTO START' : 'MANUAL' }}
                </span>
              </div>
            </header>

            <div class="generation-api-toggle-row">
              <div>
                <strong>앱 시작</strong>
                <small>앱을 실행할 때 서버도 함께 시작</small>
              </div>
              <ToggleSwitch v-model="generationApi.enabled" :disabled="generationApiMutationDisabled" />
            </div>

            <div class="generation-api-grid mt-16">
              <label class="generation-api-field">
                <span>바인드 호스트</span>
                <input v-model.trim="generationApi.bindHost" spellcheck="false" placeholder="127.0.0.1" :disabled="generationApiMutationDisabled" />
                <small>LAN 공유는 0.0.0.0을 명시해야 합니다.</small>
              </label>
              <label class="generation-api-field">
                <span>포트</span>
                <input v-model.number="generationApi.port" type="number" min="1024" max="65535" :disabled="generationApiMutationDisabled" />
                <small>설정 저장 시 충돌을 검증합니다.</small>
              </label>
            </div>
            <div v-if="generationApiLanExposed" class="generation-api-lan-warning">
              LAN에 평문 HTTP로 공개되어 token·prompt·입력 이미지가 암호화되지 않습니다.
              신뢰 LAN/VPN/HTTPS reverse proxy 안에서만 사용하고 방화벽 접근을 제한하세요.
            </div>

            <label class="generation-api-field mt-16">
              <span>Bearer 토큰</span>
              <div class="generation-api-secret">
                <input :type="generationApiTokenVisible ? 'text' : 'password'" :value="generationApi.token || generationApi.tokenPreview"
                  readonly spellcheck="false" placeholder="SAVE 또는 ROTATE로 token 생성" />
                <button class="btn-pill compact" @click="generationApiTokenVisible = !generationApiTokenVisible">
                  {{ generationApiTokenVisible ? 'HIDE' : 'SHOW' }}
                </button>
                <button class="btn-pill compact" :disabled="!generationApi.token" @click="copyGenerationApiToken">복사</button>
                <button class="btn-pill compact" :disabled="generationApiMutationDisabled" @click="runGenerationApiAction('rotate_token')">회전</button>
              </div>
            </label>

            <div class="generation-api-endpoint mt-16">
              <span>기본 URL</span>
              <code>{{ generationApiBaseUrl }}</code>
              <button class="btn-pill compact" @click="copyGenerationApiExample">예시 복사</button>
            </div>

            <div class="generation-api-actions mt-16">
              <button class="btn-pill primary" :disabled="generationApiMutationDisabled" @click="saveGenerationApiConfig">설정 적용</button>
              <button class="btn-pill" :disabled="generationApiMutationDisabled || generationApi.running" @click="runGenerationApiAction('start')">시작</button>
              <button class="btn-pill" :disabled="generationApiMutationDisabled || !generationApi.running" @click="runGenerationApiAction('stop')">중지</button>
              <button class="btn-pill" :disabled="generationApiWebMode" @click="act('show_api_manager')">백엔드 관리</button>
            </div>
            <p v-if="generationApiStatus" class="generation-api-status">{{ generationApiStatus }}</p>
          </section>

          <section class="glass-card generation-api-card mt-16">
            <header class="generation-api-header">
              <div>
                <div class="generation-api-eyebrow">허용된 원격 대상</div>
                <h2>Forge/WebUI · ComfyUI 연결</h2>
              </div>
              <button class="btn-pill" :disabled="generationApiMutationDisabled" @click="addGenerationApiTarget">+ ADD TARGET</button>
            </header>

            <label class="generation-api-field mt-16">
              <span>기본 대상</span>
              <select v-model="generationApi.defaultTarget" :disabled="generationApiMutationDisabled">
                <option value="active">ACTIVE BACKEND (현재 앱 백엔드)</option>
                <option v-for="target in generationApi.targets" :key="target.id" :value="target.id">
                  {{ target.name || target.id }} · {{ target.engine.toUpperCase() }}
                </option>
              </select>
            </label>

            <div v-if="!generationApi.targets.length" class="generation-api-empty mt-16">
              등록된 원격 target이 없습니다. 외부 요청은 현재 활성 백엔드로 전달됩니다.
            </div>
            <article v-for="(target, index) in generationApi.targets" :key="target.localKey" class="generation-api-target mt-16">
              <div class="generation-api-target-head">
                <strong>{{ target.name || `TARGET ${index + 1}` }}</strong>
                <label class="generation-api-enabled">
                  <input v-model="target.enabled" type="checkbox" :disabled="generationApiMutationDisabled" /> 사용 중
                </label>
              </div>
              <div class="generation-api-grid">
                <label class="generation-api-field">
                  <span>이름</span>
                  <input v-model.trim="target.name" placeholder="Studio Forge" :disabled="generationApiMutationDisabled" />
                </label>
                <label class="generation-api-field">
                  <span>대상 ID</span>
                  <input v-model.trim="target.id" spellcheck="false" placeholder="studio-forge" :disabled="generationApiMutationDisabled" />
                </label>
                <label class="generation-api-field">
                  <span>엔진</span>
                  <select v-model="target.engine" :disabled="generationApiMutationDisabled">
                    <option value="webui">Forge / WebUI</option>
                    <option value="comfyui">ComfyUI</option>
                  </select>
                </label>
                <label class="generation-api-field">
                  <span>API URL</span>
                  <input v-model.trim="target.url" spellcheck="false"
                    :placeholder="target.engine === 'comfyui' ? 'http://127.0.0.1:8188' : 'http://127.0.0.1:7860'"
                    :disabled="generationApiMutationDisabled" />
                </label>
              </div>
              <div v-if="target.engine === 'comfyui'" class="generation-api-grid mt-12">
                <label class="generation-api-field">
                  <span>T2I 워크플로 프로필 경로</span>
                  <input v-model.trim="target.workflowPath" spellcheck="false" placeholder="C:\\workflows\\api_t2i.json" :disabled="generationApiMutationDisabled" />
                </label>
                <label class="generation-api-field">
                  <span>I2I 워크플로 프로필 경로</span>
                  <input v-model.trim="target.img2imgWorkflowPath" spellcheck="false" placeholder="C:\\workflows\\api_i2i.json" :disabled="generationApiMutationDisabled" />
                </label>
              </div>
              <div class="generation-api-target-actions mt-12">
                <button class="btn-pill compact" :disabled="generationApiMutationDisabled || !target.url" @click="testGenerationApiTarget(target)">테스트</button>
                <button class="btn-pill compact danger" :disabled="generationApiMutationDisabled" @click="removeGenerationApiTarget(index)">제거</button>
              </div>
            </article>
          </section>

          <section class="glass-card generation-api-card mt-16">
            <header class="generation-api-header">
              <div>
                <div class="generation-api-eyebrow">최근 요청</div>
                <h2>외부 생성 작업</h2>
              </div>
              <button class="btn-pill compact" :disabled="generationApiLoading" @click="loadGenerationApiState()">새로고침</button>
            </header>
            <div v-if="!generationApi.recentJobs.length" class="generation-api-empty mt-16">최근 외부 작업이 없습니다.</div>
            <div v-else class="generation-api-jobs mt-16">
              <div v-for="job in generationApi.recentJobs.slice(0, 8)" :key="job.id" class="generation-api-job">
                <div>
                  <strong>{{ job.mode.toUpperCase() }} · {{ job.target }}</strong>
                  <code>{{ job.id }}</code>
                </div>
                <span class="generation-api-job-state" :class="job.status">{{ job.status.toUpperCase() }}</span>
              </div>
            </div>
          </section>
        </div>

        <!-- 3. App-managed runtimes / engines -->
        <div v-show="currentTab === 'runtimes'" class="section-fade runtime-section">
          <div class="hint-banner runtime-safety-warning">
            <strong>보안 안내</strong>
            확장 저장소는 엔진 프로세스 안에서 코드를 실행할 수 있습니다. 신뢰하는 저장소만 설치하세요.
            외부 설치의 확장 폴더에는 사용자가 경로를 선택하고 <b>저장</b>한 뒤에만 씁니다.
          </div>
          <div v-if="runtimeReadOnlyReason" class="hint-banner runtime-readonly-warning">
            <strong>읽기 전용</strong> {{ runtimeReadOnlyReason }}
          </div>

          <div v-if="runtimePrimaryCandidates.length" class="glass-card runtime-primary-card">
            <div class="runtime-primary-copy">
              <div class="runtime-eyebrow">주 모델 라이브러리</div>
              <h2>공유할 메인 모델 소스</h2>
              <p>
                실행·연결할 <b>실행 중인 런타임</b>과 모델 폴더의 기준이 되는 <b>주 모델 라이브러리</b>는
                서로 다른 설정입니다. 메인 소스는 전체 모델·LoRA를 제공하고, 다른 엔진의 중복되지 않은
                항목은 별도 UNIQUE 그룹으로 표시됩니다.
              </p>
            </div>
            <div class="runtime-primary-options">
              <button v-for="engineId in runtimePrimaryCandidates" :key="engineId"
                class="runtime-primary-option"
                :class="{ selected: primaryModelEngine === engineId }"
                :disabled="runtimeMutationDisabled(engineId) || primaryModelEngine === engineId"
                @click="setPrimaryModelEngine(engineId)">
                <span>{{ runtimeEngines[engineId].name }}</span>
                <strong>{{ primaryModelEngine === engineId ? 'MAIN' : 'SET AS MAIN' }}</strong>
              </button>
            </div>
          </div>

          <div class="runtime-card-list">
            <article
              v-for="engineId in runtimeEngineOrder"
              :key="engineId"
              class="glass-card runtime-card"
              :class="`runtime-card-${engineId}`"
            >
              <header class="runtime-card-header">
                <div>
                  <div class="runtime-eyebrow">앱 전용 런타임</div>
                  <h2>{{ runtimeEngines[engineId].name }}</h2>
                </div>
                <div class="runtime-badges" aria-label="Runtime status">
                  <span class="runtime-badge" :class="{ on: runtimeEngines[engineId].installed }">
                    {{ runtimeEngines[engineId].installed ? 'INSTALLED' : 'NOT INSTALLED' }}
                  </span>
                  <span class="runtime-badge" :class="{ on: runtimeEngines[engineId].running }">
                    {{ runtimeEngines[engineId].running ? 'RUNNING' : 'STOPPED' }}
                  </span>
                  <span class="runtime-badge health" :class="{ on: runtimeEngines[engineId].healthy }">
                    {{ runtimeEngines[engineId].healthy ? 'HEALTHY' : 'NOT READY' }}
                  </span>
                  <span class="runtime-badge busy" :class="{ on: runtimeEngines[engineId].busy }">
                    {{ runtimeEngines[engineId].busy ? '사용 중' : '대기' }}
                  </span>
                  <span class="runtime-badge active" :class="{ on: runtimeEngines[engineId].active }">
                    {{ runtimeEngines[engineId].active ? 'ACTIVE' : 'NOT ACTIVE' }}
                  </span>
                  <span class="runtime-badge source" :class="{ existing: runtimeEngines[engineId].sourceMode === 'existing' }">
                    {{ runtimeEngines[engineId].sourceMode === 'existing' ? 'EXISTING' : 'MANAGED' }}
                  </span>
                  <span v-if="primaryModelEngine === engineId" class="runtime-badge primary-source">모델 메인</span>
                </div>
              </header>

              <div class="runtime-meta-grid">
                <div class="runtime-meta runtime-meta-wide">
                  <span>설치 경로</span>
                  <code :title="runtimeEngines[engineId].installRoot">{{ runtimeEngines[engineId].installRoot || 'Not installed' }}</code>
                </div>
                <div class="runtime-meta runtime-meta-wide">
                  <span>원본 경로</span>
                  <code :title="runtimeEngines[engineId].sourceRoot">{{ runtimeEngines[engineId].sourceRoot || 'Not detected' }}</code>
                </div>
                <div class="runtime-meta runtime-meta-wide">
                  <span>Python</span>
                  <code :title="runtimeEngines[engineId].pythonPath">{{ runtimeEngines[engineId].pythonPath || 'Not detected' }}</code>
                </div>
                <div class="runtime-meta runtime-meta-wide">
                  <span>앱 전용 데이터</span>
                  <code :title="runtimeEngines[engineId].dataRoot || runtimeEngines[engineId].root">
                    {{ runtimeEngines[engineId].dataRoot || runtimeEngines[engineId].root || 'Not assigned' }}
                  </code>
                </div>
                <div class="runtime-meta">
                  <span>API 엔드포인트</span>
                  <code>{{ runtimeEngines[engineId].apiUrl || 'Not assigned' }}</code>
                </div>
                <div class="runtime-meta">
                  <span>버전</span>
                  <strong>{{ runtimeEngines[engineId].version || 'Unknown' }}</strong>
                </div>
                <div class="runtime-meta runtime-meta-wide">
                  <span>업데이트 상태</span>
                  <strong :class="{ 'update-ready': runtimeEngines[engineId].updateAvailable }">
                    {{ runtimeEngines[engineId].updateStatus || 'Not checked' }}
                  </strong>
                </div>
                <div v-if="runtimeModelPathEntries(engineId).length" class="runtime-meta runtime-meta-wide runtime-model-paths">
                  <span>모델 라이브러리 경로</span>
                  <div v-for="entry in runtimeModelPathEntries(engineId)" :key="`${entry.kind}:${entry.path}`">
                    <strong>{{ entry.kind }}</strong>
                    <code :title="entry.path">{{ entry.path }}</code>
                  </div>
                </div>
              </div>

              <section class="runtime-subsection runtime-install-source">
                <div class="runtime-subheading">
                  <div>
                    <h3>기존 설치</h3>
                    <p>
                      설치된 {{ runtimeEngines[engineId].name }} 루트를 연결하면 앱 전용 복사본을 다시 받지 않습니다.
                      프로세스와 앱 데이터는 Image viewer가 별도로 관리합니다.
                    </p>
                  </div>
                  <span v-if="runtimeInstallRootDirty[engineId]" class="runtime-unsaved">저장 안 됨</span>
                </div>
                <div class="runtime-path-control runtime-install-path-control">
                  <input v-model="runtimeInstallRootDrafts[engineId]" spellcheck="false"
                    :placeholder="runtimeInstallRootPlaceholder(engineId)"
                    :disabled="runtimeMutationDisabled(engineId)"
                    @input="runtimeInstallRootDirty[engineId] = true" />
                  <button class="btn-pill compact" :disabled="runtimeMutationDisabled(engineId)"
                    :title="runtimeMutationTitle" @click="browseRuntimeInstallDirectory(engineId)">찾아보기</button>
                  <button class="btn-pill compact primary"
                    :disabled="runtimeMutationDisabled(engineId) || !runtimeInstallRootDrafts[engineId].trim() || (!runtimeInstallRootDirty[engineId] && runtimeEngines[engineId].sourceMode === 'existing')"
                    :title="runtimeMutationTitle" @click="linkExistingRuntime(engineId)">연결</button>
                  <button class="btn-pill compact"
                    :disabled="runtimeMutationDisabled(engineId) || runtimeEngines[engineId].sourceMode === 'managed'"
                    :title="runtimeMutationTitle" @click="useManagedRuntime(engineId)">앱 관리 사용</button>
                </div>
                <div v-if="runtimeEngines[engineId].sourceMode === 'existing'" class="runtime-dependency-note">
                  연결된 외부 설치는 앱이 자동 업데이트하지 않습니다. <b>업데이트</b>는 비활성화되며,
                  해당 Forge/Comfy 설치의 기존 업데이트 방법을 사용해야 합니다.
                </div>
              </section>

              <div class="runtime-toggle-row">
                <div>
                  <strong>뷰어와 함께 자동 시작</strong>
                  <small>앱 시작 시 이 격리 런타임을 자동으로 실행합니다.</small>
                </div>
                <ToggleSwitch
                  :model-value="runtimeEngines[engineId].autoStart"
                  :disabled="runtimeMutationDisabled(engineId)"
                  @update:model-value="setRuntimeAutoStart(engineId, $event)"
                />
              </div>

              <section class="runtime-subsection">
                <div class="runtime-subheading">
                  <div>
                    <h3>확장 폴더</h3>
                    <p>{{ runtimeExtensionFolderHint(engineId) }}</p>
                  </div>
                  <span v-if="runtimeExtensionFolderDirty[engineId]" class="runtime-unsaved">저장 안 됨</span>
                </div>
                <div class="runtime-path-control">
                  <input
                    v-model="runtimeExtensionDrafts[engineId]"
                    spellcheck="false"
                    :placeholder="runtimeExtensionPlaceholder(engineId)"
                    :disabled="runtimeMutationDisabled(engineId)"
                    @input="runtimeExtensionFolderDirty[engineId] = true"
                  />
                  <button
                    class="btn-pill compact"
                    :disabled="runtimeMutationDisabled(engineId)"
                    :title="runtimeMutationTitle"
                    @click="browseRuntimeExtensionDirectory(engineId)"
                  >찾아보기</button>
                  <button
                    class="btn-pill compact primary"
                    :disabled="runtimeMutationDisabled(engineId) || !runtimeExtensionFolderDirty[engineId] || !runtimeExtensionDrafts[engineId].trim()"
                    :title="runtimeMutationTitle"
                    @click="saveRuntimeExtensionDirectory(engineId)"
                  >저장</button>
                </div>
              </section>

              <div class="runtime-action-grid">
                <button class="btn-pill primary" :disabled="runtimeActionDisabled(engineId, 'install')" :title="runtimeMutationTitle" @click="runRuntimeOperation(engineId, 'install')">설치</button>
                <button class="btn-pill" :disabled="runtimeActionDisabled(engineId, 'update')" :title="runtimeMutationTitle" @click="runRuntimeOperation(engineId, 'update')">업데이트</button>
                <button class="btn-pill" :disabled="runtimeActionDisabled(engineId, 'check_update')" :title="runtimeMutationTitle" @click="runRuntimeOperation(engineId, 'check_update')">확인</button>
                <button class="btn-pill" :disabled="runtimeActionDisabled(engineId, 'start')" :title="runtimeMutationTitle" @click="runRuntimeOperation(engineId, 'start')">시작</button>
                <button class="btn-pill danger" :disabled="runtimeActionDisabled(engineId, 'stop')" :title="runtimeMutationTitle" @click="runRuntimeOperation(engineId, 'stop')">중지</button>
                <button class="btn-pill accent" :disabled="runtimeActionDisabled(engineId, 'use')" :title="runtimeMutationTitle" @click="runRuntimeOperation(engineId, 'use')">사용</button>
              </div>

              <section class="runtime-subsection runtime-extension-section">
                <div class="runtime-subheading">
                  <div>
                    <h3>확장 저장소 설치</h3>
                    <p>GitHub 저장소 URL을 검토한 뒤 이 엔진의 확장 폴더에 설치합니다.</p>
                  </div>
                </div>
                <div class="runtime-repo-control">
                  <input
                    v-model="runtimeRepoUrls[engineId]"
                    type="url"
                    spellcheck="false"
                    placeholder="https://github.com/owner/repository.git"
                    :disabled="runtimeMutationDisabled(engineId) || !runtimeExtensionWritable(engineId)"
                    @keyup.enter="installRuntimeExtension(engineId)"
                  />
                  <button
                    class="btn-pill primary"
                    :disabled="runtimeMutationDisabled(engineId) || !runtimeExtensionWritable(engineId) || !runtimeRepoUrls[engineId].trim()"
                    :title="runtimeMutationTitle"
                    @click="installRuntimeExtension(engineId)"
                  >설치</button>
                </div>
                <div
                  v-if="runtimeEngines[engineId].extensionDirExternal && !runtimeExtensionWritable(engineId)"
                  class="runtime-dependency-note"
                >
                  기존 설치의 확장 폴더는 감지했지만 아직 쓰기 권한을 부여하지 않았습니다.
                  위에서 해당 폴더를 <b>찾아보기</b>한 뒤 <b>저장</b>해야 확장 설치·업데이트가 활성화됩니다.
                </div>

                <div class="runtime-extension-list">
                  <div v-if="runtimeEngines[engineId].extensions.length === 0" class="runtime-empty">
                    설치된 확장이 없습니다.
                  </div>
                  <div
                    v-for="extension in runtimeEngines[engineId].extensions"
                    :key="extension.id"
                    class="runtime-extension-item"
                  >
                    <div class="runtime-extension-copy">
                      <div>
                        <strong>{{ extension.name }}</strong>
                        <span v-if="extension.version">{{ extension.version }}</span>
                        <span v-if="extension.updateAvailable" class="extension-update-badge">업데이트</span>
                      </div>
                      <code :title="extension.repoUrl">{{ extension.repoUrl || extension.status || 'Local extension' }}</code>
                    </div>
                    <div class="runtime-extension-actions">
                      <button
                        class="btn-pill compact"
                        :disabled="runtimeExtensionActionDisabled(engineId, extension)"
                        :title="runtimeMutationTitle"
                        @click="runRuntimeExtensionOperation(engineId, 'check_extension', extension)"
                      >확인</button>
                      <button
                        class="btn-pill compact"
                        :class="{ accent: extension.updateAvailable }"
                        :disabled="runtimeExtensionActionDisabled(engineId, extension)"
                        :title="runtimeMutationTitle"
                        @click="runRuntimeExtensionOperation(engineId, 'update_extension', extension)"
                      >업데이트</button>
                    </div>
                  </div>
                </div>
              </section>

              <div v-if="runtimeEngines[engineId].message" class="runtime-message">
                {{ runtimeEngines[engineId].message }}
              </div>
            </article>
          </div>

          <div v-if="runtimeStatus" class="runtime-global-status" role="status">{{ runtimeStatus }}</div>
        </div>

        <!-- 4. Forge Neo model directories -->
        <div v-show="currentTab === 'forge'" class="section-fade">
          <div class="hint-banner forge-hint">
            이 설정은 Image viewer가 VAE·TE를 직접 찾고 Forge 파일 구성을 확인할 때 사용합니다.
            Checkpoint와 LoRA 선택 목록은 실행 중인 Forge API가 기준이므로, 다른 폴더를 지정했다면
            Forge 시작 옵션(<code>--ckpt-dirs</code>, <code>--lora-dirs</code>,
            <code>--vae-dirs</code>, <code>--text-encoder-dirs</code>)에도 같은 폴더를 등록한 뒤
            Forge에서 목록을 새로고침하세요.
          </div>
          <div v-if="forgeReadOnlyReason" class="hint-banner forge-readonly-warning">
            <strong>읽기 전용</strong>{{ forgeReadOnlyReason }}
          </div>
          <div class="glass-card">
            <div class="forge-card-heading">
              <label>Forge Neo 모델 경로</label>
              <span v-if="forgeBusy" class="forge-scanning">SCANNING…</span>
            </div>
            <div class="forge-path-list">
              <div v-for="field in forgePathFields" :key="field.key" class="forge-path-row">
                <div class="forge-path-label">
                  <span>{{ field.label }}</span>
                  <small>{{ field.description }}</small>
                </div>
                <div class="forge-path-control">
                  <input
                    v-model="forgePaths[field.key]"
                    :class="{ invalid: !!forgeErrors[field.key] }"
                    :disabled="forgeEnvironmentLocked[field.key] || forgeBusy || !forgeCanMutate"
                    :title="forgeEnvironmentLocked[field.key] ? '환경 변수로 고정된 경로입니다.' : forgeMutationTitle"
                    :placeholder="forgeDefaults[field.key]"
                    spellcheck="false"
                    @input="forgeErrors[field.key] = ''"
                  />
                  <button
                    class="btn-pill compact"
                    :disabled="forgeEnvironmentLocked[field.key] || forgeBusy || !forgeCanBrowse"
                    :title="forgeBrowseTitle"
                    @click="browseForgePath(field.key)"
                  >찾아보기</button>
                </div>
                <div class="forge-path-meta">
                  <span :class="forgeEntries[field.key].exists ? 'path-ok' : 'path-missing'">
                    {{ forgeEntries[field.key].exists ? '● 폴더 확인됨' : '● 폴더 없음' }}
                  </span>
                  <span>{{ forgeEntries[field.key].count.toLocaleString() }} files</span>
                  <span v-if="forgeEnvironmentLocked[field.key]" class="env-lock">환경변수 우선</span>
                  <span v-if="forgeErrors[field.key]" class="path-error">{{ forgeErrors[field.key] }}</span>
                </div>
              </div>
            </div>
            <div class="forge-actions mt-16">
              <button class="btn-pill primary" :disabled="forgeBusy || !forgeCanMutate" :title="forgeMutationTitle" @click="saveForgePaths">경로 저장</button>
              <button class="btn-pill" :disabled="forgeBusy || !forgeCanMutate" :title="forgeMutationTitle" @click="refreshForgePaths">다시 검색</button>
              <button class="btn-pill" :disabled="forgeBusy || !forgeCanMutate" :title="forgeMutationTitle" @click="resetForgePaths">자동으로 되돌리기</button>
            </div>
            <div v-if="forgeStatus" class="forge-status mt-12">{{ forgeStatus }}</div>
          </div>
        </div>

        <!-- 4. Prompt Logic -->
        <div v-show="currentTab === 'prompt'" class="section-fade">
          <div class="glass-card">
            <label>프롬프트 자동화</label>
            <div class="toggle-grid">
              <div class="toggle-row">
                <span>중복 자동 정리</span>
                <ToggleSwitch v-model="cleanDuplicates" />
              </div>
              <div class="toggle-row">
                <span>공백 정리</span>
                <ToggleSwitch v-model="cleanSpaces" />
              </div>
              <div class="toggle-row">
                <span>언더바 변환</span>
                <ToggleSwitch v-model="cleanUnderscore" />
              </div>
              <div class="toggle-row">
                <span>태그 블록 모드</span>
                <ToggleSwitch :model-value="defaultBlockMode" @update:model-value="defaultBlockMode = $event; setBlockMode()" />
              </div>
              <div class="toggle-row">
                <span>갤러리 메타데이터 패널</span>
                <ToggleSwitch :model-value="galleryMetadata" @update:model-value="galleryMetadata = $event; window.localStorage.setItem('galleryShowMetadata', String(galleryMetadata))" />
              </div>
              <div class="toggle-row">
                <span>캐릭터 적용 시 copyright 자동 추가</span>
                <ToggleSwitch :model-value="autoAddCopyright" @update:model-value="autoAddCopyright = $event; saveCopyrightPref()" />
              </div>
              <div class="toggle-row">
                <span>HISTORY 선택 이미지 테두리 깜빡임</span>
                <ToggleSwitch :model-value="historyBlink" @update:model-value="historyBlink = $event; saveHistoryBlink()" />
              </div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>데이터 저장</label>
            <div class="btn-row-2">
              <button class="btn-pill" @click="act('save_settings')">전역 저장</button>
              <button class="btn-pill" @click="act('show_prompt_history')">히스토리 열기</button>
            </div>
          </div>
        </div>

        <!-- 4. Tab Layout (Drag & Drop) -->
        <div v-show="currentTab === 'tabs'" class="section-fade">
          <div class="glass-card">
            <label>탭 순서</label>
            <div class="drag-list">
              <div v-for="(tab, i) in tabOrder" :key="tab"
                class="drag-item"
                draggable="true"
                @dragstart="dragStart(i)" @dragover.prevent @drop="dragDrop(i)"
              >
                <span class="handle">⠿</span>
                <span class="name">{{ tab }}</span>
              </div>
            </div>
            <div class="btn-row-2 mt-16">
              <button class="btn-pill primary" @click="applyTabOrder">레이아웃 적용</button>
              <button class="btn-pill" @click="resetTabOrder">기본값으로</button>
            </div>
          </div>
        </div>

        <!-- 5. Theme -->
        <div v-show="currentTab === 'theme'" class="section-fade">
          <div class="glass-card">
            <label>프리셋</label>
            <p class="theme-note">고르면 바로 적용됩니다. 미리보기는 아래에서 직접 바꾼 색까지 반영한 실제 모습입니다.</p>
            <div class="theme-preset-grid">
              <button
                v-for="card in themePresetCards" :key="card.id" type="button"
                class="theme-preset" :class="{ selected: card.id === themePreset }"
                :aria-pressed="card.id === themePreset"
                @click="selectThemePreset(card.id)"
              >
                <!-- 실제 색으로 칠한 축소판 — 배경·표면·글자·강조가 어떻게 보이는지 -->
                <span class="theme-preview" :style="{ background: card.colors['bg-primary'], borderColor: card.colors.border }">
                  <span class="theme-preview-bar" :style="{ background: card.colors['bg-secondary'], borderColor: card.colors.rule }">
                    <span class="theme-preview-dot" :style="{ background: card.colors.accent }"></span>
                    <span class="theme-preview-line" :style="{ background: card.colors['text-muted'] }"></span>
                  </span>
                  <span class="theme-preview-body">
                    <span class="theme-preview-card" :style="{ background: card.colors['bg-card'], borderColor: card.colors.border }">
                      <span class="theme-preview-line wide" :style="{ background: card.colors['text-primary'] }"></span>
                      <span class="theme-preview-line" :style="{ background: card.colors['text-secondary'] }"></span>
                      <span class="theme-preview-btn" :style="{ background: card.colors['accent-fill'], color: card.colors['on-accent'] }">Aa</span>
                    </span>
                    <span class="theme-preview-states">
                      <span :style="{ background: card.colors['state-info'] }"></span>
                      <span :style="{ background: card.colors['state-ok'] }"></span>
                      <span :style="{ background: card.colors['state-alert'] }"></span>
                      <span :style="{ background: card.colors['state-warn'] }"></span>
                    </span>
                  </span>
                </span>
                <span class="theme-preset-name">
                  <span>{{ card.label }}</span>
                  <Icon v-if="card.id === themePreset" name="check" size="13" />
                </span>
              </button>
            </div>
          </div>

          <div class="glass-card mt-16 icon-animation-card">
            <div class="theme-card-head">
              <label>아이콘 애니메이션</label>
              <span class="icon-animation-stage">선택값만 저장</span>
            </div>
            <p class="theme-note">
              이후 아이콘 효과를 연결할 때 사용할 스타일을 미리 선택합니다.
              지금은 설정만 저장되며 실제 아이콘 애니메이션은 적용되지 않습니다.
            </p>
            <div class="icon-animation-options" role="group" aria-label="아이콘 애니메이션 스타일">
              <button
                v-for="option in ICON_ANIMATION_OPTIONS" :key="option.id" type="button"
                class="icon-animation-option" :class="{ selected: iconAnimationStyle === option.id }"
                :aria-pressed="iconAnimationStyle === option.id"
                @click="setIconAnimationStyle(option.id)"
              >
                <span class="icon-animation-option-head">
                  <strong>{{ option.label }}</strong>
                  <span v-if="iconAnimationStyle === option.id" class="icon-animation-selected">선택됨</span>
                </span>
                <small>{{ option.description }}</small>
              </button>
            </div>
          </div>

          <div class="glass-card mt-16">
            <div class="theme-card-head">
              <label>색 직접 바꾸기</label>
              <button class="btn-pill" :disabled="!themeHasOverrides" @click="resetThemeOverrides">전체 되돌리기</button>
            </div>
            <p class="theme-note">
              여기서 고른 색은 프리셋을 바꿔도 유지됩니다.
              나머지 색(배경 · 글자 · 경계)은 프리셋이 정합니다.
            </p>
            <div class="theme-field-list">
              <ColorField
                v-for="field in themeFields" :key="field.key"
                :label="field.label"
                :hint="field.hint"
                :model-value="themeColor(field.key)"
                :preset-value="themePresetColor(field.key)"
                :role="field.key === 'accent' ? 'accent' : 'fill'"
                :mode="themeColors.mode"
                @update:model-value="setThemeColor(field.key, $event)"
                @reset="resetThemeColor(field.key)"
              />
            </div>
          </div>
        </div>

        <!-- 6. Shortcuts -->
        <div v-show="currentTab === 'shortcuts'" class="section-fade">
          <div class="hint-banner"><Icon name="info" /> 같은 단축키도 <strong>현재 활성 탭</strong>에 따라 동작이 달라집니다.
            예: <kbd>Ctrl+Z</kbd>는 Editor 탭에서는 편집 Undo, T2I/I2I/Inpaint에서는 프롬프트 Undo.
            전역 키는 모든 탭에서 동일.
          </div>
          <div class="glass-card">
            <label>전역 단축키</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>설정 저장</span><kbd>Ctrl + S</kbd></div>
              <div class="s-row"><span>이미지 생성</span><kbd>Ctrl + G</kbd></div>
              <div class="s-row"><span>모달/패널 닫기</span><kbd>Esc</kbd></div>
              <div class="s-row"><span>히스토리 새로고침</span><kbd>F5</kbd></div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>HISTORY 네비게이션</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>이전 / 다음 이미지</span><kbd><Icon name="arrow-up" /><Icon name="arrow-down" /></kbd></div>
              <div class="s-row">
                <span>최상단 / 최하단으로 점프 (보조키 + ↑↓)</span>
                <select v-model="historyJumpModifier" @change="saveHistoryJumpModifier" class="hjm-select">
                  <option value="shiftKey">Shift</option>
                  <option value="ctrlKey">Ctrl</option>
                  <option value="altKey">Alt</option>
                </select>
              </div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>EDITOR 탭 단축키</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>파일 열기</span><kbd>Ctrl + O</kbd></div>
              <div class="s-row"><span>클립보드 붙여넣기</span><kbd>Ctrl + V</kbd></div>
              <div class="s-row"><span>저장 (원본 덮어쓰기)</span><kbd>Ctrl + S</kbd></div>
              <div class="s-row"><span>다른 이름으로 저장</span><kbd>Ctrl + Shift + S</kbd></div>
              <div class="s-row"><span>편집 Undo</span><kbd>Ctrl + Z</kbd></div>
              <div class="s-row"><span>편집 Redo</span><kbd>Ctrl + Y</kbd></div>
              <div class="s-row"><span>선택 해제</span><kbd>Esc</kbd></div>
              <div class="s-row"><span>이미지 확대/축소</span><kbd>마우스 휠</kbd></div>
              <div class="s-row"><span>이미지 회전 (5°)</span><kbd>Shift + 휠</kbd></div>
              <div class="s-row"><span>확대/회전/위치 초기화</span><kbd>Ctrl 빠르게 2회</kbd></div>
              <div class="s-row"><span>화면 이동 (팬)</span><kbd>Alt + 드래그</kbd></div>
              <div class="s-row"><span>변환 초기화 (대체)</span><kbd>Alt + 더블클릭</kbd></div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>프롬프트 편집 단축키</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>프롬프트 Undo</span><kbd>Ctrl + Z</kbd></div>
              <div class="s-row"><span>프롬프트 Redo</span><kbd>Ctrl + Y / Ctrl + Shift + Z</kbd></div>
              <div class="s-row"><span>자동완성 이동</span><kbd><Icon name="arrow-up" /><Icon name="arrow-down" /></kbd></div>
              <div class="s-row"><span>자동완성 선택</span><kbd>Tab / Enter</kbd></div>
              <div class="s-row"><span>자동완성 닫기</span><kbd>Esc</kbd></div>
            </div>
          </div>
        </div>

        <!-- 7. Anima Guard -->
        <div v-show="currentTab === 'guard'" class="section-fade">
          <div class="hint-banner">
            자동 해상도와 고해상도 배율 적용 시 이미지 비율을 유지하면서 최종 크기를 제한합니다.
            값은 SD 호환을 위해 저장할 때 8배수로 정렬됩니다.
          </div>
          <div class="glass-card">
            <label>ANIMA 해상도 가드</label>
            <div class="toggle-grid">
              <div class="toggle-row">
                <span>해상도 제한 활성화</span>
                <ToggleSwitch :model-value="animaGuardEnabled"
                  @update:model-value="animaGuardEnabled = $event; saveAnimaGuardSettings()" />
              </div>
            </div>
            <div class="defaults-grid mt-16" :class="{ 'guard-fields-disabled': !animaGuardEnabled }">
              <div class="def-field">
                <span>최대 총 면적 기준 (정사각형 한 변)</span>
                <input type="number" min="256" max="8192" step="8"
                  v-model.number="animaGuardMaxAreaSide" :disabled="!animaGuardEnabled"
                  @change="saveAnimaGuardSettings" />
              </div>
              <div class="def-field">
                <span>긴 한 변 최대값 (px)</span>
                <input type="number" min="256" max="8192" step="8"
                  v-model.number="animaGuardMaxSide" :disabled="!animaGuardEnabled"
                  @change="saveAnimaGuardSettings" />
              </div>
            </div>
            <div class="info-row mt-16">
              <span class="desc">현재 총 픽셀 한도</span>
              <span class="val-badge">{{ animaGuardMaxAreaSide }} × {{ animaGuardMaxAreaSide }} · {{ animaGuardMegapixels }} MP</span>
            </div>
            <div class="info-row mt-12">
              <span class="desc">긴 변 한도</span>
              <span class="val-badge">{{ animaGuardMaxSide }} px</span>
            </div>
            <button class="btn-pill mt-16" @click="resetAnimaGuardSettings">안전 기본값으로</button>
          </div>
        </div>

        <!-- 8. 기본값 설정 (탭별) -->
        <div v-show="currentTab === 'defaults'" class="section-fade">
          <!-- UI 크기 조절 -->
          <div class="glass-card mt-16">
            <label>UI 크기 (전역 zoom)</label>
            <div class="def-field-wide">
              <span>{{ Math.round(uiScale * 100) }}% — 폰트·아이콘·패딩 비례 확대</span>
              <input type="range" min="0.8" max="1.5" step="0.05" v-model.number="uiScale"
                @input="onUiScaleChange()" @change="onUiScaleChange(true)" class="w-slider" />
              <div class="scale-presets">
                <button v-for="p in [0.9, 1.0, 1.1, 1.2, 1.3]" :key="p"
                  class="scale-btn"
                  :class="{ active: Math.abs(uiScale - p) < 0.025 }"
                  @click="uiScale = p; onUiScaleChange(true)">
                  {{ Math.round(p * 100) }}%
                </button>
              </div>
            </div>
          </div>

          <div class="glass-card mt-16">
            <label>T2I 기본값 <span class="sync-badge" v-if="t2iSynced">동기화됨</span></label>
            <div class="defaults-grid">
              <div class="def-field"><span>스텝</span><input type="number" v-model.number="defaults.steps" /></div>
              <div class="def-field"><span>CFG</span><input type="number" v-model.number="defaults.cfg" step="0.5" /></div>
              <div class="def-field"><span>너비</span><input type="number" v-model.number="defaults.width" /></div>
              <div class="def-field"><span>높이</span><input type="number" v-model.number="defaults.height" /></div>
              <div class="def-field"><span>Seed</span><input type="text" v-model="defaults.seed" /></div>
              <div class="def-field"><span>Denoising (I2I)</span><input type="number" v-model.number="defaults.denoising" step="0.05" /></div>
              <div class="def-field"><span>Sampler</span>
                <CustomSelect v-model="defaults.sampler" :options="['', ...samplerList]" placeholder="Auto" />
              </div>
              <div class="def-field"><span>Scheduler</span>
                <CustomSelect v-model="defaults.scheduler" :options="['', ...schedulerList]" placeholder="Auto" />
              </div>
            </div>
            <button class="btn-pill mt-12" @click="syncFromT2I">T2I에서 가져오기</button>
          </div>

          <div class="glass-card mt-16">
            <label>EDITOR 기본값</label>
            <div class="defaults-grid">
              <div class="def-field"><span>브러시 크기</span><input type="number" v-model.number="defaults.brushSize" /></div>
              <div class="def-field"><span>효과 세기</span><input type="number" v-model.number="defaults.effectStrength" /></div>
              <div class="def-field"><span>YOLO 신뢰도</span><input type="number" v-model.number="defaults.yoloConf" step="0.05" /></div>
              <div class="def-field"><span>스냅 반경</span><input type="number" v-model.number="defaults.snapRadius" /></div>
            </div>
            <div class="def-field-wide mt-12">
              <span>사이드 패널 너비 ({{ editorSidePanelWidth }}px)</span>
              <input type="range" min="200" max="500" step="10" v-model.number="editorSidePanelWidth"
                @input="onSidePanelWidthChange()" @change="onSidePanelWidthChange(true)" class="w-slider" />
            </div>
          </div>

          <div class="glass-card mt-16">
            <label>SEARCH 기본값</label>
            <div class="defaults-grid">
              <div class="def-field"><span>기본 등급</span>
                <CustomSelect v-model="defaults.defaultRating" :options="['g', 's', 'q', 'e']" placeholder="Rating" />
              </div>
            </div>
          </div>

          <div class="glass-card mt-16">
            <label>확장 기본값</label>
            <div class="toggle-grid">
              <label class="toggle-row"><input type="checkbox" v-model="defaults.hires_enabled" /><span>Hires.fix 기본 활성화</span></label>
              <label class="toggle-row"><input type="checkbox" v-model="defaults.ad_enabled" /><span>ADetailer 기본 활성화</span></label>
              <label class="toggle-row"><input type="checkbox" v-model="defaults.sam3_enabled" /><span>SAM3 기본 활성화</span></label>
              <label class="toggle-row"><input type="checkbox" v-model="defaults.negpip_enabled" /><span>NegPiP 기본 활성화</span></label>
            </div>
          </div>
          <div class="btn-row-2 mt-16">
            <button class="btn-pill primary" @click="saveDefaults">기본값 저장</button>
            <button class="btn-pill" @click="resetDefaults">초기 상태로</button>
          </div>
        </div>

        <!-- 9. AI Assist (Ollama) -->
        <div v-show="currentTab === 'ollama'" class="section-fade">
          <div class="glass-card">
            <label>Ollama 설정</label>
            <div class="input-stack">
              <div class="input-unit">
                <span class="unit-label">서버 URL</span>
                <input v-model="ollamaUrl" @change="saveOllamaSettings" placeholder="http://localhost:11434" />
              </div>
              <div class="input-unit mt-12">
                <span class="unit-label">모델</span>
                <CustomSelect v-if="ollamaModels.length" v-model="ollamaModel" :options="ollamaModels" placeholder="모델 선택..." @update:modelValue="saveOllamaSettings" />
                <input v-else v-model="ollamaModel" @change="saveOllamaSettings" placeholder="llama3.1, gemma3 등" />
              </div>
              <label class="ollama-unload-row mt-12">
                <input type="checkbox" v-model="ollamaUnloadOnGen" @change="saveOllamaSettings" />
                <span>이미지 생성 시 LLM 언로드 (VRAM 확보) — 12B 등 큰 모델 + SD 공유 시 권장</span>
              </label>
            </div>
            <div class="btn-row-2 mt-16">
              <button class="btn-pill primary" @click="testOllama">연결 테스트</button>
              <button class="btn-pill" @click="loadOllamaModels">모델 새로고침</button>
            </div>
            <div class="info-row mt-12" v-if="ollamaModels.length">
              <span class="desc">AVAILABLE MODELS ({{ ollamaModels.length }})</span>
              <span class="val-badge">{{ ollamaModel }}</span>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>추천 모델</label>
            <div class="recommend-grid">
              <div class="rec-item best">
                <span class="rec-name">gemma3:4b</span>
                <span class="rec-desc">가장 추천 — 빠르고 태그 품질 우수, VRAM 3GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">llama3.1:8b</span>
                <span class="rec-desc">범용 고품질, 영어 태그 강점, VRAM 5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">mistral:7b</span>
                <span class="rec-desc">빠른 응답, 창의적 태그 변형에 강함, VRAM 5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">phi4-mini:3.8b</span>
                <span class="rec-desc">초경량, VRAM 부족 시 대안, VRAM 2.5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">qwen3:8b</span>
                <span class="rec-desc">다국어+태그 강점, thinking 모드, VRAM 5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">gemma3:12b</span>
                <span class="rec-desc">최고 품질, 여유 VRAM 시 추천, VRAM 8GB</span>
              </div>
            </div>
            <div class="rec-note mt-12">
              SD 이미지 생성과 동시 사용 시 VRAM을 공유하므로 4b 이하 경량 모델 권장.<br/>
              <code>ollama pull gemma3:4b</code> 로 설치
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>사용량</label>
            <div class="shortcut-grid">
              <div class="s-row"><span><Icon name="sparkles" /> 태그 확장</span><span>기존 태그를 고품질 태그로 확장</span></div>
              <div class="s-row"><span><Icon name="message" /> 자연어</span><span>자연어 설명을 태그로 변환</span></div>
              <div class="s-row"><span><Icon name="refresh" /> 유사 태그 추천</span><span>유사하지만 다른 태그 추천</span></div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { requestAction, useWidgetStore } from '../stores/widgetStore.js'
import { getStudioClient, replyData, StudioClientError, type StudioClient } from '../studio/client'
import CustomSelect from '../components/CustomSelect.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import ColorField from '../components/ColorField.vue'
import { DEFAULT_PRESET, EDITABLE_KEYS, PRESETS, PRESET_IDS, type EditableKey } from '../theme/presets'
import { getThemeState, reconcileTheme, resolveTheme, setTheme } from '../theme/applyTheme'
import {
  DEFAULT_ICON_ANIMATION_STYLE,
  ICON_ANIMATION_OPTIONS,
  normalizeIconAnimationStyle,
  type IconAnimationStyle,
} from '../theme/iconAnimationPreference'
import type { ActionName } from '../types/bridge'

interface SubTab {
  id: string
  label: string
  icon: string
  keywords: string
}

type ForgePathKey = 'checkpoint_dir' | 'lora_dir' | 'vae_dir' | 'text_encoder_dir'

interface ForgePathEntry {
  exists: boolean
  count: number
}

type RuntimeEngineId = 'forge' | 'comfyui'
type RuntimeAction = 'install' | 'update' | 'check_update' | 'start' | 'stop' | 'use'
type RuntimeConfigAction = 'set_auto_start' | 'save_extension_dir' | 'install_extension'
  | 'set_install_root' | 'use_managed_install' | 'set_primary_model_engine'
type RuntimeExtensionAction = 'check_extension' | 'update_extension'

interface RuntimeExtensionState {
  id: string
  name: string
  repoUrl: string
  version: string
  updateAvailable: boolean
  status: string
  busy: boolean
}

interface RuntimeEngineState {
  engine: RuntimeEngineId
  name: string
  installed: boolean
  running: boolean
  healthy: boolean
  busy: boolean
  active: boolean
  autoStart: boolean
  sourceMode: 'managed' | 'existing'
  existingRoot: string
  root: string
  installRoot: string
  sourceRoot: string
  pythonPath: string
  dataRoot: string
  modelPaths: Record<string, string[]>
  apiUrl: string
  version: string
  updateAvailable: boolean
  updateStatus: string
  extensionDir: string
  extensionDirExternal: boolean
  extensionWritable: boolean | null
  extensions: RuntimeExtensionState[]
  message: string
}

type GenerationApiEngine = 'webui' | 'comfyui'

interface GenerationApiTarget {
  localKey: string
  id: string
  name: string
  engine: GenerationApiEngine
  url: string
  enabled: boolean
  workflowPath: string
  img2imgWorkflowPath: string
}

interface GenerationApiJob {
  id: string
  mode: string
  target: string
  status: string
}

// 템플릿 인라인 핸들러(82·146행)가 window.localStorage를 참조 — 셋업 스코프에 노출
const window = globalThis.window
let settingsStudioClient: StudioClient | null = null

async function studioClient(): Promise<StudioClient> {
  if (!settingsStudioClient) settingsStudioClient = await getStudioClient()
  return settingsStudioClient
}

const subTabs: SubTab[] = [
  // keywords: 사용자 검색 시 라벨 외에도 매칭할 한/영 키워드들
  { id: 'general',   label: '일반',       icon: 'settings', keywords: 'general 일반 시스템 코어 버전' },
  { id: 'api',       label: '네트워크',   icon: 'globe', keywords: 'network api 네트워크 webui comfy url 백엔드 연결' },
  { id: 'runtimes',  label: '런타임 · 엔진', icon: 'cpu', keywords: 'runtime engine forge neo comfyui install update start stop extension 확장 설치 업데이트 실행' },
  { id: 'forge',     label: 'Forge',      icon: 'package', keywords: 'forge neo checkpoint model lora vae te text encoder 경로 폴더 모델 로라' },
  { id: 'prompt',    label: '로직',       icon: 'pencil', keywords: 'logic 로직 프롬프트 와일드카드 wildcard 제외 exclude 조건부' },
  { id: 'tabs',      label: '워크스페이스', icon: 'layers', keywords: 'workspace 워크스페이스 탭 순서 tab order layout' },
  { id: 'theme',     label: '테마',       icon: 'palette', keywords: 'theme 테마 색 컬러 다크 라이트 강조색 accent color dark light icon 아이콘 animation 애니메이션 claude 클로드 gpt' },
  { id: 'shortcuts', label: '단축키',     icon: 'keyboard', keywords: 'hotkeys shortcuts 단축키 키보드 ctrl shift z y s g' },
  { id: 'guard',     label: '가드',       icon: 'shield', keywords: 'anima guard 가드 자동 해상도 제한 최대 면적 픽셀 긴 변 resolution cap vram oom' },
  { id: 'defaults',  label: '기본값',     icon: 'sliders', keywords: 'defaults 기본값 t2i i2i inpaint 해상도 steps cfg sampler 시드' },
  { id: 'ollama',    label: 'AI 어시스트', icon: 'sparkles', keywords: 'ollama ai assist 어시스트 자동완성 번역' },
]
const currentTab = ref('general')
const settingsSearch = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const filteredSubTabs = computed(() => {
  const q = settingsSearch.value.trim().toLowerCase()
  if (!q) return subTabs
  return subTabs.filter(t =>
    t.label.toLowerCase().includes(q) ||
    (t.keywords || '').toLowerCase().includes(q)
  )
})
// 검색 결과가 1개면 자동 선택
watch(filteredSubTabs, (val) => {
  if (settingsSearch.value && val.length === 1 && currentTab.value !== val[0].id) {
    currentTab.value = val[0].id
  }
})
function focusSearch() {
  searchInputRef.value?.focus()
  searchInputRef.value?.select()
}
const generationApi = reactive({
  enabled: false,
  running: false,
  bindHost: '127.0.0.1',
  port: 17860,
  token: '',
  tokenPreview: '',
  listenUrl: '',
  defaultTarget: 'active',
  targets: [] as GenerationApiTarget[],
  recentJobs: [] as GenerationApiJob[],
})
const generationApiLoaded = ref(false)
const generationApiLoading = ref(false)
const generationApiBusy = ref(false)
const generationApiOperationId = ref('')
const generationApiBridgeAvailable = ref(false)
const generationApiNativeOperations = ref(false)
const generationApiStatus = ref('')
const generationApiTokenVisible = ref(false)
const generationApiWebMode = Boolean((window as any).__AISTUDIO_WS_PORT__ || (window as any).__AISTUDIO_WS_URL__)
const generationApiReadOnlyReason = computed(() => {
  if (generationApiWebMode) return '웹 모드에서는 서버·token·원격 target 설정을 변경할 수 없습니다.'
  if (generationApiLoaded.value && !generationApiBridgeAvailable.value) return '현재 백엔드는 생성 API 관리 기능을 제공하지 않습니다.'
  if (generationApiLoaded.value && !generationApiNativeOperations.value) return '이 환경에서는 생성 API 변경 작업이 비활성화되어 있습니다.'
  return ''
})
const generationApiMutationDisabled = computed(() =>
  generationApiBusy.value || generationApiLoading.value || !generationApiLoaded.value
  || !generationApiBridgeAvailable.value || !generationApiNativeOperations.value || generationApiWebMode
)
const generationApiLanExposed = computed(() => {
  const host = generationApi.bindHost.trim().toLowerCase()
  return !['127.0.0.1', 'localhost', '::1'].includes(host)
})
const generationApiBaseUrl = computed(() => {
  if (generationApi.listenUrl) return generationApi.listenUrl.replace(/\/$/, '')
  const configured = generationApi.bindHost.trim()
  const host = ['0.0.0.0', '::', ''].includes(configured) ? '127.0.0.1' : configured
  const displayHost = host.includes(':') && !host.startsWith('[') ? `[${host}]` : host
  return `http://${displayHost}:${generationApi.port}`
})

let generationApiTargetSequence = 0

function parseGenerationApiPayload(raw: unknown): any {
  let payload: any = raw
  for (let i = 0; i < 2 && typeof payload === 'string'; i += 1) {
    payload = JSON.parse(payload || '{}')
  }
  if (payload && typeof payload === 'object' && payload.value !== undefined
    && payload.config === undefined && payload.running === undefined && payload.snapshot === undefined) {
    return parseGenerationApiPayload(payload.value)
  }
  return payload && typeof payload === 'object' ? payload : {}
}

function normalizeGenerationApiTarget(raw: any, index: number): GenerationApiTarget {
  const engine = String(raw?.engine || raw?.type || 'webui').toLowerCase() === 'comfyui'
    ? 'comfyui' as const
    : 'webui' as const
  return {
    localKey: String(raw?.localKey || `api-target-${Date.now()}-${generationApiTargetSequence++}-${index}`),
    id: String(raw?.id || raw?.targetId || ''),
    name: String(raw?.name || raw?.label || ''),
    engine,
    url: String(raw?.url || raw?.apiUrl || raw?.endpoint || ''),
    enabled: raw?.enabled !== false,
    workflowPath: String(raw?.workflowPath || raw?.txt2imgWorkflowPath || ''),
    img2imgWorkflowPath: String(raw?.img2imgWorkflowPath || ''),
  }
}

function applyGenerationApiState(raw: unknown) {
  const payload = parseGenerationApiPayload(raw)
  if (payload.ok === false && !payload.snapshot) throw new Error(String(payload.error || '생성 API 상태를 불러오지 못했습니다.'))
  const snapshot = payload.snapshot && typeof payload.snapshot === 'object' ? payload.snapshot : payload
  const config = snapshot.config && typeof snapshot.config === 'object' ? snapshot.config : snapshot
  const server = snapshot.server && typeof snapshot.server === 'object' ? snapshot.server : snapshot
  if (typeof snapshot.nativeOperations === 'boolean') generationApiNativeOperations.value = snapshot.nativeOperations
  else generationApiNativeOperations.value = !generationApiWebMode

  generationApi.enabled = Boolean(config.enabled ?? config.autoStart ?? generationApi.enabled)
  generationApi.running = Boolean(server.running ?? server.started ?? snapshot.running ?? false)
  generationApi.bindHost = String(config.bindHost ?? config.host ?? generationApi.bindHost ?? '127.0.0.1')
  generationApi.port = Number(config.port ?? generationApi.port ?? 17860)
  generationApi.defaultTarget = String(config.defaultTarget ?? config.default_target ?? 'active') || 'active'
  generationApi.listenUrl = String(server.listenUrl || server.baseUrl || snapshot.listenUrl || snapshot.baseUrl || '')

  const token = String(config.token ?? snapshot.token ?? '')
  const looksRedacted = /[*•]/.test(token)
  if (token && !looksRedacted) generationApi.token = token
  generationApi.tokenPreview = String(config.tokenPreview || snapshot.tokenPreview || (looksRedacted ? token : ''))

  const targets = config.targets ?? snapshot.targets
  if (Array.isArray(targets)) {
    generationApi.targets = targets.map(normalizeGenerationApiTarget)
  }
  const jobs = snapshot.recentJobs ?? snapshot.jobs ?? server.recentJobs
  generationApi.recentJobs = Array.isArray(jobs)
    ? jobs.map((job: any, index: number) => ({
        id: String(job?.id || job?.jobId || `job-${index}`),
        mode: String(job?.mode || job?.task || 'generation'),
        target: String(job?.target || job?.targetId || 'active'),
        status: String(job?.status || job?.state || 'unknown').toLowerCase(),
      }))
    : []
  generationApiLoaded.value = true
}

function showGenerationApiError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  generationApiStatus.value = message
  generationApiBusy.value = false
  requestAction('show_toast', { type: 'error', msg: message })
}

async function loadGenerationApiState() {
  const studio = await studioClient()
  generationApiBridgeAvailable.value = studio.supports('generation_api.snapshot')
    && studio.supports('generation_api.execute')
  if (!studio.supports('generation_api.snapshot')) {
    generationApiLoaded.value = true
    generationApiNativeOperations.value = false
    return
  }
  generationApiLoading.value = true
  try {
    const reply = await studio.invoke('generation_api.snapshot', {})
    applyGenerationApiState(replyData(reply))
  } catch (error) {
    generationApiLoaded.value = true
    showGenerationApiError(error)
  } finally {
    generationApiLoading.value = false
  }
}

async function runGenerationApiAction(action: string, payload: Record<string, unknown> = {}) {
  if (generationApiMutationDisabled.value) return
  generationApiBusy.value = true
  generationApiStatus.value = `${action.replace(/_/g, ' ')} 요청 중…`
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('generation_api.execute', { action, payload })
    const result: any = replyData(reply)
    if (result.ok === false || result.accepted === false) throw new Error(String(result.error || '작업이 거부되었습니다.'))
    // A very fast worker can emit completed before the slot callback returns.
    // Do not overwrite that terminal message with a stale "started" message.
    if (generationApiBusy.value) {
      generationApiOperationId.value = String(result.operationId || '')
      generationApiStatus.value = '작업을 시작했습니다…'
    }
  } catch (error) {
    showGenerationApiError(error)
  }
}

function serializeGenerationApiTarget(target: GenerationApiTarget) {
  return {
    id: target.id.trim(),
    name: target.name.trim(),
    engine: target.engine,
    url: target.url.trim(),
    enabled: target.enabled,
    workflowPath: target.workflowPath.trim(),
    img2imgWorkflowPath: target.img2imgWorkflowPath.trim(),
  }
}

function validateGenerationApiConfig() {
  const port = Number(generationApi.port)
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('PORT는 1024~65535 정수여야 합니다.')
  if (!generationApi.bindHost.trim()) throw new Error('BIND HOST를 입력하세요.')
  const ids = new Set<string>()
  for (const target of generationApi.targets) {
    const id = target.id.trim()
    if (!id || id === 'active' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(id)) {
      throw new Error('TARGET ID는 active 이외의 1~64자 영문·숫자·._- 조합으로 입력하세요.')
    }
    if (ids.has(id)) throw new Error(`중복된 TARGET ID입니다: ${id}`)
    ids.add(id)
    if (!target.name.trim()) throw new Error(`${id}: NAME을 입력하세요.`)
    try {
      const parsed = new URL(target.url.trim())
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('protocol')
    } catch {
      throw new Error(`${id}: http:// 또는 https:// API URL을 입력하세요.`)
    }
  }
  if (generationApi.defaultTarget !== 'active' && !ids.has(generationApi.defaultTarget)) {
    throw new Error('DEFAULT TARGET이 현재 target 목록에 없습니다.')
  }
}

async function saveGenerationApiConfig() {
  try {
    validateGenerationApiConfig()
    await runGenerationApiAction('save_config', {
      enabled: generationApi.enabled,
      bindHost: generationApi.bindHost.trim(),
      port: Number(generationApi.port),
      token: generationApi.token,
      defaultTarget: generationApi.defaultTarget,
      targets: generationApi.targets.map(serializeGenerationApiTarget),
    })
  } catch (error) {
    showGenerationApiError(error)
  }
}

function addGenerationApiTarget() {
  const existing = new Set(generationApi.targets.map(target => target.id))
  let suffix = generationApi.targets.length + 1
  while (existing.has(`remote-${suffix}`)) suffix += 1
  generationApi.targets.push(normalizeGenerationApiTarget({
    id: `remote-${suffix}`,
    name: `Remote ${suffix}`,
    engine: 'webui',
    url: 'http://127.0.0.1:7860',
    enabled: true,
  }, generationApi.targets.length))
}

function removeGenerationApiTarget(index: number) {
  const removed = generationApi.targets.splice(index, 1)[0]
  if (removed && generationApi.defaultTarget === removed.id) generationApi.defaultTarget = 'active'
}

function testGenerationApiTarget(target: GenerationApiTarget) {
  runGenerationApiAction('test_target', {
    targetId: target.id.trim(),
    target: serializeGenerationApiTarget(target),
  })
}

function handleGenerationApiEvent(raw: unknown) {
  try {
    const event = parseGenerationApiPayload(raw)
    const eventType = String(event.type || '').toLowerCase()
    if (event.snapshot) applyGenerationApiState(event.snapshot)
    if (eventType === 'reconciled') {
      // Cursor 만료 뒤 bootstrap으로 되맞춘 상태다. 완료/실패 토스트 없이
      // 놓친 terminal event 때문에 남아 있던 busy 표시만 정리한다.
      generationApiBusy.value = false
      generationApiOperationId.value = ''
      return
    }
    if (['accepted', 'started', 'progress'].includes(eventType)) {
      generationApiBusy.value = true
      generationApiOperationId.value = String(event.operationId || '')
      generationApiStatus.value = String(event.message || '작업을 시작했습니다…')
      return
    }
    generationApiBusy.value = false
    generationApiOperationId.value = ''
    const ok = eventType === 'completed' && event.ok !== false
    const errorMessage = event.error && typeof event.error === 'object'
      ? event.error.message
      : event.error
    const message = String(event.message || (ok ? '작업이 완료되었습니다.' : errorMessage || '작업에 실패했습니다.'))
    generationApiStatus.value = message
    requestAction('show_toast', { type: ok ? 'success' : 'error', msg: message })
  } catch (error) {
    showGenerationApiError(error)
  }
}

async function copyText(value: string, successMessage: string) {
  if (!value) return
  try {
    if (globalThis.navigator?.clipboard?.writeText) {
      await globalThis.navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    requestAction('show_toast', { type: 'success', msg: successMessage })
  } catch {
    requestAction('show_toast', { type: 'error', msg: '클립보드에 복사하지 못했습니다.' })
  }
}

function copyGenerationApiToken() {
  copyText(generationApi.token, 'API token을 복사했습니다.')
}

function copyGenerationApiExample() {
  const token = generationApi.token || '<TOKEN>'
  const example = `curl -X POST "${generationApiBaseUrl.value}/api/v1/generations?wait=120" -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" -d '{"target":"${generationApi.defaultTarget}","mode":"txt2img","payload":{"prompt":"masterpiece","width":1024,"height":1024}}'`
  copyText(example, 'API 호출 예시를 복사했습니다.')
}

function createRuntimeEngine(engine: RuntimeEngineId, name: string): RuntimeEngineState {
  return {
    engine, name,
    installed: false, running: false, healthy: false, busy: false, active: false, autoStart: false,
    sourceMode: 'managed', existingRoot: '', root: '', installRoot: '', sourceRoot: '',
    pythonPath: '', dataRoot: '', modelPaths: {}, apiUrl: '', version: '',
    updateAvailable: false, updateStatus: 'Not checked',
    extensionDir: '', extensionDirExternal: false, extensionWritable: null, extensions: [], message: '',
  }
}

const runtimeEngineOrder: RuntimeEngineId[] = ['forge', 'comfyui']
const runtimeEngines = reactive<Record<RuntimeEngineId, RuntimeEngineState>>({
  forge: createRuntimeEngine('forge', 'Forge Neo'),
  comfyui: createRuntimeEngine('comfyui', 'ComfyUI'),
})
const runtimeExtensionDrafts = reactive<Record<RuntimeEngineId, string>>({ forge: '', comfyui: '' })
const runtimeExtensionFolderDirty = reactive<Record<RuntimeEngineId, boolean>>({ forge: false, comfyui: false })
const runtimeInstallRootDrafts = reactive<Record<RuntimeEngineId, string>>({ forge: '', comfyui: '' })
const runtimeInstallRootDirty = reactive<Record<RuntimeEngineId, boolean>>({ forge: false, comfyui: false })
const runtimeRepoUrls = reactive<Record<RuntimeEngineId, string>>({ forge: '', comfyui: '' })
const primaryModelEngine = ref<RuntimeEngineId | ''>('')
const runtimeNativeOperations = ref(false)
const runtimeBridgeAvailable = ref(false)
const runtimeLoaded = ref(false)
const runtimeLoading = ref(false)
const runtimeStatus = ref('')
const runtimeWebMode = Boolean((window as any).__AISTUDIO_WS_PORT__ || (window as any).__AISTUDIO_WS_URL__)
const runtimeCanMutate = computed(() =>
  runtimeLoaded.value && runtimeBridgeAvailable.value && runtimeNativeOperations.value && !runtimeWebMode
)
const runtimeReadOnlyReason = computed(() => {
  if (runtimeWebMode) return '웹 모드에서는 설치·업데이트·프로세스·외부 폴더 작업을 사용할 수 없습니다.'
  if (runtimeLoaded.value && !runtimeBridgeAvailable.value) return '현재 백엔드는 런타임 관리 기능을 제공하지 않습니다.'
  if (runtimeLoaded.value && !runtimeNativeOperations.value) return '이 환경에서는 네이티브 런타임 작업이 비활성화되어 있습니다.'
  return ''
})
const runtimeMutationTitle = computed(() => runtimeReadOnlyReason.value || '런타임 작업 실행')
const runtimePrimaryCandidates = computed<RuntimeEngineId[]>(() =>
  runtimeEngineOrder.filter(engineId => runtimeEngines[engineId].installed)
)

const forgePathFields: Array<{ key: ForgePathKey; label: string; description: string }> = [
  { key: 'checkpoint_dir', label: 'CHECKPOINT / MODEL', description: 'Stable-diffusion 모델 폴더' },
  { key: 'lora_dir', label: 'LORA', description: 'LoRA 가중치 폴더' },
  { key: 'vae_dir', label: 'VAE', description: 'VAE 모듈 폴더' },
  { key: 'text_encoder_dir', label: 'TEXT ENCODER (TE)', description: 'CLIP / T5 등 TE 모듈 폴더' },
]
const forgePaths = reactive<Record<ForgePathKey, string>>({
  checkpoint_dir: '', lora_dir: '', vae_dir: '', text_encoder_dir: '',
})
const forgeDefaults = reactive<Record<ForgePathKey, string>>({
  checkpoint_dir: '', lora_dir: '', vae_dir: '', text_encoder_dir: '',
})
const forgeEntries = reactive<Record<ForgePathKey, ForgePathEntry>>({
  checkpoint_dir: { exists: false, count: 0 },
  lora_dir: { exists: false, count: 0 },
  vae_dir: { exists: false, count: 0 },
  text_encoder_dir: { exists: false, count: 0 },
})
const forgeEnvironmentLocked = reactive<Record<ForgePathKey, boolean>>({
  checkpoint_dir: false, lora_dir: false, vae_dir: false, text_encoder_dir: false,
})
const forgeErrors = reactive<Record<ForgePathKey, string>>({
  checkpoint_dir: '', lora_dir: '', vae_dir: '', text_encoder_dir: '',
})
const forgeBusy = ref(false)
const forgeCanBrowse = ref(false)
const forgeCanMutate = ref(false)
const forgeReadOnlyReason = computed(() => {
  if (generationApiWebMode) return '웹 모드에서는 로컬 모델 폴더를 확인할 수만 있고 변경할 수 없습니다.'
  if (!forgeCanMutate.value) return '현재 연결은 Forge 모델 폴더 변경 기능을 제공하지 않습니다.'
  return ''
})
const forgeMutationTitle = computed(() => forgeReadOnlyReason.value || 'Forge 모델 폴더 변경')
const forgeBrowseTitle = computed(() => {
  if (forgeCanBrowse.value) return '폴더 선택'
  if (generationApiWebMode) return forgeReadOnlyReason.value
  return '현재 연결은 네이티브 폴더 선택 기능을 제공하지 않습니다.'
})
const forgeStatus = ref('')
const cleanDuplicates = ref(true)
const cleanSpaces = ref(true)
const cleanUnderscore = ref(true)
const defaultBlockMode = ref(window.localStorage.getItem('tagBlockMode') === 'true')
const galleryMetadata = ref(window.localStorage.getItem('galleryShowMetadata') !== 'false')
const autoAddCopyright = ref(window.localStorage.getItem('autoAddCopyright') !== 'false')   // ③ 기본 on
const historyJumpModifier = ref(window.localStorage.getItem('historyJumpModifier') || 'shiftKey')
const iconAnimationStyle = ref<IconAnimationStyle>(DEFAULT_ICON_ANIMATION_STYLE)
const animaGuardEnabled = ref(true)
const animaGuardMaxAreaSide = ref(1536)
const animaGuardMaxSide = ref(2048)
const animaGuardMegapixels = computed(() =>
  ((animaGuardMaxAreaSide.value * animaGuardMaxAreaSide.value) / 1_000_000).toFixed(2)
)

function normalizeGuardDimension(value: unknown, fallback: number) {
  const parsed = Number(value)
  const finite = Number.isFinite(parsed) ? Math.trunc(parsed) : fallback
  return Math.floor(Math.max(256, Math.min(8192, finite)) / 8) * 8
}

function saveAnimaGuardSettings() {
  animaGuardMaxAreaSide.value = normalizeGuardDimension(animaGuardMaxAreaSide.value, 1536)
  animaGuardMaxSide.value = normalizeGuardDimension(animaGuardMaxSide.value, 2048)
  requestAction('save_ui_prefs', {
    animaGuardEnabled: animaGuardEnabled.value,
    animaGuardMaxAreaSide: animaGuardMaxAreaSide.value,
    animaGuardMaxSide: animaGuardMaxSide.value,
  })
}

function resetAnimaGuardSettings() {
  animaGuardEnabled.value = true
  animaGuardMaxAreaSide.value = 1536
  animaGuardMaxSide.value = 2048
  saveAnimaGuardSettings()
  requestAction('show_toast', { type: 'success', msg: 'Anima Guard가 안전 기본값으로 초기화되었습니다' })
}

function saveCopyrightPref() {
  window.localStorage.setItem('autoAddCopyright', String(autoAddCopyright.value))
  requestAction('save_ui_prefs', { autoAddCopyright: autoAddCopyright.value })
}

const historyBlink = ref(window.localStorage.getItem('historyBlinkSelected') !== 'false')
function saveHistoryJumpModifier() {
  const value = ['shiftKey', 'ctrlKey', 'altKey'].includes(historyJumpModifier.value)
    ? historyJumpModifier.value
    : 'shiftKey'
  historyJumpModifier.value = value
  window.localStorage.setItem('historyJumpModifier', value)
  requestAction('save_ui_prefs', { historyJumpModifier: value })
}
function saveHistoryBlink() {
  window.localStorage.setItem('historyBlinkSelected', String(historyBlink.value))
  requestAction('save_ui_prefs', { historyBlinkSelected: historyBlink.value })
  try { window.dispatchEvent(new CustomEvent('historyBlinkChanged', { detail: { value: historyBlink.value } })) } catch {}
}

function setIconAnimationStyle(value: unknown) {
  const next = normalizeIconAnimationStyle(value)
  iconAnimationStyle.value = next
  requestAction('save_ui_prefs', { iconAnimationStyle: next })
}

// API에서 sampler/scheduler 목록 가져오기
const wStore = useWidgetStore()
const samplerList = computed(() => wStore.getProperty('sampler_combo', 'items') || [])
const schedulerList = computed(() => wStore.getProperty('scheduler_combo', 'items') || [])

function applyUiPrefs(prefs: any) {
  if (!prefs || typeof prefs !== 'object') return
  iconAnimationStyle.value = normalizeIconAnimationStyle(prefs.iconAnimationStyle)
  if (typeof prefs.tagBlockMode === 'boolean') { defaultBlockMode.value = prefs.tagBlockMode; window.localStorage.setItem('tagBlockMode', String(prefs.tagBlockMode)) }
  if (typeof prefs.cleanDuplicates === 'boolean') cleanDuplicates.value = prefs.cleanDuplicates
  if (typeof prefs.cleanSpaces === 'boolean') cleanSpaces.value = prefs.cleanSpaces
  if (typeof prefs.cleanUnderscore === 'boolean') cleanUnderscore.value = prefs.cleanUnderscore
  if (typeof prefs.galleryShowMetadata === 'boolean') { galleryMetadata.value = prefs.galleryShowMetadata; window.localStorage.setItem('galleryShowMetadata', String(prefs.galleryShowMetadata)) }
  if (typeof prefs.autoAddCopyright === 'boolean') { autoAddCopyright.value = prefs.autoAddCopyright; window.localStorage.setItem('autoAddCopyright', String(prefs.autoAddCopyright)) }
  if (['shiftKey', 'ctrlKey', 'altKey'].includes(prefs.historyJumpModifier)) {
    historyJumpModifier.value = prefs.historyJumpModifier
    window.localStorage.setItem('historyJumpModifier', prefs.historyJumpModifier)
  }
  if (typeof prefs.historyBlinkSelected === 'boolean') {
    historyBlink.value = prefs.historyBlinkSelected
    window.localStorage.setItem('historyBlinkSelected', String(prefs.historyBlinkSelected))
    try { window.dispatchEvent(new CustomEvent('historyBlinkChanged', { detail: { value: prefs.historyBlinkSelected } })) } catch {}
  }
  const restoredScale = Number(prefs.uiScale)
  if (Number.isFinite(restoredScale) && restoredScale >= 0.8 && restoredScale <= 1.5) {
    uiScale.value = restoredScale
    window.localStorage.setItem('ui.scale', String(restoredScale))
    try { window.dispatchEvent(new CustomEvent('uiScaleChanged', { detail: { value: restoredScale } })) } catch {}
  }
  const restoredPanelWidth = Number(prefs.editorSidePanelWidth)
  if (Number.isInteger(restoredPanelWidth) && restoredPanelWidth >= 200 && restoredPanelWidth <= 500) {
    editorSidePanelWidth.value = restoredPanelWidth
    window.localStorage.setItem('editorSidePanelWidth', String(restoredPanelWidth))
    try { window.dispatchEvent(new CustomEvent('editorSidePanelWidthChanged')) } catch {}
  }
  if (typeof prefs.animaGuardEnabled === 'boolean') animaGuardEnabled.value = prefs.animaGuardEnabled
  animaGuardMaxAreaSide.value = normalizeGuardDimension(prefs.animaGuardMaxAreaSide, 1536)
  animaGuardMaxSide.value = normalizeGuardDimension(prefs.animaGuardMaxSide, 2048)
  if (Array.isArray(prefs.tabOrder) && prefs.tabOrder.length > 0) {
    tabOrder.value = [...prefs.tabOrder]
    window.localStorage.setItem('tabOrder', JSON.stringify(prefs.tabOrder))
  }
  // Ollama 설정 복원
  if (prefs.ollamaUrl) { ollamaUrl.value = prefs.ollamaUrl; window.localStorage.setItem('ollamaUrl', prefs.ollamaUrl) }
  if (prefs.ollamaModel) { ollamaModel.value = prefs.ollamaModel; window.localStorage.setItem('ollamaModel', prefs.ollamaModel) }
  if (typeof prefs.ollamaUnloadOnGen === 'boolean') { ollamaUnloadOnGen.value = prefs.ollamaUnloadOnGen; window.localStorage.setItem('ollamaUnloadOnGen', String(prefs.ollamaUnloadOnGen)) }
  // 디스크가 테마의 단일 출처다(다른 기기/프로필에서 바꾼 값이 우선). reconcileTheme 은
  // 값이 같으면 아무것도 하지 않으므로 앱 시작 시 이미 맞췄어도 중복 적용이 아니다.
  reconcileTheme(prefs)
  syncThemeState()
}

function parseRuntimePayload(raw: unknown): any {
  let payload: any = raw
  for (let i = 0; i < 2 && typeof payload === 'string'; i += 1) {
    payload = JSON.parse(payload || '{}')
  }
  if (payload && typeof payload === 'object' && payload.value !== undefined && payload.engines === undefined) {
    return parseRuntimePayload(payload.value)
  }
  return payload && typeof payload === 'object' ? payload : {}
}

function normalizeRuntimeEngineId(value: unknown): RuntimeEngineId | null {
  const key = String(value || '').trim().toLowerCase().replace(/-/g, '_')
  if (key === 'forge' || key === 'forge_neo' || key === 'webui') return 'forge'
  if (key === 'comfyui' || key === 'comfy_ui' || key === 'comfy') return 'comfyui'
  return null
}

function normalizeRuntimeExtensions(raw: unknown): RuntimeExtensionState[] {
  const entries: any[] = Array.isArray(raw)
    ? raw
    : raw && typeof raw === 'object'
      ? Object.entries(raw as Record<string, unknown>).map(([id, item]) => (
          item && typeof item === 'object' ? { id, ...(item as Record<string, unknown>) } : { id, name: item }
        ))
      : []
  return entries.map((item, index) => {
    const extension = item && typeof item === 'object' ? item as Record<string, any> : {}
    const repoUrl = String(extension.repoUrl || extension.url || extension.repository || '')
    return {
      id: String(extension.id || extension.slug || extension.name || repoUrl || `extension-${index}`),
      name: String(extension.name || extension.id || extension.slug || `Extension ${index + 1}`),
      repoUrl,
      version: String(extension.version || extension.currentVersion || extension.commit || ''),
      updateAvailable: Boolean(extension.updateAvailable || extension.hasUpdate),
      status: String(extension.status || extension.updateStatus || ''),
      busy: Boolean(extension.busy),
    }
  })
}

function normalizeRuntimeModelPaths(raw: unknown): Record<string, string[]> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const paths: Record<string, string[]> = {}
  for (const [kind, value] of Object.entries(raw as Record<string, unknown>)) {
    const entries = Array.isArray(value) ? value : value ? [value] : []
    paths[kind] = entries.map(path => String(path || '').trim()).filter(Boolean)
  }
  return paths
}

function runtimeModelPathEntries(engineId: RuntimeEngineId) {
  return Object.entries(runtimeEngines[engineId].modelPaths).flatMap(([kind, paths]) =>
    paths.map(path => ({ kind: kind.replace(/_/g, ' ').toUpperCase(), path }))
  )
}

function applyRuntimeEngineState(engineId: RuntimeEngineId, raw: any) {
  if (!raw || typeof raw !== 'object') return
  const current = runtimeEngines[engineId]
  const updateAvailable = Boolean(raw.updateAvailable ?? raw.hasUpdate ?? current.updateAvailable)
  const latestVersion = String(raw.latestVersion || raw.availableVersion || '')
  const extensionDirValue = raw.extensionDir ?? raw.extensionDirectory
    ?? raw.extensionFolder ?? raw.paths?.extensionDir
  const extensionDir = extensionDirValue == null ? current.extensionDir : String(extensionDirValue)
  const sourceMode = String(raw.sourceMode || current.sourceMode).toLowerCase() === 'existing'
    ? 'existing' as const
    : 'managed' as const
  const existingRoot = String(raw.existingRoot ?? current.existingRoot ?? '')
  Object.assign(current, {
    engine: engineId,
    name: String(raw.name || current.name),
    installed: Boolean(raw.installed ?? current.installed),
    running: Boolean(raw.running ?? current.running),
    healthy: Boolean(raw.healthy ?? raw.ready ?? current.healthy),
    busy: Boolean(raw.busy ?? current.busy),
    active: Boolean(raw.active ?? current.active),
    autoStart: Boolean(raw.autoStart ?? raw.autostart ?? current.autoStart),
    sourceMode,
    existingRoot,
    root: String(raw.root || raw.dataRoot || raw.isolatedRoot || current.root || ''),
    installRoot: String(raw.installRoot ?? raw.sourceRoot ?? raw.root ?? current.installRoot ?? ''),
    sourceRoot: String(raw.sourceRoot ?? current.sourceRoot ?? ''),
    pythonPath: String(raw.pythonPath ?? current.pythonPath ?? ''),
    dataRoot: String(raw.dataRoot ?? raw.root ?? current.dataRoot ?? ''),
    modelPaths: raw.modelPaths === undefined
      ? current.modelPaths
      : normalizeRuntimeModelPaths(raw.modelPaths),
    apiUrl: String(raw.apiUrl || raw.endpoint || raw.url || current.apiUrl || ''),
    version: String(raw.version || raw.currentVersion || current.version || ''),
    updateAvailable,
    updateStatus: String(
      raw.updateStatus || raw.versionStatus ||
      (updateAvailable ? `Update available${latestVersion ? ` · ${latestVersion}` : ''}` : current.updateStatus)
    ),
    extensionDir: extensionDir || current.extensionDir,
    extensionDirExternal: Boolean(raw.extensionDirExternal ?? current.extensionDirExternal),
    extensionWritable: typeof raw.extensionWritable === 'boolean'
      ? raw.extensionWritable
      : current.extensionWritable,
    extensions: normalizeRuntimeExtensions(raw.extensions ?? raw.installedExtensions ?? current.extensions),
    message: String(raw.message || raw.statusMessage || raw.error || ''),
  })
  if (extensionDir && runtimeExtensionFolderDirty[engineId]
    && extensionDir.trim() === runtimeExtensionDrafts[engineId].trim()) {
    runtimeExtensionFolderDirty[engineId] = false
  }
  if (!runtimeExtensionFolderDirty[engineId]) {
    runtimeExtensionDrafts[engineId] = current.extensionDir
  }
  if (existingRoot && runtimeInstallRootDirty[engineId]
    && existingRoot.trim() === runtimeInstallRootDrafts[engineId].trim()) {
    runtimeInstallRootDirty[engineId] = false
  }
  if (!runtimeInstallRootDirty[engineId]) {
    runtimeInstallRootDrafts[engineId] = existingRoot
  }
}

function applyRuntimeSnapshot(raw: unknown) {
  const payload = parseRuntimePayload(raw)
  if (payload.ok === false) throw new Error(payload.error || '런타임 상태를 불러오지 못했습니다')
  const snapshot = payload.snapshot && typeof payload.snapshot === 'object' ? payload.snapshot : payload
  if (typeof snapshot.nativeOperations === 'boolean') runtimeNativeOperations.value = snapshot.nativeOperations
  else if (typeof payload.nativeOperations === 'boolean') runtimeNativeOperations.value = payload.nativeOperations
  const primary = normalizeRuntimeEngineId(snapshot.primaryModelEngine || payload.primaryModelEngine)
  if (primary) primaryModelEngine.value = primary

  const engines = snapshot.engines || snapshot.runtimes || snapshot.instances || snapshot
  if (Array.isArray(engines)) {
    for (const engine of engines) {
      const engineId = normalizeRuntimeEngineId(engine?.engine || engine?.id || engine?.kind)
      if (engineId) applyRuntimeEngineState(engineId, engine)
    }
  } else if (engines && typeof engines === 'object') {
    for (const [key, engine] of Object.entries(engines)) {
      const engineId = normalizeRuntimeEngineId((engine as any)?.engine || key)
      if (engineId) applyRuntimeEngineState(engineId, engine)
    }
  }
  runtimeLoaded.value = true
}

function showRuntimeError(error: unknown, engineId?: RuntimeEngineId) {
  const message = error instanceof Error ? error.message : String(error)
  runtimeStatus.value = message
  if (engineId) {
    runtimeEngines[engineId].busy = false
    runtimeEngines[engineId].message = message
  }
  requestAction('show_toast', { type: 'error', msg: message })
}

async function loadBackendRuntimeState() {
  const studio = await studioClient()
  runtimeBridgeAvailable.value = studio.supports('runtime.snapshot')
    && studio.supports('runtime.execute')
  if (!studio.supports('runtime.snapshot')) {
    runtimeNativeOperations.value = false
    runtimeLoaded.value = true
    return
  }
  runtimeLoading.value = true
  try {
    const reply = await studio.invoke('runtime.snapshot', {})
    applyRuntimeSnapshot(replyData(reply))
  } catch (error) {
    runtimeLoaded.value = true
    showRuntimeError(error)
  } finally {
    runtimeLoading.value = false
  }
}

function runtimeMutationDisabled(engineId: RuntimeEngineId) {
  return !runtimeCanMutate.value || runtimeLoading.value
    || runtimeEngines[engineId].busy
    || runtimeEngineOrder.some(candidate => runtimeEngines[candidate].busy)
}

function runtimeActionDisabled(engineId: RuntimeEngineId, action: RuntimeAction) {
  if (runtimeMutationDisabled(engineId)) return true
  const engine = runtimeEngines[engineId]
  if (action === 'install') return engine.installed || engine.sourceMode === 'existing'
  if (action === 'update') return !engine.installed || engine.sourceMode === 'existing'
  if (action === 'start') return !engine.installed || engine.running
  if (action === 'stop') return !engine.running
  if (action === 'use') return !engine.healthy || engine.active
  return false
}

function runtimeExtensionActionDisabled(engineId: RuntimeEngineId, extension: RuntimeExtensionState) {
  return runtimeMutationDisabled(engineId) || !runtimeExtensionWritable(engineId) || extension.busy
}

function runtimeExtensionWritable(engineId: RuntimeEngineId) {
  const engine = runtimeEngines[engineId]
  if (typeof engine.extensionWritable === 'boolean') return engine.extensionWritable
  return engine.installed || engine.extensionDirExternal
}

function runtimeInstallRootPlaceholder(engineId: RuntimeEngineId) {
  return engineId === 'forge'
    ? 'C:\\sd-webui-forge-classic'
    : 'C:\\ComfyUI 또는 ComfyUI_windows_portable'
}

function runtimeExtensionPlaceholder(engineId: RuntimeEngineId) {
  return engineId === 'forge' ? '...\\Forge Neo\\extensions' : '...\\ComfyUI\\custom_nodes'
}

function runtimeExtensionFolderHint(engineId: RuntimeEngineId) {
  return engineId === 'forge'
    ? 'Forge extensions 폴더. 기존 설치에서는 경로를 BROWSE하고 SAVE해야 확장 쓰기를 허용합니다.'
    : 'ComfyUI custom_nodes 폴더. 기존 설치에서는 경로를 BROWSE하고 SAVE해야 확장 쓰기를 허용합니다.'
}

async function runRuntimeOperation(
  engineId: RuntimeEngineId,
  action: RuntimeAction | RuntimeConfigAction | RuntimeExtensionAction,
  payload: Record<string, unknown> = {},
) {
  if (runtimeMutationDisabled(engineId)) return false
  const engine = runtimeEngines[engineId]
  engine.busy = true
  engine.message = ''
  runtimeStatus.value = `${engine.name}: ${action.replace(/_/g, ' ')} 요청 중…`
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('runtime.execute', { engine: engineId, action, payload })
    const result: any = replyData(reply)
    if (result.ok === false || result.accepted === false) {
      throw new Error(result.error || result.message || '런타임 작업이 거부되었습니다')
    }
    // accepted event 뒤 worker가 즉시 끝나면 terminal event가 invoke 응답보다
    // 먼저 올 수 있다. 그 결과를 낡은 "접수" 상태로 다시 덮지 않는다.
    if (engine.busy) {
      if (result.state) applyRuntimeEngineState(engineId, result.state)
      runtimeStatus.value = String(result.message || `${engine.name}: 작업이 접수되었습니다.`)
      requestAction('show_toast', { type: 'info', msg: runtimeStatus.value })
      await loadBackendRuntimeState()
    }
    return true
  } catch (error) {
    showRuntimeError(error, engineId)
    return false
  }
}

async function setRuntimeAutoStart(engineId: RuntimeEngineId, autoStart: boolean) {
  await runRuntimeOperation(engineId, 'set_auto_start', { autoStart })
}

async function browseRuntimeInstallDirectory(engineId: RuntimeEngineId) {
  if (runtimeMutationDisabled(engineId)) return
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('native.pick_directory', { purpose: 'runtime_install', engine: engineId })
    const result: any = replyData(reply)
    if (result.cancelled) return
    if (result.ok === false) throw new Error(result.error || '기존 설치 폴더를 선택하지 못했습니다')
    const path = String(result.path || result.directory || '')
    if (!path) throw new Error('선택된 설치 폴더가 없습니다')
    runtimeInstallRootDrafts[engineId] = path
    runtimeInstallRootDirty[engineId] = true
  } catch (error) {
    showRuntimeError(error, engineId)
  }
}

async function linkExistingRuntime(engineId: RuntimeEngineId) {
  const existingRoot = runtimeInstallRootDrafts[engineId].trim()
  if (!existingRoot) return
  await runRuntimeOperation(engineId, 'set_install_root', { existingRoot })
}

async function useManagedRuntime(engineId: RuntimeEngineId) {
  const changed = await runRuntimeOperation(engineId, 'use_managed_install')
  if (changed) {
    runtimeInstallRootDirty[engineId] = false
    runtimeInstallRootDrafts[engineId] = ''
  }
}

async function setPrimaryModelEngine(engineId: RuntimeEngineId) {
  await runRuntimeOperation(engineId, 'set_primary_model_engine', { primaryModelEngine: engineId })
}

async function browseRuntimeExtensionDirectory(engineId: RuntimeEngineId) {
  if (runtimeMutationDisabled(engineId)) return
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('native.pick_directory', { purpose: 'runtime_extension', engine: engineId })
    const result: any = replyData(reply)
    if (result.cancelled) return
    if (result.ok === false) throw new Error(result.error || '확장 폴더를 선택하지 못했습니다')
    const path = String(result.path || result.directory || '')
    if (!path) throw new Error('선택된 확장 폴더가 없습니다')
    runtimeExtensionDrafts[engineId] = path
    runtimeExtensionFolderDirty[engineId] = true
  } catch (error) {
    showRuntimeError(error, engineId)
  }
}

async function saveRuntimeExtensionDirectory(engineId: RuntimeEngineId) {
  const extensionDir = runtimeExtensionDrafts[engineId].trim()
  if (!extensionDir) return
  await runRuntimeOperation(engineId, 'save_extension_dir', { extensionDir })
}

async function installRuntimeExtension(engineId: RuntimeEngineId) {
  const repoUrl = runtimeRepoUrls[engineId].trim()
  if (!repoUrl) return
  await runRuntimeOperation(engineId, 'install_extension', { repoUrl })
}

async function runRuntimeExtensionOperation(
  engineId: RuntimeEngineId,
  action: RuntimeExtensionAction,
  extension: RuntimeExtensionState,
) {
  await runRuntimeOperation(engineId, action, {
    extensionId: extension.id,
    repoUrl: extension.repoUrl,
  })
}

function handleBackendRuntimeEvent(raw: unknown) {
  try {
    const payload = parseRuntimePayload(raw)
    const engineId = normalizeRuntimeEngineId(payload.engine || payload.engineId || payload.state?.engine)
    const eventType = String(payload.type || payload.event || '').toLowerCase()
    if (payload.snapshot || payload.engines || payload.runtimes) applyRuntimeSnapshot(payload)
    else if (engineId && payload.state) applyRuntimeEngineState(engineId, payload.state)
    if (engineId && ['accepted', 'started', 'start', 'progress'].includes(eventType)) {
      // A started snapshot is captured immediately before manager.execute()
      // marks the engine busy.  Lifecycle state therefore wins over that one
      // field while every other snapshot field remains authoritative.
      runtimeEngines[engineId].busy = true
    }

    const rawError = payload.error && typeof payload.error === 'object'
      ? payload.error.message
      : payload.error
    const message = String(payload.message || rawError || '')
    if (message) {
      runtimeStatus.value = message
      if (engineId) runtimeEngines[engineId].message = message
    }
    if (['complete', 'completed', 'failed', 'error', 'cancelled', 'canceled'].includes(eventType)) {
      if (engineId) runtimeEngines[engineId].busy = false
      if (engineId && ['complete', 'completed'].includes(eventType)
        && String(payload.action || '') === 'install_extension') {
        runtimeRepoUrls[engineId] = ''
      }
      window.setTimeout(() => { void loadBackendRuntimeState() }, 150)
    }
  } catch (error) {
    showRuntimeError(error)
  }
}

async function loadStudioBootstrap(studio: StudioClient): Promise<boolean> {
  if (!studio.supports('sync.bootstrap')) return false

  forgeBusy.value = true
  runtimeLoading.value = true
  generationApiLoading.value = true
  try {
    const reply = await studio.invoke('sync.bootstrap', {})
    const data: any = replyData(reply)
    applyForgePathState(data.modelPaths)
    applyRuntimeSnapshot(data.runtime)
    applyGenerationApiState(data.generationApi)
    forgeCanBrowse.value = !generationApiWebMode && studio.supports('native.pick_directory')
    forgeCanMutate.value = !generationApiWebMode
      && studio.supports('model_paths.save')
      && studio.supports('model_paths.reset')
      && studio.supports('model_paths.refresh')
    runtimeBridgeAvailable.value = studio.supports('runtime.snapshot')
      && studio.supports('runtime.execute')
    generationApiBridgeAvailable.value = studio.supports('generation_api.snapshot')
      && studio.supports('generation_api.execute')
    return true
  } catch (error) {
    console.warn('[studio] bootstrap failed; retrying individual snapshots', error)
    return false
  } finally {
    forgeBusy.value = false
    runtimeLoading.value = false
    generationApiLoading.value = false
  }
}

function handleModelPathsEvent(raw: unknown) {
  try {
    const payload = parseForgePayload(raw)
    const state = payload?.snapshot && typeof payload.snapshot === 'object' ? payload.snapshot : payload
    if (state?.paths || state?.entries || state?.ok === false) applyForgePathState(state)
  } catch (error) {
    showForgeError(error)
  }
}

function parseForgePayload(raw: unknown): any {
  if (typeof raw === 'string') return JSON.parse(raw || '{}')
  return raw || {}
}

function applyForgePathState(payload: any) {
  if (payload?.ok === false || (!payload?.paths && !payload?.entries)) {
    const details = payload?.errors && typeof payload.errors === 'object' ? payload.errors : {}
    for (const field of forgePathFields) forgeErrors[field.key] = String(details[field.key] || '')
    throw new Error(payload?.error || 'Forge 경로 정보를 불러오지 못했습니다')
  }
  for (const field of forgePathFields) {
    const key = field.key
    forgePaths[key] = String(payload.paths?.[key] || '')
    forgeDefaults[key] = String(payload.defaults?.[key] || '')
    forgeEnvironmentLocked[key] = Boolean(payload.environmentLocked?.[key])
    forgeEntries[key].exists = Boolean(payload.entries?.[key]?.exists)
    forgeEntries[key].count = Number(payload.entries?.[key]?.count || 0)
    forgeErrors[key] = ''
  }
  const total = forgePathFields.reduce((sum, field) => sum + forgeEntries[field.key].count, 0)
  forgeStatus.value = `${total.toLocaleString()}개 파일을 로컬 경로에서 확인했습니다.`
}

function showForgeError(error: unknown) {
  const fieldErrors = error instanceof StudioClientError ? error.fields : undefined
  if (fieldErrors) {
    for (const field of forgePathFields) {
      forgeErrors[field.key] = String(fieldErrors[field.key] || '')
    }
  }
  const msg = error instanceof Error ? error.message : String(error)
  forgeStatus.value = msg
  requestAction('show_toast', { type: 'error', msg })
}

async function loadForgePaths() {
  const studio = await studioClient()
  forgeCanBrowse.value = !((window as any).__AISTUDIO_WS_PORT__ || (window as any).__AISTUDIO_WS_URL__)
    && studio.supports('native.pick_directory')
  forgeCanMutate.value = !generationApiWebMode
    && studio.supports('model_paths.save')
    && studio.supports('model_paths.reset')
    && studio.supports('model_paths.refresh')
  if (!studio.supports('model_paths.snapshot')) return
  forgeBusy.value = true
  try {
    const reply = await studio.invoke('model_paths.snapshot', {})
    applyForgePathState(replyData(reply))
  } catch (error) {
    showForgeError(error)
  } finally {
    forgeBusy.value = false
  }
}

async function browseForgePath(key: ForgePathKey) {
  if (!forgeCanBrowse.value) return
  forgeBusy.value = true
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('native.pick_directory', { purpose: 'model_path', key })
    const payload: any = replyData(reply)
    if (payload?.cancelled) return
    if (payload?.ok === false) throw new Error(payload?.error || '폴더를 선택하지 못했습니다')
    forgePaths[key] = String(payload.path || '')
    forgeErrors[key] = ''
  } catch (error) {
    showForgeError(error)
  } finally {
    forgeBusy.value = false
  }
}

async function saveForgePaths() {
  if (!forgeCanMutate.value) return
  forgeBusy.value = true
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('model_paths.save', { paths: { ...forgePaths } })
    applyForgePathState(replyData(reply))
  } catch (error) {
    showForgeError(error)
  } finally {
    forgeBusy.value = false
  }
}

async function refreshForgePaths() {
  if (!forgeCanMutate.value) return
  forgeBusy.value = true
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('model_paths.refresh', {})
    applyForgePathState(replyData(reply))
    requestAction('show_toast', { type: 'success', msg: 'Forge 모델 폴더를 다시 스캔했습니다' })
  } catch (error) {
    showForgeError(error)
  } finally {
    forgeBusy.value = false
  }
}

async function resetForgePaths() {
  if (!forgeCanMutate.value) return
  forgeBusy.value = true
  try {
    const studio = await studioClient()
    const reply = await studio.invoke('model_paths.reset', {})
    applyForgePathState(replyData(reply))
  } catch (error) {
    showForgeError(error)
  } finally {
    forgeBusy.value = false
  }
}

// UI prefs 로드 시 동기화
import { onBackendEvent, getBackend } from '../bridge.js'
let disconnectBackendRuntimeEvent: (() => void) | null = null
let disconnectGenerationApiEvent: (() => void) | null = null
let disconnectModelPathsEvent: (() => void) | null = null
let disconnectOllamaModelsEvent: (() => void) | null = null
let disconnectUiPrefsEvent: (() => void) | null = null
let settingsDisposed = false
onMounted(async () => {
  settingsDisposed = false
  disconnectOllamaModelsEvent = onBackendEvent('ollamaModelsReady', handleOllamaModels)
  let studio: StudioClient
  try {
    studio = await studioClient()
  } catch (error) {
    if (!settingsDisposed) {
      const message = error instanceof Error ? error.message : String(error)
      forgeStatus.value = message
      runtimeStatus.value = message
      generationApiStatus.value = message
      runtimeLoaded.value = true
      generationApiLoaded.value = true
      requestAction('show_toast', { type: 'error', msg: `설정 연결 실패: ${message}` })
    }
    return
  }
  if (settingsDisposed) return
  disconnectBackendRuntimeEvent = studio.subscribe('runtime', event => handleBackendRuntimeEvent({
    ...(event.data && typeof event.data === 'object' ? event.data as Record<string, unknown> : {}),
    ...(event.data && typeof event.data === 'object'
      && (event.data as Record<string, unknown>).update
      && typeof (event.data as Record<string, unknown>).update === 'object'
      ? (event.data as Record<string, any>).update as Record<string, unknown>
      : {}),
    message: event.data && typeof event.data === 'object'
      ? (event.data as Record<string, any>).message
        ?? (event.data as Record<string, any>).update?.message
        ?? (event.data as Record<string, any>).result?.message
      : undefined,
    type: event.type,
    operationId: event.jobId,
  }))
  disconnectGenerationApiEvent = studio.subscribe('generation_api', event => handleGenerationApiEvent({
    ...(event.data && typeof event.data === 'object' ? event.data as Record<string, unknown> : {}),
    message: event.data && typeof event.data === 'object'
      ? (event.data as Record<string, any>).message
        ?? (event.data as Record<string, any>).result?.message
      : undefined,
    type: event.type,
    operationId: event.jobId,
  }))
  disconnectModelPathsEvent = studio.subscribe('model_paths', event => handleModelPathsEvent(event.data))
  autoLoadOllamaModels()   // AI Assistant 모델 목록 시작 시 자동 로드
  // defaults 로드
  const bk: any = await getBackend()
  if (settingsDisposed) return
  const bootstrapped = await loadStudioBootstrap(studio)
  if (settingsDisposed) return
  if (!bootstrapped) {
    await Promise.all([loadForgePaths(), loadBackendRuntimeState(), loadGenerationApiState()])
    if (settingsDisposed) return
  }
  if (bk.getTabDefaults) {
    bk.getTabDefaults((json: string) => {
      try { const d = JSON.parse(json); Object.assign(defaults, d) } catch {}
    })
  }
  // SettingsView는 지연 로드되므로 시작 시 1회 emit된 이벤트를 놓쳐도 파일에서 능동 복원.
  if (bk.getUiPrefs) {
    bk.getUiPrefs((json: string) => {
      try { applyUiPrefs(JSON.parse(json)) } catch {}
    })
  }
  disconnectUiPrefsEvent = onBackendEvent('uiPrefsLoaded', (json: string) => {
    try { applyUiPrefs(JSON.parse(json)) } catch {}
  })
})
onUnmounted(() => {
  settingsDisposed = true
  disconnectBackendRuntimeEvent?.()
  disconnectBackendRuntimeEvent = null
  disconnectGenerationApiEvent?.()
  disconnectGenerationApiEvent = null
  disconnectModelPathsEvent?.()
  disconnectModelPathsEvent = null
  disconnectOllamaModelsEvent?.()
  disconnectOllamaModelsEvent = null
  disconnectUiPrefsEvent?.()
  disconnectUiPrefsEvent = null
})
function setBlockMode() {
  window.localStorage.setItem('tagBlockMode', String(defaultBlockMode.value))
  console.log('[Settings] Block mode set to:', defaultBlockMode.value)
}

const defaultOrder = ['T2I','I2I','Inpaint','Event Gen','Search','Batch / Upscale','Gallery','XYZ Plot','PNG Info','Favorites','Settings']
function _loadTabOrder() {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    if (saved.length > 0) return saved
  } catch {}
  return [...defaultOrder]
}
const tabOrder = ref<string[]>(_loadTabOrder())
let dragIdx = -1

function dragStart(i: number) { dragIdx = i }
function persistTabOrder() {
  window.localStorage.setItem('tabOrder', JSON.stringify(tabOrder.value))
  requestAction('save_ui_prefs', { tabOrder: tabOrder.value })
  requestAction('set_tab_order', { order: tabOrder.value })
  // TabBar에게 즉시 알림 — storage event는 같은 창 변경엔 발생 안 하므로 커스텀 이벤트 사용
  try { window.dispatchEvent(new CustomEvent('tabOrderChanged')) } catch {}
}
function dragDrop(i: number) {
  if (dragIdx < 0) return
  const item = tabOrder.value.splice(dragIdx, 1)[0]
  tabOrder.value.splice(i, 0, item)
  dragIdx = -1
  persistTabOrder()
}
const applyTabOrder = () => {
  persistTabOrder()
  requestAction('show_toast', { type: 'success', msg: '탭 순서가 적용되었습니다' })
}
const resetTabOrder = () => {
  tabOrder.value = [...defaultOrder]
  persistTabOrder()
}

// ── 테마 ────────────────────────────────────────────────────────────────────
// 색의 단일 출처는 core/theme_presets.py → theme/presets.ts 다. 여기서는 고르기만
// 하고, 계산·적용·영속은 전부 theme/applyTheme.ts 에 맡긴다.
const themePreset = ref(getThemeState().preset)
const themeOverrides = ref<Record<string, string>>(getThemeState().overrides)

/** setTheme 이 걸러낸 결과를 되읽는다 — 화면이 실제 적용값과 어긋나지 않게. */
function syncThemeState() {
  const state = getThemeState()
  themePreset.value = state.preset
  themeOverrides.value = state.overrides
}

function persistTheme(payload: { theme: string; themeOverrides: Record<string, string> }) {
  requestAction('save_ui_prefs', payload)
}

/** 현재 최종 색 — ColorField 의 대비 계산 배경도 여기서 꺼낸다. */
const themeColors = computed(() => resolveTheme(themePreset.value, themeOverrides.value))

// 프리셋 카드 미리보기는 **덮어쓰기를 반영한** 색으로 그린다. 프리셋 원본 색만
// 보여 주면 "고르면 이렇게 된다" 는 약속이 거짓말이 된다.
const themePresetCards = computed(() =>
  PRESET_IDS.map(id => ({
    id,
    label: PRESETS[id].label || id,
    colors: resolveTheme(id, themeOverrides.value),
  })),
)

interface ThemeColorField {
  key: EditableKey
  label: string
  hint: string
}
// EDITABLE_KEYS 순서를 그대로 따른다 — 키가 늘면 설명만 채우면 된다.
const THEME_FIELD_COPY: Record<string, { label: string; hint: string }> = {
  accent: { label: '강조', hint: '주 실행 버튼과 열린 상태 · 포커스 테두리에 쓰입니다.' },
  'state-info': { label: '선택', hint: '선택된 항목과 진행 중 표시에 쓰입니다.' },
  'state-alert': { label: '알림', hint: '오류와 경고에 쓰입니다.' },
  'state-ok': { label: '연결', hint: '성공과 연결됨 표시에 쓰입니다.' },
}
const themeFields = computed<ThemeColorField[]>(() =>
  EDITABLE_KEYS.map(key => ({
    key,
    label: THEME_FIELD_COPY[key]?.label || key,
    hint: THEME_FIELD_COPY[key]?.hint || '',
  })),
)

const themeHasOverrides = computed(() => Object.keys(themeOverrides.value).length > 0)

/** 프리셋 색(덮어쓰기 이전) — ColorField 의 '되돌리기' 목적지. */
function themePresetColor(key: EditableKey): string {
  return PRESETS[themePreset.value]?.[key] || PRESETS[DEFAULT_PRESET][key]
}
function themeColor(key: EditableKey): string {
  return themeColors.value[key] || themePresetColor(key)
}

function selectThemePreset(id: string) {
  // 덮어쓰기는 일부러 유지한다 — 고른 강조색이 프리셋 전환으로 사라지면 놀란다.
  setTheme({ preset: id }, persistTheme)
  syncThemeState()
}
function setThemeColor(key: EditableKey, value: string) {
  setTheme({ overrides: { ...themeOverrides.value, [key]: value } }, persistTheme)
  syncThemeState()
}
function resetThemeColor(key: EditableKey) {
  const next = { ...themeOverrides.value }
  delete next[key]
  setTheme({ overrides: next }, persistTheme)
  syncThemeState()
}
function resetThemeOverrides() {
  setTheme({ overrides: {} }, persistTheme)
  syncThemeState()
  requestAction('show_toast', { type: 'success', msg: '직접 바꾼 색을 모두 프리셋 기본값으로 되돌렸습니다' })
}

const act = (name: ActionName) => {
  // SAVE GLOBAL 시 localStorage 설정도 함께 저장
  if (name === 'save_settings') {
    requestAction('save_ui_prefs', {
      tagBlockMode: defaultBlockMode.value,
      cleanDuplicates: cleanDuplicates.value,
      cleanSpaces: cleanSpaces.value,
      cleanUnderscore: cleanUnderscore.value,
      galleryShowMetadata: galleryMetadata.value,
      autoAddCopyright: autoAddCopyright.value,
      historyJumpModifier: historyJumpModifier.value,
      historyBlinkSelected: historyBlink.value,
      iconAnimationStyle: iconAnimationStyle.value,
      uiScale: uiScale.value,
      editorSidePanelWidth: editorSidePanelWidth.value,
      tabOrder: tabOrder.value,
      animaGuardEnabled: animaGuardEnabled.value,
      animaGuardMaxAreaSide: animaGuardMaxAreaSide.value,
      animaGuardMaxSide: animaGuardMaxSide.value,
      // Ollama
      ollamaUrl: ollamaUrl.value,
      ollamaModel: ollamaModel.value,
      ollamaUnloadOnGen: ollamaUnloadOnGen.value,
    })
  }
  requestAction(name)
}

// 기본값 설정
const FACTORY_DEFAULTS = { steps: 20, cfg: 7, width: 1024, height: 1024, seed: '-1', denoising: 0.75, sampler: '', scheduler: '', brushSize: 20, effectStrength: 15, yoloConf: 0.25, snapRadius: 12, defaultRating: 'g', hires_enabled: false, ad_enabled: false, sam3_enabled: false, negpip_enabled: false }
const defaults = reactive({ ...FACTORY_DEFAULTS })

function saveDefaults() {
  requestAction('save_tab_defaults', { ...defaults })
}

// defaults 변경 감시 → 자동 저장 알림
let defaultsTimer: ReturnType<typeof setTimeout> | null = null
watch(defaults, () => {
  clearTimeout(defaultsTimer as ReturnType<typeof setTimeout>)
  defaultsTimer = setTimeout(() => {
    requestAction('save_tab_defaults', { ...defaults })
  }, 1500)
}, { deep: true })
function resetDefaults() { Object.assign(defaults, FACTORY_DEFAULTS) }

// 사이드 패널 너비 — localStorage로 즉시 반영하고 ui_prefs에 영속
const editorSidePanelWidth = ref(parseInt(window.localStorage.getItem('editorSidePanelWidth') || '280'))

// UI 크기 (전역 zoom) — App.vue가 _applyUiScale로 적용
const uiScale = ref(parseFloat(window.localStorage.getItem('ui.scale') || '1.0') || 1.0)
function onUiScaleChange(persist = false) {
  const v = Math.max(0.8, Math.min(1.5, uiScale.value))
  uiScale.value = v
  try { window.localStorage.setItem('ui.scale', String(v)) } catch {}
  if (persist) requestAction('save_ui_prefs', { uiScale: v })
  // 같은 창에서 즉시 반영
  try { window.dispatchEvent(new CustomEvent('uiScaleChanged', { detail: { value: v } })) } catch {}
}

// (자동화 자동 재시작 설정 제거됨 — 큐는 오직 '▶ 시작' 버튼으로만 시작. QueuePanel과 일치)
function onSidePanelWidthChange(persist = false) {
  const v = Math.max(200, Math.min(500, Math.round(editorSidePanelWidth.value)))
  editorSidePanelWidth.value = v
  window.localStorage.setItem('editorSidePanelWidth', String(v))
  if (persist) requestAction('save_ui_prefs', { editorSidePanelWidth: v })
  try { window.dispatchEvent(new CustomEvent('editorSidePanelWidthChanged')) } catch {}
}

const t2iSynced = ref(false)
async function syncFromT2I() {
  const { useWidgetStore } = await import('../stores/widgetStore.js')
  const store = useWidgetStore()
  const w: any = store.widgets
  defaults.steps = parseInt(w.steps_input) || defaults.steps
  defaults.cfg = parseFloat(w.cfg_input) || defaults.cfg
  defaults.width = parseInt(w.width_input) || defaults.width
  defaults.height = parseInt(w.height_input) || defaults.height
  defaults.seed = w.seed_input || defaults.seed
  defaults.sampler = w.sampler_combo || defaults.sampler
  defaults.scheduler = w.scheduler_combo || defaults.scheduler
  t2iSynced.value = true
  setTimeout(() => { t2iSynced.value = false }, 3000)
}

// Ollama
const ollamaUrl = ref(window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434')
const ollamaModel = ref(window.localStorage.getItem('ollamaModel') || 'gemma3:4b')
const ollamaModels = ref<string[]>([])
const ollamaUnloadOnGen = ref(window.localStorage.getItem('ollamaUnloadOnGen') === 'true')

function saveOllamaSettings() {
  window.localStorage.setItem('ollamaUrl', ollamaUrl.value)
  window.localStorage.setItem('ollamaModel', ollamaModel.value)
  window.localStorage.setItem('ollamaUnloadOnGen', String(ollamaUnloadOnGen.value))
  // ui_prefs.json에도 즉시 반영 → Python start_generation이 읽어 언로드 판단
  requestAction('save_ui_prefs', {
    ollamaUrl: ollamaUrl.value,
    ollamaModel: ollamaModel.value,
    ollamaUnloadOnGen: ollamaUnloadOnGen.value,
  })
}

async function testOllama() {
  _ollamaRequestMode = 'test'
  const backend: any = await getBackend()
  if (backend.requestOllamaModels) backend.requestOllamaModels(ollamaUrl.value)
  else if (backend.ollamaListModels) backend.ollamaListModels(ollamaUrl.value, handleOllamaModels)
}
function loadOllamaModels() { testOllama() }
// 시작 시 조용히 모델 목록 자동 로드 (caption 탭과 동일). 실패하면 Ollama 연결부터 안내.
async function autoLoadOllamaModels() {
  _ollamaRequestMode = 'auto'
  const backend: any = await getBackend()
  if (backend.requestOllamaModels) backend.requestOllamaModels(ollamaUrl.value)
  else if (backend.ollamaListModels) backend.ollamaListModels(ollamaUrl.value, handleOllamaModels)
}
let _ollamaRequestMode: 'test' | 'auto' | null = null
function handleOllamaModels(json: string) {
  if (!_ollamaRequestMode) return
  const mode = _ollamaRequestMode
  try {
    const payload = JSON.parse(json)
    const models = Array.isArray(payload) ? payload : payload.models
    if (!Array.isArray(payload) && payload.url && payload.url !== ollamaUrl.value) {
      _ollamaRequestMode = null
      return
    }
    _ollamaRequestMode = null
    if (!Array.isArray(models)) throw new Error('invalid models payload')
    ollamaModels.value = models
    if (models.length > 0) {
      if (mode === 'test') requestAction('show_toast', { type: 'success', msg: `Ollama 연결 성공! ${models.length}개 모델 발견` })
      const base = (s: string) => (s || '').split(':')[0].toLowerCase()
      const match = models.includes(ollamaModel.value)
        ? ollamaModel.value
        : models.find((m: string) => ollamaModel.value && base(m) === base(ollamaModel.value))
      const next = match || models[0]
      if (next && next !== ollamaModel.value) { ollamaModel.value = next; saveOllamaSettings() }
    } else {
      const msg = mode === 'test'
        ? 'Ollama 연결됨 — 설치된 모델 없음'
        : 'Ollama 연결을 먼저 확인하세요 (실행 중인지 · URL · 설치된 모델). Settings → AI Assistant'
      requestAction('show_toast', { type: mode === 'test' ? 'info' : 'warning', msg })
    }
  } catch {
    _ollamaRequestMode = null
    requestAction('show_toast', { type: 'error', msg: 'Ollama 연결 실패 — Ollama 실행/URL을 확인하세요' })
  }
}
</script>

<style scoped>
.settings-workspace { height: 100%; display: flex; background: var(--bg-primary); }

/* Navigation */
.settings-nav {
  width: 240px; background: var(--bg-secondary); border-right: 1px solid var(--border);
  padding: 24px 12px; display: flex; flex-direction: column; gap: 4px;
}
.nav-header { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--text-muted); letter-spacing: 0; padding: 0 12px 12px; }
.settings-search-wrap { position: relative; padding: 0 12px 12px; }
.settings-search {
  width: 100%; padding: 7px 28px 7px 10px;
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-primary); font-size: 11px; outline: none;
  font-family: inherit;
}
.settings-search:focus { border-color: var(--accent); }
.search-clear {
  position: absolute; right: 16px; top: 50%; transform: translateY(-50%);
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  font-size: 12px; padding: 0 4px;
}
.search-clear:hover { color: var(--state-alert-fg); }
.nav-empty { padding: 12px; font-size: 11px; color: var(--text-muted); text-align: center; font-style: italic; }
.nav-item {
  height: 44px; padding: 0 16px; border: none; background: transparent;
  border-radius: var(--radius-base); display: flex; align-items: center; gap: 12px;
  cursor: pointer; transition: var(--transition);
}
/* 이모지였을 땐 opacity 로 죽였지만, 선 아이콘은 흐려지면 형태가 안 읽힌다 — 색으로 구분한다 */
.nav-item .icon { flex-shrink: 0; color: var(--text-muted); transition: var(--transition); }
.nav-item .label { font-size: var(--fs-body); font-weight: var(--fw-medium); color: var(--text-secondary); letter-spacing: 0; }
.nav-item:hover { background: var(--bg-input); }
.nav-item:hover .icon, .nav-item:hover .label { color: var(--text-primary); }
.nav-item.active { background: var(--accent-dim); }
.nav-item.active .icon, .nav-item.active .label { color: var(--accent); }

/* Content Area */
.settings-body { flex: 1; overflow-y: auto; padding: 40px; }
.settings-content { max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }

.section-fade { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.glass-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 24px; }

.info-row { display: flex; justify-content: space-between; align-items: center; }
.desc { font-size: 12px; font-weight: var(--fw-bold); color: var(--text-secondary); }
.val-badge { background: var(--border); padding: 4px 12px; border-radius: var(--radius-pill); font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--accent); }

.input-stack { display: flex; flex-direction: column; gap: 16px; }
.input-unit { position: relative; }
.unit-label { position: absolute; left: 12px; top: -8px; background: var(--bg-primary); padding: 0 6px; font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--text-muted); letter-spacing: 0; }

/* Authenticated generation API gateway */
.generation-api-section { width: 100%; }
.generation-api-security {
  background: rgba(34,211,238,.07); border-color: rgba(34,211,238,.3); color: var(--text-secondary);
}
.generation-api-security strong { display: block; margin-bottom: 4px; color: var(--state-info-fg); letter-spacing: 0; }
.generation-api-security b { color: var(--text-primary); }
.generation-api-readonly {
  background: rgba(251,191,36,.07); border-color: rgba(251,191,36,.3); color: var(--text-secondary);
}
.generation-api-readonly strong { margin-right: 5px; color: var(--state-warn-fg); }
.generation-api-card { border-color: rgba(34,211,238,.17); }
.generation-api-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.generation-api-eyebrow { color: var(--state-info-fg); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; }
.generation-api-header h2 { margin: 4px 0 0; color: var(--text-primary); font-size: 18px; }
.generation-api-badges { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }
.generation-api-badge {
  padding: 4px 7px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--bg-input); color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0;
}
.generation-api-badge.on { border-color: rgba(74,222,128,.42); background: rgba(74,222,128,.09); color: var(--state-ok-fg); }
.generation-api-toggle-row {
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
  margin-top: 18px; padding: 12px 14px; border-radius: 8px; background: var(--bg-input);
}
.generation-api-toggle-row > div { display: flex; flex-direction: column; gap: 3px; }
.generation-api-toggle-row strong { color: var(--text-secondary); font-size: var(--fs-label); letter-spacing: 0; }
.generation-api-toggle-row small { color: var(--text-muted); font-size: var(--fs-label); line-height: 1.4; }
.generation-api-toggle-row :deep(.tsw:disabled) { opacity: .45; cursor: not-allowed; }
.generation-api-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.generation-api-field { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.generation-api-field > span, .generation-api-endpoint > span {
  color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0;
}
.generation-api-field > small { color: var(--text-muted); font-size: var(--fs-label); line-height: 1.4; }
.generation-api-field input, .generation-api-field select {
  width: 100%; min-width: 0; box-sizing: border-box; padding: 9px 11px;
  border: 1px solid var(--border); border-radius: 7px; outline: none;
  background: var(--bg-primary); color: var(--text-primary); font-family: 'Consolas', monospace; font-size: var(--fs-label);
}
.generation-api-field input:focus, .generation-api-field select:focus { border-color: var(--state-info-fg); }
.generation-api-field input:disabled, .generation-api-field select:disabled { opacity: .5; cursor: not-allowed; }
.generation-api-secret { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; gap: 7px; }
.generation-api-lan-warning {
  margin-top: 10px; padding: 9px 11px; border: 1px solid rgba(248,113,113,.35); border-radius: 7px;
  background: rgba(248,113,113,.07); color: var(--state-alert-fg); font-size: var(--fs-label); line-height: 1.5;
}
.generation-api-endpoint {
  min-width: 0; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-input);
}
.generation-api-endpoint code {
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--state-info-fg); font-family: 'Consolas', monospace; font-size: var(--fs-label);
}
.generation-api-actions { display: grid; grid-template-columns: 1.25fr 1fr 1fr 1.2fr; gap: 8px; }
.generation-api-actions .btn-pill { min-width: 0; }
.generation-api-status {
  margin: 12px 0 0; padding: 9px 11px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg-input); color: var(--text-secondary); font-size: var(--fs-label); line-height: 1.5;
}
.generation-api-empty {
  padding: 14px; border: 1px dashed var(--border); border-radius: 7px;
  color: var(--text-muted); text-align: center; font-size: var(--fs-label); line-height: 1.5;
}
.generation-api-target {
  padding: 14px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg-input);
}
.generation-api-target-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.generation-api-target-head > strong { color: var(--text-primary); font-size: 11px; }
.generation-api-enabled { color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; }
.generation-api-enabled input { accent-color: var(--state-info); vertical-align: -2px; }
.generation-api-target-actions { display: flex; justify-content: flex-end; gap: 7px; }
.generation-api-jobs { display: flex; flex-direction: column; gap: 7px; }
.generation-api-job {
  min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-input);
}
.generation-api-job > div { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.generation-api-job strong { color: var(--text-secondary); font-size: var(--fs-label); }
.generation-api-job code { overflow: hidden; text-overflow: ellipsis; color: var(--text-muted); font-size: var(--fs-label); white-space: nowrap; }
.generation-api-job-state {
  flex-shrink: 0; padding: 3px 7px; border-radius: var(--radius-pill); background: var(--border);
  color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0;
}
.generation-api-job-state.completed { background: rgba(74,222,128,.1); color: var(--state-ok-fg); }
.generation-api-job-state.running { background: rgba(96,165,250,.1); color: var(--state-info-fg); }
.generation-api-job-state.failed, .generation-api-job-state.cancelled { background: rgba(248,113,113,.1); color: var(--state-alert-fg); }

/* App-managed runtimes */
.runtime-section { width: 100%; }
.runtime-safety-warning {
  background: rgba(248,113,113,.08); border-color: rgba(248,113,113,.35);
}
.runtime-safety-warning strong { display: block; color: var(--state-alert-fg); letter-spacing: 0; margin-bottom: 3px; }
.runtime-safety-warning b { color: var(--text-primary); }
.runtime-readonly-warning {
  background: rgba(251,191,36,.07); border-color: rgba(251,191,36,.3); color: var(--text-secondary);
}
.runtime-readonly-warning strong { color: var(--state-warn-fg); margin-right: 5px; }
.runtime-primary-card {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, .7fr); gap: 20px;
  margin-bottom: 18px; border-color: rgba(96,165,250,.28);
  background: linear-gradient(135deg, rgba(96,165,250,.08), var(--bg-card));
}
.runtime-primary-copy h2 { margin: 4px 0 7px; color: var(--text-primary); font-size: 17px; }
.runtime-primary-copy p { margin: 0; color: var(--text-muted); font-size: var(--fs-label); line-height: 1.6; }
.runtime-primary-copy b { color: var(--text-secondary); }
.runtime-primary-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; align-self: center; }
.runtime-primary-option {
  min-width: 0; padding: 12px 10px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-input); color: var(--text-secondary); cursor: pointer;
  display: flex; flex-direction: column; align-items: flex-start; gap: 4px;
}
.runtime-primary-option span { font-size: 11px; font-weight: var(--fw-bold); }
.runtime-primary-option strong { color: var(--text-muted); font-size: var(--fs-label); letter-spacing: 0; }
.runtime-primary-option:hover:not(:disabled), .runtime-primary-option.selected {
  border-color: var(--state-info-fg); background: rgba(96,165,250,.12); color: var(--state-info-fg);
}
.runtime-primary-option.selected strong { color: var(--state-info-fg); }
.runtime-primary-option:disabled { cursor: default; opacity: .72; }
.runtime-card-list { display: flex; flex-direction: column; gap: 18px; }
.runtime-card { position: relative; overflow: hidden; }
.runtime-card::before {
  content: ''; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: var(--runtime-accent, var(--accent)); opacity: .85;
}
.runtime-card-forge { --runtime-accent: var(--tag-wear); }
.runtime-card-comfyui { --runtime-accent: var(--tag-scene); }
.runtime-card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px; }
.runtime-eyebrow { color: var(--runtime-accent); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; }
.runtime-card h2 { margin: 4px 0 0; color: var(--text-primary); font-size: 20px; letter-spacing: -.2px; }
.runtime-badges { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; max-width: 360px; }
.runtime-badge {
  padding: 4px 7px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--bg-input); color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0;
}
.runtime-badge.on { border-color: rgba(96,165,250,.45); background: rgba(96,165,250,.11); color: var(--state-info-fg); }
.runtime-badge.health.on { border-color: rgba(74,222,128,.45); background: rgba(74,222,128,.1); color: var(--state-ok-fg); }
.runtime-badge.busy.on { border-color: rgba(251,191,36,.45); background: rgba(251,191,36,.1); color: var(--state-warn-fg); animation: runtimePulse 1.25s ease-in-out infinite; }
.runtime-badge.active.on { border-color: color-mix(in srgb, var(--runtime-accent) 55%, transparent); background: color-mix(in srgb, var(--runtime-accent) 12%, transparent); color: var(--runtime-accent); }
.runtime-badge.source { border-color: rgba(96,165,250,.35); background: rgba(96,165,250,.09); color: var(--state-info-fg); }
.runtime-badge.source.existing { border-color: rgba(251,191,36,.4); background: rgba(251,191,36,.1); color: var(--state-warn-fg); }
.runtime-badge.primary-source { border-color: rgba(74,222,128,.4); background: rgba(74,222,128,.1); color: var(--state-ok-fg); }
@keyframes runtimePulse { 50% { opacity: .52; } }
.runtime-meta-grid {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px;
  margin-top: 18px;
}
.runtime-meta {
  min-width: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg-input); display: flex; flex-direction: column; gap: 4px;
}
.runtime-meta-wide { grid-column: 1 / -1; }
.runtime-meta > span { color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; }
.runtime-meta code, .runtime-meta strong {
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--text-secondary); font-family: 'Consolas', monospace; font-size: var(--fs-label); font-weight: var(--fw-bold);
}
.runtime-meta strong.update-ready { color: var(--state-warn-fg); }
.runtime-model-paths > div { min-width: 0; display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 8px; align-items: center; }
.runtime-model-paths > div + div { margin-top: 4px; }
.runtime-model-paths > div strong { color: var(--runtime-accent); font-size: var(--fs-label); letter-spacing: 0; }
.runtime-install-source b, .runtime-dependency-note b { color: var(--text-primary); }
.runtime-toggle-row {
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
  margin-top: 12px; padding: 12px 14px; border-radius: 8px; background: var(--bg-input);
}
.runtime-toggle-row > div { display: flex; flex-direction: column; gap: 3px; }
.runtime-toggle-row strong { color: var(--text-secondary); font-size: var(--fs-label); letter-spacing: 0; }
.runtime-toggle-row small { color: var(--text-muted); font-size: var(--fs-label); line-height: 1.4; }
.runtime-toggle-row :deep(.tsw:disabled) { opacity: .45; cursor: not-allowed; }
.runtime-subsection { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.runtime-subheading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 9px; }
.runtime-subheading h3 { margin: 0; color: var(--text-primary); font-size: var(--fs-label); letter-spacing: 0; }
.runtime-subheading p { margin: 3px 0 0; color: var(--text-muted); font-size: var(--fs-label); line-height: 1.45; }
.runtime-unsaved, .extension-update-badge {
  flex-shrink: 0; padding: 3px 6px; border-radius: 4px; background: rgba(251,191,36,.12);
  color: var(--state-warn-fg); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0;
}
.runtime-path-control { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 7px; }
.runtime-install-path-control { grid-template-columns: minmax(0, 1fr) auto auto auto; }
.runtime-repo-control { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.runtime-path-control input, .runtime-repo-control input {
  width: 100%; min-width: 0; padding: 9px 11px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg-primary); color: var(--text-primary); outline: none;
  font-family: 'Consolas', monospace; font-size: var(--fs-label); box-sizing: border-box;
}
.runtime-path-control input:focus, .runtime-repo-control input:focus { border-color: var(--runtime-accent); }
.runtime-path-control input:disabled, .runtime-repo-control input:disabled { opacity: .52; cursor: not-allowed; }
.runtime-dependency-note {
  margin-top: 8px; padding: 8px 10px; border: 1px solid rgba(251,191,36,.28); border-radius: 7px;
  background: rgba(251,191,36,.06); color: var(--state-warn-fg); font-size: var(--fs-label); line-height: 1.5;
}
.runtime-action-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
.runtime-action-grid .btn-pill { min-width: 0; }
.btn-pill.danger:not(:disabled) { border-color: rgba(248,113,113,.4); color: var(--state-alert-fg); }
.btn-pill.accent:not(:disabled) { border-color: var(--runtime-accent, var(--accent)); color: var(--runtime-accent, var(--accent)); }
.runtime-extension-section { margin-top: 18px; }
.runtime-extension-list { display: flex; flex-direction: column; gap: 7px; margin-top: 12px; }
.runtime-empty {
  padding: 13px; border: 1px dashed var(--border); border-radius: 7px;
  color: var(--text-muted); text-align: center; font-size: var(--fs-label);
}
.runtime-extension-item {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 11px; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-input);
}
.runtime-extension-copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.runtime-extension-copy > div { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
.runtime-extension-copy strong { color: var(--text-primary); font-size: 11px; }
.runtime-extension-copy span:not(.extension-update-badge) { color: var(--text-muted); font-size: var(--fs-label); }
.runtime-extension-copy code {
  min-width: 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--text-muted); font-family: 'Consolas', monospace; font-size: var(--fs-label);
}
.runtime-extension-actions { flex-shrink: 0; display: flex; gap: 6px; }
.runtime-message, .runtime-global-status {
  margin-top: 12px; padding: 9px 11px; border-radius: 7px; background: var(--bg-input);
  color: var(--text-secondary); font-size: var(--fs-label); line-height: 1.5;
}
.runtime-global-status { border: 1px solid var(--border); }

/* Forge model directories */
.forge-hint code {
  padding: 1px 5px; border-radius: 4px; background: var(--bg-button);
  color: var(--accent); font-family: 'Consolas', monospace; font-size: var(--fs-label);
}
.forge-readonly-warning { margin-top: 10px; border-color: rgba(245,158,11,.28); }
.forge-readonly-warning strong { color: var(--state-warn-fg); margin-right: 5px; }
.forge-card-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.forge-scanning { color: var(--accent); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; }
.forge-path-list { display: flex; flex-direction: column; gap: 14px; margin-top: 18px; }
.forge-path-row {
  padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-base);
  background: var(--bg-input);
}
.forge-path-label { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.forge-path-label > span { color: var(--text-primary); font-size: 11px; font-weight: var(--fw-bold); letter-spacing: 0; }
.forge-path-label small { color: var(--text-muted); font-size: var(--fs-label); text-align: right; }
.forge-path-control { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.forge-path-control input {
  min-width: 0; padding: 9px 11px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg-primary); color: var(--text-primary); outline: none;
  font-family: 'Consolas', monospace; font-size: 11px;
}
.forge-path-control input:focus { border-color: var(--accent); }
.forge-path-control input.invalid { border-color: var(--state-alert-fg); box-shadow: 0 0 0 1px rgba(248,113,113,.15); }
.forge-path-control input:disabled { opacity: .62; cursor: not-allowed; }
.btn-pill.compact { min-width: 74px; padding: 7px 11px; font-size: var(--fs-label); }
.forge-path-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; margin-top: 7px; color: var(--text-muted); font-size: var(--fs-label); }
.path-ok { color: var(--state-ok-fg); }
.path-missing, .path-error { color: var(--state-alert-fg); }
.path-error { width: 100%; }
.env-lock { padding: 2px 6px; border-radius: 4px; background: rgba(96,165,250,.12); color: var(--state-info-fg); font-weight: var(--fw-bold); }
.forge-actions { display: grid; grid-template-columns: 1.25fr 1fr 1fr; gap: 10px; }
.forge-status { color: var(--text-muted); font-size: var(--fs-label); line-height: 1.5; }

.toggle-grid { display: flex; flex-direction: column; gap: 8px; }
.toggle-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; background: var(--bg-input); border-radius: var(--radius-base);
  cursor: pointer; transition: var(--transition);
}
.toggle-row:hover { background: var(--bg-button); }
.toggle-row span { font-size: 13px; font-weight: var(--fw-bold); color: var(--text-secondary); }
/* 체크박스 → 토글 스위치.
   켜짐 표시는 '면'이 아니라 표시등이라 어두운 채움(--state-ok)이 아닌 -fg 를 쓴다
   (ToggleSwitch.vue 와 같은 이유 — 초록 틴트 트랙 위에서 채움색 노브는 대비가 죽는다). */
.toggle-row input[type="checkbox"] {
  appearance: none; -webkit-appearance: none; margin: 0; flex-shrink: 0;
  width: 42px; height: 22px; border-radius: 12px;
  background: var(--bg-button); border: 1px solid var(--border);
  position: relative; cursor: pointer; transition: background .18s, border-color .18s;
}
.toggle-row input[type="checkbox"]::before {
  content: ''; position: absolute; top: 2px; left: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--text-muted); transition: left .18s, background .18s;
}
.toggle-row input[type="checkbox"]:checked { background: rgba(74,222,128,0.28); border-color: var(--state-ok-fg); }
.toggle-row input[type="checkbox"]:checked::before { left: 22px; background: var(--state-ok-fg); }

.btn-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.mt-16 { margin-top: 16px; }

.drag-list { display: flex; flex-direction: column; gap: 6px; }
.drag-item {
  display: flex; align-items: center; gap: 12px; padding: 12px 16px;
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px;
  cursor: grab; transition: var(--transition);
}
.drag-item:active { cursor: grabbing; background: var(--bg-button); scale: 0.98; }
.drag-item .handle { color: var(--text-muted); }
.drag-item .name { font-size: 12px; font-weight: var(--fw-bold); letter-spacing: 0; color: var(--text-primary); }

/* Theme */
.theme-note { margin: 8px 0 0; color: var(--text-muted); font-size: var(--fs-label); line-height: 1.55; }
.theme-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.icon-animation-stage {
  padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--bg-input); color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold);
}
.icon-animation-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; margin-top: 14px; }
.icon-animation-option {
  min-width: 0; min-height: 76px; display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
  padding: 12px; border: 1px solid var(--border); border-radius: 9px;
  background: var(--bg-input); color: var(--text-secondary); text-align: left; cursor: pointer;
}
.icon-animation-option:hover { border-color: var(--edge); color: var(--text-primary); }
.icon-animation-option.selected { border-color: var(--accent); background: var(--accent-dim); color: var(--accent); }
.icon-animation-option-head { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.icon-animation-selected { font-size: var(--fs-label); font-weight: var(--fw-bold); }
.icon-animation-option strong { font-size: var(--fs-body); font-weight: var(--fw-bold); }
.icon-animation-option small { color: var(--text-muted); font-size: var(--fs-label); line-height: 1.45; }
.theme-preset-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.theme-preset {
  min-width: 0; padding: 8px; border: 1px solid var(--border); border-radius: var(--radius-base);
  background: var(--bg-input); cursor: pointer; transition: var(--transition);
  display: flex; flex-direction: column; gap: 8px;
}
.theme-preset:hover { border-color: var(--edge); }
.theme-preset.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-dim); }
.theme-preset-name {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  color: var(--text-secondary); font-size: 12px; font-weight: var(--fw-bold); letter-spacing: 0;
}
.theme-preset.selected .theme-preset-name { color: var(--accent); }

/* 미리보기 안쪽은 토큰이 아니라 **그 프리셋의 색**을 인라인으로 받는다 —
   토큰을 쓰면 어떤 카드든 지금 테마 색으로 보여서 미리보기가 거짓말이 된다. */
.theme-preview { display: block; overflow: hidden; height: 92px; border: 1px solid; border-radius: 6px; }
.theme-preview-bar { display: flex; align-items: center; gap: 5px; height: 16px; padding: 0 6px; border-bottom: 1px solid; }
.theme-preview-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.theme-preview-line { display: block; width: 60%; height: 3px; border-radius: 2px; opacity: .8; }
.theme-preview-line.wide { width: 85%; height: 4px; opacity: 1; }
.theme-preview-body { display: flex; flex-direction: column; gap: 6px; padding: 8px; }
.theme-preview-card {
  display: flex; flex-direction: column; align-items: flex-start; gap: 5px;
  padding: 7px; border: 1px solid; border-radius: 5px;
}
.theme-preview-btn { padding: 1px 8px 2px; border-radius: 4px; font-size: 9px; font-weight: var(--fw-bold); line-height: 1.6; }
.theme-preview-states { display: flex; gap: 4px; }
.theme-preview-states > span { flex: 1; height: 5px; border-radius: 3px; }

.theme-field-list { display: flex; flex-direction: column; gap: 18px; margin-top: 16px; }

.shortcut-grid { display: flex; flex-direction: column; gap: 4px; }
.s-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 10px; border-radius: 6px;
  transition: background 0.15s;
}
.s-row:hover { background: rgba(255, 255, 255, 0.025); }
.s-row span { font-size: 13px; color: var(--text-secondary); }
.hjm-select { background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 12px; font-weight: var(--fw-bold); padding: 4px 10px; cursor: pointer; }
/* kbd 단축키 표시 — style.css의 .keycap 스타일 토큰을 그대로 사용
   (전역 일관성 위해 클래스 없이도 키캡 모양이 나오도록) */
kbd {
  display: inline-block;
  min-width: 22px;
  padding: 4px 10px 5px;
  margin: 0 1px;
  background: var(--keycap-bg-grad);
  border: 1px solid var(--keycap-border);
  border-bottom-width: 2px;
  border-radius: 5px;
  box-shadow: var(--keycap-shadow);
  color: var(--keycap-color);
  font-family: 'Consolas', 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: var(--fw-bold);
  line-height: 1;
  letter-spacing: 0;
  vertical-align: middle;
}
.hint-banner {
  background: rgba(96, 165, 250, 0.08); border: 1px solid rgba(96, 165, 250, 0.3);
  border-radius: 8px; padding: 12px 14px; margin-bottom: 16px;
  font-size: 12px; line-height: 1.6; color: var(--text-secondary);
}
.hint-banner kbd { font-size: var(--fs-label); padding: 3px 7px 4px; }
.hint-banner strong { color: var(--accent); }

/* Defaults */
.defaults-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.def-field { display: flex; flex-direction: column; gap: 3px; }
.def-field-wide { display: flex; flex-direction: column; gap: 6px; }
.def-field-wide span { font-size: 11px; color: var(--text-secondary); font-weight: var(--fw-bold); }
.guard-fields-disabled { opacity: 0.45; }
.w-slider { width: 100%; accent-color: var(--accent); cursor: pointer; }

/* UI 크기 프리셋 버튼 */
.scale-presets { display: flex; gap: 6px; margin-top: 10px; }
.scale-btn {
  flex: 1; padding: 8px 6px; background: var(--bg-input);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-secondary); font-size: 11px; font-weight: var(--fw-bold);
  cursor: pointer; transition: all 0.15s; font-family: 'Consolas', monospace;
}
.scale-btn:hover { background: var(--bg-button); color: var(--text-primary); border-color: var(--text-muted); }
.scale-btn.active {
  background: var(--accent-dim); border-color: var(--accent); color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-dim);
}
.def-field span { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--text-muted); }
/* 채움용 --state-ok 는 '흰 글자와 4.6:1' 로 맞춘 값이라 그 위 글자는 흰색 고정이다
   (--text-primary 는 라이트 테마에서 검정이 되어 이 면 위에서 안 읽힌다). */
.sync-badge { background: var(--state-ok); color: #fff; padding: 1px 6px; border-radius: 4px; font-size: var(--fs-label); font-weight: var(--fw-bold); margin-left: 8px; }
.def-field input, .def-field select { padding: 8px 10px; font-size: 12px; }
.ollama-unload-row { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-secondary); cursor: pointer; line-height: 1.4; }
.ollama-unload-row input { margin-top: 2px; accent-color: var(--accent); }

/* Ollama */
.model-select { width: 100%; padding: 10px 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-primary); font-size: 13px; font-weight: var(--fw-bold); }
.model-select:focus { border-color: var(--accent); outline: none; }

.recommend-grid { display: flex; flex-direction: column; gap: 8px; }
.rec-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius-base); transition: var(--transition);
}
.rec-item:hover { border-color: var(--border-strong); }
.rec-item.best { border-color: var(--accent-dim); background: rgba(250, 204, 21, 0.03); }
.rec-name { font-size: 13px; font-weight: var(--fw-bold); color: var(--text-primary); min-width: 120px; font-family: 'Consolas', monospace; }
.rec-item.best .rec-name { color: var(--accent); }
.rec-desc { font-size: 11px; color: var(--text-muted); text-align: right; }
.rec-note { font-size: 11px; color: var(--text-muted); line-height: 1.6; }
.rec-note code { background: var(--bg-button); padding: 2px 8px; border-radius: 4px; font-size: 11px; color: var(--accent); }

@media (max-width: 820px) {
  .settings-nav { width: 190px; }
  .settings-body { padding: 24px; }
  .generation-api-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .runtime-primary-card { grid-template-columns: 1fr; }
  .runtime-card-header { flex-direction: column; }
  .runtime-badges { justify-content: flex-start; max-width: none; }
  .forge-path-label { align-items: flex-start; flex-direction: column; gap: 3px; }
  .forge-path-label small { text-align: left; }
  .forge-actions { grid-template-columns: 1fr; }
}

@media (max-width: 620px) {
  .settings-workspace { flex-direction: column; }
  .settings-nav {
    width: 100%; max-height: 168px; padding: 10px; border-right: 0; border-bottom: 1px solid var(--border);
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); overflow-y: auto; box-sizing: border-box;
  }
  .nav-header, .settings-search-wrap, .nav-empty { grid-column: 1 / -1; }
  .nav-item { height: 38px; padding: 0 10px; }
  .nav-item .label { font-size: var(--fs-label); letter-spacing: 0; }
  .theme-preset-grid { grid-template-columns: 1fr; }
  .icon-animation-options { grid-template-columns: 1fr; }
  .settings-body { padding: 16px 12px 28px; }
  .glass-card { padding: 17px; }
  .generation-api-header { flex-direction: column; }
  .generation-api-badges { justify-content: flex-start; }
  .generation-api-grid { grid-template-columns: 1fr; }
  .generation-api-secret { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .generation-api-secret input { grid-column: 1 / -1; }
  .generation-api-endpoint { grid-template-columns: 1fr auto; }
  .generation-api-endpoint > span { grid-column: 1 / -1; }
  .generation-api-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .runtime-meta-grid { grid-template-columns: 1fr; }
  .runtime-meta-wide { grid-column: auto; }
  .runtime-toggle-row { align-items: flex-start; }
  .runtime-path-control, .runtime-repo-control, .runtime-install-path-control { grid-template-columns: 1fr 1fr; }
  .runtime-path-control input, .runtime-repo-control input { grid-column: 1 / -1; }
  .runtime-action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .runtime-extension-item { align-items: flex-start; flex-direction: column; }
  .runtime-extension-actions { width: 100%; }
  .runtime-extension-actions .btn-pill { flex: 1; }
}

@media (max-width: 520px) {
  .generation-api-section { box-sizing: border-box; padding-right: 104px; }
  .generation-api-secret { grid-template-columns: 1fr; }
  .generation-api-secret input { grid-column: auto; }
}
</style>
