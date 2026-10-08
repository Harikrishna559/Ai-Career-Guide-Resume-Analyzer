document.addEventListener('DOMContentLoaded', () => {
  const setupForm = document.getElementById('interview-setup-form');
  const setupSection = document.getElementById('interview-setup');
  const interviewStage = document.getElementById('interview-stage');
  const interviewResult = document.getElementById('interview-result');
  const interviewFinal = document.getElementById('interview-final');
  const errorBox = document.getElementById('interview-error');
  const answerErrorBox = document.getElementById('interview-answer-error');
  const finalReportLoading = document.getElementById('final-report-loading');
  const finalReportError = document.getElementById('final-report-error');
  const retryFinalReportButton = document.getElementById('retry-final-report');
  const downloadInterviewReportButton = document.getElementById('download-interview-report');
  const startConsent = document.getElementById('interview-start-ai-consent');
  const startConsentError = document.getElementById('interview-start-ai-consent-error');
  const answerConsent = document.getElementById('interview-answer-ai-consent');
  const answerConsentError = document.getElementById('interview-answer-ai-consent-error');
  const loadingBox = document.getElementById('interview-loading');
  const targetRoleSelect = document.getElementById('target-role-select');
  const customRoleField = document.getElementById('custom-role-field');
  const answerBox = document.getElementById('answer-box');
  const progressLabel = document.getElementById('progress-label');
  const progressFill = document.getElementById('progress-fill');
  const questionText = document.getElementById('question-text');
  const questionCategory = document.getElementById('question-category');
  const voiceWarning = document.getElementById('voice-warning');
  const voiceToggle = document.getElementById('voice-toggle');
  const submitAnswerButton = document.getElementById('submit-answer');
  const nextQuestionButton = document.getElementById('next-question');
  const endInterviewButton = document.getElementById('end-interview');
  const skipQuestionButton = document.getElementById('skip-question');
  const retryWeakButton = document.getElementById('retry-weak-questions');

  const speechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let state = {
    questions: [],
    currentIndex: 0,
    results: [],
    config: {},
    report: null,
  };
  let finalReportRequestInProgress = false;
  let downloadRequestInProgress = false;

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

  function renderTextList(container, items, fallbackText) {
    container.replaceChildren();
    const values = Array.isArray(items) && items.length ? items : [fallbackText];
    values.forEach((item) => {
      const listItem = document.createElement('li');
      listItem.textContent = String(item);
      container.appendChild(listItem);
    });
  }

  function appendTextElement(container, tagName, text) {
    const element = document.createElement(tagName);
    element.textContent = String(text);
    container.appendChild(element);
    return element;
  }

  function setCustomRoleVisibility() {
    if (!customRoleField || !targetRoleSelect) return;
    const isCustom = targetRoleSelect.value === 'Custom Role';
    customRoleField.hidden = !isCustom;
    const input = customRoleField.querySelector('input');
    if (input) {
      input.required = isCustom;
    }
  }

  targetRoleSelect?.addEventListener('change', setCustomRoleVisibility);
  startConsent?.addEventListener('change', () => {
    if (startConsentError) startConsentError.hidden = true;
  });
  answerConsent?.addEventListener('change', () => {
    if (answerConsentError) answerConsentError.hidden = true;
  });

  function saveState() {
    const savedState = {
      ...state,
      results: state.results.map(({ answer, ...result }) => result),
      report: null,
    };
    window.appStorage.setItem('interviewState', JSON.stringify(savedState));
  }

  function restoreState() {
    const saved = window.appStorage.getJSON('interviewState', null);
    if (saved && Array.isArray(saved.questions) && saved.questions.length) {
      state = saved;
      saveState();
      showStage();
      renderCurrentQuestion();
    }
  }

  function getConfigFromForm() {
    const formData = new FormData(setupForm);
    const targetRole = formData.get('target_role');
    const selectedRole = targetRole === 'Custom Role' ? (formData.get('custom_role') || '').trim() : targetRole;
    return {
      target_role: selectedRole,
      custom_role: formData.get('custom_role') || '',
      experience_level: formData.get('experience_level') || 'Fresher',
      interview_type: formData.get('interview_type') || 'Technical',
      difficulty: formData.get('difficulty') || 'Beginner',
      question_count: Number(formData.get('question_count') || 10),
      job_description: formData.get('job_description') || '',
    };
  }

  async function startInterview(event) {
    event.preventDefault();
    hideMessage(errorBox);
    if (startConsentError) startConsentError.hidden = true;
    const config = getConfigFromForm();
    if (!config.target_role) {
      showMessage(errorBox, 'Please choose a valid target role before starting the interview.');
      return;
    }
    if (!startConsent?.checked) {
      if (startConsentError) startConsentError.hidden = false;
      startConsent?.focus();
      return;
    }

    setLoading(loadingBox, true);
    const submitButton = setupForm.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = 'Starting...';
    }

    try {
      const formData = new FormData(setupForm);
      const payload = {
        target_role: config.target_role,
        custom_role: config.custom_role,
        experience_level: config.experience_level,
        interview_type: config.interview_type,
        difficulty: config.difficulty,
        question_count: config.question_count,
        job_description: config.job_description,
        ai_consent: true,
      };

      const resumeFile = formData.get('resume');
      if (resumeFile && resumeFile.name) {
        const resumeData = new FormData();
        resumeData.append('resume', resumeFile);
        Object.entries(payload).forEach(([key, value]) => {
          if (value !== undefined && value !== null) {
            resumeData.append(key, String(value));
          }
        });

        const response = await fetch('/api/interview/start', {
          method: 'POST',
          body: resumeData,
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data?.error?.message || 'Unable to start the interview.');
        }
        state = {
          questions: data.questions,
          currentIndex: 0,
          results: [],
          config: data.config,
          report: null,
        };
      } else {
        const response = await fetch('/api/interview/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data?.error?.message || 'Unable to start the interview.');
        }
        state = {
          questions: data.questions,
          currentIndex: 0,
          results: [],
          config: data.config,
          report: null,
        };
      }

      saveState();
      showStage();
      renderCurrentQuestion();
    } catch (error) {
      showMessage(errorBox, error.message || 'Unable to start the interview.');
    } finally {
      setLoading(loadingBox, false);
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = 'Start Interview';
      }
    }
  }

  function showStage() {
    if (setupSection) setupSection.classList.add('hidden');
    if (interviewStage) interviewStage.classList.remove('hidden');
    if (interviewResult) interviewResult.classList.add('hidden');
    if (interviewFinal) interviewFinal.classList.add('hidden');
  }

  function renderCurrentQuestion() {
    const question = state.questions[state.currentIndex];
    if (!question) {
      finishInterview();
      return;
    }

    if (!interviewStage) return;
    if (interviewResult) interviewResult.classList.add('hidden');
    interviewStage.classList.remove('hidden');
    const total = state.questions.length || 1;
    const current = state.currentIndex + 1;
    const percentage = Math.max(10, Math.round((current / total) * 100));
    progressLabel.textContent = `Question ${current} of ${total}`;
    progressFill.style.width = `${percentage}%`;
    questionText.textContent = question.question;
    questionCategory.textContent = question.category || 'Technical';
    answerBox.value = '';
    answerBox.focus();
    if (speechRecognition) {
      voiceWarning.classList.add('hidden');
      voiceToggle.disabled = false;
    } else {
      voiceWarning.classList.remove('hidden');
      voiceToggle.disabled = true;
      voiceToggle.textContent = '🎤 Start Recording';
    }
  }

  async function submitAnswer() {
    if (answerConsentError) answerConsentError.hidden = true;
    if (!answerConsent?.checked) {
      if (answerConsentError) answerConsentError.hidden = false;
      answerConsent?.focus();
      return;
    }
    const answer = answerBox.value.trim();
    if (!answer) {
      showMessage(errorBox, 'Please provide an answer before continuing.');
      return;
    }

    if (!state.questions.length) {
      return;
    }
    if (answerErrorBox) hideMessage(answerErrorBox);

    const currentQuestion = state.questions[state.currentIndex];
    const response = await fetch('/api/interview/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: currentQuestion.question,
        answer,
        target_role: state.config.target_role || 'Python Developer',
        experience_level: state.config.experience_level || 'Fresher',
        interview_type: state.config.interview_type || 'Technical',
        difficulty: state.config.difficulty || 'Beginner',
        ai_consent: true,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      showMessage(answerErrorBox, data?.error?.message || 'The answer could not be evaluated.');
      return;
    }

    state.results.push({
      question: currentQuestion.question,
      category: currentQuestion.category,
      answer,
      score: data.evaluation.overall_score,
      evaluation: data.evaluation,
      target_role: state.config.target_role,
    });
    saveState();
    showEvaluation(data.evaluation);
  }

  function showEvaluation(evaluation) {
    const scoreNode = document.getElementById('evaluation-score');
    const technicalNode = document.getElementById('technical-score');
    const communicationNode = document.getElementById('communication-score');
    const completenessNode = document.getElementById('completeness-score');
    const clarityNode = document.getElementById('clarity-score');
    const strengthsList = document.getElementById('strengths-list');
    const improvementsList = document.getElementById('improvements-list');
    const betterAnswerText = document.getElementById('better-answer-text');

    scoreNode.textContent = `${evaluation.overall_score || 0}/100`;
    technicalNode.textContent = `${evaluation.technical_accuracy || 0}/100`;
    communicationNode.textContent = `${evaluation.communication || 0}/100`;
    completenessNode.textContent = `${evaluation.completeness || 0}/100`;
    clarityNode.textContent = `${evaluation.clarity || 0}/100`;
    renderTextList(strengthsList, evaluation.strengths, 'Good effort and clear attempt.');
    renderTextList(improvementsList, evaluation.improvements, 'Improve the answer with a practical example.');
    betterAnswerText.textContent = evaluation.better_answer || 'Use a clearer structure, include a real-world example, and answer the question directly.';

    if (interviewStage) interviewStage.classList.add('hidden');
    if (interviewResult) interviewResult.classList.remove('hidden');
    if (errorBox) hideMessage(errorBox);
  }

  async function finishInterview() {
    if (!state.results.length) {
      showMessage(errorBox, 'Complete and evaluate at least one answer before generating a final report.');
      return;
    }

    const technical = Math.round(state.results.reduce((sum, item) => sum + (item.evaluation.technical_accuracy || 0), 0) / state.results.length);
    const communication = Math.round(state.results.reduce((sum, item) => sum + (item.evaluation.communication || 0), 0) / state.results.length);
    const clarity = Math.round(state.results.reduce((sum, item) => sum + (item.evaluation.clarity || 0), 0) / state.results.length);
    const completeness = Math.round(state.results.reduce((sum, item) => sum + (item.evaluation.completeness || 0), 0) / state.results.length);
    const problemSolving = Math.max(50, Math.round((technical + completeness + clarity) / 3));
    const projectKnowledge = Math.max(50, Math.round((technical + completeness + communication) / 3));
    const hrReadiness = Math.max(50, Math.round((communication + clarity + completeness) / 3));
    const overallScore = Math.round((technical + communication + completeness + clarity + problemSolving + projectKnowledge + hrReadiness) / 7);
    const strengths = Array.from(new Set(state.results.flatMap(item => item.evaluation.strengths || []))).slice(0, 5);
    const weaknesses = Array.from(new Set(state.results.flatMap(item => item.evaluation.improvements || []))).slice(0, 5);
    const weakQuestions = state.results
      .filter(item => item.score < 75)
      .map(item => ({
        question: item.question,
        score: item.score,
        why: item.evaluation.improvements || ['Needs more detail and a clear example.'],
        study_topic: item.category || 'Core interview concepts',
        category: item.category || 'Technical',
        topic: item.category || 'Core interview concepts',
      }));

    const studyPlan = [
      { day: 1, topic: 'Python fundamentals', why: 'Strong basics improve confidence and accuracy.', task: 'Practice 10 concept questions and explain them aloud.' },
      { day: 2, topic: 'OOP', why: 'Helps with technical clarity and structure.', task: 'Explain inheritance, encapsulation, and polymorphism.' },
      { day: 3, topic: 'SQL', why: 'Common interview requirement for data-focused roles.', task: 'Practice joins, filters, and aggregated queries.' },
      { day: 4, topic: 'DSA basics', why: 'Improves problem-solving and reasoning speed.', task: 'Solve 3 arrays or strings questions.' },
      { day: 5, topic: 'Project explanation', why: 'Strong story-telling improves clarity and confidence.', task: 'Prepare a 90-second explanation of your strongest project.' },
      { day: 6, topic: 'HR questions', why: 'Helps with communication and personality fit.', task: 'Practice answers to strengths, motivation, and teamwork questions.' },
      { day: 7, topic: 'Mock interview', why: 'Simulates pressure and identifies final gaps.', task: 'Do one timed mock interview and review weak points.' },
    ];

    const payload = {
      overall_score: overallScore,
      technical,
      communication,
      problem_solving: problemSolving,
      project_knowledge: projectKnowledge,
      hr_readiness: hrReadiness,
      strengths,
      weaknesses,
      weak_questions: weakQuestions,
      study_plan: studyPlan,
      results: state.results.map(item => ({
        question: item.question,
        category: item.category,
        score: item.score,
        evaluation: item.evaluation,
      })),
    };

    await requestFinalReport(payload);
  }

  function showFinalReportError(message, allowRetry = false) {
    if (finalReportError) {
      finalReportError.hidden = false;
      finalReportError.textContent = message;
    }
    if (retryFinalReportButton) retryFinalReportButton.hidden = !allowRetry;
  }

  async function requestFinalReport(payload) {
    if (finalReportRequestInProgress) return;
    finalReportRequestInProgress = true;
    state.report = null;
    if (interviewStage) interviewStage.classList.add('hidden');
    if (interviewResult) interviewResult.classList.add('hidden');
    if (interviewFinal) interviewFinal.classList.remove('hidden');
    if (finalReportError) finalReportError.hidden = true;
    if (retryFinalReportButton) retryFinalReportButton.hidden = true;
    if (downloadInterviewReportButton) downloadInterviewReportButton.disabled = false;
    if (finalReportError) finalReportError.hidden = true;
    if (retryFinalReportButton) retryFinalReportButton.hidden = true;
    if (finalReportLoading) finalReportLoading.hidden = false;
    if (downloadInterviewReportButton) downloadInterviewReportButton.disabled = true;

    try {
      const response = await fetch('/api/interview/final-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok || !data.success || !data.report) {
        showFinalReportError(data?.error?.message || 'Unable to generate the interview report.', true);
        return;
      }

      state.report = data.report;
      window.appStorage.setItem('interviewReport', JSON.stringify({
        overall_score: data.report.overall_score,
        last_practice: new Date().toISOString(),
      }));
      renderFinalReport(data.report);
    } catch {
      showFinalReportError('Unable to generate the interview report. Please try again.', true);
    } finally {
      finalReportRequestInProgress = false;
      if (finalReportLoading) finalReportLoading.hidden = true;
      if (downloadInterviewReportButton) downloadInterviewReportButton.disabled = !state.report;
    }
  }

  async function downloadInterviewReport() {
    if (!state.report || downloadRequestInProgress) return;
    downloadRequestInProgress = true;
    if (downloadInterviewReportButton) {
      downloadInterviewReportButton.disabled = true;
      downloadInterviewReportButton.textContent = 'Preparing PDF...';
    }
    if (finalReportError) finalReportError.hidden = true;

    try {
      const response = await fetch('/api/export-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Interview Report',
          report_type: 'interview',
          payload: state.report,
        }),
      });
      const pdf = await window.readPdfResponse(response, 'Unable to download the interview report.');
      const downloadUrl = URL.createObjectURL(pdf);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = 'interview-report.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    } catch (error) {
      showFinalReportError(error.message || 'Unable to download the interview report. Please try again.');
    } finally {
      downloadRequestInProgress = false;
      if (downloadInterviewReportButton) {
        downloadInterviewReportButton.disabled = !state.report;
        downloadInterviewReportButton.textContent = 'Download Interview Report';
      }
    }
  }

  function renderFinalReport(report) {
    const finalScore = document.getElementById('final-score');
    const finalReadiness = document.getElementById('final-readiness');
    const finalTechnical = document.getElementById('final-technical');
    const finalCommunication = document.getElementById('final-communication');
    const finalProblem = document.getElementById('final-problem-solving');
    const finalProject = document.getElementById('final-project-knowledge');
    const finalHr = document.getElementById('final-hr');
    const finalStrengths = document.getElementById('final-strengths');
    const finalWeaknesses = document.getElementById('final-weaknesses');
    const weakQuestions = document.getElementById('weak-questions');
    const studyPlan = document.getElementById('study-plan');

    finalScore.textContent = `${report.overall_score || 0} / 100`;
    finalReadiness.textContent = report.readiness || 'Good';
    finalTechnical.textContent = `${report.technical || 0}%`;
    finalCommunication.textContent = `${report.communication || 0}%`;
    finalProblem.textContent = `${report.problem_solving || 0}%`;
    finalProject.textContent = `${report.project_knowledge || 0}%`;
    finalHr.textContent = `${report.hr_readiness || 0}%`;
    renderTextList(finalStrengths, report.strengths, 'Strong fundamentals and active learning mindset.');
    renderTextList(finalWeaknesses, report.weaknesses, 'Focus on reviewing your strong and weak topic areas.');

    weakQuestions.replaceChildren();
    const weakQuestionItems = Array.isArray(report.weak_questions) ? report.weak_questions : [];
    if (weakQuestionItems.length) {
      weakQuestionItems.forEach((item) => {
        const questionCard = document.createElement('div');
        questionCard.className = 'weak-question-item';
        appendTextElement(questionCard, 'strong', `Question: ${item.question ?? ''}`);
        appendTextElement(questionCard, 'div', `Score: ${item.score || 0}/100`);
        const reasons = Array.isArray(item.why) ? item.why.join(', ') : String(item.why || '');
        appendTextElement(questionCard, 'div', `Why: ${reasons}`);
        appendTextElement(questionCard, 'div', `Recommended Study: ${item.study_topic || item.topic || 'Core fundamentals'}`);
        weakQuestions.appendChild(questionCard);
      });
    } else {
      const emptyState = document.createElement('div');
      emptyState.className = 'weak-question-item';
      emptyState.textContent = 'No weak areas were identified this round.';
      weakQuestions.appendChild(emptyState);
    }

    studyPlan.replaceChildren();
    const studyPlanItems = Array.isArray(report.study_plan) ? report.study_plan : [];
    studyPlanItems.forEach((item) => {
      const listItem = document.createElement('li');
      appendTextElement(listItem, 'strong', `Day ${item.day ?? ''}: ${item.topic ?? ''}`);
      appendTextElement(listItem, 'div', item.why ?? '');
      appendTextElement(listItem, 'div', `Practice: ${item.task ?? ''}`);
      studyPlan.appendChild(listItem);
    });

    if (interviewResult) interviewResult.classList.add('hidden');
    if (interviewFinal) interviewFinal.classList.remove('hidden');
  }

  setupForm?.addEventListener('submit', startInterview);
  submitAnswerButton?.addEventListener('click', submitAnswer);
  nextQuestionButton?.addEventListener('click', () => {
    const currentQuestion = state.questions[state.currentIndex];
    if (!currentQuestion) {
      finishInterview();
      return;
    }

    state.currentIndex += 1;
    if (state.currentIndex >= state.questions.length) {
      finishInterview();
      return;
    }
    saveState();
    renderCurrentQuestion();
  });

  endInterviewButton?.addEventListener('click', () => finishInterview());
  retryFinalReportButton?.addEventListener('click', () => finishInterview());
  downloadInterviewReportButton?.addEventListener('click', downloadInterviewReport);
  skipQuestionButton?.addEventListener('click', () => {
    state.currentIndex += 1;
    if (state.currentIndex >= state.questions.length) {
      finishInterview();
      return;
    }
    saveState();
    renderCurrentQuestion();
  });

  retryWeakButton?.addEventListener('click', async () => {
    const weakQuestions = state.report?.weak_questions || [];
    const response = await fetch('/api/interview/retry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weak_questions: weakQuestions }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      showMessage(errorBox, data?.error?.message || 'Unable to generate retry questions.');
      return;
    }
    state.questions = data.questions;
    state.currentIndex = 0;
    state.results = [];
    saveState();
    renderCurrentQuestion();
    if (interviewFinal) interviewFinal.classList.add('hidden');
  });

  if (speechRecognition) {
    recognition = new speechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(' ');
      answerBox.value = transcript;
    };
    recognition.onerror = () => {
      voiceWarning.classList.remove('hidden');
      voiceWarning.textContent = 'Voice input could not be captured. Please type your answer instead.';
    };

    voiceToggle?.addEventListener('click', () => {
      if (recognition.running) {
        recognition.stop();
        voiceToggle.textContent = '🎤 Start Recording';
        return;
      }
      recognition.start();
      voiceToggle.textContent = '🎤 Stop Recording';
    });
  }

  restoreState();
});
