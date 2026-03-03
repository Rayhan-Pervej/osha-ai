import logging
from src.config import settings
from src.config.settings import validate
from src.api.app import create_app

# Configure logging
log_level = logging.DEBUG if settings.DEBUG else getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

if settings.DEBUG:
    # Show full debug output for the agent and bedrock only — not all libraries
    logging.getLogger("osha.agent.debug").setLevel(logging.DEBUG)
    logging.getLogger("src.agent.graph").setLevel(logging.DEBUG)
    logging.getLogger("src.llm.bedrock").setLevel(logging.DEBUG)
    logging.getLogger("src.agent.tools").setLevel(logging.DEBUG)
    # Silence noisy third-party loggers
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("langchain_aws").setLevel(logging.WARNING)
    logging.getLogger("langchain_core").setLevel(logging.WARNING)
    print("[DEBUG MODE ON] Agent trace logging enabled")

validate()
app = create_app()

if __name__ == "__main__":
    app.run(
        host=settings.API_HOST,
        port=settings.API_PORT,
        debug=settings.DEBUG,
    )
