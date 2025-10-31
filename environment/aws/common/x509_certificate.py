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
    Certificate,
    CertificateBuilder,
    ExtendedKeyUsage,
    ExtendedKeyUsageOID,
    Name,
    NameAttribute,
    NameOID,
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


def create_self_signed_certificate(CN: str) -> CertKeyPair:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    cn_attribute = Name([NameAttribute(NameOID.COMMON_NAME, CN)])
    not_valid_before = datetime.now(timezone.utc)
    not_valid_after = not_valid_before + timedelta(days=1)
    issuer_name = cn_attribute
    signing_key = private_key

    leaf_certificate = (
        CertificateBuilder()
        .subject_name(cn_attribute)
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
        .sign(signing_key, hashes.SHA256())
    )

    return CertKeyPair(leaf_certificate, private_key)
