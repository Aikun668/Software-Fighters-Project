import pytest
from unittest.mock import AsyncMock, patch

from app.services.media import (
    OpenAIImageAdapter,
    MockImageAdapter,
    get_image_adapter,
    generate_image,
    ImageResult,
)


class TestMockImageAdapter:
    @pytest.mark.asyncio
    async def test_generate(self):
        adapter = MockImageAdapter()
        result = await adapter.generate("a cat", "1024x1024")
        assert result.url != ""
        assert result.mime_type == "image/png"
        assert result.width == 1024

    @pytest.mark.asyncio
    async def test_test_connectivity(self):
        adapter = MockImageAdapter()
        assert await adapter.test_connectivity() is True


class TestOpenAIImageAdapter:
    @pytest.mark.asyncio
    async def test_generate_no_api_key_raises(self):
        adapter = OpenAIImageAdapter(api_key="")
        with pytest.raises(RuntimeError):
            await adapter.generate("a cat")

    @pytest.mark.asyncio
    async def test_generate_success(self):
        from unittest.mock import Mock
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"url": "https://example.com/image.png"}]}
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            adapter = OpenAIImageAdapter(api_key="test-key")
            result = await adapter.generate("a cat")
            assert result.url == "https://example.com/image.png"

    @pytest.mark.asyncio
    async def test_test_connectivity_success(self):
        from unittest.mock import Mock
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            adapter = OpenAIImageAdapter(api_key="test-key")
            assert await adapter.test_connectivity() is True


class TestGetImageAdapter:
    def test_default_mock(self):
        with patch.dict("os.environ", {"IMAGE_ADAPTER": "mock"}, clear=False):
            adapter = get_image_adapter()
            assert isinstance(adapter, MockImageAdapter)

    def test_openai(self):
        with patch.dict("os.environ", {"IMAGE_ADAPTER": "openai"}, clear=False):
            adapter = get_image_adapter()
            assert isinstance(adapter, OpenAIImageAdapter)


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_generate_image(self):
        with patch.dict("os.environ", {"IMAGE_ADAPTER": "mock"}, clear=False):
            result = await generate_image("a cat")
            assert result.url != ""


class TestImageResult:
    def test_defaults(self):
        result = ImageResult()
        assert result.url == ""
        assert result.mime_type == "image/png"
        assert result.width == 0
        assert result.height == 0