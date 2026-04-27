from unittest.mock import MagicMock, patch
from src.provider.anthropic_provider import AnthropicProvider
from src.provider.base import LLMResponse, ContentBlock


def test_chat_text_response():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Hello")]
    mock_response.stop_reason = "end_turn"
    mock_response.usage = None
    mock_client.messages.create.return_value = mock_response
    mock_client_cls.return_value = mock_client

    with patch("src.provider.anthropic_provider.Anthropic", mock_client_cls):
        provider = AnthropicProvider(api_key="test-key")
        result = provider.chat([{"role": "user", "content": "Hi"}])

    assert isinstance(result, LLMResponse)
    assert result.stop_reason == "end_turn"
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert result.content[0].text == "Hello"


def test_chat_tool_use_response():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock(type="tool_use", id="tu_1", input={"path": "x"})
    mock_tool_use.name = "read"
    mock_response.content = [
        MagicMock(type="text", text="I'll help"),
        mock_tool_use,
    ]
    mock_response.stop_reason = "tool_use"
    mock_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
    )
    mock_client.messages.create.return_value = mock_response
    mock_client_cls.return_value = mock_client

    with patch("src.provider.anthropic_provider.Anthropic", mock_client_cls):
        provider = AnthropicProvider(api_key="test-key")
        result = provider.chat([{"role": "user", "content": "Read file"}])

    assert result.stop_reason == "tool_use"
    assert len(result.content) == 2
    assert result.content[1].type == "tool_use"
    assert result.content[1].id == "tu_1"
    assert result.content[1].name == "read"
    assert result.content[1].input == {"path": "x"}
    assert result.usage == {"input_tokens": 10, "output_tokens": 5}


def test_chat_error_handling():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Network error")
    mock_client_cls.return_value = mock_client

    with patch("src.provider.anthropic_provider.Anthropic", mock_client_cls):
        provider = AnthropicProvider(api_key="test-key")
        result = provider.chat([{"role": "user", "content": "Hi"}])

    assert result.stop_reason == "error"
    assert "Network error" in result.content[0].text


def test_chat_max_tokens_stop_reason():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Cut off")]
    mock_response.stop_reason = "max_tokens"
    mock_response.usage = None
    mock_client.messages.create.return_value = mock_response
    mock_client_cls.return_value = mock_client

    with patch("src.provider.anthropic_provider.Anthropic", mock_client_cls):
        provider = AnthropicProvider(api_key="test-key")
        result = provider.chat([{"role": "user", "content": "Long prompt"}])

    assert result.stop_reason == "max_tokens"
