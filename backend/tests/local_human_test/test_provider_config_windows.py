import os

import pytest

from deepaha.local_human_test.provider_config import WindowsDpapiProtector


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is Windows-only")
def test_windows_dpapi_current_user_round_trip_uses_non_plaintext_ciphertext() -> None:
    protector = WindowsDpapiProtector()
    secret = b"synthetic-dpapi-secret-not-real"

    ciphertext = protector.protect(secret)

    assert ciphertext != secret
    assert secret not in ciphertext
    assert protector.unprotect(ciphertext) == secret
