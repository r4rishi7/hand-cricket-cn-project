import ipaddress
from pathlib import Path
from datetime import datetime, timezone, timedelta

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ── Config ──────────────────────────────────────────────────────────────────
SERVER_IP   = "192.168.0.139"   # set this to whatever IP the client will connect to
CERT_DAYS   = 36500             # ~100 years (forever validity)
KEY_BITS    = 2048              # RSA key size

# ── Paths ────────────────────────────────────────────────────────────────────
certs_dir = Path(__file__).resolve().parent / "certs"
certs_dir.mkdir(exist_ok=True)
key_path = certs_dir / "server.key"
crt_path = certs_dir / "server.crt"

# ── Private key ──────────────────────────────────────────────────────────────
print(f"Generating {KEY_BITS}-bit RSA private key...")
private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)

with open(key_path, "wb") as f:
    f.write(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

# ── Certificate subject / issuer ─────────────────────────────────────────────
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME,             "IN"),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME,   "Karnataka"),
    x509.NameAttribute(NameOID.LOCALITY_NAME,            "Bangalore"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME,        "Hand Cricket"),
    x509.NameAttribute(NameOID.COMMON_NAME,              SERVER_IP),   # CN = server IP
])

# ── Subject Alternative Names (SAN) ─────────────────────────────────────────
# Dedupe in case SERVER_IP is already 127.0.0.1 (was listed twice before).
san_ips = {ipaddress.IPv4Address(SERVER_IP), ipaddress.IPv4Address("127.0.0.1")}
san_entries = [x509.IPAddress(ip) for ip in sorted(san_ips)]
san_entries.append(x509.DNSName("localhost"))
san = x509.SubjectAlternativeName(san_entries)

# ── Build & sign certificate ─────────────────────────────────────────────────
now = datetime.now(timezone.utc)

certificate = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(private_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + timedelta(days=CERT_DAYS))
    .add_extension(san, critical=False)
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    # These two extensions aren't strictly required by Python's ssl module,
    # but they make this a well-formed server cert (some stricter clients /
    # OpenSSL CLI tools will warn or refuse without them).
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            key_encipherment=True,
            content_commitment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(
        x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
        critical=False,
    )
    .sign(private_key, hashes.SHA256())
)

with open(crt_path, "wb") as f:
    f.write(certificate.public_bytes(serialization.Encoding.PEM))

print("Certificate generated successfully!")
print(f"  Key : {key_path}")
print(f"  Cert: {crt_path}")
print(f"  Valid for {CERT_DAYS} days (~{CERT_DAYS//365} years)")
print(f"  SAN entries: {', '.join(str(e.value) for e in san_entries)}")