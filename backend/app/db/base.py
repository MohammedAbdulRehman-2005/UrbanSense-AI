"""
UrbanSense AI — SQLAlchemy declarative base + all model imports

All ORM models are imported here so that Alembic's autogenerate
and create_all() can discover them through the Base metadata.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here to register them with Base.metadata
# Order matters only for forward-references; SQLAlchemy handles FKs.
from backend.app.models import road_segment  # noqa: F401, E402
from backend.app.models import event          # noqa: F401, E402
from backend.app.models import opportunity    # noqa: F401, E402
from backend.app.models import observation    # noqa: F401, E402
from backend.app.models import roadtwin       # noqa: F401, E402
from backend.app.models import evidence       # noqa: F401, E402
from backend.app.models import authority_action  # noqa: F401, E402