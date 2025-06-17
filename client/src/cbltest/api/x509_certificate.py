from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import Encoding, BestAvailableEncryption, pkcs12
from cryptography.x509 import (
    BasicConstraints,
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
        self, certificate: Certificate, private_key: ec.EllipticCurvePrivateKey, *, password: str = "couchbase"
    ):
        self.certificate = certificate
        self.private_key = private_key
        self.password = password

    def pfx_bytes(self) -> bytes:
        """
        Returns the certificate and private key in PFX format.
        """
        ret_val = pkcs12.serialize_key_and_certificates(
            name=b"cbltest",
            key=self.private_key,
            cert=self.certificate,
            cas=None,
            encryption_algorithm=BestAvailableEncryption(self.password.encode('utf-8')),
        )

        return ret_val

    def pem_bytes(self) -> bytes:
        """
        Returns the certificate in PEM format.
        """
        return self.certificate.public_bytes(encoding=Encoding.PEM)


def create_ca_certificate(CN: str) -> CertKeyPair:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    #private_key = ec.generate_private_key(ec.SECP256R1())
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
        .sign(private_key, hashes.SHA256())
    )

    return CertKeyPair(ca_certificate, private_key)


def create_leaf_certificate(
    CN: str, *, issuer_data: CertKeyPair | None = None
) -> CertKeyPair:
    #private_key = ec.generate_private_key(ec.SECP256R1())
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
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
        .add_extension(
            ExtendedKeyUsage(
                [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
            ),
            critical=False,
        )
        .sign(signing_key, hashes.SHA256())
    )

    return CertKeyPair(leaf_certificate, private_key)
