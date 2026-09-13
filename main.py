import logging
import sys

from crm_lead_qualifier import qualify_lead, run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)

USAGE = (
    'Usage: python main.py "lead description"\n'
    '       python main.py --agent "jane@acmecorp.com"'
)


def main():
    args = sys.argv[1:]

    use_agent = False
    if args and args[0] == "--agent":
        use_agent = True
        args = args[1:]

    description = " ".join(args)
    if not description:
        print(USAGE, file=sys.stderr)
        return 1

    try:
        if use_agent:
            run_agent(f"Please qualify this lead for my call tomorrow: {description}")
        else:
            print(qualify_lead(description))
    except RuntimeError as e:
        # Missing/invalid configuration -- a traceback here is just noise.
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logging.getLogger(__name__).debug("Unhandled error", exc_info=True)
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
