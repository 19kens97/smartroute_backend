from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model

from apps.accounts.models import AgentProfile, Person, User


DEFAULT_PASSWORD = "Pass1234!Secure"


def _unique(value: str | None, prefix: str) -> str:
    if value:
        return value
    return f"{prefix}-{uuid.uuid4().hex[:10]}".upper()


def create_person(*, nif: str | None = None, first_name: str = "Test", last_name: str = "User", birth_date=None) -> Person:
    return Person.objects.create(nif=_unique(nif, "NIF"), first_name=first_name, last_name=last_name, birth_date=birth_date)


def create_agent_user(*, email: str | None = None, password: str = DEFAULT_PASSWORD, role: str = AgentProfile.Role.AGENT_TERRAIN, badge_number: str | None = None, first_name: str | None = None, last_name: str = "Agent", nif: str | None = None, post: str = "", precinct: str = "", is_staff: bool = False, is_superuser: bool = False, is_active: bool = True) -> User:
    UserModel = get_user_model()
    badge_number = _unique(badge_number, "BADGE")
    person = create_person(nif=nif or badge_number, first_name=first_name or str(role), last_name=last_name)
    user = UserModel.objects.create_user(person=person, account_type=UserModel.AccountType.PROFESSIONAL, email=email or f"{badge_number.lower()}@example.com", password=password, is_staff=is_staff, is_superuser=is_superuser, is_active=is_active)
    AgentProfile.objects.create(user=user, role=role, badge_number=badge_number, post=post, precinct=precinct, is_active=is_active)
    return user


def create_admin_user(**kwargs) -> User:
    kwargs.setdefault("role", AgentProfile.Role.ADMIN)
    kwargs.setdefault("is_staff", True)
    return create_agent_user(**kwargs)


def create_agent_saisie_user(**kwargs) -> User:
    kwargs.setdefault("role", AgentProfile.Role.AGENT_SAISIE)
    return create_agent_user(**kwargs)


def create_agent_terrain_user(**kwargs) -> User:
    kwargs.setdefault("role", AgentProfile.Role.AGENT_TERRAIN)
    return create_agent_user(**kwargs)


def create_personal_user(*, password: str = DEFAULT_PASSWORD, nif: str | None = None, first_name: str = "Personal", last_name: str = "User") -> User:
    UserModel = get_user_model()
    person = create_person(nif=nif, first_name=first_name, last_name=last_name)
    return UserModel.objects.create_user(person=person, account_type=UserModel.AccountType.PERSONAL, email="", password=password)
