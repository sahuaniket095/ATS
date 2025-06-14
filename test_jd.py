import PyPDF2
from google.generativeai import GenerativeModel, list_models, configure
import logging
import json
import os
from decouple import config
import re
import time

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('recruitment.utils')

def validate_api_key(api_key):
    """Validate the Google API key."""
    try:
        configure(api_key=api_key)
        models = list_models()
        logger.debug(f"Available models: {[m.name for m in models if 'generateContent' in m.supported_generation_methods]}")
        logger.debug("Google API key validated successfully")
        return True
    except Exception as e:
        logger.error(f"Invalid Google API key or connectivity issue: {str(e)}")
        return False

def get_available_model():
    """Find an available model that supports content generation."""
    try:
        configure(api_key=config('GOOGLE_API_KEY'))
        models = list_models()
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                logger.debug(f"Using model: {model.name}")
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

def summarize_jd(jd_file_path):
    """Summarize a job description from a PDF file."""
    try:
        # Extract text from PDF
        with open(jd_file_path, 'rb') as jd_file:
            pdf_reader = PyPDF2.PdfReader(jd_file)
            text = ""
            for page in pdf_reader.pages:
                extracted = page.extract_text() or ""
                text += extracted + "\n"
        logger.debug(f"JD text (first 100 chars, len={len(text)}): {text[:100]}")
        
        if not text.strip():
            logger.warning("No text extracted from JD")
            return {}
        
        # Validate API key
        if not validate_api_key(config('GOOGLE_API_KEY')):
            return {}
        
        # Try available models
        model_names = ['gemini-1.5-flash', 'gemini-1.5-pro']
        model_name = None
        for name in model_names:
            try:
                model = GenerativeModel(name)
                model_name = name
                logger.debug(f"Using model: {model_name}")
                break
            except Exception as e:
                logger.debug(f"Model {name} unavailable: {str(e)}")
                continue
        if not model_name:
            model_name = get_available_model()
        if not model_name:
            logger.error("No available Gemini model found")
            return {}
        
        model = GenerativeModel(model_name)
        prompt = (
            "Summarize this job description into a concise string of key requirements and extract the job title. "
            "Return the result as a valid JSON object with keys 'job_title' and 'summary'. "
            "Ensure all string values use double quotes and escape any single quotes within strings. "
            "Do not include markdown or code block wrappers. "
            f"Job description: {text[:4000]}"
        )
        
        # Generate summary
        try:
            response = model.generate_content(prompt)
            result = response.text.strip() if response.text else ""
            logger.debug(f"Summarized JD: {result}")
        except Exception as e:
            logger.error(f"Error summarizing JD: {str(e)}")
            return {}
        
        # Parse the response
        try:
            cleaned_result = clean_json_response(result)
            # Validate JSON before parsing
            try:
                json.loads(cleaned_result)
            except json.JSONDecodeError as e:
                logger.error(f"Cleaned JSON is invalid: {str(e)}. Cleaned response: {cleaned_result}")
                return {}
            data = json.loads(cleaned_result)
            time.sleep(60)  # Add delay to respect quota limits
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JD data: {str(e)}. Raw response: {result}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error while parsing JD data: {str(e)}")
            return {}
    except Exception as e:
        logger.error(f"Error summarizing JD: {str(e)}")
        return {}

# Run the script
jd_file_path = 'C:\\Users\\sahua\\OneDrive\\Desktop\\JD.pdf'
if os.path.exists(jd_file_path):
    result = summarize_jd(jd_file_path)
    print(f"Result: {result}")
else:
    logger.error(f"JD.pdf not found at {jd_file_path}")