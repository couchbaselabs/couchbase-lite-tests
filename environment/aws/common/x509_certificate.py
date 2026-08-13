from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from cryptography.x509 import (
    BasicConstraints,
    Certificate,
    CertificateBuilder,
    ExtendedKeyUsage,
    Name,
    NameAttribute,
    NameOID,
    ObjectIdentifier,
    random_serial_number,
)


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


def create_cert(
    cn: str,
    ca: CertKeyPair | None = None,
    is_ca: bool = False,
    usages: Sequence[ObjectIdentifier] = (),
    valid_days: int = 365,
) -> CertKeyPair:
    """
    Create an RSA 2048 certificate / key pair.

    Args:
        cn: The common name to use for the subject.
        ca: The CA to sign with.  If None, the certificate is self-signed.
        is_ca: If True, add a critical BasicConstraints(ca=True) extension.
        usages: Extended key usage OIDs (e.g. ExtendedKeyUsageOID.SERVER_AUTH).
                If empty, no EKU extension is added.
        valid_days: How long the certificate is valid for, starting now.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = Name([NameAttribute(NameOID.COMMON_NAME, cn)])

    issuer = ca.certificate.subject if ca is not None else subject
    signing_key = ca.private_key if ca is not None else key

    not_valid_before = datetime.now(timezone.utc)
    builder = (
        CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_before + timedelta(days=valid_days))
    )

    if is_ca:
        builder = builder.add_extension(BasicConstraints(ca=True, path_length=None), critical=True)

    if usages:
        builder = builder.add_extension(ExtendedKeyUsage(list(usages)), critical=False)

    return CertKeyPair(builder.sign(signing_key, hashes.SHA256()), key)
