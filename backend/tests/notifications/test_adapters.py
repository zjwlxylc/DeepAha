import pytest

from deepaha.notifications.adapters import (
    PermanentDeliveryError,
    TransientDeliveryError,
)


@pytest.mark.parametrize("error_type", [TransientDeliveryError, PermanentDeliveryError])
def test_delivery_errors_expose_only_bounded_stable_codes(
    error_type: type[TransientDeliveryError] | type[PermanentDeliveryError],
) -> None:
    error = error_type("TEST_DELIVERY_FAILURE")

    assert error.code == "TEST_DELIVERY_FAILURE"
    assert str(error) == "TEST_DELIVERY_FAILURE"


@pytest.mark.parametrize("code", ["", "lowercase", "A" * 65, "BAD-CODE"])
def test_delivery_errors_reject_unbounded_codes(code: str) -> None:
    with pytest.raises(ValueError, match="delivery error code"):
        TransientDeliveryError(code)
