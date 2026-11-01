"""
Omnix Vendor Plugin System — Cryptographic Trust Engine (Milestone 1)
Governing Specification: OMNIX_VENDOR_PLUGIN_ARCHITECTURE_SPECIFICATION.md Section 27.2

Implements deterministic Ed25519 digital signature verification over canonical
META-INF/MANIFEST.MF bytes, host trust-store management with strict separation
between production and development trust domains, explicit developer-key authorization,
and fail-closed rejection of unsigned, malformed, revoked, or untrusted packages.

CRITICAL INVARIANT:
Signature verification occurs strictly BEFORE any plugin code is extracted to
permanent storage, imported into Python memory, or executed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


# Ed25519 signatures are exactly 64 bytes
ED25519_SIGNATURE_LENGTH_BYTES = 64
# Ed25519 raw public keys are exactly 32 bytes
ED25519_PUBLIC_KEY_LENGTH_BYTES = 32

HEX_64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


class TrustStatus(str, Enum):
    """Categorized outcome of cryptographic signature and trust-store evaluation."""
    TRUSTED_PRODUCTION = "TRUSTED_PRODUCTION"
    TRUSTED_DEVELOPMENT = "TRUSTED_DEVELOPMENT"
    REJECTED_MISSING_SIGNATURE = "REJECTED_MISSING_SIGNATURE"
    REJECTED_INVALID_SIGNATURE = "REJECTED_INVALID_SIGNATURE"
    REJECTED_MALFORMED_SIGNATURE = "REJECTED_MALFORMED_SIGNATURE"
    REJECTED_UNKNOWN_KEY = "REJECTED_UNKNOWN_KEY"
    REJECTED_REVOKED_KEY = "REJECTED_REVOKED_KEY"
    REJECTED_UNAUTHORIZED_DEV_KEY = "REJECTED_UNAUTHORIZED_DEV_KEY"
    REJECTED_PROD_DEV_MISMATCH = "REJECTED_PROD_DEV_MISMATCH"
    REJECTED_MISSING_TRUST_STORE = "REJECTED_MISSING_TRUST_STORE"
    REJECTED_INVALID_METADATA = "REJECTED_INVALID_METADATA"


@dataclass(frozen=True)
class TrustVerificationResult:
    """Immutable outcome of trust evaluation."""
    is_trusted: bool
    status: TrustStatus
    key_id: Optional[str] = None
    fingerprint: Optional[str] = None
    publisher_name: Optional[str] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def raise_for_errors(self) -> None:
        """Raise TrustVerificationError if package is not trusted."""
        if not self.is_trusted:
            raise TrustVerificationError(
                self.error_message or f"Trust verification failed: {self.status.value}",
                status=self.status,
                key_id=self.key_id,
                details=self.details,
            )


class TrustVerificationError(Exception):
    """Raised when package signature or publisher trust verification fails."""
    def __init__(
        self,
        message: str,
        status: TrustStatus,
        key_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(f"[{status.value}] {message}")
        self.status = status
        self.key_id = key_id
        self.details = details or {}


class TrustEngine:
    """
    Evaluates cryptographic authenticity and authorization of plugin packages.

    Enforces:
    1. Detached Ed25519 signature verification over canonical META-INF/MANIFEST.MF bytes.
    2. Strict separation between Production Trust Store and Development Trust Store.
    3. Production mode (OMNIX_ENV=production or unset) strictly ignores development keys.
    4. Development mode (OMNIX_ENV=development) requires explicit authorization in authorized_keys.json.
    5. Independent key resolution: public keys are loaded solely from host trust stores,
       never trusted from within the package archive.
    6. Revocation enforcement against local revocation blacklists.
    """

    def __init__(
        self,
        prod_trust_store: Optional[Union[str, Path]] = None,
        dev_trust_store: Optional[Union[str, Path]] = None,
        env: Optional[str] = None,
    ):
        base_dir = Path(__file__).resolve().parent
        self.prod_trust_store = Path(prod_trust_store) if prod_trust_store else (base_dir / "trust_store")
        try:
            from config import get_app_dir
            persistent_base = Path(get_app_dir()).resolve()
        except Exception:
            persistent_base = base_dir.parent.parent
        self.dev_trust_store = Path(dev_trust_store) if dev_trust_store else (persistent_base / 'data' / 'plugins' / 'dev_trust_store')

        if env is not None:
            self.env = env.strip().lower()
        else:
            self.env = os.environ.get("OMNIX_ENV", "production").strip().lower()

    @property
    def is_production(self) -> bool:
        """True if running under production trust policy."""
        return self.env != "development"

    @staticmethod
    def compute_fingerprint(public_key: ed25519.Ed25519PublicKey) -> str:
        """Compute the canonical SHA-256 hex fingerprint of an Ed25519 public key."""
        raw_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(raw_bytes).hexdigest()

    def _parse_public_key_file(self, key_path: Path) -> ed25519.Ed25519PublicKey:
        """Parse an Ed25519 public key from PEM, raw binary (32 bytes), or hex format."""
        with open(key_path, "rb") as f:
            data = f.read()

        # 1. Try PEM format
        if b"BEGIN PUBLIC KEY" in data:
            key = serialization.load_pem_public_key(data)
            if not isinstance(key, ed25519.Ed25519PublicKey):
                raise ValueError(f"Key in '{key_path}' is not an Ed25519 public key")
            return key

        # 2. Try raw 32-byte binary
        if len(data) == ED25519_PUBLIC_KEY_LENGTH_BYTES:
            return ed25519.Ed25519PublicKey.from_public_bytes(data)

        # 3. Try 64-char hex string
        clean_text = data.decode("utf-8", errors="ignore").strip()
        if len(clean_text) == 64 and HEX_64_REGEX.match(clean_text):
            raw_bytes = bytes.fromhex(clean_text)
            return ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)

        raise ValueError(f"Unsupported public key format in '{key_path}': must be PEM, 32-byte raw, or 64-char hex")

    def _load_revocations(self, store_dir: Path) -> Set[str]:
        """Load set of revoked key IDs, fingerprints, or digests from revocations.json."""
        rev_file = store_dir / "revocations.json"
        if not rev_file.is_file():
            return set()

        try:
            with open(rev_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            revoked = set()
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        revoked.add(item.strip().lower())
            elif isinstance(data, dict):
                for item in data.get("revoked_keys", []):
                    if isinstance(item, str):
                        revoked.add(item.strip().lower())
            return revoked
        except Exception:
            # If revocation list is corrupted, fail-closed by treating all as potentially revoked
            return {"*"}

    def _load_authorized_dev_keys(self) -> Set[str]:
        """Load set of authorized development key IDs / fingerprints."""
        auth_file = self.dev_trust_store / "authorized_keys.json"
        if not auth_file.is_file():
            return set()

        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            auth_set = set()
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        auth_set.add(item.strip().lower())
            elif isinstance(data, dict):
                for item in data.get("authorized_keys", []):
                    if isinstance(item, str):
                        auth_set.add(item.strip().lower())
            return auth_set
        except Exception:
            return set()

    def find_key(self, key_id: str) -> Tuple[Optional[ed25519.Ed25519PublicKey], Optional[TrustStatus], Optional[str]]:
        """
        Locate public key by key_id across authorized trust stores based on environment.

        Returns:
            Tuple of (public_key, trust_tier_status, error_reason)
        """
        if not key_id or not isinstance(key_id, str) or not key_id.strip():
            return None, None, "Invalid or empty key_id"

        clean_id = key_id.strip()

        # 1. Check Production Trust Store
        if self.prod_trust_store.is_dir():
            prod_revocations = self._load_revocations(self.prod_trust_store)
            if "*" in prod_revocations or clean_id.lower() in prod_revocations:
                return None, TrustStatus.REJECTED_REVOKED_KEY, f"Production key '{clean_id}' is revoked"

            prod_key_path = self.prod_trust_store / f"{clean_id}.pub"
            if prod_key_path.is_file():
                try:
                    pub_key = self._parse_public_key_file(prod_key_path)
                    fp = self.compute_fingerprint(pub_key)
                    if fp.lower() in prod_revocations:
                        return None, TrustStatus.REJECTED_REVOKED_KEY, f"Production key fingerprint '{fp}' is revoked"
                    return pub_key, TrustStatus.TRUSTED_PRODUCTION, None
                except Exception as exc:
                    return None, TrustStatus.REJECTED_INVALID_METADATA, f"Failed to parse production key: {exc}"

        # 2. Check Development Trust Store
        dev_key_path = self.dev_trust_store / f"{clean_id}.pub" if self.dev_trust_store.is_dir() else None
        dev_key_exists = dev_key_path is not None and dev_key_path.is_file()

        if self.is_production:
            if dev_key_exists:
                # Key exists in dev store, but we are running in production mode
                return None, TrustStatus.REJECTED_PROD_DEV_MISMATCH, (
                    f"Key '{clean_id}' exists in development trust store but is strictly rejected in production mode. "
                    "Production builds accept only official production keys."
                )
            return None, TrustStatus.REJECTED_UNKNOWN_KEY, f"Key '{clean_id}' not found in production trust store"

        # Development mode (OMNIX_ENV=development)
        if dev_key_exists and dev_key_path:
            dev_revocations = self._load_revocations(self.dev_trust_store)
            if "*" in dev_revocations or clean_id.lower() in dev_revocations:
                return None, TrustStatus.REJECTED_REVOKED_KEY, f"Development key '{clean_id}' is revoked"

            authorized_dev_keys = self._load_authorized_dev_keys()
            try:
                pub_key = self._parse_public_key_file(dev_key_path)
                fp = self.compute_fingerprint(pub_key)
                if fp.lower() in dev_revocations:
                    return None, TrustStatus.REJECTED_REVOKED_KEY, f"Development key fingerprint '{fp}' is revoked"

                # Check explicit authorization in authorized_keys.json
                if clean_id.lower() not in authorized_dev_keys and fp.lower() not in authorized_dev_keys:
                    return None, TrustStatus.REJECTED_UNAUTHORIZED_DEV_KEY, (
                        f"Development key '{clean_id}' (fingerprint {fp[:16]}...) is not authorized. "
                        "Key must be explicitly registered in authorized_keys.json to establish development trust."
                    )
                return pub_key, TrustStatus.TRUSTED_DEVELOPMENT, None
            except Exception as exc:
                return None, TrustStatus.REJECTED_INVALID_METADATA, f"Failed to parse development key: {exc}"

        return None, TrustStatus.REJECTED_UNKNOWN_KEY, f"Key '{clean_id}' not found in production or development trust store"

    def verify_manifest_signature(
        self,
        manifest_mf_bytes: bytes,
        signature_bytes: Optional[bytes],
        key_id: Optional[str],
        publisher_name: Optional[str] = None,
    ) -> TrustVerificationResult:
        """
        Verify Ed25519 signature over canonical META-INF/MANIFEST.MF bytes.

        Args:
            manifest_mf_bytes: The canonical raw bytes of META-INF/MANIFEST.MF.
            signature_bytes: The 64-byte raw detached signature from META-INF/SIGNATURE.sig.
            key_id: The publisher key identifier from manifest.json.
            publisher_name: Optional claimed publisher name for diagnostic reporting.

        Returns:
            TrustVerificationResult with status and cryptographic evidence.
        """
        # Gate 1: Check signature presence
        if not signature_bytes:
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_MISSING_SIGNATURE,
                key_id=key_id,
                publisher_name=publisher_name,
                error_message="Package is unsigned (missing META-INF/SIGNATURE.sig)",
            )

        # Gate 2: Check signature format and length
        if len(signature_bytes) != ED25519_SIGNATURE_LENGTH_BYTES:
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_MALFORMED_SIGNATURE,
                key_id=key_id,
                publisher_name=publisher_name,
                error_message=(
                    f"Signature size ({len(signature_bytes)} bytes) is invalid; "
                    f"Ed25519 signatures must be exactly {ED25519_SIGNATURE_LENGTH_BYTES} bytes"
                ),
            )

        # Gate 3: Check key_id presence
        if not key_id or not key_id.strip():
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_INVALID_METADATA,
                key_id=key_id,
                publisher_name=publisher_name,
                error_message="Manifest missing required publisher.key_id",
            )

        clean_key_id = key_id.strip()

        # Gate 4: Resolve trusted public key
        pub_key, trust_tier, error_reason = self.find_key(clean_key_id)
        if pub_key is None or trust_tier is None:
            status = trust_tier or TrustStatus.REJECTED_UNKNOWN_KEY
            return TrustVerificationResult(
                is_trusted=False,
                status=status,
                key_id=clean_key_id,
                publisher_name=publisher_name,
                error_message=error_reason or "Public key not trusted",
            )

        fingerprint = self.compute_fingerprint(pub_key)

        # Gate 5: Perform cryptographic Ed25519 verification
        try:
            pub_key.verify(signature_bytes, manifest_mf_bytes)
        except InvalidSignature:
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_INVALID_SIGNATURE,
                key_id=clean_key_id,
                fingerprint=fingerprint,
                publisher_name=publisher_name,
                error_message=(
                    f"Ed25519 cryptographic signature verification failed for key '{clean_key_id}'. "
                    "Package payload or META-INF/MANIFEST.MF was altered or signed with an unmatching private key."
                ),
            )
        except Exception as exc:
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_INVALID_SIGNATURE,
                key_id=clean_key_id,
                fingerprint=fingerprint,
                publisher_name=publisher_name,
                error_message=f"Cryptographic verification error: {exc}",
            )

        # Verified authentic and authorized
        return TrustVerificationResult(
            is_trusted=True,
            status=trust_tier,
            key_id=clean_key_id,
            fingerprint=fingerprint,
            publisher_name=publisher_name,
            details={"environment": self.env, "trust_store": str(self.prod_trust_store if trust_tier == TrustStatus.TRUSTED_PRODUCTION else self.dev_trust_store)},
        )

    def verify_archive(
        self,
        archive_path: Union[str, Path],
        key_id: Optional[str] = None,
        publisher_name: Optional[str] = None,
    ) -> TrustVerificationResult:
        """
        Verify cryptographic publisher signature of a .xpl plugin archive.
        Reads META-INF/MANIFEST.MF, META-INF/SIGNATURE.sig, and manifest.json if key_id is omitted.
        """
        path_obj = Path(archive_path)
        if not path_obj.is_file():
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_INVALID_METADATA,
                key_id=key_id,
                publisher_name=publisher_name,
                error_message=f"Archive file not found: {path_obj}",
            )

        signature_bytes: Optional[bytes] = None
        manifest_mf_bytes: Optional[bytes] = None

        try:
            with zipfile.ZipFile(path_obj, "r") as zf:
                namelist = zf.namelist()
                if "META-INF/SIGNATURE.sig" in namelist:
                    signature_bytes = zf.read("META-INF/SIGNATURE.sig")
                if "META-INF/MANIFEST.MF" in namelist:
                    manifest_mf_bytes = zf.read("META-INF/MANIFEST.MF")
                if not key_id and "manifest.json" in namelist:
                    try:
                        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                        pub_sec = manifest_data.get("publisher", {})
                        if isinstance(pub_sec, dict):
                            key_id = pub_sec.get("key_id")
                            if not publisher_name:
                                publisher_name = pub_sec.get("name")
                    except Exception:
                        pass
        except Exception as exc:
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_INVALID_METADATA,
                key_id=key_id,
                publisher_name=publisher_name,
                error_message=f"Failed to read archive signature members: {exc}",
            )

        if not manifest_mf_bytes:
            return TrustVerificationResult(
                is_trusted=False,
                status=TrustStatus.REJECTED_MISSING_SIGNATURE,
                key_id=key_id,
                publisher_name=publisher_name,
                error_message="Archive missing canonical META-INF/MANIFEST.MF",
            )

        return self.verify_manifest_signature(
            manifest_mf_bytes=manifest_mf_bytes,
            signature_bytes=signature_bytes,
            key_id=key_id,
            publisher_name=publisher_name,
        )
