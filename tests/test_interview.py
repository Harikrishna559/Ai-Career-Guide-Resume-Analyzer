import re
from pathlib import Path

import pytest

from services.ai import AIServiceError
from services.interview_service import InterviewService


def test_interview_frontend_uses_safe_dom_rendering():
    project_root = Path(__file__).resolve().parents[1]
    frontend_files = [
        project_root / 'public' / 'static' / 'js' / 'interview.js',
        project_root / 'templates' / 'interview-simulator.html',
    ]
    unsafe_sink = re.compile(
        r'\.innerHTML\s*=|\.outerHTML\s*=|\.insertAdjacentHTML\s*\(|document\.write\s*\('
    )

    for frontend_file in frontend_files:
        source = frontend_file.read_text(encoding='utf-8')
        assert not unsafe_sink.search(source), f'Unsafe DOM sink found in {frontend_file.name}'

    interview_script = frontend_files[0].read_text(encoding='utf-8')
    assert 'document.createElement' in interview_script
    assert '.textContent =' in interview_script


@pytest.fixture
def service():
    class UnconfiguredAIService:
        def is_configured(self):
            return False

        def generate_json(self, prompt, *, response_schema=None):
            raise AssertionError("Unconfigured AI should not be called.")

    return InterviewService(ai_service=UnconfiguredAIService())


def test_interview_setup_validation(service):
    config = {
        'target_role': 'Python Developer',
        'experience_level': 'Fresher',
        'interview_type': 'Technical',
        'difficulty': 'Intermediate',
        'question_count': 5,
    }
    validated = service.validate_setup(config)
    assert validated['target_role'] == 'Python Developer'
    assert validated['question_count'] == 5
    assert validated['difficulty'] == 'Intermediate'


def test_invalid_role_rejected(service):
    with pytest.raises(ValueError):
        service.validate_setup({'target_role': '', 'experience_level': 'Fresher', 'interview_type': 'Technical', 'difficulty': 'Beginner', 'question_count': 5})


def test_missing_role_rejected(service):
    with pytest.raises(ValueError):
        service.validate_setup({'target_role': None, 'experience_level': 'Fresher', 'interview_type': 'Technical', 'difficulty': 'Beginner', 'question_count': 5})


def test_question_generation(service):
    questions = service.generate_questions({
        'target_role': 'Python Developer',
        'experience_level': 'Fresher',
        'interview_type': 'Technical',
        'difficulty': 'Beginner',
        'question_count': 3,
    }, resume_text='Python, Flask, SQL, Git', job_description='Python Developer with Flask, REST API and SQL')
    assert len(questions) == 3
    assert all('question' in q for q in questions)
    assert all('category' in q for q in questions)


def test_answer_validation(service):
    with pytest.raises(ValueError):
        service.validate_answer('')


def test_max_answer_length(service):
    answer = 'A' * 5000
    with pytest.raises(ValueError):
        service.validate_answer(answer)


def test_score_calculation(service):
    result = service.calculate_score(82, 76, 88, 90, 75, 84)
    assert result >= 0
    assert result <= 100
    assert result == pytest.approx(82.5, rel=1e-2)


def test_malformed_ai_json(service):
    class ConfiguredAIService:
        def is_configured(self):
            return True

        def generate_json(self, prompt, *, response_schema=None):
            return '{not valid json'

    service.ai_service = ConfiguredAIService()
    with pytest.raises(ValueError):
        service.generate_questions({
            'target_role': 'Python Developer',
            'experience_level': 'Fresher',
            'interview_type': 'Technical',
            'difficulty': 'Beginner',
            'question_count': 2,
        })


def test_ai_provider_failure(service):
    def raise_error(*args, **kwargs):
        raise AIServiceError('AI_NOT_CONFIGURED', 'AI service is not configured.')

    class FailingAIService:
        def is_configured(self):
            return True

        generate_json = raise_error

    service.ai_service = FailingAIService()
    with pytest.raises(AIServiceError):
        service.generate_questions({
            'target_role': 'Python Developer',
            'experience_level': 'Fresher',
            'interview_type': 'Technical',
            'difficulty': 'Beginner',
            'question_count': 2,
        })


def test_interview_service_uses_injected_provider_independent_service():
    class ConfiguredAIService:
        def is_configured(self):
            return True

        def generate_json(self, prompt, *, response_schema=None):
            return [{"question": "Explain Python lists.", "category": "Technical"}]

    service = InterviewService(ai_service=ConfiguredAIService())
    questions = service.generate_questions({
        'target_role': 'Python Developer',
        'experience_level': 'Fresher',
        'interview_type': 'Technical',
        'difficulty': 'Beginner',
        'question_count': 1,
    })
    assert questions[0]['question'] == "Explain Python lists."


def test_invalid_ai_evaluation_uses_existing_deterministic_fallback(service):
    class InvalidAIService:
        def is_configured(self):
            return True

        def generate_json(self, prompt, *, response_schema=None):
            raise AIServiceError("AI_INVALID_RESPONSE", "safe provider-independent message")

    service.ai_service = InvalidAIService()
    result = service.evaluate_answer(
        "Explain Python lists.",
        "I use Python lists in a project and test the API.",
    )
    assert 0 <= result["overall_score"] <= 100
    assert result["better_answer"]


def test_incomplete_ai_evaluation_uses_existing_deterministic_fallback(service):
    class IncompleteAIService:
        def is_configured(self):
            return True

        def generate_json(self, prompt, *, response_schema=None):
            return {
                "overall_score": 88,
                "technical_accuracy": 85,
            }

    service.ai_service = IncompleteAIService()
    result = service.evaluate_answer(
        "Explain how you test a Flask API.",
        "I use Python and Flask to build an API, add SQL storage, and test the project.",
    )

    assert result["overall_score"] != 88
    assert result["communication"] > 0
    assert result["completeness"] > 0


def test_final_report(service):
    report = service.build_final_report({
        'overall_score': 78,
        'technical': 82,
        'communication': 74,
        'problem_solving': 79,
        'project_knowledge': 85,
        'hr_readiness': 71,
        'strengths': ['Strong Python fundamentals'],
        'weaknesses': ['Communication'],
        'weak_questions': [{'question': 'Explain database normalization', 'score': 52, 'why': ['Incomplete explanation'], 'study_topic': 'DBMS normalization'}],
        'study_plan': [{'day': 1, 'topic': 'Python fundamentals', 'why': 'Foundation', 'task': 'Practice 10 Python questions'}],
    })
    assert report['overall_score'] == 78
    assert report['readiness'] == 'Good'
    assert 'study_plan' in report


def test_retry_weak_questions(service):
    weak_questions = [
        {'question': 'Explain database normalization', 'score': 52, 'topic': 'DBMS', 'category': 'Technical'},
        {'question': 'Tell me about a challenge you faced', 'score': 60, 'topic': 'Communication', 'category': 'Behavioral'},
    ]
    retried = service.retry_weak_questions(weak_questions)
    assert len(retried) == 2
    assert all('question' in item for item in retried)


def test_existing_routes_remain_functional():
    from app import app
    client = app.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/career-guide').status_code == 200
    assert client.get('/resume-analyzer').status_code == 200
    assert client.get('/job-description').status_code == 200
    assert client.get('/dashboard').status_code == 200
