from src.config import settings
from src.config.settings import validate
from src.api.app import create_app

validate()
app = create_app()

if __name__ == "__main__":
    app.run(
        host=settings.API_HOST,
        port=settings.API_PORT,
        debug=settings.DEBUG,
    )
