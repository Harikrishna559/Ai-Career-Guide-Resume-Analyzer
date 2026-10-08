document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('career-form');
  if (!form) return;

  const errorBox = document.getElementById('career-error');
  const loadingBox = document.getElementById('career-loading');
  const consentCheckbox = form.querySelector('[name="ai_consent"]');
  const consentError = document.getElementById('career-ai-consent-error');
  const submitButton = form.querySelector('button[type="submit"]');

  consentCheckbox?.addEventListener('change', () => {
    if (consentError) consentError.hidden = true;
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(errorBox);
    if (consentError) consentError.hidden = true;

    const formData = Object.fromEntries(new FormData(form).entries());
    const requiredFields = ['name', 'target_role', 'current_skills', 'experience_level'];
    const missing = requiredFields.filter((field) => !String(formData[field] || '').trim());
    if (missing.length) {
      showMessage(errorBox, 'Please fill in all required fields before generating your plan.', 'error');
      return;
    }

    const hours = Number(formData.hours_per_day || 0);
    if (!hours || hours < 1 || hours > 12) {
      showMessage(errorBox, 'Hours per day must be between 1 and 12.', 'error');
      return;
    }

    if (!consentCheckbox?.checked) {
      if (consentError) consentError.hidden = false;
      consentCheckbox?.focus();
      return;
    }
    formData.ai_consent = true;

    setLoading(loadingBox, true);
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = 'Building your plan...';
    }

    try {
      const response = await fetch('/api/career-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        const message = data?.error?.message || 'Unable to generate the career plan right now.';
        throw new Error(message);
      }

      if (!window.appStorage.setItem('careerGuideResults', JSON.stringify(data))) {
        throw new Error('Browser storage is unavailable. Enable storage to view your career plan.');
      }
      window.location.href = '/career-result';
    } catch (error) {
      let message = error.message || 'We could not generate the plan.';
      if (message.includes('Gemini API key') || message.includes('API key is not configured')) {
        message = 'Gemini API key is not configured. Please add GEMINI_API_KEY to the .env file.';
      } else if (message.includes('authentication') || message.includes('unauthorized')) {
        message = 'Gemini API authentication failed. Please verify your API key.';
      } else if (message.includes('rate limit')) {
        message = 'AI service rate limit reached. Please try again after some time.';
      } else if (message.includes('connection') || message.includes('network')) {
        message = 'We couldn\'t connect to the AI service. Please try again.';
      } else if (message.includes('unexpected response') || message.includes('No useful AI response')) {
        message = 'The AI returned an unexpected response. Please try again.';
      }
      showMessage(errorBox, message, 'error');
    } finally {
      setLoading(loadingBox, false);
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = 'Generate My 30-Day Plan';
      }
    }
  });
});
