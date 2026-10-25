import pytest
from pydantic import ValidationError

from core.schemas import ProjectCreate
from services.project_service import _hash_access_code, verify_access_code


def test_access_code_requires_at_least_eight_characters() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(
            name="测试项目",
            product_name="测试产品",
            access_code="short",
            markets=["US"],
        )


def test_access_code_is_salted_and_verifiable() -> None:
    first = _hash_access_code("demo2026")
    second = _hash_access_code("demo2026")
    assert first != second
    assert "demo2026" not in first
    assert verify_access_code("demo2026", first)
    assert not verify_access_code("wrong-code", first)

