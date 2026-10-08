import json
import math
import re
from typing import Any

from services.ai import AIServiceError, create_ai_service
from services.resume_parser import parse_resume_details

ROLE_TOPICS = {
    'software engineer': ['Data structures', 'Object-oriented programming', 'Database design', 'System design', 'Problem solving', 'Projects'],
    'python developer': ['Python fundamentals', 'OOP', 'Flask', 'REST APIs', 'SQL', 'Testing', 'Git', 'Project architecture'],
    'java developer': ['Java fundamentals', 'Collections', 'OOP', 'Spring Boot', 'REST APIs', 'SQL', 'Project architecture'],
    'frontend developer': ['HTML', 'CSS', 'JavaScript', 'Responsive design', 'DOM', 'APIs', 'Performance'],
    'backend developer': ['APIs', 'Databases', 'Authentication', 'Security', 'System design', 'Performance'],
    'full stack developer': ['Frontend', 'Backend', 'Database design', 'APIs', 'Authentication', 'Deployment'],
    'data analyst': ['SQL', 'Excel', 'Statistics', 'Visualization', 'Business questions', 'Data cleaning'],
    'data scientist': ['Python', 'Statistics', 'Machine learning', 'Data preprocessing', 'Model evaluation', 'Business impact'],
    'ai/ml engineer': ['Python', 'Machine learning', 'Deep learning', 'Generative AI', 'LLMs', 'Model evaluation', 'APIs'],
    'cloud engineer': ['Cloud concepts', 'AWS', 'Azure', 'GCP', 'Networking', 'IAM', 'Storage'],
    'devops engineer': ['Linux', 'Git', 'CI/CD', 'Docker', 'Kubernetes', 'Monitoring', 'Cloud'],
    'cybersecurity engineer': ['Networking', 'Security fundamentals', 'Authentication', 'Threats', 'Vulnerabilities', 'Security tools'],
    'cybersecurity analyst': ['Networking', 'Security fundamentals', 'Authentication', 'Threats', 'Vulnerabilities', 'Security tools'],
    'ui/ux designer': ['User needs', 'Wireframes', 'Design systems', 'Usability', 'Accessibility', 'Research'],
}

INTERVIEW_TYPES = {
    'technical': 'Technical',
    'hr': 'HR',
    'behavioral': 'Behavioral',
    'coding': 'Coding',
    'mixed': 'Mixed',
}


class InterviewService:
    def __init__(self, ai_service=None):
        self.ai_service = ai_service or create_ai_service()

    def validate_setup(self, config):
        payload = dict(config or {})
        target_role = str(payload.get('target_role') or payload.get('role') or '').strip()
        custom_role = str(payload.get('custom_role') or '').strip()
        if custom_role:
            target_role = custom_role
        if not target_role:
            raise ValueError('Target role is required.')

        experience_level = str(payload.get('experience_level') or 'Fresher').strip() or 'Fresher'
        interview_type = str(payload.get('interview_type') or 'Technical').strip() or 'Technical'
        difficulty = str(payload.get('difficulty') or 'Beginner').strip() or 'Beginner'
        question_count = int(payload.get('question_count') or 5)
        if question_count < 1:
            question_count = 5
        elif question_count > 15:
            question_count = 15

        return {
            'target_role': target_role,
            'experience_level': experience_level,
            'interview_type': interview_type,
            'difficulty': difficulty,
            'question_count': question_count,
            'custom_role': custom_role,
        }

    def _extract_keywords(self, text):
        if not text:
            return []
        words = re.findall(r"[A-Za-z][A-Za-z0-9+/.-]*", text.lower())
        return [word for word in words if len(word) > 2][:25]

    def _build_question_list(self, validated, resume_text='', job_description=''):
        role = validated['target_role'].lower()
        interview_type = validated['interview_type'].lower()
        experience_level = validated['experience_level'].lower()
        difficulty = validated['difficulty'].lower()
        question_count = validated['question_count']

        base_topics = ROLE_TOPICS.get(role, ['Problem solving', 'Projects', 'Communication', 'Core fundamentals'])
        resume_keywords = []
        if resume_text:
            parsed = parse_resume_details(resume_text)
            resume_keywords = [str(item).lower() for item in parsed.get('skills', [])]
        jd_keywords = self._extract_keywords(job_description)

        if experience_level in {'student', 'fresher', 'graduate'}:
            preferred_topics = [
                'Tell me about yourself',
                'Explain your final-year project',
                'What did you personally contribute to your project?',
                'What is OOP?',
                'Why did you choose this technology?',
                'What challenges did you face?',
                'What are your strengths?',
            ]
        else:
            preferred_topics = [
                'Explain a project you built in detail',
                'Describe a technical challenge you solved',
                'How do you prioritize work and trade-offs?',
                'What is your approach to debugging?',
                'What would you do in a production incident?',
            ]

        if interview_type == 'hr':
            prompt_topics = [
                'Tell me about yourself',
                'Why are you interested in this role?',
                'What are your strengths and weaknesses?',
                'Why should we hire you?',
                'How do you handle conflict?',
                'Where do you see yourself in 2 years?'
            ]
        elif interview_type == 'behavioral':
            prompt_topics = [
                'Tell me about a challenge you faced in a project',
                'Describe a time you worked in a team',
                'How do you handle deadlines?',
                'What motivates you?',
                'Tell me about a mistake you fixed',
                'How do you learn new skills?'
            ]
        elif interview_type == 'coding':
            prompt_topics = [
                'Write a Python function to reverse a list',
                'Explain your approach to solving a coding problem',
                'How do you test your code?',
                'What is the time complexity of your solution?',
                'How do you handle edge cases?',
                'How would you debug a failing test case?'
            ]
        else:
            prompt_topics = [
                f'Can you explain {base_topics[0]} in your own words?',
                f'How would you apply {base_topics[1]} in a real project?',
                'Describe a project you are proud of and your contribution.',
                'How do you debug a production issue?',
                'What would you learn next for this role?',
                'Why are you a good fit for this opportunity?'
            ]

        relevant_topics = prompt_topics + [
            topic for topic in base_topics if topic.lower() not in {q.lower() for q in prompt_topics}
        ]

        if resume_keywords:
            for skill in resume_keywords[:3]:
                relevant_topics.insert(0, f'Can you explain your experience with {skill}?')

        if jd_keywords:
            for keyword in jd_keywords[:3]:
                if keyword not in {'the', 'with', 'for', 'that', 'role'}:
                    relevant_topics.insert(0, f'How have you worked with {keyword} in practice?')

        questions = []
        seen = set()
        for topic in relevant_topics:
            if len(questions) >= question_count:
                break
            normalized = re.sub(r'\s+', ' ', topic).strip()
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            category = 'Technical' if interview_type in {'technical', 'coding', 'mixed'} else 'Behavioral'
            questions.append({
                'question': normalized,
                'category': category,
                'difficulty': difficulty.title(),
                'expected_topics': [normalized],
                'target_role': validated['target_role'],
            })

        while len(questions) < question_count:
            fallback = f'How would you explain your understanding of {base_topics[len(questions) % len(base_topics)]} for this role?'
            questions.append({
                'question': fallback,
                'category': 'Technical',
                'difficulty': difficulty.title(),
                'expected_topics': [base_topics[len(questions) % len(base_topics)]],
                'target_role': validated['target_role'],
            })

        return questions[:question_count]

    def _parse_ai_response(self, raw_response):
        if isinstance(raw_response, dict):
            return raw_response
        if isinstance(raw_response, list):
            return {'questions': raw_response}
        if not isinstance(raw_response, str):
            raise ValueError('Malformed AI JSON.')

        stripped = raw_response.strip()
        if not stripped:
            raise ValueError('Malformed AI JSON.')
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            match = re.search(r'```json\s*(\{.*?\}|\[.*?\])\s*```', stripped, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError as exc:
                    raise ValueError('Malformed AI JSON.') from exc
            raise ValueError('Malformed AI JSON.')

    def generate_questions(self, config, resume_text='', job_description=''):
        validated = self.validate_setup(config)
        prompt = (
            'Generate a structured JSON array for interview questions. '
            'Return valid JSON only with keys: question, category, difficulty, expected_topics. '
            f'Role: {validated["target_role"]}. Experience: {validated["experience_level"]}. '
            f'Interview type: {validated["interview_type"]}. Difficulty: {validated["difficulty"]}. '
            f'Questions needed: {validated["question_count"]}. '
            f'Resume text: {resume_text[:4000]}. Job description: {job_description[:4000]}.'
        )

        if not self.ai_service.is_configured():
            return self._build_question_list(validated, resume_text, job_description)

        try:
            raw = self.ai_service.generate_json(prompt)
            parsed = self._parse_ai_response(raw)
            if isinstance(parsed, dict) and 'questions' in parsed:
                items = parsed['questions']
            elif isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict) and 'question' in parsed:
                items = [parsed]
            else:
                raise ValueError('Malformed AI JSON.')
        except AIServiceError:
            raise
        except ValueError:
            raise
        except Exception:
            return self._build_question_list(validated, resume_text, job_description)

        processed = []
        for item in items[:validated['question_count']]:
            if not isinstance(item, dict):
                continue
            question = str(item.get('question') or item.get('prompt') or '').strip()
            if not question:
                continue
            processed.append({
                'question': question,
                'category': str(item.get('category') or 'Technical').strip() or 'Technical',
                'difficulty': str(item.get('difficulty') or validated['difficulty']).strip() or validated['difficulty'],
                'expected_topics': item.get('expected_topics') or [question],
                'target_role': validated['target_role'],
            })

        if not processed:
            return self._build_question_list(validated, resume_text, job_description)

        while len(processed) < validated['question_count']:
            processed.extend(self._build_question_list(validated, resume_text, job_description)[len(processed):validated['question_count']])
            break

        return processed[:validated['question_count']]

    def validate_answer(self, answer, max_length=3000):
        cleaned = str(answer or '').strip()
        if not cleaned:
            raise ValueError('Answer cannot be empty.')
        if len(cleaned) > max_length:
            raise ValueError('Answer must be 3000 characters or less.')
        return cleaned

    def calculate_score(self, *scores):
        values = [float(value) for value in scores if value is not None]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    def _determine_readiness(self, score):
        if score >= 90:
            return 'Excellent'
        if score >= 80:
            return 'Strong'
        if score >= 70:
            return 'Good'
        if score >= 60:
            return 'Needs Improvement'
        return 'Needs Significant Improvement'

    def evaluate_answer(self, question, answer, target_role='Python Developer', experience_level='Fresher', interview_type='Technical', difficulty='Beginner', context=None):
        cleaned = self.validate_answer(answer)
        prompt = (
            'Evaluate the candidate answer with valid JSON only. '
            'Return keys: overall_score, technical_accuracy, communication, completeness, clarity, strengths, improvements, better_answer, follow_up_question. '
            f'Question: {question}. Answer: {cleaned}. Role: {target_role}. Experience: {experience_level}. '
            f'Interview type: {interview_type}. Difficulty: {difficulty}. Context: {json.dumps(context or {}, ensure_ascii=False)}.'
        )

        try:
            raw = self.ai_service.generate_json(prompt)
            data = self._parse_ai_response(raw)
            if not isinstance(data, dict):
                raise AIServiceError('AI_INVALID_RESPONSE', 'AI service returned an unexpected response. Please try again.')
            score_fields = {
                'overall_score': data.get('overall_score'),
                'technical_accuracy': data.get('technical_accuracy', data.get('technical')),
                'communication': data.get('communication'),
                'completeness': data.get('completeness'),
                'clarity': data.get('clarity'),
            }
            for field, value in score_fields.items():
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 100
                ):
                    raise ValueError(f'AI evaluation is missing a valid {field} score.')
        except AIServiceError as exc:
            if exc.code != 'AI_INVALID_RESPONSE':
                raise
            return self._fallback_evaluation(question, cleaned, target_role, experience_level, interview_type, difficulty, context)
        except ValueError:
            return self._fallback_evaluation(question, cleaned, target_role, experience_level, interview_type, difficulty, context)

        overall_score = float(data.get('overall_score', 0) or 0)
        technical_accuracy = float(data.get('technical_accuracy', data.get('technical', 0)) or 0)
        communication = float(data.get('communication', 0) or 0)
        completeness = float(data.get('completeness', 0) or 0)
        clarity = float(data.get('clarity', 0) or 0)
        strengths = data.get('strengths') or []
        improvements = data.get('improvements') or []
        better_answer = str(data.get('better_answer') or '').strip() or 'Focus on a clear explanation with a practical example.'
        follow_up_question = data.get('follow_up_question') or None

        return {
            'overall_score': min(max(int(round(overall_score)), 0), 100),
            'technical_accuracy': min(max(int(round(technical_accuracy)), 0), 100),
            'communication': min(max(int(round(communication)), 0), 100),
            'completeness': min(max(int(round(completeness)), 0), 100),
            'clarity': min(max(int(round(clarity)), 0), 100),
            'strengths': strengths[:4],
            'improvements': improvements[:4],
            'better_answer': better_answer,
            'follow_up_question': follow_up_question,
            'label': self._determine_readiness(min(max(int(round(overall_score)), 0), 100)),
        }

    def _fallback_evaluation(self, question, answer, target_role, experience_level, interview_type, difficulty, context=None):
        answer_lower = answer.lower()
        keywords = {'python', 'flask', 'sql', 'api', 'project', 'debug', 'team', 'security', 'testing', 'analysis'}
        mentions = sum(1 for word in keywords if word in answer_lower)
        length_score = min(100, int(len(answer) / 30))
        technical_score = min(100, 60 + mentions * 8)
        communication_score = min(100, 60 + min(30, len(answer) // 40))
        completeness_score = min(100, 50 + min(50, len(answer) // 25))
        clarity_score = min(100, 60 + min(30, mentions * 5))
        overall = round((technical_score + communication_score + completeness_score + clarity_score) / 4, 2)
        strengths = ['Relevant technical concepts mentioned', 'Clear attempt to explain the answer'] if mentions else ['Answered the question directly']
        improvements = ['Add a practical example', 'Explain the trade-offs more clearly']
        if target_role.lower() == 'python developer' and 'flask' not in answer_lower:
            improvements.append('Reference the relevant Python framework or tool when appropriate')
        better_answer = 'A concise answer with a practical example and clear reasoning is usually stronger.'
        follow_up = None
        if 'flask' in answer_lower or 'api' in answer_lower:
            follow_up = 'You mentioned APIs. How would you handle a production failure or timeout in this service?'
        return {
            'overall_score': int(overall),
            'technical_accuracy': int(technical_score),
            'communication': int(communication_score),
            'completeness': int(completeness_score),
            'clarity': int(clarity_score),
            'strengths': strengths[:4],
            'improvements': improvements[:4],
            'better_answer': better_answer,
            'follow_up_question': follow_up,
            'label': self._determine_readiness(int(overall)),
        }

    def build_final_report(self, payload):
        scores = {
            'technical': payload.get('technical', 0),
            'communication': payload.get('communication', 0),
            'problem_solving': payload.get('problem_solving', 0),
            'project_knowledge': payload.get('project_knowledge', 0),
            'hr_readiness': payload.get('hr_readiness', 0),
        }
        overall_score = payload.get('overall_score')
        if overall_score is None:
            overall_score = self.calculate_score(*scores.values())
        strengths = payload.get('strengths') or []
        weaknesses = payload.get('weaknesses') or []
        weak_questions = payload.get('weak_questions') or []
        study_plan = payload.get('study_plan') or []
        report = {
            'overall_score': int(round(float(overall_score))),
            'technical': int(round(float(scores['technical']))),
            'communication': int(round(float(scores['communication']))),
            'problem_solving': int(round(float(scores['problem_solving']))),
            'project_knowledge': int(round(float(scores['project_knowledge']))),
            'hr_readiness': int(round(float(scores['hr_readiness']))),
            'readiness': self._determine_readiness(int(round(float(overall_score)))),
            'strengths': strengths[:5],
            'weaknesses': weaknesses[:5],
            'weak_questions': weak_questions[:5],
            'study_plan': study_plan[:7],
        }
        return report

    def retry_weak_questions(self, weak_questions):
        items = weak_questions or []
        generated = []
        for item in items[:3]:
            topic = str(item.get('topic') or item.get('study_topic') or item.get('question') or 'Core concepts').strip()
            category = str(item.get('category') or 'Technical').strip() or 'Technical'
            question = str(item.get('question') or f'Can you explain {topic} clearly?').strip()
            generated.append({
                'question': question,
                'category': category,
                'difficulty': 'Intermediate',
                'expected_topics': [topic],
                'target_role': 'Python Developer',
            })
        if not generated:
            generated = [{
                'question': 'Tell me about a project you are most proud of and your role in it.',
                'category': 'Behavioral',
                'difficulty': 'Beginner',
                'expected_topics': ['Project explanation'],
                'target_role': 'Python Developer',
            }]
        return generated
