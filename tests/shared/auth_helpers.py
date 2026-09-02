"""
Helpers for running an existing test under more than one authentication method.

The point is to let a test that already sets up its users and channels keep doing so,
and swap only *how the replicator authenticates*.  A test parametrized over
``AUTH_MODES`` then proves that role- and channel-based authorization behaves the same
whether the identity arrived as Basic credentials, a session token, or a JWT --
which is the property the auth suite actually cares about.
"""

from typing import Any, Final, cast

from cbltest import CBLPyTest
from cbltest.api.replicator_types import (
    ReplicatorAuthenticator,
    ReplicatorBasicAuthenticator,
    ReplicatorBearerAuthenticator,
    ReplicatorSessionAuthenticator,
)
from cbltest.api.syncgateway import LocalJWT, SyncGateway
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from shared.jwt_helper import generate_jwt, generate_rsa_keypair, public_key_to_jwk

AUTH_MODES: Final[list[str]] = ["basic", "session", "jwt"]
"""The auth methods an existing test can be parametrized over."""

JWT_ISSUER: Final[str] = "https://qe.example.com"
JWT_AUDIENCE: Final[str] = "cbl-js-qe"
JWT_KID: Final[str] = "qe-test-key"
JWT_PROVIDER: Final[str] = "qe"

_ISSUER_HOST: Final[str] = "qe.example.com"


def auth_mode_for(cblpytest: CBLPyTest) -> str:
    """
    The auth method this run should use, read from ``--test-props``.

    A run-level switch rather than a pytest parametrize. Only CBL JS supports session
    and bearer credentials differently, so multiplying every shared test by three would
    triple iOS, Android, C, Java and .NET runtime to cover a JS-only concern. CI runs
    the suite again with a different props file instead, which also means a failure
    names the auth mode in the job rather than in a test ID.

    Defaults to ``"basic"``, so an existing run behaves exactly as before.

    :raises ValueError: If the props file names a mode that does not exist, rather than
        silently falling back to basic and reporting a green run that tested nothing new.
    """
    mode = cast(str, cblpytest.extra_props.get("auth_mode", "basic"))
    if mode not in AUTH_MODES:
        raise ValueError(f"auth_mode {mode!r} in --test-props is not one of {AUTH_MODES}")
    return mode


def jwt_username(username: str) -> str:
    """
    The username Sync Gateway derives from a JWT's ``sub`` claim.

    With no explicit ``user_prefix`` on the provider, Sync Gateway builds the account
    name as ``<issuer-host>_<sub>``, so a JWT for ``sub: alice`` resolves to the user
    ``qe.example.com_alice`` -- not ``alice``.  Getting this wrong produces a 401 that
    looks like a signature failure but is really "no such user", so it is worth having
    in one place.
    """
    return f"{_ISSUER_HOST}_{username}"


async def configure_jwt_provider(sync_gateway: SyncGateway, db_name: str) -> RSAPrivateKey:
    """
    Adds a ``local_jwt`` provider to an existing database and returns its signing key.

    Uses ``local_jwt`` rather than a full ``oidc`` provider so no external identity
    provider is needed in the topology: the keypair is minted in-process and only its
    public half is handed to Sync Gateway.

    Preserves whatever database config is already in place -- these helpers run against
    databases a test has already set up via ``configure_dataset``, so the config is read
    back and amended rather than replaced.
    """
    private_key, public_key = generate_rsa_keypair()
    config = await sync_gateway.get_database_config(db_name)
    config.local_jwt = {
        JWT_PROVIDER: LocalJWT(
            issuer=JWT_ISSUER,
            client_id=JWT_AUDIENCE,
            register=False,
            algorithms=["RS256"],
            keys=[public_key_to_jwk(public_key, kid=JWT_KID)],
        )
    }
    await sync_gateway.update_database_config(db_name, config)
    return private_key


async def mirror_user_for_jwt(
    sync_gateway: SyncGateway,
    db_name: str,
    username: str,
    collection_access: dict | None = None,
    admin_roles: list[str] | None = None,
) -> str:
    """
    Creates a JWT-addressable twin of an existing user, with the same grants.

    A test that already created ``alice`` with particular channels and roles can call
    this to get an equivalent ``qe.example.com_alice``, so the JWT run exercises the
    same authorization rules without the test having to know about the name mangling.

    The twin gets no password -- it is reachable only by JWT, which keeps the two
    identities from being accidentally interchangeable in a test.

    :return: The derived username, for use as the JWT's ``sub`` mapping target
    """
    derived = jwt_username(username)
    await sync_gateway.delete_user(db_name, derived)
    await sync_gateway.add_user(
        db_name,
        derived,
        collection_access=collection_access,
        admin_roles=admin_roles,
    )
    return derived


async def make_authenticator(
    sync_gateway: SyncGateway,
    db_name: str,
    username: str,
    password: str,
    mode: str,
    *,
    collection_access: dict | None = None,
    admin_roles: list[str] | None = None,
    jwt_key: RSAPrivateKey | None = None,
) -> ReplicatorAuthenticator:
    """
    Builds a replicator authenticator for `username` using the given auth method.

    ``basic``    -- the credentials as-is; no Sync Gateway changes.
    ``session``  -- mints a session for the user via the admin API.
    ``jwt``      -- configures a ``local_jwt`` provider (unless `jwt_key` is supplied),
                    mirrors the user under its derived name, and signs a token.

    For ``jwt``, `collection_access` and `admin_roles` must describe the same grants the
    test gave the original user; they cannot be read back reliably from Sync Gateway in
    a form ``add_user`` accepts, so the caller passes them explicitly.

    Pass `jwt_key` to reuse a provider configured earlier in the same test -- calling
    this twice without it reconfigures the provider with a fresh keypair and invalidates
    any token already issued.
    """
    if mode == "basic":
        return ReplicatorBasicAuthenticator(username, password)

    if mode == "session":
        session = await sync_gateway.create_session(db_name, username)
        return ReplicatorSessionAuthenticator(session.session_id)

    if mode == "jwt":
        key = jwt_key if jwt_key is not None else await configure_jwt_provider(sync_gateway, db_name)
        await mirror_user_for_jwt(
            sync_gateway,
            db_name,
            username,
            collection_access=collection_access,
            admin_roles=admin_roles,
        )
        return ReplicatorBearerAuthenticator(
            generate_jwt(
                key,
                subject=username,
                expires_in=3600,
                kid=JWT_KID,
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            )
        )

    raise ValueError(f"Unknown auth mode {mode!r}; expected one of {AUTH_MODES}")


def describe_auth(mode: str, username: str) -> str:
    """A phrase for mark_test_step, so the step log says which identity is in play."""
    return cast(
        str,
        {
            "basic": f"basic credentials for {username}",
            "session": f"session token for {username}",
            "jwt": f"bearer token for {username} (as {jwt_username(username)})",
        }.get(mode, cast(Any, mode)),
    )
