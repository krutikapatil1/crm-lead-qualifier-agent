# crm-lead-qualifier-agent

Qualifies inbound CRM leads using an LLM.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # then add your real OPENAI_API_KEY
```

## Usage

One-shot rating (Hot/Warm/Cold):

```bash
python main.py "Acme Corp, 500 employees, asked about enterprise pricing"
```

Full tool-calling agent (looks up the domain, checks CRM history, scores the lead):

```bash
python main.py --agent "jane@acmecorp.com"
```
