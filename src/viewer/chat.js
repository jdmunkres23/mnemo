// ── AI 채팅 상태 ──
let aiState = {
  sessionId: null,
  chatId: null,
  messages: [],          // { role, content, meta?: { query_type, search_results } }
  sessionTitle: '',
  loading: false,
};

const FALLBACK_MODELS = [
  { id: 'llama-3.1-8b-instant',    context_window: 131072 },
  { id: 'llama-3.3-70b-versatile', context_window: 131072 },
  { id: 'mixtral-8x7b-32768',      context_window: 32768 },
];

// 알려진 모델의 한국어 설명
const MODEL_META = {
  'llama-3.1-8b-instant':         { label: 'Llama 3.1 8B',          desc: '빠른 응답, 일상적인 질문에 최적' },
  'llama-3.3-70b-versatile':      { label: 'Llama 3.3 70B',         desc: '복잡한 분석과 추론에 최적' },
  'llama-3.1-70b-versatile':      { label: 'Llama 3.1 70B',         desc: '복잡한 분석과 추론에 최적' },
  'llama3-70b-8192':              { label: 'Llama 3 70B',            desc: '강력한 범용 모델' },
  'llama3-8b-8192':               { label: 'Llama 3 8B',             desc: '빠르고 효율적인 범용 모델' },
  'llama-3.2-1b-preview':         { label: 'Llama 3.2 1B',          desc: '초경량, 엣지 추론용' },
  'llama-3.2-3b-preview':         { label: 'Llama 3.2 3B',          desc: '초경량, 빠른 응답' },
  'llama-3.2-11b-vision-preview':  { label: 'Llama 3.2 11B Vision', desc: '이미지 이해 지원 멀티모달' },
  'llama-3.2-90b-vision-preview':  { label: 'Llama 3.2 90B Vision', desc: '고성능 비전 + 텍스트 모델' },
  'mixtral-8x7b-32768':           { label: 'Mixtral 8x7B',          desc: '긴 컨텍스트, MoE 아키텍처' },
  'gemma2-9b-it':                 { label: 'Gemma 2 9B',             desc: 'Google 경량 고효율 모델' },
  'gemma-7b-it':                  { label: 'Gemma 7B',               desc: 'Google 경량 모델' },
  'llama-guard-3-8b':             { label: 'Llama Guard 3 8B',       desc: '안전성 분류 전용 모델' },
};

let _serverHasKey = false;
let _historyViewOpen = false;
let _settingsViewOpen = false;
let _cachedChats = [];
let _lastFetchedModels = FALLBACK_MODELS;

// ── 초기화 ──
function initAIChat(sessionId) {
  aiState.sessionId = sessionId;
  aiState.chatId = null;
  aiState.messages = [];
  aiState.loading = false;

  const label = document.getElementById('aiSessionLabel');
  if (label) {
    const s = sessionId && window.sessionMap ? window.sessionMap[sessionId] : null;
    aiState.sessionTitle = s ? s.title : '';
    label.textContent = aiState.sessionTitle ? `— ${aiState.sessionTitle.slice(0, 20)}` : '';
  }

  _renderAIMessages();
  _updateSendBtn();

  if (sessionId) {
    _loadChatHistory(sessionId);
  }
}

// 패널이 처음 열릴 때 1회 실행: 서버 키 상태 확인 + 모델 목록 로드
async function _initAIChatPanel() {
  await _checkServerKey();
  await _fetchModels();
}

async function _checkServerKey() {
  try {
    const res = await fetch('/api/groq-key-status');
    const data = await res.json();
    _serverHasKey = !!data.has_server_key;
    _updateKeyStatusUI();
  } catch (e) {
    _serverHasKey = false;
  }
}

function _updateKeyStatusUI() {
  const hint = document.getElementById('aiKeyHint');
  if (!hint) return;
  if (_serverHasKey) {
    hint.textContent = '.env 키 사용 중 (입력 생략 가능)';
    hint.style.color = '#5c9e5c';
  } else {
    hint.textContent = 'API 키를 입력하세요';
    hint.style.color = '';
  }
}

async function _fetchModels() {
  const apiKey = loadApiKey();
  const url = apiKey
    ? `/api/groq-models?api_key=${encodeURIComponent(apiKey)}`
    : '/api/groq-models';

  try {
    const res = await fetch(url);
    const data = await res.json();
    if (data.models && data.models.length) {
      _lastFetchedModels = data.models;
      _buildModelDropdown(data.models);
      return;
    }
  } catch (e) {}

  _lastFetchedModels = FALLBACK_MODELS;
  _buildModelDropdown(FALLBACK_MODELS);
}

function _buildModelDropdown(models) {
  const popover = document.getElementById('aiModelPopover');
  if (!popover) return;

  const saved = localStorage.getItem('groq_model') || 'llama-3.1-8b-instant';
  // 선택된 모델이 목록에 없으면 첫 번째로 초기화
  const currentId = models.some(m => m.id === saved) ? saved : models[0]?.id || saved;
  aiState.model = currentId;

  popover.innerHTML = models.map(m => {
    const meta = MODEL_META[m.id] || {};
    const label = meta.label || m.id;
    const desc  = meta.desc  || '';
    const ctx   = m.context_window ? `${Math.round(m.context_window / 1024)}k` : '';
    const sel   = m.id === currentId;
    return `<div class="ai-model-item${sel ? ' selected' : ''}" onclick="selectAIModel('${m.id}')">
  <div class="ai-model-item-info">
    <div class="ai-model-item-name">${escHtml(label)}<span class="ai-model-ctx">${ctx}</span></div>
    ${desc ? `<div class="ai-model-item-desc">${escHtml(desc)}</div>` : ''}
  </div>
  <i class="ti ti-check ai-model-check"></i>
</div>`;
  }).join('');

  _updateModelBtn(currentId, models);
}

function selectAIModel(modelId) {
  aiState.model = modelId;
  localStorage.setItem('groq_model', modelId);

  // 체크마크 업데이트
  document.querySelectorAll('#aiModelPopover .ai-model-item').forEach(el => {
    const isThis = el.getAttribute('onclick') === `selectAIModel('${modelId}')`;
    el.classList.toggle('selected', isThis);
  });

  // 버튼 레이블 업데이트
  const popover = document.getElementById('aiModelPopover');
  const models = popover
    ? [...popover.querySelectorAll('.ai-model-item')].map(el => ({
        id: el.getAttribute('onclick').match(/'([^']+)'/)?.[1] || '',
      }))
    : [];
  _updateModelBtn(modelId, models);
  closeModelDropdown();
}

function _updateModelBtn(modelId, models) {
  const btn = document.getElementById('aiModelBtn');
  if (!btn) return;
  const meta = MODEL_META[modelId];
  const label = meta ? meta.label : modelId;
  btn.querySelector('.ai-model-btn-label').textContent = label;
}

function toggleModelDropdown() {
  const popover = document.getElementById('aiModelPopover');
  if (!popover) return;
  const open = popover.classList.toggle('open');
  if (open) {
    // 외부 클릭 시 닫기
    setTimeout(() => {
      document.addEventListener('click', _closeDropdownOnOutside, { once: true });
    }, 0);
  }
}

function closeModelDropdown() {
  const popover = document.getElementById('aiModelPopover');
  if (popover) popover.classList.remove('open');
}

function _closeDropdownOnOutside(e) {
  const dropdown = document.getElementById('aiModelDropdown');
  if (dropdown && !dropdown.contains(e.target)) closeModelDropdown();
}

// ── 새 채팅 ──
function newAIChat() {
  if (_historyViewOpen) _setHistoryView(false);
  aiState.chatId = null;
  aiState.messages = [];
  _renderAIMessages();
  const ta = document.getElementById('aiTa');
  if (ta) ta.focus();
}

// ── 히스토리 뷰 토글 ──
function toggleAIHistory() {
  _setHistoryView(!_historyViewOpen);
}

function _setHistoryView(open) {
  _historyViewOpen = open;
  const chatView = document.getElementById('aiChatView');
  const histView = document.getElementById('aiHistoryView');
  const histBtn  = document.getElementById('aiHistoryBtn');
  const title    = document.getElementById('aiPanelTitle');
  if (chatView) chatView.style.display = open ? 'none' : 'flex';
  if (histView) histView.style.display = open ? 'flex' : 'none';
  if (histBtn)  histBtn.classList.toggle('active', open);
  if (title)    title.textContent = open ? '대화 기록' : 'AI 채팅';
  if (open) _renderHistoryView();
}

function _renderHistoryView() {
  const items   = document.getElementById('aiHistItems');
  const empty   = document.getElementById('aiHistEmpty');
  if (!items) return;

  if (!_cachedChats.length) {
    items.innerHTML = '';
    if (empty) empty.style.display = 'flex';
    return;
  }
  if (empty) empty.style.display = 'none';

  items.innerHTML = _cachedChats.map(c => {
    const isActive = c.id === aiState.chatId;
    return `<div class="ai-hist-full-item${isActive ? ' active' : ''}" onclick="openHistChat('${c.id}')">
  <div class="ai-hist-full-body">
    <div class="ai-hist-full-title">${escHtml(c.title || 'AI 채팅')}</div>
    <div class="ai-hist-full-meta">${_fmtDate(c.updated_at)} · ${c.message_count || 0}개</div>
  </div>
  <button class="hico ai-hist-del-btn" onclick="deleteAIChat(event,'${c.id}')" title="삭제">
    <i class="ti ti-trash" style="font-size:13px"></i>
  </button>
</div>`;
  }).join('');
}

function _fmtDate(iso) {
  if (!iso) return '';
  const d    = new Date(iso);
  const diff = Math.floor((Date.now() - d) / 86400000);
  if (diff === 0) return '오늘';
  if (diff === 1) return '어제';
  if (diff < 7)  return `${diff}일 전`;
  return `${d.getMonth() + 1}.${d.getDate()}`;
}

async function openHistChat(chatId) {
  await loadAIChat(chatId);
  _setHistoryView(false);
}

// ── 설정 패널 토글 (AI 채팅 패널 오른쪽에 별도로 열리는 독립 패널) ──
function toggleAISettings() {
  _setSettingsView(!_settingsViewOpen);
}

function _setSettingsView(open) {
  _settingsViewOpen = open;
  const panel  = document.getElementById('aiSettingsPanel');
  const setBtn = document.getElementById('aiSettingsBtn');
  if (panel)  panel.classList.toggle('hidden', !open);
  if (setBtn) setBtn.classList.toggle('active', open);
  if (open) _openSettingsView();
}

async function _openSettingsView() {
  const inp = document.getElementById('groqApiKeyInput');
  if (inp) inp.value = loadApiKey();

  _populateSettingsModelSelects();

  const modeSel = document.getElementById('aiRoutingModeSel');
  if (modeSel) modeSel.value = _getRoutingMode();

  await _loadUsageStatus();
}

function _populateSettingsModelSelects() {
  const models = (_lastFetchedModels && _lastFetchedModels.length) ? _lastFetchedModels : FALLBACK_MODELS;
  const optionsHtml = models.map(m => {
    const meta = MODEL_META[m.id] || {};
    return `<option value="${m.id}">${escHtml(meta.label || m.id)}</option>`;
  }).join('');

  const answerSel = document.getElementById('aiModelSelSettings');
  if (answerSel) {
    answerSel.innerHTML = optionsHtml;
    answerSel.value = _getModel();
  }
  const routingSel = document.getElementById('aiRoutingModelSel');
  if (routingSel) {
    routingSel.innerHTML = optionsHtml;
    routingSel.value = _getRoutingModel();
  }
}

// ── 사용량 ──
async function _loadUsageStatus() {
  const resetEl = document.getElementById('aiUsageReset');
  const listEl  = document.getElementById('aiUsageList');
  if (!listEl) return;
  listEl.innerHTML = '<div class="ai-usage-empty">불러오는 중...</div>';

  try {
    const res = await fetch('/api/usage-status');
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    if (resetEl) resetEl.textContent = `리셋까지 ${_fmtDuration(data.reset_seconds)}`;

    const used = (data.models || []).filter(m => m.used > 0);
    if (!used.length) {
      listEl.innerHTML = '<div class="ai-usage-empty">오늘 사용 기록 없음</div>';
      return;
    }
    used.sort((a, b) => b.pct - a.pct);

    listEl.innerHTML = used.map(m => {
      const barClass = m.pct >= 90 ? ' danger' : m.pct >= 60 ? ' warn' : '';
      const label = (MODEL_META[m.model] || {}).label || m.model;
      return `<div class="ai-usage-row">
  <div class="ai-usage-row-top">
    <span class="ai-usage-name">${escHtml(label)}</span>
    <span class="ai-usage-nums">${m.used.toLocaleString()} / ${m.limit.toLocaleString()} (${m.pct}%)</span>
  </div>
  <div class="ai-usage-bar"><div class="ai-usage-bar-fill${barClass}" style="width:${Math.min(100, m.pct)}%"></div></div>
  <div class="ai-usage-remaining">남은 ${m.remaining.toLocaleString()}</div>
</div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div class="ai-usage-empty">사용량을 불러오지 못했습니다</div>';
  }
}

function _fmtDuration(seconds) {
  if (!seconds || seconds <= 0) return '곧';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}시간 ${m}분` : `${m}분`;
}

// ── API 키 저장 (모델/라우팅 선택은 바로 적용되므로 버튼 없이 change로 처리) ──
function saveApiKey() {
  const inp = document.getElementById('groqApiKeyInput');
  const key = inp ? inp.value.trim() : '';
  if (key) {
    localStorage.setItem('groq_api_key', key);
    _showToast('API 키가 저장됐습니다');
  }
}

function loadApiKey() {
  return localStorage.getItem('groq_api_key') || '';
}

function _getRoutingModel() {
  return localStorage.getItem('groq_routing_model') || 'llama-3.1-8b-instant';
}

function _setRoutingModel(modelId) {
  localStorage.setItem('groq_routing_model', modelId);
  const sel = document.getElementById('aiRoutingModelSel');
  if (sel) sel.value = modelId;
}

function _getRoutingMode() {
  return localStorage.getItem('groq_routing_mode') || 'auto';
}

// 설정 패널의 셀렉트, AI 채팅 툴바의 퀵 셀렉트 둘 다 동일한 값을 갖도록 동기화
function _setRoutingMode(mode) {
  localStorage.setItem('groq_routing_mode', mode);
  const quick = document.getElementById('aiRoutingModeQuick');
  const full  = document.getElementById('aiRoutingModeSel');
  if (quick) quick.value = mode;
  if (full)  full.value = mode;
}

function _getModel() {
  return aiState.model || localStorage.getItem('groq_model') || 'llama-3.1-8b-instant';
}

// ── 메시지 전송 ──
async function sendAIMessage() {
  if (aiState.loading) return;

  const ta = document.getElementById('aiTa');
  const text = ta ? ta.value.trim() : '';
  if (!text) return;

  const apiKey = loadApiKey();
  if (!apiKey && !_serverHasKey) {
    _showApiKeyPrompt();
    return;
  }

  if (!aiState.sessionId) {
    _appendAISystemMsg('먼저 대화를 선택하세요.');
    return;
  }

  // 사용자 메시지 추가
  aiState.messages.push({ role: 'user', content: text });
  if (ta) { ta.value = ''; ta.style.height = 'auto'; }
  _updateSendBtn();
  _renderAIMessages();

  aiState.loading = true;
  _setThinking(true);

  try {
    const routing = await _getRagContext(aiState.sessionId, text);

    const groqMessages = [
      { role: 'system', content: routing.system },
      ...aiState.messages.map(m => ({ role: m.role, content: m.content })),
    ];

    const res = await fetch('/api/groq-proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: groqMessages,
        model: _getModel(),
        api_key: apiKey,
        max_tokens: 2048,
      }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }

    aiState.messages.push({
      role: 'assistant',
      content: data.content,
      meta: { query_type: routing.query_type, search_results: routing.search_results },
    });
    _updateRateBadge(data.rate_limit, data.usage);
    await _saveChatHistory();

  } catch (err) {
    aiState.messages.push({ role: 'assistant', content: `오류: ${err.message}` });
  } finally {
    aiState.loading = false;
    _setThinking(false);
    _renderAIMessages();
    _updateSendBtn();
  }
}

// ── RAG: 인덱싱 후 쿼리 라우팅 결과(system 프롬프트 + 출처 메타) 반환 ──
async function _getRagContext(sessionId, query) {
  // 1. 인덱싱 (이미 돼 있으면 서버에서 재사용)
  await fetch('/api/index-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });

  // 2. 쿼리 라우팅 + 벡터 검색 (simple/analytical/retrieval에 따라 system이 서버에서 조립됨)
  const mode = _getRoutingMode();
  const res = await fetch('/api/query-semantic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      query,
      top_k: 3,
      api_key: loadApiKey(),
      routing_model: _getRoutingModel(),
      forced_type: mode === 'auto' ? null : mode,
    }),
  });
  if (!res.ok) throw new Error('검색 실패');
  const data = await res.json();
  return {
    system: data.system || '당신은 도움이 되는 AI 어시스턴트입니다.',
    query_type: data.query_type || 'simple',
    search_results: data.search_results || [],
  };
}

// ── 채팅 기록 ──
async function _saveChatHistory() {
  const title = aiState.messages.length > 0
    ? aiState.messages[0].content.slice(0, 30)
    : 'AI 채팅';

  try {
    const res = await fetch('/api/chat-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: aiState.chatId || undefined,
        session_id: aiState.sessionId,
        messages: aiState.messages,
        title,
      }),
    });
    const data = await res.json();
    if (data.id) {
      const isNew = !aiState.chatId;  // chatId 세팅 전에 체크해야 정확함
      aiState.chatId = data.id;
      // 새 채팅이면 캐시 맨 앞에 추가
      if (isNew) {
        _cachedChats.unshift({
          id: data.id,
          session_id: aiState.sessionId,
          title,
          updated_at: new Date().toISOString(),
          message_count: aiState.messages.length,
        });
      } else {
        const cached = _cachedChats.find(c => c.id === data.id);
        if (cached) {
          cached.updated_at = new Date().toISOString();
          cached.message_count = aiState.messages.length;
        }
      }
    }
  } catch (e) {}
}

async function _loadChatHistory(sessionId) {
  try {
    const res = await fetch(`/api/chat-list?session_id=${encodeURIComponent(sessionId)}`);
    _cachedChats = await res.json() || [];
    if (_cachedChats.length > 0) await loadAIChat(_cachedChats[0].id);
  } catch (e) {}
}

async function loadAIChat(chatId) {
  try {
    const res = await fetch(`/api/chat-load?id=${encodeURIComponent(chatId)}`);
    if (!res.ok) return;
    const data = await res.json();
    aiState.chatId = data.id;
    aiState.messages = data.messages || [];
    _renderAIMessages();
  } catch (e) {}
}

async function deleteAIChat(evt, chatId) {
  evt.stopPropagation();
  try {
    await fetch(`/api/chat-delete?id=${encodeURIComponent(chatId)}`, { method: 'DELETE' });
    _cachedChats = _cachedChats.filter(c => c.id !== chatId);
    if (aiState.chatId === chatId) {
      aiState.chatId = null;
      aiState.messages = [];
      _renderAIMessages();
    }
    if (_historyViewOpen) _renderHistoryView();
  } catch (e) {}
}

// ── 렌더링 ──
function _renderAIMessages() {
  const list = document.getElementById('aiMsgList');
  if (!list) return;

  const empty = document.getElementById('aiEmptyMsg');
  if (!aiState.messages.length) {
    if (empty) empty.style.display = 'flex';
    list.querySelectorAll('.ai-bubble-row').forEach(el => el.remove());
    return;
  }
  if (empty) empty.style.display = 'none';

  list.querySelectorAll('.ai-bubble-row').forEach(el => el.remove());

  aiState.messages.forEach(msg => {
    const div = document.createElement('div');
    div.className = `ai-bubble-row ${msg.role === 'user' ? 'user' : 'ai'}`;
    const html = msg.role === 'user'
      ? `<div class="ai-bubble user">${escHtml(msg.content).replace(/\n/g, '<br>')}</div>`
      : `<div class="ai-msg-col"><div class="ai-bubble ai">${renderMarkdown(msg.content)}</div>${_renderSourceChips(msg.meta)}</div>`;
    div.innerHTML = html;
    list.appendChild(div);
  });

  list.scrollTop = list.scrollHeight;
}

// AI 답변 아래 출처 표시: retrieval이면 턴 범위 칩(클릭 시 대화 뷰어로 스크롤), 아니면 안내 텍스트
function _renderSourceChips(meta) {
  if (!meta) return '';

  if (meta.query_type === 'simple') {
    return `<div class="ai-source-row"><span class="ai-source-label">출처: 세션 데이터 미사용</span></div>`;
  }
  if (meta.query_type === 'analytical') {
    return `<div class="ai-source-row"><span class="ai-source-label">출처: 전체 토픽 요약 기반</span></div>`;
  }

  const results = meta.search_results || [];
  if (!results.length) {
    return `<div class="ai-source-row"><span class="ai-source-label">출처: 관련 내용을 찾지 못함</span></div>`;
  }

  // 유사도 내림차순 정렬 — 점수는 그대로 텍스트로 보여주되, 결과 내 상대적 유사도에 따라
  // 진하기(불투명도)를 다르게 줘서 가장 관련 있는 걸 시각적으로 바로 구분되게 함
  const sorted = [...results].sort((a, b) => (b.score || 0) - (a.score || 0));
  const scores = sorted.map(r => r.score || 0);
  const maxScore = Math.max(...scores);
  const minScore = Math.min(...scores);
  const range = maxScore - minScore || 1;

  const chips = sorted.map(r => {
    const label = r.turn_start === r.turn_end ? `turn ${r.turn_start}` : `turn ${r.turn_start}-${r.turn_end}`;
    const score = typeof r.score === 'number' ? ` · ${r.score.toFixed(2)}` : '';
    const tip = escHtml((r.summary || '').slice(0, 120));
    const norm = typeof r.score === 'number' ? (r.score - minScore) / range : 1;
    const opacity = (0.5 + norm * 0.5).toFixed(2); // 결과 중 최저 0.5 ~ 최고 1.0
    return `<button class="ai-source-chip" style="opacity:${opacity}" onclick="scrollToTurn(${r.turn_start})" title="${tip}">${label}${score}</button>`;
  }).join('');
  return `<div class="ai-source-row">${chips}</div>`;
}

function _appendAISystemMsg(text) {
  const list = document.getElementById('aiMsgList');
  if (!list) return;
  const div = document.createElement('div');
  div.className = 'ai-system-msg';
  div.textContent = text;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function _showApiKeyPrompt() {
  _appendAISystemMsg('먼저 설정(⚙) 에서 Groq API 키를 입력하세요.');
  toggleAISettings();
}

function _setThinking(on) {
  const el = document.getElementById('aiThinking');
  if (el) el.style.display = on ? 'flex' : 'none';
}

function _updateSendBtn() {
  const ta = document.getElementById('aiTa');
  const btn = document.getElementById('aiSendBtn');
  if (!ta || !btn) return;
  const hasText = !!ta.value.trim();
  btn.classList.toggle('on', hasText && !aiState.loading);
  btn.disabled = !hasText || aiState.loading;
}

function _updateRateBadge(rateLimit, usage) {
  const badge = document.getElementById('rateBadge');
  if (!badge) return;

  const rem = rateLimit && rateLimit.remaining_tokens;
  const total = usage && usage.total_tokens;

  if (rem !== undefined && rem !== '') {
    badge.textContent = `토큰 잔여 ${Number(rem).toLocaleString()}`;
    badge.style.display = 'inline';
  } else if (total) {
    badge.textContent = `${Number(total).toLocaleString()} 토큰 사용`;
    badge.style.display = 'inline';
  }
}

function _showToast(msg) {
  const t = document.createElement('div');
  t.className = 'ai-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}

// ── 입력창 이벤트 바인딩 (DOM 로드 후) ──
function _bindAIChatInput() {
  const ta = document.getElementById('aiTa');
  const btn = document.getElementById('aiSendBtn');
  if (!ta || !btn) return;

  ta.addEventListener('input', () => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
    _updateSendBtn();
  });

  ta.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendAIMessage();
    }
  });

  btn.addEventListener('click', sendAIMessage);

  const settingsBtn = document.getElementById('aiSettingsBtn');
  if (settingsBtn) settingsBtn.addEventListener('click', toggleAISettings);

  const saveBtn = document.getElementById('aiSaveKeyBtn');
  if (saveBtn) saveBtn.addEventListener('click', saveApiKey);

  const modelBtn = document.getElementById('aiModelBtn');
  if (modelBtn) modelBtn.addEventListener('click', toggleModelDropdown);

  const answerModelSel = document.getElementById('aiModelSelSettings');
  if (answerModelSel) answerModelSel.addEventListener('change', () => selectAIModel(answerModelSel.value));

  const routingModelSel = document.getElementById('aiRoutingModelSel');
  if (routingModelSel) routingModelSel.addEventListener('change', () => _setRoutingModel(routingModelSel.value));

  const routingModeSel = document.getElementById('aiRoutingModeSel');
  if (routingModeSel) routingModeSel.addEventListener('change', () => _setRoutingMode(routingModeSel.value));

  const routingModeQuick = document.getElementById('aiRoutingModeQuick');
  if (routingModeQuick) {
    routingModeQuick.value = _getRoutingMode();
    routingModeQuick.addEventListener('change', () => _setRoutingMode(routingModeQuick.value));
  }

  // 패널 첫 로드: 서버 키 확인 + 모델 목록 가져오기
  _initAIChatPanel();
}

// DOMContentLoaded 이후 바인딩
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _bindAIChatInput);
} else {
  _bindAIChatInput();
}
