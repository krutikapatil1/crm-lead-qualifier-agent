import logging

import openai
from openai import OpenAI

from .config import MODEL, require_api_key

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You qualify inbound sales leads. Given a lead description, reply with a "
    "rating of Hot, Warm, or Cold, followed by one sentence of justification."
)


def qualify_lead(description):
    client = OpenAI(api_key=require_api_key())
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
        )
    except openai.APIConnectionError:
        logger.exception("Could not reach the OpenAI API")
        raise
    except openai.RateLimitError:
        logger.exception("Rate limited")
        raise
    except openai.APIStatusError as e:
        logger.exception("API returned HTTP %s", e.status_code)
        raise
    return response.choices[0].message.content
