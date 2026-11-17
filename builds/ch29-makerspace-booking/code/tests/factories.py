import factory
from factory.alchemy import SQLAlchemyModelFactory
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.resource import Resource, ResourceCategory, ResourceState
from app.models.user import User, UserStatus


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "commit"

    email = factory.Sequence(lambda n: f"factory_user_{n}@example.com")
    password_hash = factory.LazyFunction(lambda: generate_password_hash("testpassword1"))
    display_name = factory.Sequence(lambda n: f"Factory User {n}")
    status = UserStatus.active
    is_admin = False
    notification_prefs = {}
    tenant_id = None


class ResourceFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Resource
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "commit"

    name = factory.Sequence(lambda n: f"Resource {n}")
    category = ResourceCategory.equipment
    description = None
    location = None
    is_archived = False
    state = ResourceState.available
    thumbnail = None
    tenant_id = None
