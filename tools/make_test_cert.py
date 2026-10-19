"""Make a self-signed test certificate for the redirector host.

The game will almost certainly REJECT this (it only trusts EA's own GOS CAs).
The point is to see *how* it rejects it - the server logs the TLS alert.
Usage: py -3 tools/make_test_cert.py   (needs: pip install cryptography)
"""

import datetime as dt
import sys
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    sys.exit("Needs the 'cryptography' package:  py -3 -m pip install cryptography")

HOSTS = ["spring18.gosredirector.ea.com", "localhost"]
out = Path(__file__).resolve().parent.parent / "certs"
out.mkdir(exist_ok=True)

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0]),
                  x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Madden Forever test")])
now = dt.datetime.now(dt.timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), critical=False)
        .sign(key, hashes.SHA256()))

(out / "server.key").write_bytes(key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption()))
(out / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print(f"wrote {out / 'server.crt'} and {out / 'server.key'}")
