window.appStorage = {
  getItem(key, fallback = null) {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : value;
    } catch {
      return fallback;
    }
  },
  getJSON(key, fallback = {}) {
    try {
      const value = this.getItem(key);
      return value === null ? fallback : JSON.parse(value);
    } catch {
      return fallback;
    }
  },
  setItem(key, value) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch {
      return false;
    }
  },
  removeKeys(keys) {
    let removed = true;
    keys.forEach((key) => {
      try {
        localStorage.removeItem(key);
      } catch {
        removed = false;
      }
    });
    return removed;
  },
};

window.readPdfResponse = async (response, fallbackMessage) => {
  if (!response.ok) {
    let errorData = null;
    try {
      errorData = await response.json();
    } catch {
      errorData = null;
    }
    const message = errorData?.error?.message;
    throw new Error(typeof message === 'string' && message ? message : fallbackMessage);
  }

  const contentType = (response.headers.get('content-type') || '')
    .split(';', 1)[0]
    .trim()
    .toLowerCase();
  if (contentType !== 'application/pdf') {
    throw new Error('The server returned an invalid report file.');
  }
  return response.blob();
};

document.addEventListener('DOMContentLoaded', () => {
  const menuToggle = document.getElementById('mobile-menu-toggle');
  const navigationPanel = document.getElementById('navigation-panel');

  if (menuToggle && navigationPanel) {
    const setMenuOpen = (open) => {
      menuToggle.setAttribute('aria-expanded', String(open));
      menuToggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
      navigationPanel.classList.toggle('is-open', open);
    };

    menuToggle.hidden = false;
    menuToggle.addEventListener('click', () => {
      setMenuOpen(menuToggle.getAttribute('aria-expanded') !== 'true');
    });
    navigationPanel.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => setMenuOpen(false));
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menuToggle.getAttribute('aria-expanded') === 'true') {
        setMenuOpen(false);
        menuToggle.focus();
      }
    });
    document.addEventListener('click', (event) => {
      if (
        menuToggle.getAttribute('aria-expanded') === 'true'
        && !navigationPanel.contains(event.target)
        && !menuToggle.contains(event.target)
      ) {
        setMenuOpen(false);
      }
    });
  }

  const cached = window.appStorage.getJSON('careerGuideResults', null);
  if (cached && window.location.pathname === '/career-result') {
    const data = cached;
    renderCareerResult(data);
  }

  const resumeCached = window.appStorage.getJSON('resumeAnalysisResults', null);
  if (resumeCached && typeof resumeCached === 'object') {
    delete resumeCached.resume_text;
    delete resumeCached.parsed_details;
    window.appStorage.setItem('resumeAnalysisResults', JSON.stringify(resumeCached));
  }
  if (resumeCached && window.location.pathname === '/resume-result') {
    renderResumeResult(resumeCached);
  }

  const interviewState = window.appStorage.getJSON('interviewState', null);
  if (interviewState && Array.isArray(interviewState.results)) {
    interviewState.results = interviewState.results
      .filter(result => result && typeof result === 'object' && !Array.isArray(result))
      .map(({ answer, ...result }) => result);
    interviewState.report = null;
    window.appStorage.setItem('interviewState', JSON.stringify(interviewState));
  }
});

function showMessage(element, message, type = 'error') {
  if (!element) return;
  element.hidden = false;
  element.textContent = message;
  element.className = 'form-message ' + type;
}

function hideMessage(element) {
  if (!element) return;
  element.hidden = true;
  element.textContent = '';
}

function setLoading(element, visible) {
  if (!element) return;
  element.hidden = !visible;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function generateRoadmapText(data) {
  const summary = data.career_summary || 'Career roadmap';
  const roadmap = (data.roadmap || []).map(item => `Day ${item.day}: ${item.topic} - ${item.learning} (${item.time})`).join('\n');
  return `${summary}\n\n${roadmap}`;
}

function getLocalSaved(key) {
  return window.appStorage.getJSON(key, []);
}

function renderCareerResult(data) {
  const container = document.getElementById('results-content');
  if (!container) return;

  const roadmap = data.roadmap || [];
  const readinessScore = typeof data.readiness_score === 'number'
    && Number.isFinite(data.readiness_score)
    && data.readiness_score >= 0
    && data.readiness_score <= 100
    ? data.readiness_score
    : null;
  const skills = (data.current_skills || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const gaps = (data.skill_gaps || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const resources = (data.resources || []).map(item => `<li><strong>${escapeHtml(item.type)}</strong> - ${escapeHtml(item.title)} (${escapeHtml(item.url || 'Official resource')})</li>`).join('');
  const projects = (data.projects || []).map(item => `<li><strong>${escapeHtml(item.name)}</strong> - ${escapeHtml(item.difficulty)} - ${escapeHtml(item.technologies || '')}</li>`).join('');
  const interview = (data.interview_topics || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const nextSteps = (data.next_steps || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const roadmapList = roadmap.map((item) => {
    const key = `roadmap_${item.day}`;
    const progress = window.appStorage.getJSON('roadmapProgress', {});
    const checked = progress[key] ? 'checked' : '';
    return `<li class="roadmap-item"><label><input type="checkbox" data-roadmap-day="${escapeHtml(item.day)}" ${checked} /> <strong>Day ${escapeHtml(item.day)}</strong>: ${escapeHtml(item.topic)} - ${escapeHtml(item.learning)} (${escapeHtml(item.time)})</label></li>`;
  }).join('');

  const items = [
    `<article class="result-card score-card"><h3>Career Snapshot</h3><div class="score-value">${readinessScore === null ? 'Not provided' : `${escapeHtml(readinessScore)}/100`}</div><p>${escapeHtml(data.career_summary || '')}</p><p>Readiness is an AI-generated estimate, not a validated placement or hiring prediction.</p></article>`,
    `<article class="result-card"><h3>AI-Estimated Career Readiness</h3>${readinessScore === null ? '<p>No readiness estimate was provided.</p>' : `<div class="progress-bar"><span class="progress-fill" style="width:${readinessScore}%"></span></div><p>${escapeHtml(readinessScore)}/100. This estimate is generated by the AI model from your submitted profile; it is not independently validated.</p>`}</article>`,
    `<article class="result-card"><h3>Current Skills</h3><ul class="skill-list">${skills || '<li>Not provided</li>'}</ul></article>`,
    `<article class="result-card"><h3>Skill Gaps</h3><ul class="skill-list">${gaps || '<li>No major gaps identified</li>'}</ul></article>`,
    `<article class="result-card"><h3>30-Day Roadmap</h3><ul class="roadmap-list">${roadmapList || '<li>No roadmap available</li>'}</ul></article>`,
    `<article class="result-card"><h3>Learning Resources</h3><ul class="resource-list">${resources || '<li>No resources generated</li>'}</ul></article>`,
    `<article class="result-card"><h3>Projects</h3><ul class="skill-list">${projects || '<li>No projects recommended</li>'}</ul></article>`,
    `<article class="result-card"><h3>Interview Preparation</h3><ul class="simple-list">${interview || '<li>No interview prep available</li>'}</ul></article>`,
    `<article class="result-card"><h3>Next Steps</h3><ul class="simple-list">${nextSteps || '<li>No next steps generated</li>'}</ul></article>`
  ];

  container.innerHTML = items.join('');
  updateRoadmapProgress(data);

  document.querySelectorAll('[data-roadmap-day]').forEach((box) => {
    box.addEventListener('change', () => {
      const progress = window.appStorage.getJSON('roadmapProgress', {});
      progress[`roadmap_${box.dataset.roadmapDay}`] = box.checked;
      window.appStorage.setItem('roadmapProgress', JSON.stringify(progress));
      window.appStorage.setItem('roadmapCompleted', String(Object.values(progress).filter(Boolean).length));
      updateRoadmapProgress(data);
    });
  });

  document.getElementById('copy-plan')?.addEventListener('click', () => {
    navigator.clipboard.writeText(generateRoadmapText(data)).catch(() => alert('Copy failed.'));
  });

  document.getElementById('download-plan')?.addEventListener('click', () => {
    const blob = new Blob([generateRoadmapText(data)], { type: 'text/plain' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'career-roadmap.txt';
    link.click();
    URL.revokeObjectURL(link.href);
  });
}

function updateRoadmapProgress(data) {
  const roadmap = Array.isArray(data.roadmap) ? data.roadmap : [];
  const trackableDays = roadmap.filter(item => item && item.day !== undefined && item.day !== null);
  const stored = window.appStorage.getJSON('roadmapProgress', {});
  const progress = stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {};
  const completed = trackableDays.filter(item => progress[`roadmap_${item.day}`] === true).length;
  const total = trackableDays.length;
  const percent = total ? Math.round((completed / total) * 100) : null;
  const summary = document.createElement('div');
  summary.className = 'result-card progress-tracker';
  summary.innerHTML = percent === null
    ? '<h3>Progress Tracking</h3><p>Progress is unavailable because this plan has no trackable roadmap days.</p>'
    : `<h3>Progress Tracking</h3><p>${completed} of ${total} roadmap steps completed.</p><div class="progress-bar"><span class="progress-fill" style="width:${percent}%"></span></div><p>${percent}% of this roadmap completed</p>`;

  const container = document.getElementById('results-content');
  if (container) {
    const existing = container.querySelector('.progress-tracker');
    if (existing) existing.remove();
    container.appendChild(summary);
  }
}

function renderResumeResult(data) {
  const container = document.getElementById('resume-results');
  if (!container) return;

  const atsScore = typeof data.ats_score === 'number'
    && Number.isFinite(data.ats_score)
    && data.ats_score >= 0
    && data.ats_score <= 100
    ? data.ats_score
    : null;
  const scoreBreakdown = data.score_breakdown || {};
  const scoreHtml = Object.entries(scoreBreakdown).map(([key, value]) => `<div><strong>${escapeHtml(key)}</strong><div>${escapeHtml(value)}%</div></div>`).join('');
  const stronger = (data.strong_keywords || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const missing = (data.missing_keywords || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const priorities = (data.priority_keywords || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const suggestions = (data.resume_strengths || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const skills = (data.missing_skills || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const certifications = (data.certifications || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const projects = (data.projects_to_add || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const sections = (data.sections_to_improve || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const portals = (data.job_portals || []).map(item => `<li><strong>${escapeHtml(item.portal_name)}</strong> - ${escapeHtml(item.why)} - <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Open</a></li>`).join('');
  const jobSearches = (data.recommended_searches || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const health = Object.entries(data.resume_health || {}).map(([key, value]) => `<li><strong>${escapeHtml(key.replace(/_/g, ' '))}</strong>: ${escapeHtml(value)}</li>`).join('');
  const summary = data.professional_summary || 'Professional summary not available.';
  const summaryVersions = data.summary_versions || {};
  const versionsHtml = Object.entries(summaryVersions)
    .map(([key, value]) => `<article class="result-card"><h3>${escapeHtml(key.replace(/_/g, ' '))}</h3><p>${escapeHtml(value || '')}</p></article>`)
    .join('');

  const items = [
    `<article class="result-card score-card"><h3>ATS Compatibility Score</h3><div class="score-value">${atsScore === null ? 'Not calculated' : `${escapeHtml(atsScore)}/100`}</div><p>Rule-based ATS compatibility estimate, not AI-generated or an official score from a specific company ATS. Keyword Match, Skills Match, and Job Role Relevance vary with role keywords; structure, experience, projects, certifications, education, and formatting use fixed baseline values.</p><div class="score-breakdown">${scoreHtml}</div></article>`,
    `<article class="result-card"><h3>Resume Strengths</h3><ul class="simple-list">${suggestions || '<li>No strengths detected</li>'}</ul></article>`,
    `<article class="result-card"><h3>Missing Skills</h3><ul class="simple-list">${skills || '<li>No major missing skills detected</li>'}</ul></article>`,
    `<article class="result-card"><h3>Missing Keywords</h3><ul class="simple-list">${missing || '<li>No missing keywords</li>'}</ul></article>`,
    `<article class="result-card"><h3>Strong Keywords</h3><ul class="simple-list">${stronger || '<li>No strong keywords found</li>'}</ul></article>`,
    `<article class="result-card"><h3>Priority Keywords</h3><ul class="simple-list">${priorities || '<li>No priority keywords</li>'}</ul></article>`,
    `<article class="result-card"><h3>Certifications</h3><ul class="simple-list">${certifications || '<li>No certifications suggested</li>'}</ul></article>`,
    `<article class="result-card"><h3>Projects to Consider</h3><ul class="simple-list">${projects || '<li>No project recommendations</li>'}</ul></article>`,
    `<article class="result-card"><h3>Resume Sections to Improve</h3><ul class="simple-list">${sections || '<li>No improvement suggestions</li>'}</ul></article>`,
    `<article class="result-card"><h3>Professional Summary</h3><p>${escapeHtml(summary)}</p></article>`,
    versionsHtml,
    `<article class="result-card"><h3>Job Portals</h3><ul class="simple-list">${portals || '<li>No portals available</li>'}</ul></article>`,
    `<article class="result-card"><h3>Recommended Job Searches</h3><ul class="simple-list">${jobSearches || '<li>No recommended job searches</li>'}</ul></article>`,
    `<article class="result-card"><h3>Resume Health</h3><ul class="simple-list">${health || '<li>No resume health data</li>'}</ul></article>`
  ];

  container.innerHTML = items.join('');

  document.getElementById('copy-suggestions')?.addEventListener('click', () => {
    const text = [
      `Rule-based ATS Compatibility Score: ${atsScore === null ? 'Not calculated' : `${atsScore}/100`}`,
      ...(data.missing_skills || []).map(skill => `Missing Skill: ${skill}`),
      ...(data.missing_keywords || []).map(keyword => `Missing Keyword: ${keyword}`),
    ].join('\n');
    navigator.clipboard.writeText(text).catch(() => alert('Copy failed.'));
  });

  document.getElementById('download-analysis')?.addEventListener('click', () => {
    const payload = {
      title: `Resume Analysis: ${data.target_role || 'Target Role'}`,
      report_type: 'resume',
      payload: data,
    };
    fetch('/api/export-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((response) => window.readPdfResponse(response, 'Report failed to export.')).then((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'resume-analysis-report.pdf';
      link.click();
      URL.revokeObjectURL(url);
    }).catch((error) => alert(error.message || 'Report failed to export.'));
  });
}
