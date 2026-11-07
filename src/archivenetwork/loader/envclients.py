"""Build one environment's S3 storage, DynamoDB tables and caller identity.

For an `aws` env every client comes from `AuthManager.session(env)`, so the bucket and the tables
are always reached as the same identity in the same account. A `floci` env gets dummy `test`/`test`
credentials and never asks the auth manager: real keys must never travel to the emulator.
"""

from __future__ import annotations

from typing import Protocol

import boto3
from botocore.config import Config as BotoConfig

from . import dynamo
from .envs import Env
from .storage import ENDPOINT_CONNECT_TIMEOUT, ENDPOINT_READ_TIMEOUT, S3Storage

FLOCI_KEY = "test"  # floci ignores credentials, but boto3 requires a pair

S3_AWS_CONFIG = BotoConfig(
    connect_timeout=ENDPOINT_CONNECT_TIMEOUT,
    read_timeout=ENDPOINT_READ_TIMEOUT,
    retries={"mode": "standard", "max_attempts": 2},
    signature_version="s3v4",  # presigned row previews; SigV2 URLs are refused by newer regions
)


class SessionSource(Protocol):
    def session(self, env: Env) -> boto3.Session: ...


def tables_for(env: Env, auth: SessionSource) -> dynamo.Tables:
    if env.kind == "floci":
        return dynamo.connect(env.table_prefix, env.endpoint_url, env.region)
    return dynamo.from_session(auth.session(env), env.table_prefix, env.region)


def storage_for(env: Env, auth: SessionSource) -> S3Storage:
    if env.kind == "floci":
        return S3Storage(
            env.s3_bucket,
            env.region,
            FLOCI_KEY,
            FLOCI_KEY,
            endpoint_url=env.endpoint_url,
            create_if_missing=True,  # floci starts empty; an AWS bucket is never created here
        )
    client = auth.session(env).client("s3", region_name=env.region, config=S3_AWS_CONFIG)
    return S3Storage(env.s3_bucket, env.region, client=client, create_if_missing=False)


def identity_for(env: Env, auth: SessionSource) -> tuple[str, str]:
    """`(arn, account)` of whoever this env's session is; `get_caller_identity` needs no grant."""
    if env.kind == "floci":
        return ("floci", "")
    ident = auth.session(env).client("sts", region_name=env.region).get_caller_identity()
    return (ident["Arn"], ident["Account"])
