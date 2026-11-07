"""Each environment's S3 and DynamoDB clients come from that environment's one session."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from archivenetwork.loader import envclients
from archivenetwork.loader.awsauth import SignedOut
from archivenetwork.loader.envs import Env, Sso

REGION = "ap-southeast-1"

FLOCI = Env("local", "floci", "Local", REGION, "local-bucket", "an-local",
            endpoint_url="http://127.0.0.1:1")
AWS = Env("dev", "aws", "Dev", REGION, "dev-bucket", "an-dev",
          sso=Sso("https://d.awsapps.com/start", REGION, "123456789012", "Curators"))


@pytest.fixture(autouse=True)
def _aws_creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


class SpySession:
    """A real boto3 session that records every client it hands out."""

    def __init__(self):
        self._session = boto3.Session(region_name=REGION)
        self.made: list = []

    def client(self, service, **kw):
        c = self._session.client(service, **kw)
        self.made.append(c)
        return c


class FakeAuth:
    def __init__(self, session=None, error: Exception | None = None):
        self._session = session or SpySession()
        self.error = error
        self.asked: list[str] = []

    def session(self, env):
        self.asked.append(env.name)
        if self.error:
            raise self.error
        return self._session


def test_floci_storage_creates_bucket_aws_does_not():
    auth = FakeAuth()
    floci = envclients.storage_for(FLOCI, auth)
    assert floci.create_if_missing is True
    assert floci.bucket == "local-bucket"
    assert floci.client.meta.endpoint_url == "http://127.0.0.1:1"
    assert auth.asked == []  # real credentials never travel to the emulator
    aws = envclients.storage_for(AWS, auth)
    assert aws.create_if_missing is False
    assert aws.bucket == "dev-bucket"


def test_floci_tables_are_on_the_emulator():
    t = envclients.tables_for(FLOCI, FakeAuth())
    assert t.on_emulator is True
    assert t.prefix == "an-local"
    assert t.client.meta.endpoint_url == "http://127.0.0.1:1"


def test_aws_clients_come_from_the_env_session():
    auth = FakeAuth()
    tables = envclients.tables_for(AWS, auth)
    storage = envclients.storage_for(AWS, auth)
    made = auth._session.made
    assert tables.client in made
    assert storage.client in made
    assert tables.on_emulator is False
    assert tables.prefix == "an-dev"
    assert storage.client.meta.region_name == REGION
    assert storage.client.meta.config.connect_timeout == 3


@mock_aws
def test_identity_for_aws_returns_account():
    arn, account = envclients.identity_for(AWS, FakeAuth())
    assert account == "123456789012"
    assert arn.startswith("arn:aws:")


def test_identity_for_floci():
    assert envclients.identity_for(FLOCI, FakeAuth()) == ("floci", "")


def test_aws_clients_raise_signed_out():
    auth = FakeAuth(error=SignedOut("dev"))
    for fn in (envclients.tables_for, envclients.storage_for, envclients.identity_for):
        with pytest.raises(SignedOut):
            fn(AWS, auth)


def test_from_session_uses_bounded_timeouts():
    from archivenetwork.loader import dynamo

    t = dynamo.from_session(boto3.Session(region_name=REGION), "pfx", REGION)
    assert t.on_emulator is False
    assert t.client.meta.config.connect_timeout == 3
    assert t.client.meta.region_name == REGION


@mock_aws
def test_aws_storage_presigns_with_sigv4_for_fifteen_minutes():
    url = envclients.storage_for(AWS, FakeAuth()).presign("fb-exports/a/b/1.jpg")
    assert "dev-bucket" in url and "fb-exports/a/b/1.jpg" in url
    assert "X-Amz-Expires=900" in url
