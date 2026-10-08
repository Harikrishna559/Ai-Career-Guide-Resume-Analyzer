document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('job-description-form');
  if (form) {
    const submitButton = form.querySelector('button[type="submit"]');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const errorBox = document.getElementById('jd-error');
      const loadingBox = document.getElementById('jd-loading');
      const targetRole = document.getElementById('jd-target-role')?.value?.trim();
      const jobDescription = document.getElementById('job-description')?.value?.trim();
      const resumeText = document.getElementById('resume-text')?.value?.trim();

      if (!targetRole || !jobDescription) {
        if (errorBox) {
          errorBox.hidden = false;
          errorBox.textContent = 'Please provide both a target role and a job description.';
          errorBox.className = 'form-message error';
        }
        return;
      }

      if (loadingBox) {
        loadingBox.hidden = false;
      }
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Comparing...';
      }

      try {
        const response = await fetch('/api/analyze-job-description', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_role: targetRole,
            job_description: jobDescription,
            resume_text: resumeText || '',
          }),
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data?.error?.message || 'Unable to compare against the job description.');
        }
        if (!window.appStorage.setItem('jobDescriptionResults', JSON.stringify(data))) {
          throw new Error('Browser storage is unavailable. Enable storage to view your job match.');
        }
        window.location.href = '/job-description-result';
      } catch (error) {
        if (errorBox) {
          errorBox.hidden = false;
          errorBox.textContent = error.message || 'Unable to compare against the job description.';
          errorBox.className = 'form-message error';
        }
      } finally {
        if (loadingBox) {
          loadingBox.hidden = true;
        }
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = 'Analyze Job Match';
        }
      }
    });
  }

  const resultContainer = document.getElementById('jd-results');
  if (resultContainer) {
    const data = window.appStorage.getJSON('jobDescriptionResults', {});
    const roleKeywordScore = typeof data.match_score === 'number'
      && Number.isFinite(data.match_score)
      && data.match_score >= 0
      && data.match_score <= 100
      ? data.match_score
      : null;
    const scoreCard = `
      <article class="result-card score-card">
        <h3>Role Keyword Estimate</h3>
        <div class="score-value">${roleKeywordScore === null ? 'Not calculated' : `${escapeHtml(roleKeywordScore)}/100`}</div>
        <p>Rule-based estimate from role-catalog keywords and the supplied resume text; it is not AI-generated. This is not a structured resume match. ${data.match_result ? 'The structured resume-to-JD result is shown separately below.' : 'No resume text was supplied, so this score does not represent a resume match.'}</p>
        <p>${escapeHtml(data.job_summary || 'Role keyword summary is unavailable.')}</p>
      </article>
    `;
    const matched = (data.matched_skills || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const missing = (data.missing_skills || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const keywords = (data.missing_keywords || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const learning = (data.learning_plan || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const resumeImprovements = (data.resume_improvements || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    const interview = (data.interview_topics || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');

    const match = data.match_result;
    const dimensionLabels = {
      skill_match: 'Skill match',
      experience_match: 'Experience match',
      education_match: 'Education match',
      keyword_match: 'Keyword match',
    };
    const dimensions = match && Object.entries(dimensionLabels).map(([key, label]) => {
      const value = match[key];
      const displayValue = typeof value === 'number' && Number.isFinite(value)
        ? `${escapeHtml(value)}/100`
        : 'Not assessed (insufficient evidence)';
      return `<li><strong>${label}:</strong> ${displayValue}</li>`;
    }).join('');
    const weights = match && match.score_method && match.score_method.weights
      ? Object.entries(match.score_method.weights)
        .map(([key, value]) => {
          const label = dimensionLabels[key] || key;
          return `<li><strong>${label}:</strong> ${escapeHtml(Math.round(value * 10000) / 100)}%</li>`;
        })
        .join('')
      : '';
    const structuredMatch = match ? `
      <article class="result-card">
        <h3>Structured Resume ↔ JD Match (Rule-Based)</h3>
        <p>Deterministic match based on extracted resume and job-description profile evidence. Required skills contribute 80% and preferred skills 20% of the skill dimension when both groups are present. Unavailable evidence is left unassessed; available dimensions are reweighted in the overall estimate.</p>
        <p><strong>Overall match estimate:</strong> ${typeof match.overall_match === 'number' && Number.isFinite(match.overall_match) ? `${escapeHtml(match.overall_match)}/100` : 'Not assessed (insufficient evidence)'}</p>
        <h4>Dimensions</h4><ul class="simple-list">${dimensions}</ul>
        <h4>Weights used for the overall estimate</h4><ul class="simple-list">${weights || '<li>No dimensions had enough evidence to calculate an overall estimate.</li>'}</ul>
        <h4>Matched skills</h4><ul class="simple-list">${(match.matched_skills || []).map(item => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No matching skills identified.</li>'}</ul>
        <h4>Strengths</h4><ul class="simple-list">${(match.strengths || []).map(item => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No strengths identified from available evidence.</li>'}</ul>
        <h4>Missing required skills</h4><ul class="simple-list">${(match.missing_required_skills || []).map(item => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No missing required skills identified.</li>'}</ul>
        <h4>Missing preferred skills</h4><ul class="simple-list">${(match.missing_preferred_skills || []).map(item => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No missing preferred skills identified.</li>'}</ul>
        <h4>Evidence and recommendations</h4><ul class="simple-list">${(match.gaps || []).map(item => `<li>${escapeHtml(item)}</li>`).join('')}${(match.recommendations || []).map(item => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No additional recommendations.</li>'}</ul>
      </article>
    ` : '';

    resultContainer.innerHTML = [
      scoreCard,
      structuredMatch,
      `<article class="result-card"><h3>Role Keywords Found in Both JD and Resume</h3><ul class="simple-list">${matched || '<li>No role keywords found in both texts.</li>'}</ul></article>`,
      `<article class="result-card"><h3>Role Keywords Not Found in Resume Text</h3><ul class="simple-list">${missing || '<li>No role keyword gaps detected.</li>'}</ul></article>`,
      `<article class="result-card"><h3>Role Keywords Not Found in JD</h3><ul class="simple-list">${keywords || '<li>No role keywords missing from the JD.</li>'}</ul></article>`,
      `<article class="result-card"><h3>Learning Plan</h3><ul class="simple-list">${learning || '<li>No learning plan generated.</li>'}</ul></article>`,
      `<article class="result-card"><h3>Resume Improvements</h3><ul class="simple-list">${resumeImprovements || '<li>No improvement suggestions.</li>'}</ul></article>`,
      `<article class="result-card"><h3>Interview Topics</h3><ul class="simple-list">${interview || '<li>No interview topics generated.</li>'}</ul></article>`,
    ].join('');

    document.getElementById('copy-jd-match')?.addEventListener('click', () => {
      const text = `Rule-based role keyword estimate: ${roleKeywordScore === null ? 'Not calculated' : `${roleKeywordScore}/100`}\n${data.job_summary || ''}`;
      navigator.clipboard.writeText(text).catch(() => alert('Copy failed.'));
    });

    document.getElementById('download-jd-report')?.addEventListener('click', () => {
      const payload = {
        title: `Job Match Report: ${data.target_role || 'Role'}`,
        report_type: 'job-description',
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
        link.download = 'job-description-report.pdf';
        link.click();
        URL.revokeObjectURL(url);
      }).catch((error) => alert(error.message || 'Report failed to export.'));
    });
  }
});

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
