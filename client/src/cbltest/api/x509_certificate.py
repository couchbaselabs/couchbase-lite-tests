from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, pkcs12
from cryptography.x509 import (
    BasicConstraints,
    Certificate,
    CertificateBuilder,
    Name,
    NameAttribute,
    NameOID,
    random_serial_number,
)


class CertKeyPair:
    """
    A class representing a certificate and its associated private key.
    """

    def __init__(self, certificate: Certificate, private_key: Ed25519PrivateKey):
        self.certificate = certificate
        self.private_key = private_key

    def pfx_bytes(self) -> bytes:
        """
        Returns the certificate and private key in PFX format.
        """
        ret_val = pkcs12.serialize_key_and_certificates(
            name=b"cbltest",
            key=self.private_key,
            cert=self.certificate,
            cas=None,
            encryption_algorithm=NoEncryption(),
        )

        return ret_val

    def pem_bytes(self) -> bytes:
        """
        Returns the certificate in PEM format.
        """
        return self.certificate.public_bytes(encoding=Encoding.PEM)


def create_ca_certificate(CN: str) -> CertKeyPair:
    private_key = Ed25519PrivateKey.generate()
    cn_attribute = Name([NameAttribute(NameOID.COMMON_NAME, CN)])
    not_valid_before = datetime.now(timezone.utc)
    not_valid_after = not_valid_before + timedelta(days=1)

    ca_certificate: Certificate = (
        CertificateBuilder()
        .subject_name(cn_attribute)
        .issuer_name(cn_attribute)
        .public_key(private_key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
        .add_extension(BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, None)
    )

    return CertKeyPair(ca_certificate, private_key)


def create_leaf_certificate(
    CN: str, *, issuer_data: CertKeyPair | None = None
) -> CertKeyPair:
    private_key = Ed25519PrivateKey.generate()
    cn_attribute = Name([NameAttribute(NameOID.COMMON_NAME, CN)])
    not_valid_before = datetime.now(timezone.utc)
    not_valid_after = not_valid_before + timedelta(days=1)
    issuer_name = issuer_data.certificate.subject if issuer_data else cn_attribute
    signing_key = issuer_data.private_key if issuer_data else private_key

    leaf_certificate = (
        CertificateBuilder()
        .subject_name(cn_attribute)
        .issuer_name(issuer_name)
        .public_key(private_key.public_key())
        .serial_number(random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
        .sign(signing_key, None)
    )

    return CertKeyPair(leaf_certificate, private_key)
