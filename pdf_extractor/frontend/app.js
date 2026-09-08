// State Management
const state = {
  activeMode: 'upload', // 'upload' | 'folder'
  discoveredFiles: [],  // [{ filename, full_path, size_formatted, ... }]
  selectedFiles: new Set(),
  activeResult: null,
  batchResult: null,
};

// DOM Elements
const themeToggleBtn = document.getElementById('themeToggleBtn');
const tabFolderBtn = document.getElementById('tabFolderBtn');
const tabUploadBtn = document.getElementById('tabUploadBtn');
const modeFolderView = document.getElementById('modeFolderView');
const modeUploadView = document.getElementById('modeUploadView');
const folderPathInput = document.getElementById('folderPathInput');
const browseFolderBtn = document.getElementById('browseFolderBtn');
const loadSamplesBtn = document.getElementById('loadSamplesBtn');
const dropZone = document.getElementById('dropZone');
const fileUploadInput = document.getElementById('fileUploadInput');
const fileListContainer = document.getElementById('fileListContainer');
const selectAllFilesBtn = document.getElementById('selectAllFilesBtn');
const clearAllFilesBtn = document.getElementById('clearAllFilesBtn');
const selectedCountBadge = document.getElementById('selectedCountBadge');
const mainSectionInput = document.getElementById('mainSectionInput');
const subSectionInput = document.getElementById('subSectionInput');
const naturalQueryInput = document.getElementById('naturalQueryInput');
const runExtractBtn = document.getElementById('runExtractBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingStatusText = document.getElementById('loadingStatusText');
const placeholderState = document.getElementById('placeholderState');
const resultContainer = document.getElementById('resultContainer');
const batchContainer = document.getElementById('batchContainer');

// Result View Elements
const resDocName = document.getElementById('resDocName');
const resTargetBadge = document.getElementById('resTargetBadge');
const resPagesBadge = document.getElementById('resPagesBadge');
const downloadHtmlBtn = document.getElementById('downloadHtmlBtn');
const downloadTxtBtn = document.getElementById('downloadTxtBtn');
const downloadJsonBtn = document.getElementById('downloadJsonBtn');
const downloadCsvBtn = document.getElementById('downloadCsvBtn');
const downloadExcelBtn = document.getElementById('downloadExcelBtn');
const valStatusDot = document.getElementById('valStatusDot');
const valStatusMessage = document.getElementById('valStatusMessage');
const valConfidenceBadge = document.getElementById('valConfidenceBadge');
const includedSectionsTags = document.getElementById('includedSectionsTags');
const excludedSectionsTags = document.getElementById('excludedSectionsTags');
const valTablesCount = document.getElementById('valTablesCount');
const valBlocksCount = document.getElementById('valBlocksCount');

// Tabs & Panels
const tabDocView = document.getElementById('tabDocView');
const tabBlocksView = document.getElementById('tabBlocksView');
const tabTablesView = document.getElementById('tabTablesView');
const tabJsonView = document.getElementById('tabJsonView');
const tabTextView = document.getElementById('tabTextView');
const tabTreeView = document.getElementById('tabTreeView');
const tablesTabCount = document.getElementById('tablesTabCount');

const viewDocPanel = document.getElementById('viewDocPanel');
const viewBlocksPanel = document.getElementById('viewBlocksPanel');
const viewTablesPanel = document.getElementById('viewTablesPanel');
const viewJsonPanel = document.getElementById('viewJsonPanel');
const viewTextPanel = document.getElementById('viewTextPanel');
const viewTreePanel = document.getElementById('viewTreePanel');

const docPaperContent = document.getElementById('docPaperContent');
const docPageSpanBadge = document.getElementById('docPageSpanBadge');
const docElementCountBadge = document.getElementById('docElementCountBadge');
const docPrintBtn = document.getElementById('docPrintBtn');
const docCopyBtn = document.getElementById('docCopyBtn');

const blocksFeed = document.getElementById('blocksFeed');
const tablesContainer = document.getElementById('tablesContainer');
const rawJsonContent = document.getElementById('rawJsonContent');
const copyJsonBtn = document.getElementById('copyJsonBtn');
const rawTextContent = document.getElementById('rawTextContent');
const copyTextBtn = document.getElementById('copyTextBtn');
const treeContainer = document.getElementById('treeContainer');

// Batch Elements
const batchSummaryStats = document.getElementById('batchSummaryStats');
const batchTableBody = document.getElementById('batchTableBody');
const downloadBatchCsvBtn = document.getElementById('downloadBatchCsvBtn');
const downloadBatchExcelBtn = document.getElementById('downloadBatchExcelBtn');

// Modal Elements
const traceModal = document.getElementById('traceModal');
const closeModalBtn = document.getElementById('closeModalBtn');
const modalContent = document.getElementById('modalContent');
const sourcePageImg = document.getElementById('sourcePageImg');

// 1. Theme Toggle
themeToggleBtn.addEventListener('click', () => {
  document.body.classList.toggle('theme-light');
  const isLight = document.body.classList.contains('theme-light');
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
});

if (localStorage.getItem('theme') === 'light') {
  document.body.classList.add('theme-light');
}

// 2. Tab Navigation for Input Modes
tabFolderBtn.addEventListener('click', () => {
  tabFolderBtn.classList.add('active');
  tabUploadBtn.classList.remove('active');
  modeFolderView.classList.add('active');
  modeUploadView.classList.remove('active');
  state.activeMode = 'folder';
});

tabUploadBtn.addEventListener('click', () => {
  tabUploadBtn.classList.add('active');
  tabFolderBtn.classList.remove('active');
  modeUploadView.classList.add('active');
  modeFolderView.classList.remove('active');
  state.activeMode = 'upload';
});

// 3. Preset Query Pills
document.querySelectorAll('.pill-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    mainSectionInput.value = btn.dataset.main || '';
    subSectionInput.value = btn.dataset.sub || '';
    naturalQueryInput.value = '';
  });
});

// 4. File Discovery - Folder Mode
browseFolderBtn.addEventListener('click', async () => {
  const path = folderPathInput.value.trim();
  if (!path) {
    alert('Please enter a folder path.');
    return;
  }
  await fetchDiscoveredFiles('/api/files/browse', { folder_path: path });
});

if (loadSamplesBtn) {
  loadSamplesBtn.addEventListener('click', async () => {
    folderPathInput.value = 'sample_reports';
    await fetchDiscoveredFiles('/api/files/samples');
  });
}

async function fetchDiscoveredFiles(endpoint, payload = null) {
  showLoading('Scanning directory for PDF documents...');
  try {
    const opts = payload ? {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    } : { method: 'GET' };

    const res = await fetch(endpoint, opts);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to read directory');

    state.discoveredFiles = data.files || [];
    state.selectedFiles.clear();
    // Default select first file
    if (state.discoveredFiles.length > 0) {
      state.selectedFiles.add(state.discoveredFiles[0].full_path);
    }
    renderFileList();
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    hideLoading();
  }
}

// 5. File Upload Handling
dropZone.addEventListener('click', () => fileUploadInput.click());
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', async (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length > 0) {
    await handleFileUpload(e.dataTransfer.files);
  }
});

fileUploadInput.addEventListener('change', async (e) => {
  if (e.target.files.length > 0) {
    await handleFileUpload(e.target.files);
  }
});

async function handleFileUpload(files) {
  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }

  showLoading('Uploading and validating PDF files...');
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Upload failed');

    for (const f of data.files) {
      state.discoveredFiles.push({
        filename: f.original_filename,
        full_path: f.file_path,
        size_formatted: `${(f.size_bytes / 1024).toFixed(1)} KB`,
      });
      state.selectedFiles.add(f.file_path);
    }
    renderFileList();
  } catch (err) {
    alert(`Upload error: ${err.message}`);
  } finally {
    hideLoading();
  }
}

// 6. Render Uploaded / Discovered Files List
function renderFileList() {
  if (state.discoveredFiles.length === 0) {
    fileListContainer.innerHTML = `
      <div class="empty-state-hint">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" style="display:block;margin:0 auto 6px;opacity:0.5"><path d="M14 2H6a2 2 0 0 1-2-2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
        No PDF uploaded yet.<br>
        <span style="font-size:0.72rem;opacity:0.75">Upload a PDF above to begin extraction.</span>
      </div>
    `;
    selectedCountBadge.textContent = '0 selected';
    return;
  }

  fileListContainer.innerHTML = '';
  state.discoveredFiles.forEach((file) => {
    const isSelected = state.selectedFiles.has(file.full_path);
    const item = document.createElement('div');
    item.className = `file-item ${isSelected ? 'selected' : ''}`;
    item.innerHTML = `
      <div class="file-item-left">
        <input type="checkbox" ${isSelected ? 'checked' : ''} data-path="${escapeHtml(file.full_path)}">
        <span class="file-name" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</span>
      </div>
      <div class="file-item-right">
        <span class="file-size">${escapeHtml(file.size_formatted)}</span>
        <button class="btn-remove-file" title="Remove PDF" data-path="${escapeHtml(file.full_path)}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
    `;

    // Item click toggles selection (unless clicking the remove button)
    item.addEventListener('click', (e) => {
      if (e.target.closest('.btn-remove-file')) return;
      if (e.target.tagName !== 'INPUT') {
        const cb = item.querySelector('input[type="checkbox"]');
        cb.checked = !cb.checked;
      }
      const cb = item.querySelector('input[type="checkbox"]');
      if (cb.checked) {
        state.selectedFiles.add(file.full_path);
        item.classList.add('selected');
      } else {
        state.selectedFiles.delete(file.full_path);
        item.classList.remove('selected');
      }
      updateSelectedCounter();
    });

    // Remove single file button
    const removeBtn = item.querySelector('.btn-remove-file');
    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      removeFile(file.full_path);
    });

    fileListContainer.appendChild(item);
  });

  updateSelectedCounter();
}

function removeFile(fullPath) {
  const filename = fullPath.split('/').pop();
  fetch(`/api/upload/${encodeURIComponent(filename)}`, { method: 'DELETE' }).catch(() => {});
  state.discoveredFiles = state.discoveredFiles.filter(f => f.full_path !== fullPath);
  state.selectedFiles.delete(fullPath);
  renderFileList();
}

function updateSelectedCounter() {
  const count = state.selectedFiles.size;
  selectedCountBadge.textContent = `${count} selected`;
}

selectAllFilesBtn.addEventListener('click', () => {
  state.discoveredFiles.forEach(f => state.selectedFiles.add(f.full_path));
  renderFileList();
});

clearAllFilesBtn.addEventListener('click', () => {
  state.discoveredFiles.forEach(f => {
    const fn = f.full_path.split('/').pop();
    fetch(`/api/upload/${encodeURIComponent(fn)}`, { method: 'DELETE' }).catch(() => {});
  });
  state.discoveredFiles = [];
  state.selectedFiles.clear();
  renderFileList();
});

// 7. Run Extraction
runExtractBtn.addEventListener('click', async () => {
  if (state.selectedFiles.size === 0) {
    alert('Please select at least one PDF file to extract.');
    return;
  }

  const mainSec = mainSectionInput.value.trim();
  const subSec = subSectionInput.value.trim();
  const naturalQuery = naturalQueryInput.value.trim();

  if (state.selectedFiles.size === 1) {
    const filePath = Array.from(state.selectedFiles)[0];
    const fileObj = state.discoveredFiles.find(f => f.full_path === filePath);
    const filename = fileObj ? fileObj.filename : 'document.pdf';

    showLoading(`Extracting Section ${mainSec}${subSec ? ' → ' + subSec : ''} from ${filename}...`);
    try {
      const res = await fetch('/api/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: filePath,
          filename: filename,
          main_section: mainSec,
          target_subsection: subSec || null,
          natural_query: naturalQuery || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Extraction failed');

      state.activeResult = data;
      displaySingleResult(data);
    } catch (err) {
      alert(`Extraction error: ${err.message}`);
    } finally {
      hideLoading();
    }
  } else {
    // Batch Extraction
    showLoading(`Processing batch of ${state.selectedFiles.size} PDF files...`);
    try {
      const res = await fetch('/api/extract/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          files: Array.from(state.selectedFiles),
          main_section: mainSec,
          target_subsection: subSec || null,
          natural_query: naturalQuery || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Batch extraction failed');

      state.batchResult = data;
      displayBatchResult(data);
    } catch (err) {
      alert(`Batch error: ${err.message}`);
    } finally {
      hideLoading();
    }
  }
});

// 8. Display Single Document Result
function displaySingleResult(result) {
  placeholderState.style.display = 'none';
  batchContainer.style.display = 'none';
  resultContainer.style.display = 'block';

  resDocName.textContent = result.document;
  resTargetBadge.textContent = `${result.requested_section}${result.requested_subsection ? ' → ' + result.requested_subsection : ''}`;
  resPagesBadge.textContent = result.start_page ? `Pages ${result.start_page} – ${result.end_page}` : 'No Pages';

  // Export URLs
  if (result.download_urls) {
    if (downloadHtmlBtn) downloadHtmlBtn.href = result.download_urls.html || '#';
    downloadTxtBtn.href = result.download_urls.txt || '#';
    downloadJsonBtn.href = result.download_urls.json || '#';
    downloadCsvBtn.href = result.download_urls.csv || '#';
    downloadExcelBtn.href = result.download_urls.excel || '#';
  }

  // Validation Banner
  const val = result.validation || {};
  valStatusMessage.textContent = val.status_message || result.status;
  valConfidenceBadge.textContent = `Confidence: ${(val.confidence_score * 100).toFixed(0)}%`;

  if (val.confidence_score >= 0.8) {
    valStatusDot.className = 'status-dot success';
    valConfidenceBadge.style.color = 'var(--success)';
  } else if (val.confidence_score >= 0.5) {
    valStatusDot.className = 'status-dot warning';
    valConfidenceBadge.style.color = 'var(--warning)';
  } else {
    valStatusDot.className = 'status-dot danger';
    valConfidenceBadge.style.color = 'var(--danger)';
  }

  // Included & Excluded tags
  includedSectionsTags.innerHTML = '';
  (val.included_sections || []).forEach(sec => {
    const span = document.createElement('span');
    span.className = 'tag-included';
    span.textContent = `✓ Section ${sec}`;
    includedSectionsTags.appendChild(span);
  });

  excludedSectionsTags.innerHTML = '';
  (val.excluded_sections || []).forEach(sec => {
    const span = document.createElement('span');
    span.className = 'tag-excluded';
    span.textContent = `✗ Section ${sec}`;
    excludedSectionsTags.appendChild(span);
  });

  valTablesCount.textContent = val.tables_included_count || 0;
  valBlocksCount.textContent = (result.structured_content && result.structured_content.length) || (result.blocks && result.blocks.length) || 0;
  tablesTabCount.textContent = val.tables_included_count || 0;

  // Default to Authentic Document View (PDF Flow)
  switchViewerTab(tabDocView, viewDocPanel);

  // Render Authentic Document Flow (As present in PDF)
  renderDocumentFlow(result);

  // Render Structured Elements
  renderStructuredFeed(result.structured_content || [], result.blocks || []);

  // Render Tables Feed
  renderTablesFeed(result.structured_content || [], result.blocks || []);

  // Render Structured JSON
  rawJsonContent.textContent = JSON.stringify(result, null, 2);

  // Render Clean TXT
  rawTextContent.textContent = result.content || '(No content extracted)';

  // Render Hierarchy Tree
  renderHierarchyTree(result.section_tree || [], val.included_sections || []);
}

// 8b. Authentic Formatted Document Flow View (As present in PDF)
function renderDocumentFlow(result) {
  if (!docPaperContent) return;
  docPaperContent.innerHTML = '';

  const items = (result.structured_content && result.structured_content.length > 0)
    ? result.structured_content
    : (result.blocks || []);

  if (items.length === 0) {
    docPaperContent.innerHTML = '<div class="empty-state-hint">No content available to render in document view.</div>';
    return;
  }

  // Header Banner
  const headerDiv = document.createElement('div');
  headerDiv.className = 'doc-header-banner';
  headerDiv.innerHTML = `
    <div class="doc-header-title">${escapeHtml(result.document || 'Extracted Document')}</div>
    <div class="doc-header-subtitle">
      <span>Section: <strong>${escapeHtml(result.requested_section)}${result.requested_subsection ? ' → ' + escapeHtml(result.requested_subsection) : ''}</strong></span>
      <span>•</span>
      <span>Pages: <strong>${result.start_page} – ${result.end_page}</strong></span>
      <span>•</span>
      <span>Elements: <strong>${items.length}</strong></span>
    </div>
  `;
  docPaperContent.appendChild(headerDiv);

  let currentPage = null;

  items.forEach((item) => {
    const pageNum = item.page || item.page_num;

    // Page Divider
    if (pageNum && pageNum !== currentPage) {
      currentPage = pageNum;
      const marker = document.createElement('div');
      marker.className = 'doc-page-marker';
      marker.innerHTML = `
        <div class="doc-page-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
          Page ${currentPage}
        </div>
        <div class="doc-page-line"></div>
      `;
      docPaperContent.appendChild(marker);
    }

    const type = item.type || item.block_type || 'paragraph';

    if (type === 'heading') {
      const level = item.level || (item.section_number && item.section_number.includes('.') ? (item.section_number.split('.').length) : 1);
      const tag = level === 1 ? 'h2' : (level === 2 ? 'h3' : 'h4');
      const heading = document.createElement(tag);
      heading.className = `doc-heading doc-h${Math.min(level, 4)}`;

      const numHtml = item.section_number ? `<span class="doc-sec-num">${escapeHtml(item.section_number)}</span>` : '';
      const titleText = item.title || item.text || '';
      heading.innerHTML = `${numHtml} ${escapeHtml(titleText)}`;
      docPaperContent.appendChild(heading);
    } else if (type === 'table') {
      const tableWrapper = document.createElement('div');
      tableWrapper.className = 'doc-table-wrapper';
      const captionText = item.caption ? `<div class="doc-table-caption">${escapeHtml(item.caption)} (Page ${pageNum})</div>` : '';
      const tableHtml = buildHtmlTable(item.columns || item.table_columns, item.rows || item.table_rows, item.raw_rows || item.table_data);
      tableWrapper.innerHTML = `
        ${captionText}
        ${tableHtml}
      `;
      docPaperContent.appendChild(tableWrapper);
    } else if (type === 'bullet_list' || type === 'numbered_list') {
      const listItems = item.items || item.bullet_items || (item.text ? [item.text] : []);
      const tag = type === 'bullet_list' ? 'ul' : 'ol';
      const listElem = document.createElement(tag);
      listElem.className = 'doc-list';
      listElem.innerHTML = listItems.map(it => `<li>${escapeHtml(it)}</li>`).join('');
      docPaperContent.appendChild(listElem);
    } else {
      // Paragraph or caption
      const text = item.text || '';
      if (!text.trim()) return;

      // Detect sub-headers like "Important Identified Risks" or "Important potential risks" or "Missing information"
      const trimmed = text.trim();
      const isSubhead = (
        trimmed.length < 60 && 
        !trimmed.endsWith('.') && 
        !trimmed.endsWith(':') &&
        (
          /^(important|missing|identified|potential|summary|general|clinical|safety concerns)/i.test(trimmed) ||
          (/^[A-Z][A-Za-z0-9\s,\/-]+$/.test(trimmed) && trimmed.split(/\s+/).length <= 6)
        )
      );

      if (isSubhead) {
        const subhead = document.createElement('h4');
        subhead.className = 'doc-subhead';
        subhead.textContent = trimmed;
        docPaperContent.appendChild(subhead);
      } else {
        const p = document.createElement('p');
        p.className = 'doc-paragraph';
        p.textContent = text;
        docPaperContent.appendChild(p);
      }
    }
  });

  // Update Toolbar Badges
  if (docPageSpanBadge) {
    docPageSpanBadge.textContent = result.start_page ? `Pages ${result.start_page} – ${result.end_page}` : 'Single Page';
  }
  if (docElementCountBadge) {
    docElementCountBadge.textContent = `${items.length} Extracted Items`;
  }
}

// 9. Structured Elements Feed
function renderStructuredFeed(structuredItems, rawBlocks) {
  blocksFeed.innerHTML = '';
  const items = structuredItems.length > 0 ? structuredItems : rawBlocks;

  if (items.length === 0) {
    blocksFeed.innerHTML = '<div class="empty-state-hint">No elements extracted for this section.</div>';
    return;
  }

  items.forEach((item, idx) => {
    const card = document.createElement('div');
    const type = item.type || item.block_type || 'paragraph';
    let extraClass = '';
    if (type === 'heading') extraClass = 'heading-block';
    if (type === 'table') extraClass = 'table-block';

    card.className = `trace-block ${extraClass}`;

    let contentHtml = '';
    if (type === 'heading') {
      const title = item.title || item.text || '';
      contentHtml = `<div class="trace-text" style="font-weight: 700; font-size: 1.05rem; color: #818CF8;">${escapeHtml(item.section_number || '')} ${escapeHtml(title)}</div>`;
    } else if (type === 'table') {
      contentHtml = buildHtmlTable(item.columns, item.rows, item.raw_rows || item.table_data);
    } else if (type === 'bullet_list' || type === 'numbered_list') {
      const listItems = item.items || item.bullet_items || [item.text];
      const tag = type === 'bullet_list' ? 'ul' : 'ol';
      contentHtml = `<${tag} class="structured-bullet-list">${listItems.map(it => `<li>${escapeHtml(it)}</li>`).join('')}</${tag}>`;
    } else {
      contentHtml = `<div class="trace-text">${escapeHtml(item.text || '')}</div>`;
    }

    card.innerHTML = `
      <div class="trace-block-header">
        <span class="trace-page-badge">Page ${item.page || item.page_num}${item.section_number || item.section ? ' • Section ' + (item.section_number || item.section) : ''}</span>
        <span class="trace-type-badge">${type.toUpperCase()}</span>
        <button class="btn-view-source" onclick="openSourceInspector(${idx})">View Source Page</button>
      </div>
      ${contentHtml}
    `;

    blocksFeed.appendChild(card);
  });
}

function buildHtmlTable(columns, rows, rawRows) {
  if (columns && columns.length > 0 && rows && rows.length > 0) {
    let html = '<div class="rendered-table-container"><table class="custom-table"><thead><tr>';
    columns.forEach(col => {
      html += `<th>${escapeHtml(col)}</th>`;
    });
    html += '</tr></thead><tbody>';

    rows.forEach(r => {
      html += '<tr>';
      columns.forEach(col => {
        html += `<td>${escapeHtml(r[col] || '')}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
  } else if (rawRows && rawRows.length > 0) {
    const header = rawRows[0];
    const bodyRows = rawRows.slice(1);
    let html = '<div class="rendered-table-container"><table class="custom-table"><thead><tr>';
    header.forEach(h => {
      html += `<th>${escapeHtml(h || '')}</th>`;
    });
    html += '</tr></thead><tbody>';
    bodyRows.forEach(row => {
      html += '<tr>';
      row.forEach(cell => {
        html += `<td>${escapeHtml(cell || '')}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
  }
  return '';
}

// 10. Extracted Tables Feed
function renderTablesFeed(structuredItems, rawBlocks) {
  tablesContainer.innerHTML = '';
  const tableItems = structuredItems.filter(it => it.type === 'table');

  if (tableItems.length === 0) {
    // Fallback to raw blocks with table data
    const rawTableBlocks = rawBlocks.filter(b => (b.block_type === 'table' || b.type === 'table') && (b.table_data || b.table_rows));
    if (rawTableBlocks.length === 0) {
      tablesContainer.innerHTML = '<div class="empty-state-hint">No tables found in the extracted section.</div>';
      return;
    }
    rawTableBlocks.forEach((tb, i) => {
      const card = document.createElement('div');
      card.className = 'trace-block table-block';
      card.innerHTML = `
        <div class="trace-block-header">
          <span class="trace-page-badge">Page ${tb.page || tb.page_num}</span>
          <span class="trace-type-badge">TABLE</span>
        </div>
        ${buildHtmlTable(tb.table_columns, tb.table_rows, tb.table_data)}
      `;
      tablesContainer.appendChild(card);
    });
    return;
  }

  tableItems.forEach((tb, i) => {
    const card = document.createElement('div');
    card.className = 'trace-block table-block';
    card.innerHTML = `
      <div class="trace-block-header">
        <span class="trace-page-badge">Page ${tb.page} • Section ${tb.section_number || 'N/A'}</span>
        <span class="trace-type-badge">TABLE (${(tb.rows && tb.rows.length) || 0} ROWS)</span>
      </div>
      <h4 style="font-size: 0.82rem; margin: 6px 0; color: #E2E8F0;">${escapeHtml(tb.caption || 'Table')}</h4>
      ${buildHtmlTable(tb.columns, tb.rows, tb.raw_rows)}
    `;
    tablesContainer.appendChild(card);
  });
}

// 11. Hierarchy Tree View
function renderHierarchyTree(treeNodes, includedSections) {
  treeContainer.innerHTML = '';
  if (!treeNodes || treeNodes.length === 0) {
    treeContainer.innerHTML = '<div class="empty-state-hint">No hierarchy available.</div>';
    return;
  }

  function createNodeElement(node) {
    const isIncluded = includedSections.includes(node.number);
    const wrapper = document.createElement('div');
    wrapper.className = 'tree-node';

    const line = document.createElement('div');
    line.className = `tree-node-line ${isIncluded ? 'included' : 'excluded'}`;
    line.innerHTML = `
      <span class="tree-node-num">${node.number}</span>
      <span class="tree-node-title">${escapeHtml(node.title)}</span>
      <span class="tree-node-pages">p. ${node.start_page}–${node.end_page}</span>
    `;
    wrapper.appendChild(line);

    if (node.children && node.children.length > 0) {
      node.children.forEach(child => {
        wrapper.appendChild(createNodeElement(child));
      });
    }
    return wrapper;
  }

  treeNodes.forEach(root => {
    treeContainer.appendChild(createNodeElement(root));
  });
}

// 12. Visual Source Page & Traceability Inspector Modal
window.openSourceInspector = function(itemIdx) {
  if (!state.activeResult) return;
  const items = (state.activeResult.structured_content && state.activeResult.structured_content.length > 0)
    ? state.activeResult.structured_content
    : state.activeResult.blocks;

  const item = items[itemIdx];
  if (!item) return;

  const docName = state.activeResult.document;
  const page = item.page || item.page_num;
  const bbox = item.bbox;

  modalContent.innerHTML = `
    <table class="trace-meta-table">
      <tr>
        <td class="trace-meta-label">Document Source:</td>
        <td><strong>${escapeHtml(docName)}</strong></td>
      </tr>
      <tr>
        <td class="trace-meta-label">Original Page:</td>
        <td><strong>Page ${page}</strong></td>
      </tr>
      <tr>
        <td class="trace-meta-label">Assigned Section:</td>
        <td><strong>${item.section_number || item.section || 'N/A'}</strong></td>
      </tr>
      <tr>
        <td class="trace-meta-label">Element Type:</td>
        <td><span class="badge badge-target">${(item.type || item.block_type || 'PARAGRAPH').toUpperCase()}</span></td>
      </tr>
      <tr>
        <td class="trace-meta-label">Coordinates (bbox):</td>
        <td><code>${bbox ? bbox.map(v => v.toFixed(1)).join(', ') : 'N/A'}</code></td>
      </tr>
    </table>
    <h4 style="font-size: 0.8rem; margin-bottom: 6px; color: var(--text-secondary);">Raw Extracted Content:</h4>
    <div style="background-color: var(--bg-primary); padding: 10px; border-radius: 6px; font-size: 0.82rem; white-space: pre-wrap; font-family: var(--font-mono); max-height: 200px; overflow-y: auto;">
      ${escapeHtml(item.text || item.title || JSON.stringify(item.rows || item.items || '', null, 2))}
    </div>
  `;

  // Set high-res source image with bbox highlight parameter
  const bboxParam = bbox ? `?bbox=${bbox.join(',')}` : '';
  sourcePageImg.src = `/api/source/${encodeURIComponent(docName)}/${page}${bboxParam}`;

  traceModal.style.display = 'flex';
};

closeModalBtn.addEventListener('click', () => {
  traceModal.style.display = 'none';
  sourcePageImg.src = '';
});

traceModal.addEventListener('click', (e) => {
  if (e.target === traceModal) {
    traceModal.style.display = 'none';
    sourcePageImg.src = '';
  }
});

// 13. Viewer Tabs Navigation
if (tabDocView) tabDocView.addEventListener('click', () => switchViewerTab(tabDocView, viewDocPanel));
tabBlocksView.addEventListener('click', () => switchViewerTab(tabBlocksView, viewBlocksPanel));
tabTablesView.addEventListener('click', () => switchViewerTab(tabTablesView, viewTablesPanel));
tabJsonView.addEventListener('click', () => switchViewerTab(tabJsonView, viewJsonPanel));
tabTextView.addEventListener('click', () => switchViewerTab(tabTextView, viewTextPanel));
tabTreeView.addEventListener('click', () => switchViewerTab(tabTreeView, viewTreePanel));

function switchViewerTab(activeBtn, activePanel) {
  [tabDocView, tabBlocksView, tabTablesView, tabJsonView, tabTextView, tabTreeView].forEach(b => b && b.classList.remove('active'));
  [viewDocPanel, viewBlocksPanel, viewTablesPanel, viewJsonPanel, viewTextPanel, viewTreePanel].forEach(p => p && p.classList.remove('active'));
  if (activeBtn) activeBtn.classList.add('active');
  if (activePanel) activePanel.classList.add('active');
}

if (docPrintBtn) {
  docPrintBtn.addEventListener('click', () => {
    window.print();
  });
}

if (docCopyBtn) {
  docCopyBtn.addEventListener('click', () => {
    if (!state.activeResult) return;
    const content = state.activeResult.content || '';
    navigator.clipboard.writeText(content);
    docCopyBtn.textContent = 'Copied!';
    setTimeout(() => {
      docCopyBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        Copy Text
      `;
    }, 2000);
  });
}

copyJsonBtn.addEventListener('click', () => {
  navigator.clipboard.writeText(rawJsonContent.textContent);
  copyJsonBtn.textContent = 'Copied!';
  setTimeout(() => copyJsonBtn.textContent = 'Copy JSON', 2000);
});

copyTextBtn.addEventListener('click', () => {
  navigator.clipboard.writeText(rawTextContent.textContent);
  copyTextBtn.textContent = 'Copied!';
  setTimeout(() => copyTextBtn.textContent = 'Copy TXT', 2000);
});

// 14. Batch Result View
function displayBatchResult(batch) {
  placeholderState.style.display = 'none';
  resultContainer.style.display = 'none';
  batchContainer.style.display = 'block';

  batchSummaryStats.textContent = `Processed ${batch.total_documents} files: ${batch.successful} successful, ${batch.failed} failed/missing`;
  downloadBatchCsvBtn.href = batch.summary_csv_url || '#';
  downloadBatchExcelBtn.href = batch.summary_excel_url || '#';

  batchTableBody.innerHTML = '';
  batch.results.forEach(res => {
    const tr = document.createElement('tr');
    const isSuccess = res.status === 'success';
    const conf = res.validation ? `${(res.validation.confidence_score * 100).toFixed(0)}%` : '0%';
    const blocksCount = (res.structured_content && res.structured_content.length) || (res.blocks && res.blocks.length) || 0;
    const tablesCount = res.validation ? res.validation.tables_included_count : 0;
    const pages = res.start_page ? `${res.start_page}–${res.end_page}` : 'N/A';

    tr.innerHTML = `
      <td><strong>${escapeHtml(res.document)}</strong></td>
      <td>
        <span class="badge ${isSuccess ? 'badge-engine' : 'badge-pages'}" style="${!isSuccess ? 'color: var(--danger); border-color: var(--danger);' : ''}">
          ${res.status.toUpperCase()}
        </span>
      </td>
      <td>${res.requested_section}${res.requested_subsection ? ' → ' + res.requested_subsection : ''}</td>
      <td>${pages}</td>
      <td>${conf}</td>
      <td>${blocksCount}</td>
      <td>${tablesCount}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="inspectBatchItem('${escapeHtml(res.document)}')">Inspect</button>
      </td>
    `;
    batchTableBody.appendChild(tr);
  });
}

window.inspectBatchItem = function(docName) {
  if (!state.batchResult) return;
  const item = state.batchResult.results.find(r => r.document === docName);
  if (item) {
    state.activeResult = item;
    displaySingleResult(item);
  }
};

// Helpers
function showLoading(msg) {
  loadingStatusText.textContent = msg;
  loadingOverlay.style.display = 'flex';
}

function hideLoading() {
  loadingOverlay.style.display = 'none';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialize with clean file list on page load (only show files uploaded by user)
window.addEventListener('DOMContentLoaded', () => {
  renderFileList();
});
