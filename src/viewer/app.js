// ── 상태 ──
let SESSIONS = [];
let sessionMap = {};
window.sessionMap = sessionMap;  // chat.js에서 접근
let activeId = null;
let _toolCounter = 0;
let chatPanelOpen = false;
let _activeBranchIdx = 0;
let _activeBranches = null;


// ── 블록 렌더링 ──
function renderBlock(block) {
  const type = block.type || 'text';

  if (type === 'text') {
    const text = block.text || '';
    if (!text.trim()) return '';
    return `<div class="msg-bubble ai">${renderMarkdown(text)}</div>`;
  }

  if (type === 'thinking') {
    return renderThinkingBlock(block);
  }

  if (type === 'tool_use') {
    // tool_use가 단독으로 오는 경우 (segmentBlocks가 처리 못한 경우)
    const id = 'tool-' + (++_toolCounter);
    const name = block.name || '도구 실행';
    const inputHtml = `<div class="block-tool-step">
      <i class="ti ti-file-text"></i>
      <span>${escHtml(name)}</span>
      <span class="block-tool-badge">${getToolBadge(name)}</span>
    </div>`;
    return `<div class="block-tool" id="${id}">
      <div class="block-tool-header" onclick="toggleBlock('${id}')">
        <i class="ti ti-chevron-right chevron"></i>
        <span class="block-tool-name">${escHtml(name)}</span>
      </div>
      <div class="block-tool-body">${inputHtml}</div>
    </div>`;
  }

  if (type === 'tool_result') {
    const isError = block.is_error;
    const icon = isError ? 'ti-circle-x' : 'ti-circle-check';
    const color = isError ? '#e8441a' : '#5c9e5c';
    const label = isError ? '오류' : '완료';
    return `<div class="block-tool-step done" style="margin:0 0 8px">
      <i class="ti ${icon}" style="color:${color}"></i>
      <span style="color:var(--text3);font-size:13px">${label}</span>
    </div>`;
  }

  // 알 수 없는 타입 폴백
  return `<div style="font-size:12px;color:var(--text3);padding:2px 0">[${escHtml(type)}]</div>`;
}

function renderBlocks(blocks) {
  if (!blocks || !blocks.length) return '';
  const segs = segmentBlocks(blocks);
  return segs.map(seg => {
    if (seg.type === 'tool_group') return renderToolGroup(seg.pairs);
    return renderBlock(seg);
  }).join('\n');
}

// ── 데이터 로드 ──
async function loadData() {
  try {
    document.getElementById('loadingMsg').textContent = '세션 목록 불러오는 중...';
    const res = await fetch('/api/sessions');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    SESSIONS = await res.json();
    SESSIONS.forEach(s => { sessionMap[s.session_id] = s; });
    window.sessionMap = sessionMap;

    document.getElementById('loadingScreen').classList.add('hidden');
    document.getElementById('app').style.display = 'flex';
    renderSidebar();
    if (SESSIONS.length) loadConv(SESSIONS[0].session_id);
  } catch (err) {
    document.getElementById('loadingMsg').style.display = 'none';
    document.getElementById('loadingError').style.display = 'block';
    document.getElementById('loadingError').innerHTML = `
      <strong>서버에 연결할 수 없습니다</strong><br><br>
      뷰어를 시작하려면:<br>
      <code style="background:#f0ede8;padding:4px 8px;border-radius:4px;display:inline-block;margin-top:8px">
        python -m viewer
      </code><br>
      <span style="font-size:12px;color:var(--text3);margin-top:8px;display:block">
        그 후 브라우저에서 http://localhost:8080/viewer/ 열기
      </span>
      <br><small style="color:var(--text3)">${err.message}</small>
    `;
  }
}

// ── 사이드바 렌더링 ──
function renderSidebar() {
  const sb = document.getElementById('sbHistory');
  const groups = {};
  SESSIONS.forEach(s => {
    const ym = (s.updated_at || '').slice(0, 7);
    (groups[ym] = groups[ym] || []).push(s);
  });
  const sorted = Object.keys(groups).sort((a, b) => b.localeCompare(a));
  let html = '';
  sorted.forEach(ym => {
    let label = ym;
    try { const [y, m] = ym.split('-'); label = `${y}년 ${parseInt(m)}월`; } catch (e) {}
    html += `<div class="sb-lbl">${label}</div>`;
    groups[ym].forEach(s => {
      html += `<div class="hist-item" data-id="${s.session_id}" onclick="loadConv('${s.session_id}')">
        <span class="hist-text">${escHtml(s.title)}</span>
        ${s.has_branches ? '<i class="ti ti-git-branch branch-badge" title="분기된 대화"></i>' : ''}
        <i class="ti ti-dots hist-dots"></i>
      </div>`;
    });
  });
  sb.innerHTML = html;
}

// ── 턴 렌더링 ──
function renderTurnEl(turn, index) {
  const div = document.createElement('div');
  if (index !== undefined) div.dataset.turnIndex = index;
  if (turn.role === 'user') {
    div.className = 'msg-row user';
    const textBlocks = (turn.blocks || []).filter(b => b.type === 'text');
    const userText = textBlocks.length
      ? textBlocks.map(b => escHtml(b.text || '').replace(/\n/g, '<br>')).join('')
      : '';
    div.innerHTML = `<div class="msg-content"><div class="msg-bubble user">${userText}</div></div>`;
  } else {
    div.className = 'msg-row';
    const blocksHtml = renderBlocks(turn.blocks || []);
    div.innerHTML = `<div class="msg-content" style="flex:1">
      ${blocksHtml}
      <button class="copy-btn" onclick="copyMsg(this)"><i class="ti ti-copy"></i></button>
    </div>`;
  }
  return div;
}

function renderTurns(turns, container, withIndex) {
  (turns || []).forEach((turn, i) => container.appendChild(renderTurnEl(turn, withIndex ? i : undefined)));
}

// AI 채팅 출처 칩에서 호출: 대화 뷰어의 해당 턴으로 스크롤 + 하이라이트
function scrollToTurn(index) {
  const el = document.querySelector(`[data-turn-index="${index}"]`);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('turn-highlight');
  setTimeout(() => el.classList.remove('turn-highlight'), 1600);
}

function renderBranchSection(container) {
  const old = document.getElementById('branch-section');
  if (old) old.remove();

  const total = _activeBranches.length;
  const idx = _activeBranchIdx;

  const section = document.createElement('div');
  section.id = 'branch-section';

  const nav = document.createElement('div');
  nav.className = 'branch-nav';
  nav.innerHTML = `
    <button class="branch-btn" onclick="switchBranch(-1)" ${idx === 0 ? 'disabled' : ''}>
      <i class="ti ti-chevron-left"></i>
    </button>
    <span class="branch-label">${idx + 1} / ${total}</span>
    <button class="branch-btn" onclick="switchBranch(1)" ${idx === total - 1 ? 'disabled' : ''}>
      <i class="ti ti-chevron-right"></i>
    </button>
  `;
  section.appendChild(nav);

  renderTurns(_activeBranches[idx], section);
  container.appendChild(section);
}

function switchBranch(delta) {
  const total = _activeBranches ? _activeBranches.length : 0;
  if (!total) return;
  _activeBranchIdx = Math.max(0, Math.min(total - 1, _activeBranchIdx + delta));
  renderBranchSection(document.getElementById('chatInner'));
}

// ── 대화 로드 ──
async function loadConv(id) {
  activeId = id;
  _toolCounter = 0;

  document.getElementById('welcomeWrap').style.display = 'none';
  document.getElementById('chatCol').style.display = 'flex';

  // 사이드바 active 상태
  document.querySelectorAll('.hist-item').forEach(el =>
    el.classList.toggle('active', el.dataset.id === id)
  );

  // 제목 업데이트 (캐시에 있으면 즉시)
  const cached = sessionMap[id];
  if (cached) document.getElementById('chatTitleText').textContent = cached.title;

  const inner = document.getElementById('chatInner');
  inner.innerHTML = '';

  try {
    const res = await fetch(`/api/session/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const session = await res.json();

    document.getElementById('chatTitleText').textContent = session.title;
    _toolCounter = 0;

    // AI 채팅 패널 세션 연동
    if (typeof initAIChat === 'function') initAIChat(id);

    _activeBranchIdx = 0;
    _activeBranches = session.branches || null;

    renderTurns(session.turns, inner, true);

    if (_activeBranches && _activeBranches.length > 1) {
      renderBranchSection(inner);
    }

    requestAnimationFrame(() => {
      const cs = document.getElementById('chatScroll');
      cs.scrollTop = cs.scrollHeight;
    });
  } catch (err) {
    inner.innerHTML = `<div style="color:var(--text3);font-size:14px;padding:20px">
      대화를 불러오는 중 오류가 발생했습니다: ${escHtml(err.message)}
    </div>`;
  }
}

function goWelcome() {
  activeId = null;
  document.getElementById('welcomeWrap').style.display = 'flex';
  document.getElementById('chatCol').style.display = 'none';
  document.getElementById('chatTitleText').textContent = '새 채팅';
  document.querySelectorAll('.hist-item').forEach(el => el.classList.remove('active'));
  if (typeof initAIChat === 'function') initAIChat(null);
}

// ── AI 채팅 패널 토글 ──
function toggleChatPanel() {
  chatPanelOpen = !chatPanelOpen;
  document.getElementById('aiChatPanel').classList.toggle('hidden', !chatPanelOpen);
  document.getElementById('aiChatBtn').classList.toggle('active', chatPanelOpen);
}

// ── 사이드바 토글 ──
let sbOpen = true;
document.getElementById('sbToggle').addEventListener('click', toggleSb);
document.getElementById('topbarSbBtn').addEventListener('click', toggleSb);
document.getElementById('topbarSbBtn').style.display = 'none';
function toggleSb() {
  sbOpen = !sbOpen;
  document.getElementById('sidebar').classList.toggle('collapsed', !sbOpen);
  document.getElementById('topbarSbBtn').style.display = sbOpen ? 'none' : 'flex';
}

document.getElementById('logoBtn').addEventListener('click', goWelcome);
document.getElementById('newChatBtn').addEventListener('click', goWelcome);
document.getElementById('topNewChat').addEventListener('click', goWelcome);

// ── 스크롤 ──
const chatScroll = document.getElementById('chatScroll');
const scrollFab = document.getElementById('scrollFab');
chatScroll.addEventListener('scroll', () => {
  const atBot = chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight < 100;
  scrollFab.classList.toggle('show', !atBot && chatScroll.scrollHeight > chatScroll.clientHeight + 200);
});

// ── 입력창 ──
function setSend(ta, btn) { btn.classList.toggle('on', !!ta.value.trim()); }
[['wTa', 'wSend']].forEach(([tid, bid]) => {
  const ta = document.getElementById(tid), btn = document.getElementById(bid);
  ta.addEventListener('input', () => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
    setSend(ta, btn);
  });
});

// ── 복사 ──
function copyMsg(btn) {
  const content = btn.closest('.msg-content');
  const text = [...content.querySelectorAll('.msg-bubble.ai, .block-thinking-body')]
    .map(el => el.innerText).join('\n\n').trim();
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    setTimeout(() => btn.classList.remove('copied'), 1500);
  }).catch(() => {});
}

// ── 검색 ──
function openSearch() {
  document.getElementById('searchOverlay').classList.add('show');
  setTimeout(() => document.getElementById('searchInput').focus(), 50);
}
function closeSearch() {
  document.getElementById('searchOverlay').classList.remove('show');
  document.getElementById('searchInput').value = '';
  document.getElementById('searchResults').innerHTML = '<div class="sr-empty">검색어를 입력하세요</div>';
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeSearch();
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); openSearch(); }
});
function doSearch(q) {
  const res = document.getElementById('searchResults');
  q = q.trim().toLowerCase();
  if (!q) { res.innerHTML = '<div class="sr-empty">검색어를 입력하세요</div>'; return; }
  const hits = SESSIONS.filter(s => s.title.toLowerCase().includes(q)).slice(0, 25);
  if (!hits.length) { res.innerHTML = '<div class="sr-empty">검색 결과가 없습니다</div>'; return; }
  const hl = s => escHtml(s).replace(new RegExp(escHtml(q), 'gi'), m => `<mark style="background:#ffeaa0;border-radius:2px">${m}</mark>`);
  res.innerHTML = hits.map(s => `<div class="sr-item" onclick="loadConv('${s.session_id}');closeSearch()">
    <div class="sr-title">${hl(s.title)}</div>
    <div class="sr-date">${(s.updated_at || '').slice(0, 10)}</div>
  </div>`).join('');
}

// ── 시작 ──
loadData();
