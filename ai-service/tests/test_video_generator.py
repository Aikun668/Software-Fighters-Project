import pytest
from unittest.mock import AsyncMock, patch

from app.services.video_generator import VideoGenerator, SlideData, VideoResult
from app.services.media.tts_adapter import TTSResult, MockTTSAdapter


@pytest.fixture
def video_gen():
    return VideoGenerator(use_mock=True)


class TestVideoGeneratorMock:
    @pytest.mark.asyncio
    async def test_generate_mock_slides(self, video_gen):
        result = await video_gen.generate("机器学习入门", "基础概念", num_slides=3)
        assert isinstance(result, VideoResult)
        assert len(result.slides) == 3
        assert result.slides[0].title == "机器学习入门 导论"
        assert result.format == "pptx"

    @pytest.mark.asyncio
    async def test_generate_slides_count(self, video_gen):
        result = await video_gen.generate("测试主题", "测试内容", num_slides=5)
        assert len(result.slides) == 3

    @pytest.mark.asyncio
    async def test_slide_data_structure(self, video_gen):
        result = await video_gen.generate("主题", "内容")
        slide = result.slides[0]
        assert slide.title
        assert isinstance(slide.bullets, list)
        assert len(slide.bullets) > 0
        assert slide.narration
        assert slide.duration > 0

    @pytest.mark.asyncio
    async def test_fallback_pptx_format(self, video_gen):
        with patch.object(video_gen, "ffmpeg_available", False):
            result = await video_gen.generate("主题", "内容")
            assert result.format == "pptx"
            assert result.video_bytes
            assert len(result.video_bytes) > 0

    @pytest.mark.asyncio
    async def test_render_slide_image(self, video_gen):
        slide = SlideData(
            title="测试标题",
            bullets=["要点1", "要点2"],
            image_description="测试图",
        )
        image_bytes = video_gen._render_slide_image(slide)
        assert isinstance(image_bytes, bytes)
        assert len(image_bytes) > 0

    @pytest.mark.asyncio
    async def test_mock_narration(self, video_gen):
        slides = [
            SlideData(title="页1", bullets=["A", "B"], image_description="图1"),
            SlideData(title="页2", bullets=["C", "D"], image_description="图2"),
        ]
        result = video_gen._mock_narration(slides)
        assert result[0].narration
        assert "页1" in result[0].narration
        assert result[0].duration == 5

    @pytest.mark.asyncio
    async def test_mock_slides_content(self, video_gen):
        slides = video_gen._mock_slides("深度学习", 3)
        assert len(slides) == 3
        assert "深度学习" in slides[0].title
        assert all(len(s.bullets) > 0 for s in slides)


class TestVideoGeneratorWithTTS:
    @pytest.mark.asyncio
    async def test_generate_voiceover(self):
        tts = MockTTSAdapter()
        gen = VideoGenerator(tts_adapter=tts, use_mock=True)
        slides = [
            SlideData(title="页1", bullets=["A"], image_description="图", narration="测试文本", duration=5),
        ]
        results = await gen._generate_voiceover(slides)
        assert len(results) == 1
        assert isinstance(results[0], TTSResult)
        assert results[0].audio_bytes

    @pytest.mark.asyncio
    async def test_generate_voiceover_empty(self):
        tts = MockTTSAdapter()
        gen = VideoGenerator(tts_adapter=tts, use_mock=True)
        slides = [
            SlideData(title="页1", bullets=["A"], image_description="图", narration="", duration=5),
        ]
        results = await gen._generate_voiceover(slides)
        assert len(results) == 1
        assert results[0].audio_bytes == b""


class TestVideoGeneratorFFmpeg:
    @pytest.mark.asyncio
    async def test_ffmpeg_check(self):
        gen = VideoGenerator(use_mock=True)
        assert isinstance(gen.ffmpeg_available, bool)

    def test_check_ffmpeg_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = VideoGenerator._check_ffmpeg()
            assert result is False


class TestSlideData:
    def test_slide_creation(self):
        slide = SlideData(
            title="测试",
            bullets=["A", "B"],
            image_description="图",
            narration="旁白",
            duration=10,
        )
        assert slide.title == "测试"
        assert slide.duration == 10


class TestVideoResult:
    def test_result_creation(self):
        slides = [SlideData(title="T", bullets=["A"], image_description="I")]
        result = VideoResult(
            video_bytes=b"test",
            slides=slides,
            format="pptx",
            duration_seconds=15,
        )
        assert result.format == "pptx"
        assert result.duration_seconds == 15