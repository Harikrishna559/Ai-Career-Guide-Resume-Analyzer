import os

from app import app
from services.ats_analyzer import generate_summary_versions, analyze_job_description
from services.career_service import build_role_library


def test_homepage_renders():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'AI Career Guide & Resume Analyzer' in response.data


def test_career_plan_validates_input():
    client = app.test_client()
    response = client.post('/api/career-plan', json={
        'name': '',
        'target_role': '',
        'current_skills': '',
        'experience_level': '',
        'hours_per_day': 0,
        'ai_consent': True,
    })
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert 'Name cannot be empty' in payload['error']['message'] or 'Target role cannot be empty' in payload['error']['message']


def test_health_check_reports_configuration_state():
    client = app.test_client()
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ok'
    assert 'gemini_configured' in payload


def test_role_library_supports_dict_based_metadata():
    roles = build_role_library()
    assert isinstance(roles, list)
    assert any(role.get('role') == 'Python Developer' for role in roles)


def test_summary_versions_and_job_description_analysis_work():
    resume = 'Python developer with Flask, SQL, Git, REST API, Docker, and project experience.'
    summary = generate_summary_versions(resume, 'Python Developer', {'skills': ['python', 'flask', 'sql', 'git']})
    assert 'ats_friendly' in summary
    assert 'professional' in summary
    assert 'fresher_friendly' in summary

    jd = 'Looking for Python Developer with Flask, SQL, REST API, Git and Docker experience.'
    result = analyze_job_description(jd, 'Python Developer', {'skills': ['python', 'flask', 'sql']})
    assert result['match_score'] >= 0
    assert 'missing_skills' in result
    assert 'learning_plan' in result


def test_job_description_and_report_routes_exist():
    client = app.test_client()
    response = client.post('/api/analyze-job-description', json={
        'job_description': 'Python Developer with Flask, SQL, APIs',
        'target_role': 'Python Developer',
        'resume_text': 'Python, Flask, SQL, Git'
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    legacy_jd_response = client.post('/api/analyze-jd', json={
        'job_description': 'Python Developer with Flask, SQL, APIs',
        'target_role': 'Python Developer',
        'resume_text': 'Python, Flask, SQL, Git'
    })
    assert legacy_jd_response.status_code == 200

    pdf_response = client.post('/api/export-report', json={
        'report_type': 'resume',
        'title': 'Resume Summary',
        'payload': {'ats_score': 88, 'missing_skills': ['Docker']}
    })
    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == 'application/pdf'

    pdf_legacy_response = client.post('/api/generate-pdf', json={
        'report_type': 'resume',
        'title': 'Resume Summary',
        'payload': {'ats_score': 90, 'missing_skills': ['Docker']}
    })
    assert pdf_legacy_response.status_code == 200
    assert pdf_legacy_response.mimetype == 'application/pdf'

    bullet_response = client.post('/api/improve-bullet', json={
        'bullet': 'Worked on backend APIs using Flask and SQL.',
        'target_role': 'Python Developer'
    })
    assert bullet_response.status_code == 200
    bullet_payload = bullet_response.get_json()
    assert bullet_payload['success'] is True
    assert 'Flask' in bullet_payload['improved_bullet']
