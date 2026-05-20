/* ═══════════════════════════════════════════════════════════════════
   app.js — JobHunt AI Frontend Logic
   ═══════════════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────────────────────────
let currentMode = 'resume';
let allJobs = [];
let currentJobId = null;
let eventSource = null;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initDropZone();
  initLocationCards();
  initBoardChips();
  initGoogleAuthBtn();
});

// ── Mode switch ───────────────────────────────────────────────────────────────
function switchMode(mode) {
  currentMode = mode;
  document.getElementById('btn-resume').classList.toggle('active', mode === 'resume');
  document.getElementById('btn-manual').classList.toggle('active', mode === 'manual');
  document.getElementById('pane-resume').classList.toggle('hidden', mode !== 'resume');
  document.getElementById('pane-manual').classList.toggle('hidden', mode !== 'manual');
}

// ── Drop zone ─────────────────────────────────────────────────────────────────
function initDropZone() {
  const zone  = document.getElementById('drop-zone');
  const input = document.getElementById('resume-input');

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelected(file, input);
  });
  input.addEventListener('change', () => {
    if (input.files[0]) handleFileSelected(input.files[0], input);
  });
}

function handleFileSelected(file, input) {
  if (!file.name.endsWith('.pdf')) {
    showToast('Please upload a PDF file.', 'warn');
    return;
  }
  // Sync to input for form submission
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;

  const nameEl = document.getElementById('file-name');
  nameEl.textContent = `✅  ${file.name}  (${(file.size / 1024).toFixed(0)} KB)`;
  nameEl.classList.remove('hidden');

  const dropText = document.querySelector('.drop-text');
  if (dropText) dropText.innerHTML = 'Resume loaded — ready to search!';
}

// ── Location cards ────────────────────────────────────────────────────────────
function initLocationCards() {
  document.querySelectorAll('.loc-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.loc-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const val = card.querySelector('input[type="radio"]').value;
      document.getElementById('custom-city-wrap').classList.toggle('hidden', val !== 'outside_india');
    });
  });
}

// ── Board chips ───────────────────────────────────────────────────────────────
function initBoardChips() {
  document.querySelectorAll('.board-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      chip.classList.toggle('active');
      chip.querySelector('input[type="checkbox"]').checked = chip.classList.contains('active');
    });
  });
}

// ── Google Auth ───────────────────────────────────────────────────────────────
function initGoogleAuthBtn() {
  const btn = document.getElementById('connect-google-btn');
  if (!btn) return;
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    btn.textContent = 'Connecting…';
    try {
      const res = await fetch('/auth/google');
      const data = await res.json();
      if (data.ok) {
        showToast('Google Sheets connected! ✅', 'success');
        document.getElementById('auth-badge').innerHTML =
          '<span class="dot dot-green"></span> Google Sheets Connected';
        document.getElementById('auth-badge').classList.remove('auth-warn');
      } else {
        showToast('Auth failed: ' + data.message, 'warn');
        btn.textContent = 'Connect Google Sheets';
      }
    } catch {
      showToast('Could not connect to Google.', 'warn');
      btn.textContent = 'Connect Google Sheets';
    }
  });
}

// ── Start Search ──────────────────────────────────────────────────────────────
async function startSearch() {
  // Validate
  if (currentMode === 'resume') {
    const input = document.getElementById('resume-input');
    if (!input.files || !input.files[0]) {
      showToast('Please upload a PDF resume first.', 'warn');
      return;
    }
  } else {
    const role   = document.getElementById('role-input').value.trim();
    const skills = document.getElementById('skills-input').value.trim();
    if (!role && !skills) {
      showToast('Please enter a role or skills.', 'warn');
      return;
    }
  }

  // Cancel any existing SSE
  if (eventSource) { eventSource.close(); eventSource = null; }

  // Build form data
  const fd = new FormData();

  if (currentMode === 'resume') {
    fd.append('resume', document.getElementById('resume-input').files[0]);
  } else {
    fd.append('role',   document.getElementById('role-input').value.trim());
    fd.append('skills', document.getElementById('skills-input').value.trim());
  }

  const locCard = document.querySelector('.loc-card.active input[type="radio"]');
  fd.append('location', locCard ? locCard.value : 'chennai');
  fd.append('custom_city', document.getElementById('custom-city').value.trim() || 'Singapore');

  const naukriActive = document.getElementById('chip-naukri').classList.contains('active');
  fd.append('naukri', naukriActive ? 'true' : 'false');

  // UI: show progress, hide results
  setUISearching(true);
  showProgress(0, 'Starting job search…');

  try {
    const res  = await fetch('/search', { method: 'POST', body: fd });
    const data = await res.json();
    if (!data.job_id) throw new Error('No job_id returned from server');
    currentJobId = data.job_id;
    listenSSE(currentJobId);
  } catch (err) {
    showToast('Search failed: ' + err.message, 'error');
    setUISearching(false);
  }
}

// ── SSE listener ──────────────────────────────────────────────────────────────
function listenSSE(jobId) {
  eventSource = new EventSource(`/stream/${jobId}`);

  eventSource.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    showProgress(d.percent, d.message);
  });

  eventSource.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    eventSource.close();
    eventSource = null;
    setUISearching(false);
    renderResults(d.jobs, d.sheets_url);
  });

  eventSource.addEventListener('error', e => {
    let msg = 'An error occurred during search.';
    try { msg = JSON.parse(e.data).message; } catch {}
    showToast(msg, 'error');
    eventSource.close();
    eventSource = null;
    setUISearching(false);
    showProgress(0, '');
    document.getElementById('progress-card').classList.add('hidden');
  });

  eventSource.onerror = () => {
    if (eventSource.readyState === EventSource.CLOSED) return;
    showToast('Connection to server lost.', 'error');
    eventSource.close();
    setUISearching(false);
  };
}

// ── Progress ──────────────────────────────────────────────────────────────────
function showProgress(pct, msg) {
  const card = document.getElementById('progress-card');
  card.classList.remove('hidden');
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-pct').textContent = pct + '%';
  if (msg) document.getElementById('progress-msg').textContent = msg;
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(jobs, sheetsUrl) {
  allJobs = jobs || [];
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('progress-card').classList.add('hidden');

  // Sheets card
  if (sheetsUrl) {
    document.getElementById('sheets-link').href = sheetsUrl;
    document.getElementById('sheets-count').textContent = `${allJobs.length} jobs synced`;
    document.getElementById('sheets-card').classList.remove('hidden');
  }

  if (!allJobs.length) {
    showToast('No jobs found matching your criteria. Try broadening your search.', 'warn');
    return;
  }

  // Results card
  document.getElementById('results-meta').textContent = `${allJobs.length} jobs found`;
  document.getElementById('results-card').classList.remove('hidden');
  renderTable(allJobs);
}

function renderTable(jobs) {
  const tbody = document.getElementById('jobs-tbody');
  tbody.innerHTML = '';
  jobs.forEach((job, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${scoreBadge(job.score, job.grade)}</td>
      <td title="${esc(job.title)}" style="max-width:180px">${esc(job.title)}</td>
      <td title="${esc(job.company)}">${esc(job.company)}</td>
      <td title="${esc(job.location)}">${esc(job.location)}</td>
      <td>${esc(job.salary) || '<span class="apply-na">N/A</span>'}</td>
      <td>${sourceTag(job.source)}</td>
      <td style="color:var(--text-dim);font-size:12px">${esc(job.date_posted)}</td>
      <td>${applyBtn(job.job_url)}</td>
    `;
    // Click row to show JD
    tr.addEventListener('click', (e) => {
      if (e.target.closest('a')) return; // don't hijack apply link
      showJD(job);
    });
    tbody.appendChild(tr);
  });
}

// ── Filter ────────────────────────────────────────────────────────────────────
function filterTable() {
  const q = document.getElementById('filter-input').value.toLowerCase();
  const filtered = allJobs.filter(j =>
    (j.title + j.company + j.location + j.source).toLowerCase().includes(q)
  );
  renderTable(filtered);
  document.getElementById('results-meta').textContent = `${filtered.length} of ${allJobs.length} jobs`;
}

// ── JD Drawer ─────────────────────────────────────────────────────────────────
function showJD(job) {
  const drawer = document.getElementById('jd-drawer');
  document.getElementById('jd-title').textContent = `${job.title} — ${job.company}`;
  document.getElementById('jd-body').textContent  = job.description
    ? job.description + (job.description.length >= 400 ? '…' : '')
    : 'No description available for this listing.';
  drawer.classList.remove('hidden');
  drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function closeJD() {
  document.getElementById('jd-drawer').classList.add('hidden');
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function setUISearching(searching) {
  const btn   = document.getElementById('search-btn');
  const label = document.getElementById('btn-label');
  btn.disabled = searching;
  label.textContent = searching ? '⏳ Searching…' : '🚀 Search Jobs Now';
}

function scoreBadge(score, grade) {
  const cls = { 'A+': 'score-ap', 'A': 'score-a', 'B': 'score-b', 'C': 'score-c', 'D': 'score-d' }[grade] || 'score-d';
  return `<span class="score-badge ${cls}">${score}</span>`;
}

function sourceTag(src) {
  const srcLower = (src || '').toLowerCase();
  const cls = {
    linkedin: 'src-linkedin', indeed: 'src-indeed',
    glassdoor: 'src-glassdoor', google: 'src-google', naukri: 'src-naukri',
  }[srcLower] || 'src-default';
  return `<span class="source-tag ${cls}">${esc(src)}</span>`;
}

function applyBtn(url) {
  if (url && url.startsWith('http')) {
    return `<a class="apply-btn" href="${esc(url)}" target="_blank" rel="noopener">Apply →</a>`;
  }
  return `<span class="apply-na">—</span>`;
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const existing = document.getElementById('toast-container');
  if (existing) existing.remove();

  const colors = {
    success: '#22c55e', warn: '#f59e0b', error: '#ef4444', info: '#6c63ff'
  };
  const container = document.createElement('div');
  container.id = 'toast-container';
  container.style.cssText = `
    position: fixed; bottom: 28px; right: 28px; z-index: 9999;
    background: rgba(20,20,45,0.95); color: #e2e8f0;
    border: 1px solid ${colors[type] || colors.info}55;
    border-left: 3px solid ${colors[type] || colors.info};
    padding: 14px 20px; border-radius: 10px;
    font-family: Inter, sans-serif; font-size: 14px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    max-width: 380px; line-height: 1.5;
    animation: slideInToast 0.3s ease;
  `;
  container.textContent = message;

  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideInToast {
      from { opacity:0; transform: translateY(12px); }
      to   { opacity:1; transform: translateY(0); }
    }
  `;
  document.head.appendChild(style);
  document.body.appendChild(container);
  setTimeout(() => container.remove(), 5000);
}
