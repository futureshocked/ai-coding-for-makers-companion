import click
from datetime import time

from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.resource import DEFAULT_WEEKDAY_END, DEFAULT_WEEKDAY_START, Resource, ResourceCategory, ResourceState
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus


SEED_TENANTS = [
    dict(name="Acme Makerspace",   subdomain="acme"),
    dict(name="WidgetCo Workshop", subdomain="widgetco"),
]

# Per-tenant users. Same emails across tenants exercise per-tenant uniqueness.
SEED_USERS_PER_TENANT = [
    dict(email="admin@test.com", password="adminpass",  display_name="Admin", is_admin=True),
    dict(email="alice@test.com", password="memberpass", display_name="Alice", is_admin=False),
    dict(email="bob@test.com",   password="memberpass", display_name="Bob",   is_admin=False),
]

_MR_WD_START = time(8, 0)
_MR_WD_END   = time(21, 0)
_MR_WE_START = time(9, 0)
_MR_WE_END   = time(15, 0)

SEED_RESOURCES = [
    # meeting_room — extended hours including weekends
    dict(category=ResourceCategory.meeting_room, name="Main Meeting Room",           capacity=8, location="Room 101",      weekday_start=_MR_WD_START, weekday_end=_MR_WD_END, weekend_start=_MR_WE_START, weekend_end=_MR_WE_END),
    dict(category=ResourceCategory.meeting_room, name="Small Meeting Room",          capacity=4, location="Room 102",      weekday_start=_MR_WD_START, weekday_end=_MR_WD_END, weekend_start=_MR_WE_START, weekend_end=_MR_WE_END),
    # equipment
    dict(category=ResourceCategory.equipment,    name="Oscilloscope — Rigol DS1054Z",       location="Bench 3",    weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    dict(category=ResourceCategory.equipment,    name="Bench Power Supply",                       location="Bench 1",    weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    dict(category=ResourceCategory.equipment,    name="3D Printer — Prusa MK4",             location="Workshop",   weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    # workbench
    dict(category=ResourceCategory.workbench,    name="Workbench A",                              location="Workshop",   weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    dict(category=ResourceCategory.workbench,    name="Workbench B",                              location="Workshop",   weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    # hot_spot
    dict(category=ResourceCategory.hot_spot,     name="Hot Spot 1",                               location="Common Area", weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    dict(category=ResourceCategory.hot_spot,     name="Hot Spot 2",                               location="Common Area", weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    # book
    dict(category=ResourceCategory.book,         name="Arduino Programming Guide",                location="Library Shelf A", weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
    dict(category=ResourceCategory.book,         name="Electronics for Makers",                   location="Library Shelf A", weekday_start=DEFAULT_WEEKDAY_START, weekday_end=DEFAULT_WEEKDAY_END, weekend_start=None, weekend_end=None),
]


@click.command("seed-db")
@with_appcontext
def seed_db():
    """Seed the database with demo tenants, users, and resources."""
    tenants = _seed_tenants()
    for tenant in tenants:
        _seed_users_for_tenant(tenant)
        _seed_resources_for_tenant(tenant)
    db.session.commit()
    click.echo("Done.")


def _seed_tenants() -> list[Tenant]:
    tenants: list[Tenant] = []
    for data in SEED_TENANTS:
        tenant = db.session.execute(
            db.select(Tenant).filter_by(subdomain=data["subdomain"])
        ).scalar_one_or_none()
        if tenant:
            click.echo(f"  skip tenant {data['subdomain']}")
        else:
            tenant = Tenant(
                name=data["name"],
                subdomain=data["subdomain"],
                status=TenantStatus.active,
                is_listed=True,
            )
            db.session.add(tenant)
            db.session.flush()
            click.echo(f"  add  tenant {data['subdomain']}")
        tenants.append(tenant)
    return tenants


def _seed_users_for_tenant(tenant: Tenant) -> None:
    for data in SEED_USERS_PER_TENANT:
        existing = db.session.execute(
            db.select(User).filter_by(tenant_id=tenant.id, email=data["email"])
        ).scalar_one_or_none()
        if existing:
            click.echo(f"  skip user {data['email']} @ {tenant.subdomain}")
            continue
        db.session.add(User(
            tenant_id=tenant.id,
            email=data["email"],
            password_hash=generate_password_hash(data["password"]),
            display_name=data["display_name"],
            status=UserStatus.active,
            is_admin=data["is_admin"],
        ))
        click.echo(f"  add  user {data['email']} @ {tenant.subdomain}")


def _seed_resources_for_tenant(tenant: Tenant) -> None:
    for data in SEED_RESOURCES:
        existing = db.session.execute(
            db.select(Resource).filter_by(tenant_id=tenant.id, name=data["name"])
        ).scalar_one_or_none()
        if existing:
            click.echo(f"  skip resource {data['name']} @ {tenant.subdomain}")
            continue
        db.session.add(Resource(
            tenant_id=tenant.id,
            state=ResourceState.available,
            is_archived=False,
            **data,
        ))
        click.echo(f"  add  resource {data['name']} @ {tenant.subdomain}")


@click.command("delete-seed-users")
@with_appcontext
def delete_seed_users():
    """Delete the SEED_USERS_PER_TENANT test accounts across all seed tenants. Idempotent."""
    deleted = 0
    for tenant_data in SEED_TENANTS:
        tenant = db.session.execute(
            db.select(Tenant).filter_by(subdomain=tenant_data["subdomain"])
        ).scalar_one_or_none()
        if tenant is None:
            continue
        for data in SEED_USERS_PER_TENANT:
            user = db.session.execute(
                db.select(User).filter_by(tenant_id=tenant.id, email=data["email"])
            ).scalar_one_or_none()
            if user is None:
                continue
            db.session.delete(user)
            deleted += 1
            click.echo(f"  delete {data['email']} @ {tenant.subdomain}")
    if deleted:
        db.session.commit()
    click.echo(f"Done. Removed {deleted} seed user(s).")


@click.command("create-admin")
@click.option("--tenant-subdomain", prompt=True, help="Subdomain of the tenant to create the admin under.")
@click.option("--email", prompt=True, help="Admin email address.")
@click.option("--display-name", prompt=True, help="Display name shown in the UI.")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Initial password (you can change it after logging in).",
)
@with_appcontext
def create_admin(tenant_subdomain: str, email: str, display_name: str, password: str):
    """Create a tenant admin user. Used to bootstrap the first admin of a tenant."""
    tenant = db.session.execute(
        db.select(Tenant).filter_by(subdomain=tenant_subdomain)
    ).scalar_one_or_none()
    if tenant is None:
        raise click.ClickException(f"Tenant '{tenant_subdomain}' not found.")
    existing = db.session.execute(
        db.select(User).filter_by(tenant_id=tenant.id, email=email)
    ).scalar_one_or_none()
    if existing:
        raise click.ClickException(f"User {email} already exists in tenant {tenant_subdomain}.")
    db.session.add(User(
        tenant_id=tenant.id,
        email=email,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        status=UserStatus.active,
        is_admin=True,
    ))
    db.session.commit()
    click.echo(f"Created admin {email} in tenant {tenant_subdomain}.")


@click.command("create-super-admin")
@click.option("--email", prompt=True, help="Super-admin email address.")
@click.option("--display-name", prompt=True, help="Display name shown in the UI.")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Initial password (you can change it after logging in).",
)
@with_appcontext
def create_super_admin(email: str, display_name: str, password: str):
    """Create the platform super-admin. Logs in at app.<APEX_HOST>. Tenant-less."""
    existing = db.session.execute(
        db.select(User).filter_by(tenant_id=None, email=email)
    ).scalar_one_or_none()
    if existing:
        raise click.ClickException(f"Super-admin {email} already exists.")
    db.session.add(User(
        tenant_id=None,
        email=email,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        status=UserStatus.active,
        is_admin=False,
        is_super_admin=True,
    ))
    db.session.commit()
    click.echo(f"Created super-admin {email}.")
