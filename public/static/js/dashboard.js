document.addEventListener('DOMContentLoaded', () => {
  const summary = document.getElementById('dashboard-summary');
  const clearButton = document.getElementById('clear-saved-data');
  const clearStatus = document.getElementById('clear-data-status');

  function getStoredObject(key) {
    const value = window.appStorage.getJSON(key, null);
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  }

  function getScore(value) {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100
      ? value
      : null;
  }

  function createMetricCard(title, value, detail, score = null) {
    const card = document.createElement('article');
    card.className = 'result-card dashboard-metric';

    const heading = document.createElement('h3');
    heading.textContent = title;
    const metricValue = document.createElement('strong');
    metricValue.className = score === null ? 'score-value metric-placeholder' : 'score-value';
    metricValue.textContent = value;
    card.append(heading, metricValue);

    if (score !== null) {
      const progress = document.createElement('div');
      progress.className = 'progress-bar';
      progress.setAttribute('aria-label', `${title}: ${score}%`);
      const fill = document.createElement('span');
      fill.className = 'progress-fill';
      fill.style.width = `${score}%`;
      progress.appendChild(fill);
      card.appendChild(progress);
    }

    if (detail) {
      const description = document.createElement('p');
      description.textContent = detail;
      card.appendChild(description);
    }
    return card;
  }

  function getRoadmapMetric(career, progress) {
    const roadmap = career?.success === true ? career.roadmap : null;
    if (!Array.isArray(roadmap) || !roadmap.length || roadmap.some(item => (
      !item || typeof item !== 'object' || item.day === undefined || item.day === null
    ))) {
      return { value: 'Start a career plan', detail: 'Create a plan to track your learning progress.' };
    }

    const completed = roadmap.filter(item => progress[`roadmap_${item.day}`] === true).length;
    const percent = Math.round((completed / roadmap.length) * 100);
    return {
      value: `${percent}%`,
      detail: `${completed} of ${roadmap.length} roadmap steps completed.`,
      score: percent,
    };
  }

  function getPracticeDate(value) {
    if (typeof value !== 'string') return 'Not recorded';
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return 'Not recorded';
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(timestamp));
  }

  function renderDashboard() {
    if (!summary) return;
    const career = getStoredObject('careerGuideResults');
    const resume = getStoredObject('resumeAnalysisResults');
    const jobMatch = getStoredObject('jobDescriptionResults');
    const interview = getStoredObject('interviewReport');
    const progress = getStoredObject('roadmapProgress') || {};

    const careerScore = career?.success === true ? getScore(career.readiness_score) : null;
    const atsScore = resume?.success === true ? getScore(resume.ats_score) : null;
    const matchScore = jobMatch?.success === true ? getScore(jobMatch.match_score) : null;
    const interviewScore = getScore(interview?.overall_score);
    const roadmap = getRoadmapMetric(career, progress);

    summary.replaceChildren(
      createMetricCard(
        'Career Readiness',
        careerScore === null ? 'Start a career plan' : `${careerScore}/100`,
        careerScore === null ? 'Your plan results will appear here.' : 'AI-provided readiness estimate from your saved career plan; not a validated hiring prediction.',
        careerScore,
      ),
      createMetricCard(
        'ATS Compatibility Estimate',
        atsScore === null ? 'Not analyzed yet' : `${atsScore}/100`,
        atsScore === null ? 'Analyze a resume to see your result.' : 'Rule-based estimate using role keywords and fixed category baselines.',
        atsScore,
      ),
      createMetricCard(
        'JD Keyword Estimate',
        matchScore === null ? 'No match yet' : `${matchScore}/100`,
        matchScore === null ? 'Analyze a job description to see your result.' : 'Rule-based role-keyword estimate; a structured resume match is shown separately when resume text was supplied.',
        matchScore,
      ),
      createMetricCard('Roadmap Progress', roadmap.value, roadmap.detail, roadmap.score ?? null),
      createMetricCard(
        'Interview Score',
        interviewScore === null ? 'Complete an interview' : `${interviewScore}/100`,
        interviewScore === null
          ? 'Your result will appear after an interview.'
          : `Calculated score from AI evaluation outputs and locally derived category estimates. Last practice: ${getPracticeDate(interview.last_practice)}`,
        interviewScore,
      ),
    );
  }

  renderDashboard();

  clearButton?.addEventListener('click', () => {
    if (!window.confirm('Clear saved application data from this browser? This removes saved career, resume, job match, interview results, and roadmap progress.')) {
      return;
    }

    const keys = [
      'careerGuideResults',
      'resumeAnalysisResults',
      'jobDescriptionResults',
      'interviewState',
      'interviewReport',
      'roadmapProgress',
      'roadmapCompleted',
    ];
    if (clearStatus) {
      clearStatus.hidden = false;
      clearStatus.textContent = window.appStorage.removeKeys(keys)
        ? 'Saved application data has been cleared from this browser.'
        : 'Browser storage is unavailable; some saved application data could not be cleared.';
    } else {
      window.appStorage.removeKeys(keys);
    }
    renderDashboard();
  });
});
