import os
import PyPDF2
from google.generativeai import GenerativeModel, list_models, configure
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
import logging
import re
import json
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configure logging
logger = logging.getLogger(__name__)

class QuotaExceededError(Exception):
    pass

retry_on_quota_exceeded = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(QuotaExceededError)
)

def validate_api_key():
    """Validate Google API key configuration."""
    try:
        configure(api_key=settings.GOOGLE_API_KEY)
        models = list_models()
        logger.debug(f"Available models: {[m.name for m in models if 'generateContent' in m.supported_generation_methods]}")
        return True
    except Exception as e:
        logger.error(f"Invalid Google API key or connectivity issue: {str(e)}")
        return False

def get_available_model():
    """Fetch an available Gemini model for content generation."""
    try:
        configure(api_key=settings.GOOGLE_API_KEY)
        models = list_models()
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                logger.debug(f"Available model: {model.name}")
                return model.name.split('/')[-1]
        logger.error("No models supporting generateContent found")
        return None
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        return None

def clean_json_response(text):
    """Remove Markdown code block wrappers and fix JSON syntax issues."""
    text = text.strip()
    # Normalize special quotes to standard ones
    text = text.replace("’", "'").replace("‘", "'").replace("“", "\"").replace("”", "\"")
    # Remove Markdown code blocks
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    # Remove trailing punctuation before closing brace
    text = re.sub(r'[\.,;]\s*}$', '}', text)

    # Escape single quotes within double-quoted strings
    def escape_single_quotes(match):
        content = match.group(1)
        content = content.replace("'", "\\'")
        return f'"{content}"'
    text = re.sub(r'"([^"]*)"', escape_single_quotes, text)

    # Replace single-quoted strings with double-quoted strings
    text = re.sub(r"'([^']*)'", r'"\1"', text)

    # Log the cleaned response for debugging
    logger.debug(f"Cleaned JSON response: {text[:100]}...")
    return text

@retry_on_quota_exceeded
def make_api_call(model, prompt):
    """Make an API call with retry logic for quota errors."""
    try:
        response = model.generate_content(prompt)
        return response
    except Exception as e:
        if "429" in str(e):
            raise QuotaExceededError(f"Quota exceeded: {str(e)}")
        raise

def extract_cv_data(cv_file):
    """Extract name, email, skills, experience, education, and certifications from a CV PDF."""
    try:
        pdf_reader = PyPDF2.PdfReader(cv_file)
        text = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text() or ""
            text += extracted + "\n"
        logger.debug(f"Extracted CV text (first 50 chars, len={len(text)}): {text[:50]}...")
        
        if not text.strip():
            logger.warning("No text extracted from CV")
            return {}
        
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        candidate_email = email_match.group(0) if email_match else None
        
        if not validate_api_key():
            return {}
        
        model_name = get_available_model() or 'gemini-1.5-flash'
        model = GenerativeModel(model_name)
        prompt = (
            "Extract the following from this CV in a structured format: "
            "Name, Email, Skills, Experience, Education, Certifications. "
            "Return as a valid JSON object without markdown wrappers. Ensure all string values use double quotes and escape any single quotes within strings. Example: "
            "{\"name\": \"John Doe\", \"email\": \"john.doe@example.com\", \"summary\": \"Skills: Python, Django; Experience: 3 years as a developer; Education: B.Tech in CS; Certifications: AWS Certified Developer\"} "
            f"CV text: {text[:4000]}"
        )
        try:
            response = make_api_call(model, prompt)
            result = response.text.strip() if response.text else ""
            logger.debug(f"Extracted CV data: {result[:100]}...")
        except QuotaExceededError as e:
            logger.error(f"Quota exceeded after retries: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Gemini API error in CV extraction: {str(e)}")
            return {}
        
        try:
            cleaned_result = clean_json_response(result)
            data = json.loads(cleaned_result)
            if not data.get('email') and candidate_email:
                data['email'] = candidate_email
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {str(e)}. Raw response: {result}")
            return {}
    except Exception as e:
        logger.error(f"Error extracting CV data: {str(e)}")
        return {}

def summarize_jd(jd_file):
    """Summarize a job description PDF into key requirements and extract job title."""
    try:
        pdf_reader = PyPDF2.PdfReader(jd_file)
        text = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text() or ""
            text += extracted + "\n"
        logger.debug(f"Extracted JD text (first 50 chars, len={len(text)}): {text[:50]}...")
        
        if not text.strip():
            logger.warning("No text extracted from JD")
            return {}
        
        if not validate_api_key():
            return {}
        
        model_name = get_available_model() or 'gemini-1.5-flash'
        model = GenerativeModel(model_name)
        prompt = (
            "Summarize this job description into a concise string of key requirements and extract the job title. "
            "Return as a valid JSON object without markdown wrappers. Ensure all string values use double quotes and escape any single quotes within strings. Example: "
            "{\"job_title\": \"Software Engineer\", \"summary\": \"Skills: Python, Django; Experience: 3+ years; Qualifications: B.Tech; Responsibilities: Develop web applications\"} "
            f"Job description: {text[:4000]}"
        )
        try:
            response = make_api_call(model, prompt)
            result = response.text.strip() if response.text else ""
            logger.debug(f"Summarized JD: {result[:100]}...")
        except QuotaExceededError as e:
            logger.error(f"Quota exceeded after retries: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Gemini API error in JD summarization: {str(e)}")
            return {}
        
        try:
            cleaned_result = clean_json_response(result)
            # Validate JSON before parsing
            try:
                json.loads(cleaned_result)
            except json.JSONDecodeError as e:
                logger.error(f"Cleaned JSON is invalid: {str(e)}. Cleaned response: {cleaned_result}")
                return {}
            data = json.loads(cleaned_result)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {str(e)}. Raw response: {result}")
            return {}
    except Exception as e:
        logger.error(f"Error summarizing JD: {str(e)}")
        return {}

def calculate_match_score(cv_data, jd_summary):
    """Calculate a match score between CV data and JD summary."""
    try:
        if not isinstance(cv_data, dict) or not isinstance(jd_summary, dict):
            logger.error("CV data or JD summary is not a dictionary")
            return 0.0
        required_keys = ['summary']
        for data in [cv_data, jd_summary]:
            if not all(key in data for key in required_keys):
                logger.error(f"Missing required keys in data: {data}")
                return 0.0
        cv_summary = cv_data.get('summary', '').lower()
        jd_summary_str = jd_summary.get('summary', '').lower()
        cv_words = set(cv_summary.split())
        jd_words = set(jd_summary_str.split())
        common_words = cv_words.intersection(jd_words)
        score = (len(common_words) / len(jd_words) * 100) if jd_words else 0.0
        logger.debug(f"Match score: {score}")
        return round(score, 2)
    except Exception as e:
        logger.error(f"Error calculating match score: {str(e)}")
        return 0.0

def send_interview_email(candidate_email, candidate_name, job_title):
    """Send an interview invitation email to the candidate."""
    try:
        context = {
            'candidate_name': candidate_name,
            'job_title': job_title,
            'interview_times': [
                "Monday, June 16, 2025, 10:00 AM IST",
                "Tuesday, June 17, 2025, 2:00 PM IST",
            ],
        }
        message = render_to_string('emails/interview_invitation.txt', context)
        send_mail(
            subject=f"Interview Invitation for {job_title}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[candidate_email],
            fail_silently=False,
        )
        logger.info(f"Email sent to {candidate_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {candidate_email}: {str(e)}")

def send_custom_email(candidate_email, candidate_name, subject, message):
    """Send a custom email to a candidate."""
    try:
        full_message = render_to_string('emails/custom_email.txt', {
            'candidate_name': candidate_name,
            'message': message,
        })
        send_mail(
            subject=subject,
            message=full_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[candidate_email],
            fail_silently=False,
        )
        logger.info(f"Custom email sent to {candidate_email}")
    except Exception as e:
        logger.error(f"Failed to send custom email to {candidate_email}: {str(e)}")