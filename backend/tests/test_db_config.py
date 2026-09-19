import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config import Settings
from app.db import connection_candidates


def settings(**kw):
    base = dict(supabase_url=None, supabase_db_password=None, supabase_region=None, database_url=None)
    return Settings(_env_file=None, **{**base, **kw})


def test_direct_host_is_derived_from_the_project_url_and_password():
    (direct,) = connection_candidates(settings(supabase_url="https://abcdefghij.supabase.co", supabase_db_password="pw"))
    d = conninfo_to_dict(direct)
    assert d["host"] == "db.abcdefghij.supabase.co" and d["user"] == "postgres" and d["dbname"] == "postgres"
    assert d["password"] == "pw" and d["sslmode"] == "require"


def test_pooler_candidates_are_added_when_a_region_is_given():
    c = connection_candidates(settings(supabase_url="https://abcdefghij.supabase.co", supabase_db_password="pw", supabase_region="ap-south-1"))
    hosts = [conninfo_to_dict(x)["host"] for x in c]
    assert hosts == ["db.abcdefghij.supabase.co", "aws-0-ap-south-1.pooler.supabase.com", "aws-1-ap-south-1.pooler.supabase.com"]
    assert conninfo_to_dict(c[1])["user"] == "postgres.abcdefghij"


def test_passwords_with_special_characters_need_no_url_encoding():
    pw = "p@ss/w:rd#1 %&?='\""
    (direct,) = connection_candidates(settings(supabase_url="https://abcdefghij.supabase.co", supabase_db_password=pw))
    assert conninfo_to_dict(direct)["password"] == pw


def test_database_url_overrides_everything():
    assert connection_candidates(settings(database_url="postgresql://u:p@h:5432/db")) == ["postgresql://u:p@h:5432/db"]


@pytest.mark.parametrize("kw", [
    {},
    {"supabase_url": "https://abcdefghij.supabase.co"},  # no password
    {"supabase_db_password": "pw"},  # no URL
    {"supabase_url": "https://YOUR-PROJECT-REF.supabase.co", "supabase_db_password": "pw"},  # placeholder URL
])
def test_missing_or_placeholder_config_gives_a_clear_error(kw):
    with pytest.raises(RuntimeError, match="SUPABASE_DB_PASSWORD"):
        connection_candidates(settings(**kw))


def test_region_is_discovered_when_the_direct_host_is_unreachable(monkeypatch):
    import app.db as db

    def fake_try(info: str):
        d = conninfo_to_dict(info)
        if d["host"] == "aws-1-ap-south-1.pooler.supabase.com":
            return True, ""
        if "pooler" in d["host"]:
            return False, "FATAL:  Tenant or user not found"
        return False, "failed to resolve host"

    monkeypatch.setattr(db, "_try", fake_try)
    info = db.resolve_conninfo(settings(supabase_url="https://abcdefghij.supabase.co", supabase_db_password="pw"))
    assert conninfo_to_dict(info)["host"] == "aws-1-ap-south-1.pooler.supabase.com"
    assert conninfo_to_dict(info)["user"] == "postgres.abcdefghij"


def test_a_rejected_password_is_reported_as_such(monkeypatch):
    import app.db as db

    monkeypatch.setattr(db, "_try", lambda info: (False, "FATAL:  password authentication failed for user"))
    with pytest.raises(RuntimeError, match="password was rejected"):
        db.resolve_conninfo(settings(supabase_url="https://abcdefghij.supabase.co", supabase_db_password="bad"))
