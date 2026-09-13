import json
import logging

from openai import OpenAI

try:
    from .config import MODEL, require_api_key
except ImportError:
    # Running this file directly as a script (e.g. the IDE's Run button) leaves it
    # with no parent package, so fall back to an absolute import off the repo root.
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from crm_lead_qualifier.config import MODEL, require_api_key

logger = logging.getLogger(__name__)

# Hard cap on agent turns so a model that keeps requesting tools can never spin forever.
MAX_TURNS = 8


def lookup_domain_info(domain: str) -> str:
    """
    Look up domain information using an external API.

    Args:
        domain (str): The domain to look up.

    Returns:
        str: The information retrieved from the API.
    """
    mock_data = {
        "acmecorp.com": {"industry": "Software/SaaS", "size": "501-1000 employees", "revenue": "$50M - $100M"},
        "widgetco.net": {"industry": "Manufacturing", "size": "100-250 employees", "revenue": "$10M - $25M"},
        "globalfin.org": {"industry": "Financial Services", "size": "5000+ employees", "revenue": "$1B+"},
    }

    info = mock_data.get(domain, {"industry": "Unknown", "size": "Unknown", "revenue": "Unknown"})
    return json.dumps(info)


def check_crm_history(email: str) -> str:
    """
    Retrieve CRM history for a given email address.

    Args:
        email (str): The email address to look up.

    Returns:
        str: The CRM history for the given email address.
    """
    # Mock database for demonstration
    mock_data = {
        "jane@acmecorp.com": {"last_contact": "2025-11-15", "status": "Cold Lead", "notes": "Attended webinar, no follow-up yet."},
        "bob@widgetco.net": {"last_contact": "2025-12-01", "status": "Active Opportunity", "notes": "Discussed Q1 budget and product integration."},
        "default": {"last_contact": "N/A", "status": "No Record", "notes": "New lead, first contact opportunity."},
    }

    history = mock_data.get(email, mock_data["default"])
    return json.dumps(history)


def calculate_lead_score(data_summary: str) -> str:
    """
    Analyzes the collected data (domain and CRM history) to assign a lead score (High/Medium/Low).
    This function simulates a complex scoring algorithm.
    """
    print("-> TOOL ACTIVATED: Calculating lead score...")

    data = json.loads(data_summary)
    # The model may call this before both gathering tools have run, so treat
    # either section as optional rather than indexing straight into it.
    domain_info = data.get("domain_info") or {}
    crm_history = data.get("crm_history") or {}

    score = "Low"  # Default score

    # Simple scoring logic for demonstration
    if domain_info.get("revenue", "").startswith("$1B+"):
        score = "High"
    elif crm_history.get("status") == "Active Opportunity":
        score = "High"
    elif domain_info.get("revenue", "").startswith("$50M"):
        score = "Medium"

    return json.dumps({"lead_score": score})


AVAILABLE_FUNCTIONS = {
    "lookup_domain_info": lookup_domain_info,
    "check_crm_history": check_crm_history,
    "calculate_lead_score": calculate_lead_score,
}

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "lookup_domain_info",
            "description": "Retrieves general business information (industry, size, revenue) about a company based on its domain name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "The company's domain name, e.g., 'acmecorp.com'"},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_crm_history",
            "description": "Checks the internal CRM system for past contact, status, and notes associated with a specific lead email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "The full email address of the lead."},
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_lead_score",
            "description": "Calculates the priority score (High/Medium/Low) for a lead based on a summary of all collected domain and CRM history data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_summary": {"type": "string", "description": "A JSON string containing the combined domain_info and crm_history."},
                },
                "required": ["data_summary"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are an expert CRM Lead Qualifier Agent. Your sole task is to analyze a sales lead "
    "provided via email address. You must follow these steps precisely: "
    "1. Identify the domain from the email. "
    "2. Call `lookup_domain_info` and `check_crm_history` sequentially to gather all data. "
    "3. Combine all collected data into a single JSON object. "
    "4. Call `calculate_lead_score` with the combined JSON object. "
    "5. Finally, synthesize all information (domain info, CRM history, and score) "
    "into a single, easy-to-read summary for a busy sales rep."
)


def _dispatch(function_name, raw_arguments, collected_data):
    """
    Run one tool call and return its result string.

    Every failure path returns a string as well, because the API requires a tool
    message for each requested tool_call -- omitting one makes the *next* request
    fail with a 400.
    """
    function_to_call = AVAILABLE_FUNCTIONS.get(function_name)
    if not function_to_call:
        logger.warning("Model requested unknown function %r", function_name)
        return json.dumps({"error": f"Unknown function: {function_name}"})

    try:
        function_args = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as e:
        logger.warning("Malformed arguments for %s: %s", function_name, e)
        return json.dumps({"error": f"Malformed arguments: {e}"})

    # The score tool is scored off everything gathered so far, not off whatever
    # the model happened to echo back, so its arguments are replaced wholesale.
    if function_name == "calculate_lead_score":
        function_args = {"data_summary": json.dumps(collected_data)}

    try:
        result = function_to_call(**function_args)
    except Exception as e:
        logger.warning("Tool %s raised %s: %s", function_name, type(e).__name__, e)
        return json.dumps({"error": f"{type(e).__name__}: {e}"})

    # Feed the gathering tools' output forward into the scoring step.
    if function_name == "lookup_domain_info":
        collected_data["domain_info"] = json.loads(result)
    elif function_name == "check_crm_history":
        collected_data["crm_history"] = json.loads(result)

    return result


def run_agent(user_prompt: str):
    """
    The main execution loop for the CRM Lead Qualifier Agent.
    """
    print("\n--- Running Lead Qualifier Agent ---")

    client = OpenAI(api_key=require_api_key())

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    collected_data = {}

    for _ in range(MAX_TURNS):
        print("\n[AI Thinking...]")
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )

        print(f'Response is: ', response)

        response_message = response.choices[0].message
        messages.append(response_message.model_dump(exclude_none=True))

        if not response_message.tool_calls:
            print("\n--- FINAL AGENT SUMMARY ---")
            print(response_message.content)
            return response_message.content

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_result = _dispatch(function_name, tool_call.function.arguments, collected_data)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": function_result,
            })

    logger.warning("Hit MAX_TURNS (%s) without a final answer", MAX_TURNS)
    print(f"\n--- STOPPED: hit the {MAX_TURNS}-turn cap without a final summary ---")
    return None


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    lead = " ".join(sys.argv[1:]) or "jane@acmecorp.com"
    run_agent(f"Please qualify this lead for my call tomorrow: {lead}")
