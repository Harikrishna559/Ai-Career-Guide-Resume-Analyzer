document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('resume-form');
  const uploadBox = document.getElementById('upload-box');
  const resumeInput = document.getElementById('resume-file');
  const fileName = document.getElementById('file-name');
  const errorBox = document.getElementById('resume-error');
  const loadingBox = document.getElementById('resume-loading');
  const submitButton = document.getElementById('resume-submit-btn');

  if (resumeInput && uploadBox) {
    resumeInput.addEventListener('change', (event) => {
      const file = event.target.files && event.target.files[0];
      fileName.textContent = file ? file.name : 'No file selected';
    });
  }

  if (!form) return;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideMessage(errorBox);

    const file = resumeInput && resumeInput.files ? resumeInput.files[0] : null;
    const targetRole = document.getElementById('resume-target-role')?.value?.trim();
    const jobDescription = document.getElementById('resume-job-description')?.value?.trim();

    if (!file) {
      showMessage(errorBox, 'Please upload a resume in PDF, DOCX, or TXT format.', 'error');
      return;
    }
    if (!targetRole) {
      showMessage(errorBox, 'Target role cannot be empty.', 'error');
      return;
    }

    const allowedTypes = ['pdf', 'docx', 'txt'];
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!allowedTypes.includes(extension)) {
      showMessage(errorBox, 'Unsupported file type. Please upload a PDF, DOCX, or TXT file.', 'error');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showMessage(errorBox, 'Resume file is too large. Please upload a smaller file.', 'error');
      return;
    }

    setLoading(loadingBox, true);
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = 'Analyzing...';
    }

    const formData = new FormData();
    formData.append('resume', file);
    formData.append('target_role', targetRole);
    if (jobDescription) {
      formData.append('job_description', jobDescription);
    }

    try {
      const response = await fetch('/api/analyze-resume', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        const message = data?.error?.message || 'Unable to analyze the resume right now.';
        throw new Error(message);
      }
      const savedResults = { ...data };
      delete savedResults.resume_text;
      delete savedResults.parsed_details;
      if (!window.appStorage.setItem('resumeAnalysisResults', JSON.stringify(savedResults))) {
        throw new Error('Browser storage is unavailable. Enable storage to view your resume analysis.');
      }
      window.location.href = '/resume-result';
    } catch (error) {
      let message = error.message || 'We could not analyze the resume.';
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
        submitButton.textContent = 'Analyze Resume';
      }
    }
  });
});
