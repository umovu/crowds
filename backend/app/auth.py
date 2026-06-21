"""
Supabase JWT verification.

The frontend signs in with Supabase and sends the access token as
`Authorization: Bearer <jwt>` on every /api request. This module verifies that
token and exposes the caller via `flask.g.user`.

Verification strategy (handles both Supabase signing modes):
  - Asymmetric keys (RS256/ES256, default for new projects): verify against the
    project JWKS endpoint `/auth/v1/.well-known/jwks.json` (cached by PyJWKClient).
  - Legacy symmetric key (HS256): verify with the shared JWT secret if
    SUPABASE_JWT_SECRET is set.

Config (env):
  SUPABASE_URL          e.g. https://<ref>.supabase.co   (required)
  SUPABASE_JWT_SECRET   legacy HS256 secret               (optional)
  AUTH_DISABLED         set to 'true' to bypass auth in local dev (optional)
"""

import os
import functools

import jwt
from jwt import PyJWKClient
from flask import request, jsonify, g

# Supabase tokens carry aud="authenticated" for signed-in users.
_EXPECTED_AUDIENCE = "authenticated"

_jwk_client = None


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    return url


def _get_jwk_client():
    """Lazily build a cached JWKS client for the project's asymmetric keys."""
    global _jwk_client
    if _jwk_client is None:
        url = _supabase_url()
        if not url:
            return None
        jwks_url = f"{url}/auth/v1/.well-known/jwks.json"
        # PyJWKClient caches keys in-memory and refreshes on unknown kid.
        _jwk_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwk_client


def _decode(token: str) -> dict:
    """Verify and decode a Supabase access token. Raises jwt exceptions on failure."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    if alg == "HS256":
        secret = os.environ.get("SUPABASE_JWT_SECRET")
        if not secret:
            raise jwt.InvalidTokenError(
                "HS256 token received but SUPABASE_JWT_SECRET is not configured"
            )
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=_EXPECTED_AUDIENCE,
        )

    # Asymmetric (RS256 / ES256): fetch the matching public key from JWKS.
    client = _get_jwk_client()
    if client is None:
        raise jwt.InvalidTokenError("SUPABASE_URL is not configured")
    signing_key = client.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256", "ES256"],
        audience=_EXPECTED_AUDIENCE,
    )


def _extract_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return None


def verify_request():
    """
    Verify the bearer token on the current request.

    On success, populates flask.g.user with the decoded claims and returns None.
    On failure, returns a (response, status) tuple to short-circuit the request.
    """
    if os.environ.get("AUTH_DISABLED", "").lower() == "true":
        g.user = {"sub": "dev", "email": "dev@local", "aud": _EXPECTED_AUDIENCE}
        return None

    token = _extract_token()
    if not token:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        claims = _decode(token)
    except jwt.ExpiredSignatureError:
        return jsonify({"success": False, "error": "Token expired"}), 401
    except jwt.InvalidTokenError as e:
        return jsonify({"success": False, "error": f"Invalid token: {e}"}), 401
    except Exception as e:  # JWKS fetch error, etc.
        return jsonify({"success": False, "error": f"Auth error: {e}"}), 401

    g.user = claims
    return None


def require_auth(fn):
    """Decorator form, for protecting individual routes if needed."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        failed = verify_request()
        if failed is not None:
            return failed
        return fn(*args, **kwargs)
    return wrapper
