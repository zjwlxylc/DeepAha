"""Single current application entry point; no legacy extraction/review routers."""
from deepaha.product.api import create_app
app = create_app()
