"""X.509 certificate helpers for Edge Server mTLS tests.

Generates an in-memory CA and CA-signed server/client certificates using
`cryptography` (the same library `jwt_helper.py` uses), so tests can exercise
mutual-TLS (mTLS) edge-to-edge replication without shipping fixture certs.

Key points for the mTLS scenario:
  * The CA signs both the target's server cert and the source's client cert.
  * The server cert must carry the target hostname/IP as a SubjectAltName (SAN)
    so the replicating client can verify it against `trusted_root_certs`.
  * The client cert carries a clientAuth EKU; the server cert a serverAuth EKU.
"""

import datetime
import ipaddress

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _san_entry(value: str) -> x509.GeneralName:
    """DNSName for a hostname, IPAddress for an IP literal."""
    try:
        return x509.IPAddress(ipaddress.ip_address(value))
    except ValueError:
        return x509.DNSName(value)


def generate_ca(
    common_name: str = "Edge Test CA",
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Generate a self-signed CA. Returns (cert, private_key)."""
    key = _rsa_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def generate_signed_cert(
    ca_cert: x509.Certificate,
    ca_key: rsa.RSAPrivateKey,
    common_name: str,
    sans: list[str] | None = None,
    client: bool = False,
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Generate a CA-signed leaf cert. Returns (cert, private_key).

    Args:
        common_name: CN to put in the subject.
        sans: hostnames/IPs to add as SubjectAltNames (needed for the server cert).
        client: True → clientAuth EKU (for the replicating source);
                False → serverAuth EKU (for the target).
    """
    key = _rsa_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    eku = x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH] if client else [ExtendedKeyUsageOID.SERVER_AUTH])
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(eku, critical=False)
    )
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName([_san_entry(s) for s in sans]), critical=False)
    return builder.sign(ca_key, hashes.SHA256()), key


def cert_pem(cert: x509.Certificate) -> str:
    """PEM-encode a certificate."""
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def key_pem(key: rsa.RSAPrivateKey) -> str:
    """PEM-encode an unencrypted PKCS#8 private key ("BEGIN PRIVATE KEY")."""
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
