'use strict';

(function () {
  const form = document.getElementById('generator-form');
  const apiUrlInput = document.getElementById('apiUrl');
  const statusEl = document.getElementById('status');
  const resultEl = document.getElementById('result');
  const mcpUrlEl = document.getElementById('mcpUrl');
  const copyBtn = document.getElementById('copyBtn');
  const generateBtn = document.getElementById('generateBtn');

  // Use same-origin API in deployment; fallback to local API in dev when UI served on 8000
  const API_BASE = (location.hostname === '127.0.0.1' && location.port === '8000')
    ? 'http://127.0.0.1:5050'
    : '';

  async function generateMcpUrl(apiUrl) {
    const url = `${API_BASE}/generate?openapi_url=${encodeURIComponent(apiUrl)}`;
    const res = await fetch(url, { method: 'GET' });
    if (!res.ok) {
      let msg = `API error (${res.status})`;
      try {
        const data = await res.json();
        if (data && data.detail) msg = data.detail;
      } catch {}
      throw new Error(msg);
    }
    const data = await res.json();
    if (!data || !data.mcp_url) throw new Error('Malformed response from API');
    return data.mcp_url;
  }

  function isValidUrl(value) {
    try {
      const u = new URL(value);
      return u.protocol === 'http:' || u.protocol === 'https:';
    } catch (_) {
      return false;
    }
  }

  

  function setStatus(text, kind) {
    statusEl.textContent = text || '';
    statusEl.classList.remove('loading', 'success', 'error');
    if (kind) statusEl.classList.add(kind);
  }

  function showResult(url) {
    mcpUrlEl.href = url;
    mcpUrlEl.textContent = url;
    resultEl.classList.remove('hidden');
  }

  function hideResult() {
    resultEl.classList.add('hidden');
    mcpUrlEl.removeAttribute('href');
    mcpUrlEl.textContent = '';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const apiUrl = apiUrlInput.value.trim();
    hideResult();

    if (!apiUrl) {
      setStatus('Please enter an OpenAPI URL.', 'error');
      apiUrlInput.focus();
      return;
    }
    if (!isValidUrl(apiUrl)) {
      setStatus('Enter a valid http(s) URL.', 'error');
      apiUrlInput.focus();
      return;
    }

    generateBtn.disabled = true;
    apiUrlInput.setAttribute('aria-busy', 'true');
    setStatus('Generating…', 'loading');

    try {
      const url = await generateMcpUrl(apiUrl);
      showResult(url);
      setStatus('Done.', 'success');
    } catch (err) {
      console.error(err);
      setStatus(`Failed: ${err?.message || 'Please try again.'}`, 'error');
    } finally {
      generateBtn.disabled = false;
      apiUrlInput.removeAttribute('aria-busy');
    }
  });

  copyBtn.addEventListener('click', async () => {
    const url = mcpUrlEl.href;
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      const prev = copyBtn.title;
      copyBtn.title = 'Copied!';
      copyBtn.setAttribute('aria-label', 'Copied!');
      copyBtn.style.opacity = '0.7';
      setTimeout(() => {
        copyBtn.title = prev || 'Copy URL';
        copyBtn.setAttribute('aria-label', 'Copy URL');
        copyBtn.style.opacity = '1';
      }, 1200);
    } catch (err) {
      console.error('Copy failed', err);
      setStatus('Could not copy URL.', 'error');
    }
  });
})();
