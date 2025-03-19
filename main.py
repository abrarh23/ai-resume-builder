import requests
import json
from flask import Flask, request
from flask_cors import CORS
from flask import jsonify 
from dotenv import load_dotenv
import os
from datetime import datetime
import logging
from openai import OpenAI
from loguru import logger
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_AUTH = os.getenv("GEMINI_AUTH")
QUREOS_AUTH = os.getenv("QUREOS_AUTH")

app = Flask(__name__)
cors = CORS(app)

def get_parse_resume_json(resume_url: str) -> dict:

    url = "https://apiv3aws.qureos.com/cv-parser/parse?model=4"

    payload = json.dumps({
    "resumeUrl": resume_url
    })
    headers = {
    'Authorization': f'Bearer {QUREOS_AUTH}',
    'Content-Type': 'application/json',
    'User-Agent': 'insomnia/2023.5.8'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    return json.loads(response.text)

def remove_null_values(data: dict|list) -> dict:
  """
  Recursively removes key-value pairs where the value is None from a dictionary.

  Args:
    data: The dictionary to process.

  Returns:
    The dictionary with None values removed.
  """

  if isinstance(data, dict):
    return {k: remove_null_values(v) for k, v in data.items() if v is not None}
  elif isinstance(data, list):
    return [remove_null_values(item) for item in data]
  else:
    return data

def convert_fields(obj):
    """Recursively convert Object ID to string and dateime to string datetime format"""
    if isinstance(obj, dict):
        # If obj is a dictionary, iterate over its items
        for key, value in obj.items():
            obj[key] = convert_fields(value)  # Recursively call for nested objects
    elif isinstance(obj, list):
        # If obj is a list, iterate through the list and apply conversion to each item
        return [convert_fields(item) for item in obj]
    elif isinstance(obj, datetime):
        # Convert datetime to ISO format string
        return obj.isoformat()
    
    # If obj is neither a dict, list, nor datetime, return it unchanged
    return obj

def calculate_duration_in_years(work_history: list[dict]) -> float:
    """To calculate duration in years (with decimal places"""
    try:
        current_date = datetime.now()  # Store the current date once for consistency
        for job in work_history:
            # Handle start date (it could be either a string or a datetime object)
            start_at = job.get('startAt')
            if isinstance(start_at, str):  # If startAt is a string, parse it
                start_date = datetime.strptime(start_at, "%Y-%m-%d")
            elif isinstance(start_at, datetime):  # If it's already a datetime object, use it
                start_date = start_at
            else:
                logging.warning("Start_at:", type(start_at))
                start_date = None
                logging.warning("startAt field must be a string or a datetime object")

            # Handle end date (it could be either a string, a datetime object, or missing)
            end_at = job.get('endAt') if job.get('endAt') else current_date
            if isinstance(end_at, str):  # If endAt is a string, parse it
                end_date = datetime.strptime(end_at, "%Y-%m-%d")
            elif isinstance(end_at, datetime):  # If it's already a datetime object, use it
                end_date = end_at
            else:  # If endAt is None, use the current date
                logging.warning("end_at:", type(start_at))
                end_date = current_date
                logging.warning("endAt field must be a string or a datetime object")

            # Calculate the difference in days
            total_days = (end_date - start_date).days
            
            # Approximate number of days in a year (to account for leap years)
            days_in_year = 365.25
            
            # Calculate duration in years (with decimal places)
            duration_in_years = total_days / days_in_year
            
            # Insert duration in years into the job dictionary (rounded to 2 decimal places)
            job['durationInYears'] = round(duration_in_years, 2)
            job['start_date_str'] = start_date.strftime('%Y-%m-%d')
            job['end_date_str'] = end_date.strftime('%Y-%m-%d')

    except Exception as e:
        job['durationInYears'] = 0
        job['start_date_str'] = '0'
        job['end_date_str'] = '0'
        logging.warning("Error in calculate_duration_in_years function:", str(e))
        
def convert_graduated_at(education_history: list[dict]) -> None:
    for education in education_history:
        if 'graduatedAt' in education and education['graduatedAt']:
            # Parse the ISO timestamp
            graduated_at_date = education.get('graduatedAt', None)
            if isinstance(graduated_at_date, str):  # If startAt is a string, parse it
                  graduated_at_date = datetime.strptime(graduated_at_date, "%Y-%m-%d")
            elif isinstance(graduated_at_date, datetime):  # If it's already a datetime object, use it
                graduated_at_date = graduated_at_date
            else:
                app.logger.warning("Issue in data type of graduated at date in education history:", type(graduated_at_date))
                raise ValueError("startAt field must be a string or a datetime object")
            # Convert to desired string format (e.g., 'YYYY-MM-DD')
            education['graduatedAtDate'] = graduated_at_date.strftime('%Y-%m-%d')

def modify_candidate_data(user_data: dict) -> dict:
    """Insert duration of work exp and graduatedAt dates"""
    try:
        calculate_duration_in_years(user_data['cv']['workHistory'])
        convert_graduated_at(user_data['cv']['educationHistory'])

    except Exception as e:
        logging.warning("Error in get_all_candidates function candidate_data:", user_data['cv'])
        logging.warning("Exception:", str(e))
    return user_data

def convert_single_json_to_prompt_v2(user_data: dict, applied_job_desc: str) -> str:
    """Convert each candidate data to formatted string"""
    
    user_data = remove_null_values(user_data['cv'])
    current_location = user_data.get("city", "unknown city") + ", " + user_data.get("country", "unknown country")
    aboutme = user_data.get('bio', None)
    experience_details = user_data.get("workHistory", [])
    education_details = user_data.get("educationHistory", [])    
    certifications = user_data.get("certificates", [])
    languages = user_data.get("languages", [])
    nationality_details = user_data.get('nationality', None)
    linkedin = user_data.get('linkedIn', None)
    email = user_data.get("email", None)
    phone = user_data.get("phone", None)
    project_details = user_data.get("projects", [])
    skills = user_data.get("skills", [])
    
    
    # Initialize the prompt
    prompt = "The following are the details of person's whole resume:\n"

    # Add the current location of the individual
    prompt += f"""\nThe person is currently located in {current_location}{". Email: " + email if email else ""}{". Phone: " + phone if phone else ""}{". linkedin: " + linkedin if linkedin else ""}\n"""

    if aboutme:
        prompt += f"About me: \n{aboutme}\n" 
    
    if experience_details:
        prompt += "\nExperiences:\n"
        
        # Loop through the experience list and create sentence-based format
        for idx, experience in enumerate(experience_details, 1):
            job_title = experience.get("title", "Unknown Position")
            company_name = experience.get("companyName", "Unknown Company")
            job_loc = experience.get("location", "Unknown Location")
            duration_year = experience.get("durationInYears", "Unknown Duration")
            job_desc = experience.get("jobDescription", "unknown job description")
            start_date_str = experience.get("start_date_str", "Unknown start date")
            end_at = str(experience.get("endAt", "Present"))
            # Construct the experience sentence
            prompt += f"""{idx}: {job_title} at {company_name} in {job_loc}, with {duration_year} years of experience starting from {start_date_str} and {"presently working" if end_at == "Present" else "ending at " + end_at}. Job description was: {job_desc}\n"""
    
    if skills:
        if isinstance(skills, list):
            skills = ', '.join([skill for skill in skills])
            prompt += f"\nPerson is skilled in the following: {skills}\n"

    if education_details:
        prompt += "\nEducation: \n"
        for idx, education in enumerate(education_details, 1):
            education_field = education.get("degreeAndField", "Unknown Field")
            education_school_name = education.get("schoolName", "Unknown School")
            education_grad_date = education.get("graduatedAtDate", "Unknown graduation date")
            prompt += f"{idx}. Studied {education_field} from {education_school_name} and graduated at {education_grad_date}.\n"
    
    if certifications:
        prompt += "Certification:\n"
        for idx, certification in enumerate(certifications, 1):
            certification_field = certification.get("title", "unknown certification name")
            certification_school = certification.get("company", "unknown certification institution")
            certification_issue_date = certification.get("issueDate", None)

            # Construct the certification sentence
            prompt += f"""{idx}. Certification in {certification_field} from {certification_school}{" at " + {certification_issue_date} if certification_issue_date else ""}.\n"""

    if nationality_details:
        prompt += f"\nThis person is {nationality_details} national.\n"
    
    if project_details:
        prompt += "\nPerson has done following projects in his career:\n"
        for idx, project in enumerate(project_details,1):
            project_title = project.get("title", "unknown project title")
            project_start_at =project.get("startAt", None)
            project_end_at = project.get("endAt", None)
            prompt += f"""\n{idx}. {project_title}{". Started at " + project_start_at if project_start_at else ""}{" and ended at " + project_end_at if project_end_at else ""}"""
    
    if languages:
        prompt += "\nLanguages:\n"
        for idx, language in enumerate(languages, 1):
            if language is None:
                continue
            if isinstance(language, str):
                prompt += f"{idx}. Candidate speaks {language}.\n"
            else:
                language_name = language.get("name", "Unknown language name")
                language_proficiency = language.get("proficiency", "Unknown")

                # Construct the certification sentence
                prompt += f"\n{idx}. Candidate speaks {language_name} with {language_proficiency} proficiency.\n"
        
    # Append instruction for JSON-only output
    prompt += "\n\n[No prose, output only JSON]\n"

    prompt += "\nFollowing is the job description of the job this candidate is applying to:\n\n"
    prompt += applied_job_desc
    return prompt    

def connect_to_openai() -> OpenAI:
    OPENAI_AUTH = os.getenv("OPENAI_AUTH")
    openai_client = OpenAI(api_key=OPENAI_AUTH)
    return openai_client

def get_openai_gen_resume(user_prompt: str, system_prompt: str) -> dict:

    response = connect_to_openai().chat.completions.create(
    model="gpt-4o",
    messages=[
        {
        "role": "system",
        "content": [
            {
            "type": "text",
            "text": f"{system_prompt}"
            }
        ]
        },
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": f"{user_prompt}"
            }
        ]
        }
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
        "name": "resume_schema",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
            "cv": {
                "type": "object",
                "properties": {
                "languages": {
                    "type": "array",
                    "description": "List of languages spoken by the individual.",
                    "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                        "type": "string",
                        "description": "Name of the language"
                        },
                        "proficiency": {
                        "type": "string",
                        "description": "Proficiency in the langauage"
                        }
                    },
                    "required": [
                        "name",
                        "proficiency"
                    ],
                    "additionalProperties": False
                    }
                },
                "city": {
                    "type": "string",
                    "description": "The city of residence."
                },
                "country": {
                    "type": "string",
                    "description": "The country of residence."
                },
                "educationHistory": {
                    "type": "array",
                    "description": "List of educational qualifications.",
                    "items": {
                    "type": "object",
                    "properties": {
                        "degreeAndField": {
                        "type": "string",
                        "description": "The degree and field of study."
                        },
                        "schoolName": {
                        "type": "string",
                        "description": "The name of the school or university attended."
                        },
                        "startedAt": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "The date when the education started."
                        },
                        "graduatedAt": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "The date when the education was completed."
                        }
                    },
                    "required": [
                        "degreeAndField",
                        "schoolName",
                        "startedAt",
                        "graduatedAt"
                    ],
                    "additionalProperties": False
                    }
                },
                "workHistory": {
                    "type": "array",
                    "description": "List of work experiences.",
                    "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                        "type": "string",
                        "description": "Job title."
                        },
                        "companyName": {
                        "type": "string",
                        "description": "Name of the company."
                        },
                        "startAt": {
                        "type": "string",
                        "description": "The start date of employment."
                        },
                        "endAt": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "The end date of employment."
                        },
                        "jobDescription": {
                        "type": "string",
                        "description": "Description of the job role."
                        },
                        "location": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "Location of the job."
                        }
                    },
                    "required": [
                        "title",
                        "companyName",
                        "startAt",
                        "endAt",
                        "jobDescription",
                        "location"
                    ],
                    "additionalProperties": False
                    }
                },
                "projects": {
                    "type": "array",
                    "description": "List of projects undertaken.",
                    "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                        "type": "string",
                        "description": "Title of the project."
                        },
                        "startAt": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "The start date of the project."
                        },
                        "endAt": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "The end date of the project."
                        }
                    },
                    "required": [
                        "title",
                        "startAt",
                        "endAt"
                    ],
                    "additionalProperties": False
                    }
                },
                "linkedIn": {
                    "type": [
                    "string",
                    "null"
                    ],
                    "description": "LinkedIn profile URL."
                },
                "website": {
                    "type": [
                    "string",
                    "null"
                    ],
                    "description": "Personal website URL."
                },
                "skills": {
                    "type": "array",
                    "description": "List of skills possessed.",
                    "items": {
                    "type": "string"
                    }
                },
                "bio": {
                    "type": [
                    "string",
                    "null"
                    ],
                    "description": "Short biography."
                },
                "email": {
                    "type": "string",
                    "description": "Email address."
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number."
                },
                "certificates": {
                    "type": "array",
                    "description": "List of certificates earned.",
                    "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                        "type": "string",
                        "description": "Title of the certificate."
                        },
                        "company": {
                        "type": "string",
                        "description": "Company or institution that issued the certificate."
                        },
                        "issueDate": {
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "The date when the certificate was issued."
                        }
                    },
                    "required": [
                        "title",
                        "company",
                        "issueDate"
                    ],
                    "additionalProperties": False
                    }
                }
                },
                "required": [
                "languages",
                "city",
                "country",
                "educationHistory",
                "workHistory",
                "projects",
                "linkedIn",
                "website",
                "skills",
                "bio",
                "email",
                "phone",
                "certificates"
                ],
                "additionalProperties": False
            }
            },
            "required": [
            "cv"
            ],
            "additionalProperties": False
        }
        }
    },
    temperature=1,
    max_completion_tokens=2048,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0
    )

    return response.choices[0].message.content

@app.route("/get_ai_resume", methods=['GET'])
def main() -> dict:
    params = request.get_json()
    resume_url = params.get("resume_url", "https://storage.googleapis.com/qureos-prod/apprentice-profile/7559/data-analyst-abrar-hasan.pdf")
    logger.debug(f"resume_url: {resume_url}")
    applied_job_desc = params.get("applied_job_desc", """# The job description of the job that the candidate is applying to:
About the opportunity

Assist the Head of MD Office in strategic planning process; identifying key metrics, aligning targets and evaluating performance.

Oversee coordination of regional and local programmes and projects; undertake research and prepare pre-meeting briefings.

Work cross functionally to understand business needs; analyse data to identify trends, drive insights and present actionable recommendations.

Plan and align goals across teams, ensuring alignment with central & regional objectives.

Develop and manage business’s OKRs to forecast and analyse company performance through budgeting, resource planning and goal setting.


What you need to be successful

3-4 years experience as a BI/Data analyst.

A Bachelor’s degree (minimum) or Master’s degree (preferred) in a quantitative discipline such as Computer Science or relevant discipline.

Proven expertise in SQL and experience designing scalable, efficient queries to support data-driven decision-making.

Demonstrated ability to craft compelling and creative data visualizations using Tableau or similar modern visualization tools.

Strong command over the entire data analysis lifecycle including; problem formulation, data auditing and rigoro.

Experience in data visualization, data storytelling, tableau, SQL, python (preferred), presentation of the query.



Who we are

foodpanda is part of the Delivery Hero Group, the world’s pioneering local delivery platform, our mission is to deliver an amazing experience—fast, easy, and to your door. We operate in over 70+ countries worldwide. Headquartered in Berlin, Germany. Delivery Hero has been listed on the Frankfurt Stock Exchange since 2017 and is part of the MDAX stock market index.


What's in it for you

What does your playfield look like?  

We work in a flexible but fast paced environment.

We start and end with customers to deliver exceptional service.

We love to innovate, prioritize, decide, and deliver. 

We love what we do, and we don’t rest until our targets are achieved. So if you’re also someone who is driven until the dream is achieved, come join us.""")

    parse_resp = get_parse_resume_json(resume_url)
    user_prompt = convert_single_json_to_prompt_v2(modify_candidate_data(parse_resp), applied_job_desc)
    system_prompt = "Your job is to adjust the job description in experience section of the resume of the candidate according to the job description that the candidate is applying to. Try to rewrite the job description in the experience section of resume and replace only those sentences which are not relevant to the job. The new sentences that you add should maintain the tone of writing like rest of the resume. Reorder the sentences or bullet points that are more relevant to the job description to the top and less relevant points to the bottom. Write the job description in first-person perspective and use action verbs like 'managed', 'led', 'achieved', 'developed', 'implemented', etc. Use quantitative metircs in terms of numbers, percentages to make the job description more specific and realistic. Return the response in the JSON format. Resume and job description that the candidate is applying to will be provided in the prompt."
    
    ai_resume = get_openai_gen_resume(user_prompt, system_prompt)
    json_str = json.loads(ai_resume)
    return jsonify(json_str), 200

@app.route("/healthcheck", methods=['GET'])
def healthcheck():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

