import pytest
from unittest.mock import patch, MagicMock

from expense_tracker.config import Settings
from expense_tracker.services.ai import (
    GeminiProvider,
    ExternalAIOptInRequired,
    MissingAPIKeyError,
    AIProviderError,
    TransactionContext,
)

@pytest.fixture
def base_settings():
    settings = Settings()
    settings.privacy.allow_external_ai = True
    settings.ai.provider = "gemini"
    settings.ai.model = "gemini-3.7-flash"
    return settings

@pytest.fixture
def tx_context():
    return TransactionContext(
        transaction_id="tx-123",
        amount=150.0,
        merchant_raw="STARBUCKS",
        merchant_normalized="Starbucks",
        description="Coffee",
        direction="debit",
        account="checking"
    )

@pytest.fixture
def categories_sample():
    return [
        {
            "id": "cat-1",
            "name": "Food & Dining",
            "subcategories": [{"id": "sub-1", "name": "Coffee"}],
        }
    ]

def test_ai_disabled(base_settings):
    base_settings.privacy.allow_external_ai = False
    with pytest.raises(ExternalAIOptInRequired):
        GeminiProvider(base_settings)

@patch("os.getenv", return_value=None)
def test_missing_api_key(mock_getenv, base_settings):
    with pytest.raises(MissingAPIKeyError):
        GeminiProvider(base_settings)

@patch("os.getenv", return_value="dummy_key")
@patch("expense_tracker.services.ai.gemini_provider.genai.Client")
def test_successful_classification(mock_client_class, mock_getenv, base_settings, tx_context, categories_sample):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = '{"category_id": "cat-1", "subcategory_id": "sub-1", "confidence": 0.9, "signals": ["Coffee shop"]}'
    mock_client.models.generate_content.return_value = mock_response
    
    provider = GeminiProvider(base_settings)
    result = provider.classify_transaction(tx_context, categories_sample)
    
    assert result.category_id == "cat-1"
    assert result.subcategory_id == "sub-1"
    assert result.confidence == 0.9
    assert result.signals == ["Coffee shop"]
    
    # Verify the genai Client was called correctly
    mock_client.models.generate_content.assert_called_once()
    kwargs = mock_client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.7-flash"
    assert kwargs["config"].response_mime_type == "application/json"

@patch("os.getenv", return_value="dummy_key")
@patch("expense_tracker.services.ai.gemini_provider.genai.Client")
def test_malformed_model_output(mock_client_class, mock_getenv, base_settings, tx_context, categories_sample):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = '{"invalid_json":'
    mock_client.models.generate_content.return_value = mock_response
    
    provider = GeminiProvider(base_settings)
    with pytest.raises(AIProviderError, match="schema error"):
        provider.classify_transaction(tx_context, categories_sample)

@patch("os.getenv", return_value="dummy_key")
@patch("expense_tracker.services.ai.gemini_provider.genai.Client")
def test_invalid_category_ids(mock_client_class, mock_getenv, base_settings, tx_context, categories_sample):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    # Missing required category_id
    mock_response.text = '{"confidence": 0.9, "signals": ["Coffee shop"]}'
    mock_client.models.generate_content.return_value = mock_response
    
    provider = GeminiProvider(base_settings)
    with pytest.raises(AIProviderError, match="schema error"):
        provider.classify_transaction(tx_context, categories_sample)

@patch("os.getenv", return_value="dummy_key")
@patch("expense_tracker.services.ai.gemini_provider.genai.Client")
def test_gemini_api_errors(mock_client_class, mock_getenv, base_settings, tx_context, categories_sample):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_client.models.generate_content.side_effect = Exception("API rate limit exceeded")
    
    provider = GeminiProvider(base_settings)
    with pytest.raises(AIProviderError, match="API rate limit exceeded"):
        provider.classify_transaction(tx_context, categories_sample)

