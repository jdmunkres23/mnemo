// ── 코드 블록 HTML ──
function codeBlock(text) {
  if (!text.trim()) return '';
  return `<pre class="tool-code-block"><code>${escHtml(text)}</code></pre>`;
}

// ── bash_tool 결과 파싱 ──
function parseBashResult(text) {
  try {
    const obj = JSON.parse(text);
    return { returncode: obj.returncode, stdout: obj.stdout || '', stderr: obj.stderr || '' };
  } catch (e) {
    return { returncode: null, stdout: text, stderr: '' };
  }
}

// ── tool_use 아이콘 ──
function getToolIcon(name) {
  const n = (name || '').toLowerCase();
  if (n.includes('web_search') || n.includes('search')) return 'ti-world';
  if (n.includes('bash') || n.includes('shell') || n.includes('computer')) return 'ti-terminal';
  if (n.includes('create_file') || n.includes('create')) return 'ti-file-plus';
  if (n.includes('str_replace') || n.includes('edit')) return 'ti-edit';
  if (n.includes('view') || n.includes('read')) return 'ti-file-text';
  if (n.includes('present_files')) return 'ti-download';
  if (n.includes('visualize')) return 'ti-chart-bar';
  if (n.includes('artifacts')) return 'ti-code';
  if (n.includes('web_fetch')) return 'ti-link';
  if (n.includes('conversation_search')) return 'ti-history';
  if (n.includes('ask_user')) return 'ti-help-circle';
  return 'ti-tool';
}

function getToolBadge(name) {
  if (!name) return '';
  const n = name.toLowerCase();
  if (n.includes('bash') || n.includes('computer') || n.includes('shell')) return '스크립트';
  if (n.includes('str_replace') || n.includes('edit') || n.includes('write')) return '편집';
  if (n.includes('read') || n.includes('view') || n.includes('file')) return '파일';
  if (n.includes('search') || n.includes('web')) return '검색';
  if (n.includes('create')) return '생성';
  return '실행';
}

function getGroupLabel(firstName, count) {
  const n = firstName.toLowerCase();
  if (n.includes('web_search') || n.includes('search')) return '웹 검색됨';
  if (n.includes('bash') || n.includes('shell') || n.includes('computer')) return '명령 실행됨';
  if (n.includes('str_replace') || n.includes('edit')) return '파일 편집됨';
  if (n.includes('read') || n.includes('view')) return '파일 읽음';
  if (n.includes('create') || n.includes('write')) return '파일 생성됨';
  if (n.includes('visualize') || n.includes('chart')) return '시각화 실행됨';
  return count > 1 ? `${count}개 작업 실행됨` : firstName;
}

// ── tool_result content에서 텍스트 추출 ──
function getResultText(result) {
  if (!result) return '';
  const content = result.content;
  if (Array.isArray(content)) {
    return content.filter(c => c.type === 'text').map(c => c.text || '').join('\n').trim();
  }
  if (typeof content === 'string') return content.trim();
  return '';
}

// ── 검색 결과 카드들 HTML ──
function renderSearchCards(result) {
  const items = (result?.content || []).filter(c => c.type === 'knowledge');
  if (!items.length) return '';
  const cardsHtml = items.map(item => {
    const title = escHtml(item.title || '(제목 없음)');
    const url = item.url || '#';
    const faviconUrl = item.metadata?.favicon_url || '';
    const siteName = escHtml(item.metadata?.site_name || item.metadata?.site_domain || url);
    const faviconHtml = faviconUrl
      ? `<img class="src-favicon" src="${faviconUrl}" alt="" onerror="this.style.display='none';this.nextSibling.style.display='flex'">
         <div class="src-favicon-fallback" style="display:none"><i class="ti ti-world" style="font-size:9px"></i></div>`
      : `<div class="src-favicon-fallback"><i class="ti ti-world" style="font-size:9px"></i></div>`;
    return `<a class="search-result-card" href="${escHtml(url)}" target="_blank" rel="noopener">
      ${faviconHtml}
      <div class="src-body">
        <div class="src-title">${title}</div>
        <div class="src-domain">${siteName}</div>
      </div>
    </a>`;
  }).join('');
  return `<div class="search-results-wrap">${cardsHtml}</div>`;
}

// ── 단일 tool_use+tool_result 쌍 내부 body 렌더 ──
function renderToolPairBody(use, result) {
  const name = (use.name || '').toLowerCase();
  const input = use.input || {};
  const resultText = getResultText(result);
  const isError = result?.is_error;

  if (name === 'web_search' || name === 'web_fetch') {
    const query = input.query || input.q || input.url || '';
    const items = (result?.content || []).filter(c => c.type === 'knowledge');
    return `<div class="tool-pair-body">
      ${query ? `<div class="tool-pair-meta"><i class="ti ti-search" style="font-size:12px"></i> ${escHtml(query)}</div>` : ''}
      ${items.length ? renderSearchCards(result) : (resultText ? codeBlock(resultText) : '')}
    </div>`;
  }

  if (name === 'bash_tool') {
    const cmd = input.command || '';
    const desc = input.description || '';
    const { returncode, stdout, stderr } = parseBashResult(resultText);
    const exitColor = returncode === 0 ? '#5c9e5c' : returncode === null ? 'var(--text3)' : '#e8441a';
    const exitLabel = returncode === null ? '' : `exit ${returncode}`;
    return `<div class="tool-pair-body">
      ${desc ? `<div class="tool-pair-meta">${escHtml(desc)}</div>` : ''}
      ${cmd ? codeBlock(cmd) : ''}
      ${(stdout || stderr) ? `<div class="tool-result-output">
        ${exitLabel ? `<span class="tool-exit-code" style="color:${exitColor}">${exitLabel}</span>` : ''}
        ${stdout ? codeBlock(stdout) : ''}
        ${stderr ? `<div class="tool-stderr">${codeBlock(stderr)}</div>` : ''}
      </div>` : ''}
    </div>`;
  }

  if (name === 'view') {
    const path = input.path || '';
    const desc = input.description || '';
    return `<div class="tool-pair-body">
      ${desc ? `<div class="tool-pair-meta">${escHtml(desc)}</div>` : ''}
      ${path ? `<div class="tool-pair-meta"><i class="ti ti-file" style="font-size:12px"></i> ${escHtml(path)}</div>` : ''}
      ${resultText ? codeBlock(resultText) : ''}
    </div>`;
  }

  if (name === 'str_replace') {
    const path = input.path || '';
    const desc = input.description || '';
    const oldStr = input.old_str || '';
    const newStr = input.new_str || '';
    return `<div class="tool-pair-body">
      ${desc ? `<div class="tool-pair-meta">${escHtml(desc)}</div>` : ''}
      ${path ? `<div class="tool-pair-meta"><i class="ti ti-file" style="font-size:12px"></i> ${escHtml(path)}</div>` : ''}
      ${oldStr ? `<div class="tool-diff-label">삭제</div>${codeBlock(oldStr)}` : ''}
      ${newStr ? `<div class="tool-diff-label" style="color:#5c9e5c">추가</div>${codeBlock(newStr)}` : ''}
      ${resultText ? `<div class="tool-pair-meta" style="color:${isError ? '#e8441a' : '#5c9e5c'}">${escHtml(resultText.slice(0, 120))}</div>` : ''}
    </div>`;
  }

  if (name === 'create_file') {
    const path = input.path || '';
    const desc = input.description || '';
    const fileText = input.file_text || '';
    return `<div class="tool-pair-body">
      ${desc ? `<div class="tool-pair-meta">${escHtml(desc)}</div>` : ''}
      ${path ? `<div class="tool-pair-meta"><i class="ti ti-file-plus" style="font-size:12px"></i> ${escHtml(path)}</div>` : ''}
      ${fileText ? codeBlock(fileText.slice(0, 2000) + (fileText.length > 2000 ? '\n… (이하 생략)' : '')) : ''}
      ${resultText ? `<div class="tool-pair-meta" style="color:#5c9e5c">${escHtml(resultText.slice(0, 120))}</div>` : ''}
    </div>`;
  }

  if (name === 'present_files') {
    const filepaths = input.filepaths || [];
    const files = (result?.content || []).filter(c => c.type === 'local_resource');
    return `<div class="tool-pair-body">
      ${files.length ? files.map(f => `
        <div class="present-file-card">
          <i class="ti ti-file-text" style="font-size:18px;color:var(--text3)"></i>
          <div>
            <div style="font-size:13px;font-weight:500">${escHtml(f.name || f.file_path?.split('/').pop() || '파일')}</div>
            <div style="font-size:11px;color:var(--text3)">${escHtml(f.file_path || '')}</div>
          </div>
        </div>`).join('') : filepaths.map(p => `
        <div class="present-file-card">
          <i class="ti ti-file-text" style="font-size:18px;color:var(--text3)"></i>
          <div style="font-size:13px;color:var(--text2)">${escHtml(p.split('/').pop())}</div>
        </div>`).join('')}
    </div>`;
  }

  if (name === 'artifacts') {
    const title = input.title || '';
    const content = input.content || '';
    return `<div class="tool-pair-body">
      ${title ? `<div class="tool-pair-meta"><i class="ti ti-code" style="font-size:12px"></i> ${escHtml(title)}</div>` : ''}
      ${content ? codeBlock(content.slice(0, 1500) + (content.length > 1500 ? '\n… (이하 생략)' : '')) : ''}
    </div>`;
  }

  if (name === 'visualize:show_widget') {
    const title = input.title || '';
    const msgs = (input.loading_messages || []).join(' · ');
    return `<div class="tool-pair-body">
      ${title ? `<div class="tool-pair-meta"><i class="ti ti-chart-bar" style="font-size:12px"></i> ${escHtml(title)}</div>` : ''}
      ${msgs ? `<div class="tool-pair-meta" style="color:var(--text3)">${escHtml(msgs)}</div>` : ''}
    </div>`;
  }

  if (name === 'conversation_search') {
    const query = input.query || '';
    return `<div class="tool-pair-body">
      ${query ? `<div class="tool-pair-meta"><i class="ti ti-history" style="font-size:12px"></i> "${escHtml(query)}"</div>` : ''}
      ${resultText ? `<div class="tool-result-text">${escHtml(resultText.slice(0, 400))}${resultText.length > 400 ? '…' : ''}</div>` : ''}
    </div>`;
  }

  // 폴백: input 요약 + result 텍스트
  const inputSummary = Object.entries(input).slice(0, 3)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 60)}`).join(' · ');
  return `<div class="tool-pair-body">
    ${inputSummary ? `<div class="tool-pair-meta">${escHtml(inputSummary)}</div>` : ''}
    ${resultText ? codeBlock(resultText.slice(0, 500) + (resultText.length > 500 ? '\n…' : '')) : ''}
  </div>`;
}

// ── 검색 쌍 렌더링 ──
function renderSearchPair(use, result) {
  const query = use.input?.query || use.input?.q || Object.values(use.input || {})[0] || '';
  const items = (result?.content || []).filter(c => c.type === 'knowledge');
  return { queryText: query, totalCount: items.length, cardsHtml: renderSearchCards(result) };
}

// ── tool_group 렌더링 ──
function renderToolGroup(pairs) {
  const id = 'tg-' + (++_toolCounter);
  const firstName = pairs[0]?.use?.name || '도구 실행';
  const label = getGroupLabel(firstName, pairs.length);
  const icon = getToolIcon(firstName);
  const isSearch = firstName === 'web_search' || firstName === 'web_fetch';

  let innerHtml = '';

  if (isSearch && pairs.length > 1) {
    innerHtml = pairs.map(({ use, result }) => {
      const { queryText, totalCount, cardsHtml } = renderSearchPair(use, result);
      return `<div class="tool-group-row">
        <div class="tool-group-row-top">
          <i class="ti ti-world" style="color:var(--text3);font-size:13px;flex-shrink:0"></i>
          <span class="tool-group-name">${escHtml((queryText || '').slice(0, 80))}${(queryText || '').length > 80 ? '…' : ''}</span>
          ${totalCount ? `<span class="src-count">결과 ${totalCount}개</span>` : ''}
        </div>
        ${cardsHtml ? `<div style="margin-top:4px">${cardsHtml}</div>` : ''}
      </div>`;
    }).join('');
  } else if (pairs.length === 1) {
    innerHtml = renderToolPairBody(pairs[0].use, pairs[0].result);
  } else {
    innerHtml = pairs.map(({ use, result }) => {
      const name = use.name || '';
      const input = use.input || {};
      const mainVal = Object.values(input)[0] || '';
      const preview = typeof mainVal === 'string' ? mainVal.slice(0, 60) : JSON.stringify(mainVal).slice(0, 60);
      const isError = result?.is_error;
      const doneIcon = isError ? 'ti-circle-x' : 'ti-circle-check';
      const doneColor = isError ? '#e8441a' : '#5c9e5c';
      return `<div class="tool-group-row">
        <div class="tool-group-row-top">
          <i class="ti ${getToolIcon(name)}" style="color:var(--text3);font-size:13px;flex-shrink:0"></i>
          <span class="tool-group-name">${escHtml(preview)}${preview.length >= 60 ? '…' : ''}</span>
          <i class="ti ${doneIcon}" style="color:${doneColor};font-size:13px;margin-left:auto;flex-shrink:0"></i>
        </div>
      </div>`;
    }).join('');
  }

  const countSpan = pairs.length > 1
    ? ` <span style="color:var(--text3);font-size:12px">(${pairs.length}개)</span>` : '';

  return `<div class="block-tool" id="${id}">
    <div class="block-tool-header" onclick="toggleBlock('${id}')">
      <i class="ti ti-chevron-right chevron"></i>
      <span class="block-tool-name">${label}${countSpan}</span>
    </div>
    <div class="block-tool-body tool-group-body">${innerHtml}</div>
  </div>`;
}

// ── 블록 시퀀스를 세그먼트로 분리 ──
function segmentBlocks(blocks) {
  const segs = [];
  let i = 0;
  while (i < blocks.length) {
    const b = blocks[i];
    if (b.type === 'tool_use') {
      const pairs = [];
      while (i < blocks.length && blocks[i].type === 'tool_use') {
        const use = blocks[i];
        const result = (blocks[i + 1] && blocks[i + 1].type === 'tool_result') ? blocks[i + 1] : null;
        pairs.push({ use, result });
        i += result ? 2 : 1;
      }
      segs.push({ type: 'tool_group', pairs });
    } else {
      segs.push(b);
      i++;
    }
  }
  return segs;
}
