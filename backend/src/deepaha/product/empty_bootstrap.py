"""Explicit empty-database bootstrap; never called by application startup."""
from pathlib import Path
from sqlalchemy import inspect
from .service import Product


def bootstrap_empty(database_url: str, object_root: Path) -> None:
    product = Product(database_url, object_root)
    try:
        if inspect(product.db.engine).get_table_names():
            raise RuntimeError('NONEMPTY_SCHEMA: refusing bootstrap')
        if any(p.is_file() for p in Path(object_root).rglob('*')):
            raise RuntimeError('NONEMPTY_OBJECTS: refusing bootstrap')
        product.initialize()
    finally:
        product.db.engine.dispose()


if __name__ == '__main__':
    import os
    from sqlalchemy.engine import make_url
    from .config import Settings
    settings = Settings.from_env()
    expected = os.environ.get('DEEPAHA_EMPTY_BOOTSTRAP_DATABASE')
    # The install binding provides the new DB name; a production URL cannot be
    # substituted accidentally. This entry point is not exposed by Gateway.
    if not expected or make_url(settings.database_url).database != expected:
        raise SystemExit('BOOTSTRAP_DATABASE_BINDING_REQUIRED')
    bootstrap_empty(settings.database_url, settings.data_dir / 'objects')
