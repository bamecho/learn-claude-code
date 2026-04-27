"""Quick smoke test verifying provider base imports."""
from src.provider.base import ContentBlock, LLMResponse, LLMProvider


def test_imports_available():
    assert ContentBlock is not None
    assert LLMResponse is not None
    assert LLMProvider is not None
