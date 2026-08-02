from unittest.mock import MagicMock
import pytest
import anthropic

from goplay_core.models import get_active_haiku_model


def test_get_active_haiku_model_selects_latest_haiku():
    """Should select the highest/latest haiku model from API response."""
    mock_client = MagicMock(spec=anthropic.Anthropic)
    
    # Mock return list from Anthropic models API
    m1 = MagicMock()
    m1.id = "claude-3-haiku-20240307"
    m2 = MagicMock()
    m2.id = "claude-3-5-haiku-20241022"
    m3 = MagicMock()
    m3.id = "claude-3-5-sonnet-20241022"
    
    mock_client.models.list.return_value.data = [m1, m2, m3]

    selected = get_active_haiku_model(mock_client)
    assert selected == "claude-3-5-haiku-20241022"


def test_get_active_haiku_model_fallback_to_first_available():
    """Should fallback to available_ids[0] if no haiku model exists."""
    mock_client = MagicMock(spec=anthropic.Anthropic)
    m1 = MagicMock()
    m1.id = "claude-3-5-sonnet-20241022"
    
    mock_client.models.list.return_value.data = [m1]

    selected = get_active_haiku_model(mock_client)
    assert selected == "claude-3-5-sonnet-20241022"


def test_get_active_haiku_model_exception_fallback():
    """Should fallback to hardcoded default model ID if API call fails."""
    mock_client = MagicMock(spec=anthropic.Anthropic)
    mock_client.models.list.side_effect = Exception("API Connection Failed")

    selected = get_active_haiku_model(mock_client)
    assert selected == "claude-3-haiku-20240307"
