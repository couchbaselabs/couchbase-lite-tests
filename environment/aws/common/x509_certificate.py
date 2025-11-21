import ipaddress
from datetime import datetime, timedelta, timezone
from typing import IO, cast

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives.asymmetric.types import (
    CertificateIssuerPrivateKeyTypes,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
    pkcs12,
)
from cryptography.x509 import (
    BasicConstraints,
    Certificate,
    CertificateBuilder,
    DNSName,
    ExtendedKeyUsage,
    ExtendedKeyUsageOID,
    GeneralName,
    IPAddress,
    Name,
    NameAttribute,
    NameOID,
    SubjectAlternativeName,
    random_serial_number,
)

_ALLOWED_ISSUER_KEY_TYPES = (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)


class CertKeyPair:
    """
    A class representing a certificate and its associated private key.
    """

    def __init__(
        self,
        certificate: Certificate,
        private_key: pkcs12.PKCS12PrivateKeyTypes,
    ):
        self.certificate = certificate
        self.private_key = private_key

    def pem_bytes(self) -> bytes:
        """
        Returns the certificate in PEM format.
        """
        return self.certificate.public_bytes(encoding=Encoding.PEM)

    def private_pem_bytes(self) -> bytes:
        """
        Returns the private key in PEM format.
        """
        return self.private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )


def load_private_key(pem_source: IO[bytes]) -> CertificateIssuerPrivateKeyTypes:
    pem_data = pem_source.read()
    private_key = load_pem_private_key(pem_data, password=None)
    if not isinstance(private_key, _ALLOWED_ISSUER_KEY_TYPES):
        raise TypeError(
            "Loaded private key is not a valid certificate issuer key type."
        )

    return cast(CertificateIssuerPrivateKeyTypes, private_key)


def create_certificate(
    CN: str,
    ca_certificate: Certificate | None,
    ca_private_key: CertificateIssuerPrivateKeyTypes | None,
    san_entries: set[str] | None = None,
) -> CertKeyPair:
    """
    Create a leaf certificate signed by the provided CA certificate/key.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = Name([NameAttribute(NameOID.COMMON_NAME, CN)])
    not_valid_before = datetime.now(timezone.utc)
    not_valid_after = not_valid_before + timedelta(days=1)

    if san_entries is None:
        san_entries = {CN}
    else:
        san_entries = san_entries | {CN}

    signing_key = ca_private_key if ca_private_key is not None else private_key
    issuer_name = ca_certificate.subject if ca_certificate is not None else subject

    san_list: list[GeneralName] = []
    for name in san_entries:
        try:
            # Try to parse as an IP address
            san_list.append(IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            # Fallback to DNS name
            san_list.append(DNSName(name))

    leaf_certificate = (
        CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(private_key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
        .add_extension(
            ExtendedKeyUsage(
                [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
            ),
            critical=False,
        )
        .add_extension(BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(SubjectAlternativeName(san_list), critical=False)
        .sign(signing_key, hashes.SHA256())
    )
    return CertKeyPair(leaf_certificate, private_key)
