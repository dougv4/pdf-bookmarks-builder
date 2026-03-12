import { invoke } from '@tauri-apps/api/core';

const PREFS_KEY = 'pdf-bookmarks-desktop-prefs';

const els = {
  inputPath: document.querySelector('#input-path'),
  outputPath: document.querySelector('#output-path'),
  pickInputBtn: document.querySelector('#pick-input-btn'),
  pickOutputBtn: document.querySelector('#pick-output-btn'),
  optimizeCheckbox: document.querySelector('#optimize-checkbox'),
  colorDpi: document.querySelector('#color-dpi'),
  grayDpi: document.querySelector('#gray-dpi'),
  jpegQuality: document.querySelector('#jpeg-quality'),
  structuredToc: document.querySelector('#structured-toc'),
  validateBtn: document.querySelector('#validate-btn'),
  processBtn: document.querySelector('#process-btn'),
  validationBanner: document.querySelector('#validation-banner'),
  previewBox: document.querySelector('#preview-box'),
  logBox: document.querySelector('#log-box'),
  metricInput: document.querySelector('#metric-input'),
  metricOptimized: document.querySelector('#metric-optimized'),
  metricOutput: document.querySelector('#metric-output'),
  metricBookmarks: document.querySelector('#metric-bookmarks'),
  resultPaths: document.querySelector('#result-paths'),
};

const state = {
  busy: false,
  lastValidation: null,
  prefs: loadPrefs(),
};

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
  } catch {
    return {};
  }
}

function savePrefs() {
  localStorage.setItem(PREFS_KEY, JSON.stringify(state.prefs));
}

function applyPrefs() {
  els.optimizeCheckbox.checked = state.prefs.optimize ?? true;
  els.colorDpi.value = String(state.prefs.colorDpi ?? 150);
  els.grayDpi.value = String(state.prefs.grayDpi ?? 150);
  els.jpegQuality.value = String(state.prefs.jpegQuality ?? 80);
  els.outputPath.value = state.prefs.outputPath ?? '';
  els.inputPath.value = state.prefs.inputPath ?? '';
  els.structuredToc.value = state.prefs.structuredToc ?? '';
}

function syncPrefs() {
  state.prefs.optimize = els.optimizeCheckbox.checked;
  state.prefs.colorDpi = Number(els.colorDpi.value || 150);
  state.prefs.grayDpi = Number(els.grayDpi.value || 150);
  state.prefs.jpegQuality = Number(els.jpegQuality.value || 80);
  state.prefs.outputPath = els.outputPath.value.trim();
  state.prefs.inputPath = els.inputPath.value.trim();
  state.prefs.structuredToc = els.structuredToc.value;
  state.prefs.lastDir = inferDir(els.outputPath.value.trim()) || inferDir(els.inputPath.value.trim()) || state.prefs.lastDir || '';
  savePrefs();
}

function inferDir(path) {
  if (!path) return '';
  const normalized = path.replace(/\\/g, '/');
  const idx = normalized.lastIndexOf('/');
  if (idx <= 0) return '';
  return normalized.slice(0, idx);
}

function formatBytes(value) {
  if (!value) return '-';
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function setBusy(nextBusy, message = 'Processando...') {
  state.busy = nextBusy;
  els.validateBtn.disabled = nextBusy;
  els.processBtn.disabled = nextBusy;
  els.pickInputBtn.disabled = nextBusy;
  els.pickOutputBtn.disabled = nextBusy;
  if (nextBusy) {
    setBanner('busy', message);
  }
}

function setBanner(kind, text) {
  els.validationBanner.className = `status-banner ${kind}`;
  els.validationBanner.textContent = text;
}

function setLogs(text) {
  els.logBox.textContent = text || 'Nenhuma execucao ainda.';
}

function renderResult(data) {
  els.metricInput.textContent = formatBytes(data.input_size_bytes);
  els.metricOptimized.textContent = formatBytes(data.optimized_size_bytes);
  els.metricOutput.textContent = formatBytes(data.output_size_bytes);
  els.metricBookmarks.textContent = data.bookmark_count ? String(data.bookmark_count) : '-';
  els.resultPaths.innerHTML = `
    <p><strong>PDF final:</strong> ${escapeHtml(data.output_file_path || '-')}</p>
    <p><strong>Preview salvo:</strong> ${escapeHtml(data.preview_file_path || '-')}</p>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function summarizeLogs(logs) {
  if (!Array.isArray(logs) || !logs.length) {
    return 'Nenhum log retornado.';
  }
  return logs
    .map((entry) => {
      const blocks = [`$ ${entry.cmd}`];
      if (entry.stdout) blocks.push(entry.stdout);
      if (entry.stderr) blocks.push(entry.stderr);
      return blocks.join('\n');
    })
    .join('\n\n');
}

function ensureCoreFields() {
  if (!els.inputPath.value.trim()) {
    throw new Error('Selecione um PDF de entrada.');
  }
  if (!els.outputPath.value.trim()) {
    throw new Error('Defina o caminho do PDF de saida.');
  }
  if (!els.structuredToc.value.trim()) {
    throw new Error('Cole o sumario estruturado antes de continuar.');
  }
}

function suggestedOutputName(inputPath) {
  const normalized = inputPath.replace(/\\/g, '/');
  const filename = normalized.split('/').pop() || 'output.pdf';
  const idx = filename.toLowerCase().endsWith('.pdf') ? filename.length - 4 : filename.length;
  return `${filename.slice(0, idx)}.bookmarked.pdf`;
}

async function pickInputPdf() {
  syncPrefs();
  const picked = await invoke('pick_input_pdf', {
    payload: { lastDir: state.prefs.lastDir || null },
  });
  if (!picked) return;
  els.inputPath.value = picked;
  state.prefs.inputPath = picked;
  state.prefs.lastDir = inferDir(picked) || state.prefs.lastDir || '';
  if (!els.outputPath.value.trim()) {
    els.outputPath.value = `${state.prefs.lastDir}/${suggestedOutputName(picked)}`;
  }
  syncPrefs();
}

async function pickOutputPdf() {
  syncPrefs();
  const picked = await invoke('pick_output_pdf', {
    payload: {
      inputPath: els.inputPath.value.trim() || null,
      suggestedName: suggestedOutputName(els.inputPath.value.trim() || 'output.pdf'),
      lastDir: state.prefs.lastDir || null,
    },
  });
  if (!picked) return;
  els.outputPath.value = picked;
  state.prefs.outputPath = picked;
  state.prefs.lastDir = inferDir(picked) || state.prefs.lastDir || '';
  syncPrefs();
}

async function validatePreview() {
  syncPrefs();
  const structuredToc = els.structuredToc.value;
  setBusy(true, 'Validando sumario...');
  try {
    const result = await invoke('validate_preview', {
      payload: { structuredToc },
    });
    state.lastValidation = result;
    els.previewBox.textContent = result.preview_text || 'Sem preview no momento.';
    if (result.valid) {
      setBanner('success', `Sumario valido. ${result.bookmark_count} marcadores prontos.`);
    } else {
      setBanner('error', (result.errors || []).join(' | ') || 'Sumario invalido.');
    }
    els.metricBookmarks.textContent = result.bookmark_count ? String(result.bookmark_count) : '-';
    setLogs(result.valid ? 'Validacao concluida sem executar Ghostscript/qpdf.' : (result.errors || []).join('\n'));
  } catch (error) {
    setBanner('error', error.message || String(error));
    setLogs(error.message || String(error));
  } finally {
    setBusy(false, els.validationBanner.textContent);
  }
}

async function processPdf() {
  syncPrefs();
  try {
    ensureCoreFields();
  } catch (error) {
    setBanner('error', error.message);
    return;
  }

  setBusy(true, 'Processando PDF localmente...');
  try {
    const payload = {
      inputPdf: els.inputPath.value.trim(),
      outputPdf: els.outputPath.value.trim(),
      structuredToc: els.structuredToc.value,
      optimize: els.optimizeCheckbox.checked,
      colorDpi: Number(els.colorDpi.value || 150),
      grayDpi: Number(els.grayDpi.value || 150),
      jpegQuality: Number(els.jpegQuality.value || 80),
    };
    const result = await invoke('process_pdf', { payload });
    renderResult(result);
    els.previewBox.textContent = result.preview_text || 'Sem preview no momento.';
    setLogs(summarizeLogs(result.logs));
    if (result.status === 'success') {
      setBanner('success', 'PDF processado com sucesso.');
    } else {
      setBanner('error', (result.errors || []).join(' | ') || 'Falha no processamento.');
    }
  } catch (error) {
    setBanner('error', error.message || String(error));
    setLogs(error.message || String(error));
  } finally {
    setBusy(false, els.validationBanner.textContent);
  }
}

function registerEvents() {
  els.pickInputBtn.addEventListener('click', () => pickInputPdf());
  els.pickOutputBtn.addEventListener('click', () => pickOutputPdf());
  els.validateBtn.addEventListener('click', () => validatePreview());
  els.processBtn.addEventListener('click', () => processPdf());
  for (const input of [els.optimizeCheckbox, els.colorDpi, els.grayDpi, els.jpegQuality, els.outputPath, els.structuredToc]) {
    input.addEventListener('change', syncPrefs);
    input.addEventListener('input', syncPrefs);
  }
}

function boot() {
  applyPrefs();
  registerEvents();
  setBanner('muted', 'Aguardando validacao.');
}

boot();
