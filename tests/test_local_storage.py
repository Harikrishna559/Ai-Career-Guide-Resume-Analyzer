from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_resume_storage_omits_extracted_resume_content():
    source = (PROJECT_ROOT / 'static' / 'js' / 'resume.js').read_text(encoding='utf-8')
    main_source = (PROJECT_ROOT / 'static' / 'js' / 'main.js').read_text(encoding='utf-8')

    assert "delete savedResults.resume_text" in source
    assert "delete savedResults.parsed_details" in source
    assert "setItem('resumeAnalysisResults', JSON.stringify(savedResults))" in source
    assert 'delete resumeCached.resume_text' in main_source
    assert 'delete resumeCached.parsed_details' in main_source


def test_interview_storage_omits_submitted_answers_and_full_report():
    source = (PROJECT_ROOT / 'static' / 'js' / 'interview.js').read_text(encoding='utf-8')

    assert 'results: state.results.map(({ answer, ...result }) => result)' in source
    assert 'report: null' in source
    main_source = (PROJECT_ROOT / 'static' / 'js' / 'main.js').read_text(encoding='utf-8')
    assert 'interviewState.results = interviewState.results' in main_source
    assert '.filter(result => result && typeof result === \'object\' && !Array.isArray(result))' in main_source
    assert 'saveState();\n      showStage();' in source
    assert "overall_score: data.report.overall_score" in source
    assert "overall_score: payload.overall_score" not in source


def test_dashboard_clear_action_removes_only_named_application_keys():
    source = (PROJECT_ROOT / 'templates' / 'dashboard.html').read_text(encoding='utf-8')
    dashboard_script = (PROJECT_ROOT / 'static' / 'js' / 'dashboard.js').read_text(encoding='utf-8')
    expected_keys = {
        'careerGuideResults',
        'resumeAnalysisResults',
        'jobDescriptionResults',
        'interviewState',
        'interviewReport',
        'roadmapProgress',
        'roadmapCompleted',
    }

    for key in expected_keys:
        assert f"'{key}'" in dashboard_script
    assert "url_for('static', filename='js/dashboard.js')" in source
    assert 'window.appStorage.removeKeys(keys)' in dashboard_script
    assert "window.appStorage.setItem('interviewReport'" in (PROJECT_ROOT / 'static' / 'js' / 'interview.js').read_text(encoding='utf-8')
    assert 'window.confirm(' in dashboard_script
    assert 'Clear saved application data' in source

    app_storage = (PROJECT_ROOT / 'static' / 'js' / 'main.js').read_text(encoding='utf-8')
    assert 'localStorage.clear(' not in app_storage
    assert 'localStorage.removeItem(key)' in app_storage


def test_application_storage_access_handles_unavailable_and_malformed_storage():
    source = (PROJECT_ROOT / 'static' / 'js' / 'main.js').read_text(encoding='utf-8')

    assert 'getJSON(key, fallback = {})' in source
    assert 'JSON.parse(value)' in source
    assert 'catch {' in source
    assert 'setItem(key, value)' in source
    assert 'return false;' in source
