function toggleBlock(id) {
  document.getElementById(id)?.classList.toggle('open');
}

function renderThinkingBlock(block) {
  const id = 'think-' + (++_toolCounter);
  const text = escHtml(block.thinking || block.text || '');
  return `<div class="block-thinking" id="${id}">
    <div class="block-thinking-header" onclick="toggleBlock('${id}')">
      <i class="ti ti-chevron-right"></i>
      <span>생각하는 중...</span>
    </div>
    <div class="block-thinking-body">${text.replace(/\n/g, '<br>')}</div>
  </div>`;
}
