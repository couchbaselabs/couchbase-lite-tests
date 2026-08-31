import base64
import json
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# Generates a 2048-bit RSA key pair
# Private key → signs the JWT token (ES uses this token)
# Public key → given to SGW so it can verify the token's signature
def generate_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate an RSA key pair for signing JWTs."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


from cbltest.api.syncgateway import JWK


def public_key_to_jwk(public_key: rsa.RSAPublicKey, kid: str = "test-key-1") -> JWK:
    """Convert RSA public key to JWK format for SGW OIDC config."""
    numbers = public_key.public_numbers()
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return JWK(
        kty="RSA",
        n=_b64url(n),
        e=_b64url(e),
        alg="RS256",
        use="sig",
        kid=kid,
    )


def generate_jwt(
    private_key: rsa.RSAPrivateKey,
    subject: str = "edge",
    expires_in: int = 300,
    kid: str = "test-key-1",
    issuer: str = "test-issuer",
    audience: str = "edge-server",
    alg: str = "RS256",
    sign_with: rsa.RSAPrivateKey | None = None,
) -> str:
    """Generate a signed RS256 JWT token.

    Args:
        private_key: RSA private key for signing.
        subject: The 'sub' claim — maps to the SGW username.
        expires_in: Token validity in seconds.  Pass a negative value to mint an
            already-expired token.
        kid: Key ID to include in the JWT header.
        issuer: The 'iss' claim — must match the provider's configured issuer.
        audience: The 'aud' claim — must match the provider's configured client_id.
        alg: The 'alg' header value.  Only RS256 is actually signed; pass 'none' to
            mint an unsigned token for algorithm-confusion tests.
        sign_with: Sign with this key instead of `private_key`, to mint a token whose
            signature will not verify against the published JWK.

    Returns:
        Signed JWT string.
    """
    now = int(time.time())
    header = _b64url(
        json.dumps(
            {"alg": alg, "typ": "JWT", "kid": kid},
            separators=(",", ":"),
        ).encode()
    )
    payload = _b64url(
        json.dumps(
            {
                "sub": subject,
                "iss": issuer,
                "aud": audience,
                "iat": now,
                "exp": now + expires_in,
            },
            separators=(",", ":"),
        ).encode()
    )
    if alg == "none":
        return f"{header}.{payload}."
    signing_key = sign_with if sign_with is not None else private_key
    sig = _b64url(signing_key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256()))
    return f"{header}.{payload}.{sig}"


# How JWT auth flow works:
#
# 1. Test generates: private_key → signs JWT token
# 2. Test gives SGW: public_key (as JWK) → SGW can verify token signatures
# 3. Test gives ES: the signed JWT token (inline or in file)
# 4. ES connects to SGW with: "Authorization: Bearer <token>" in WSS upgrade
# 5. SGW verifies: signature matches JWK, claims (iss, aud, exp) are valid
# 6. SGW identifies user as: "<provider>_<sub>" = "test-provider_user1"
