import asyncio
import io
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from app.services.media.tts_adapter import TTSAdapter, TTSResult, get_tts_adapter
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)

SLIDE_WIDTH = 1280
SLIDE_HEIGHT = 720
TITLE_FONT_SIZE = 48
BULLET_FONT_SIZE = 28
BG_COLOR = "#1a1a2e"
TITLE_COLOR = "#ffffff"
BULLET_COLOR = "#e0e0e0"
ACCENT_COLOR = "#4a9eff"


@dataclass
class SlideData:
    title: str
    bullets: list[str]
    image_description: str
    narration: str = ""
    duration: int = 5


@dataclass
class VideoResult:
    video_bytes: bytes
    slides: list[SlideData]
    format: Literal["mp4", "pptx"]
    duration_seconds: int


class VideoGenerator:
    def __init__(
        self,
        llm_client=None,
        tts_adapter: TTSAdapter | None = None,
        use_mock: bool = True,
    ):
        self.llm_client = llm_client
        self.tts_adapter = tts_adapter or get_tts_adapter()
        self.use_mock = use_mock
        self.ffmpeg_available = self._check_ffmpeg()

    @staticmethod
    def _check_ffmpeg() -> bool:
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("FFmpeg not found, video synthesis will fall back to PPTX")
            return False

    async def generate(
        self,
        topic: str,
        content: str,
        num_slides: int = 6,
    ) -> VideoResult:
        slides = await self._generate_slides(topic, content, num_slides)
        slides = await self._generate_narration(slides)

        if not self.ffmpeg_available:
            return await self._fallback_pptx(slides)

        images = await self._render_slides(slides)
        audio_clips = await self._generate_voiceover(slides)
        video_bytes = await self._synthesize_video(images, audio_clips, slides)

        total_duration = sum(s.duration for s in slides)
        return VideoResult(
            video_bytes=video_bytes,
            slides=slides,
            format="mp4",
            duration_seconds=total_duration,
        )

    async def _generate_slides(
        self, topic: str, content: str, num_slides: int
    ) -> list[SlideData]:
        if self.use_mock:
            return self._mock_slides(topic, num_slides)

        sys_prompt = self._load_prompt("slides.yaml", "system")
        user_tpl = self._load_prompt("slides.yaml", "user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {"topic": topic, "content": content, "num_slides": str(num_slides)},
        )

        response = await self._call_llm(system_prompt=sys_prompt, user_prompt=user_prompt)
        try:
            data = json.loads(response)
            slides_data = data.get("slides", [])
            return [
                SlideData(
                    title=s.get("title", ""),
                    bullets=s.get("bullets", []),
                    image_description=s.get("image_description", ""),
                )
                for s in slides_data
            ]
        except json.JSONDecodeError:
            logger.error("Failed to parse slide generation response")
            return self._mock_slides(topic, num_slides)

    async def _generate_narration(self, slides: list[SlideData]) -> list[SlideData]:
        if self.use_mock:
            return self._mock_narration(slides)

        sys_prompt = self._load_prompt("script.yaml", "system")
        user_tpl = self._load_prompt("script.yaml", "user_template")
        slides_json = json.dumps(
            [{"title": s.title, "bullets": s.bullets} for s in slides],
            ensure_ascii=False,
        )
        user_prompt = interpolate_variables(user_tpl, {"slides_json": slides_json})

        response = await self._call_llm(system_prompt=sys_prompt, user_prompt=user_prompt)
        try:
            data = json.loads(response)
            scripts = data.get("scripts", [])
            for script in scripts:
                idx = script.get("slide_index", 0)
                if 0 <= idx < len(slides):
                    slides[idx].narration = script.get("narration", "")
                    slides[idx].duration = script.get("duration_estimate", 5)
            return slides
        except json.JSONDecodeError:
            logger.error("Failed to parse narration generation response")
            return self._mock_narration(slides)

    async def _render_slides(self, slides: list[SlideData]) -> list[bytes]:
        return [self._render_slide_image(s) for s in slides]

    def _render_slide_image(self, slide: SlideData) -> bytes:
        img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", TITLE_FONT_SIZE)
            bullet_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", BULLET_FONT_SIZE)
        except OSError:
            title_font = ImageFont.load_default()
            bullet_font = ImageFont.load_default()

        draw.rectangle(
            [(0, 0), (SLIDE_WIDTH, 8)],
            fill=ACCENT_COLOR,
        )

        title = slide.title[:30]
        draw.text(
            (SLIDE_WIDTH // 2, 80),
            title,
            fill=TITLE_COLOR,
            font=title_font,
            anchor="mt",
        )

        y = 200
        for bullet in slide.bullets[:5]:
            text = bullet[:40]
            draw.text(
                (100, y),
                f"• {text}",
                fill=BULLET_COLOR,
                font=bullet_font,
            )
            y += 60

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def _generate_voiceover(
        self, slides: list[SlideData]
    ) -> list[TTSResult]:
        tasks = []
        for slide in slides:
            if slide.narration.strip():
                tasks.append(self.tts_adapter.generate(slide.narration))
            else:
                tasks.append(self._empty_tts_result())
        return await asyncio.gather(*tasks)

    async def _synthesize_video(
        self,
        images: list[bytes],
        audio_clips: list[TTSResult],
        slides: list[SlideData],
    ) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            for i, img_data in enumerate(images):
                (tmp_path / f"slide_{i:03d}.png").write_bytes(img_data)

            for i, audio in enumerate(audio_clips):
                if audio.audio_bytes:
                    (tmp_path / f"audio_{i:03d}.mp3").write_bytes(audio.audio_bytes)

            concat_file = tmp_path / "concat.txt"
            concat_parts = []
            for i in range(len(slides)):
                duration = slides[i].duration
                concat_parts.append(f"file 'slide_{i:03d}.png'")
                concat_parts.append(f"duration {duration}")
            concat_parts.append(f"file 'slide_{len(slides)-1:03d}.png'")
            concat_file.write_text("\n".join(concat_parts))

            video_path = tmp_path / "output.mp4"
            audio_filter_parts = []
            for i in range(len(audio_clips)):
                if audio_clips[i].audio_bytes:
                    audio_filter_parts.append(f"[{i+1}:a]adelay=delays={sum(s.duration for s in slides[:i])*1000}:all=1[a{i}]")

            if audio_filter_parts:
                filter_complex = ";".join(audio_filter_parts) + ";" + "".join(f"[a{i}]" for i in range(len(audio_clips)) if audio_clips[i].audio_bytes) + f"amix=inputs={sum(1 for a in audio_clips if a.audio_bytes)}:duration=longest[outa]"
                input_args = ["-f", "concat", "-safe", "0", "-i", str(concat_file)]
                for i in range(len(audio_clips)):
                    if audio_clips[i].audio_bytes:
                        input_args += ["-i", str(tmp_path / f"audio_{i:03d}.mp3")]
                input_args += [
                    "-filter_complex", filter_complex,
                    "-map", "0:v",
                    "-map", "[outa]",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-shortest",
                    str(video_path),
                    "-y",
                ]
            else:
                input_args = [
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-r", "1",
                    str(video_path),
                    "-y",
                ]

            try:
                subprocess.run(
                    ["ffmpeg"] + input_args,
                    capture_output=True,
                    check=True,
                )
                return video_path.read_bytes()
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg failed: {e.stderr.decode()}")
                raise RuntimeError("Video synthesis failed")

    async def _fallback_pptx(self, slides: list[SlideData]) -> VideoResult:
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
        except ImportError:
            logger.error("python-pptx not installed, cannot generate fallback PPTX")
            raise RuntimeError("Neither FFmpeg nor python-pptx is available")

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        for slide_data in slides:
            blank_layout = prs.slide_layouts[6]
            slide = prs.slides.add_slide(blank_layout)

            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(0.5), Inches(12.333), Inches(1)
            )
            title_frame = title_box.text_frame
            title_frame.text = slide_data.title
            title_frame.paragraphs[0].font.size = Pt(36)
            title_frame.paragraphs[0].font.bold = True

            content_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(2), Inches(12.333), Inches(5)
            )
            content_frame = content_box.text_frame
            for bullet in slide_data.bullets:
                p = content_frame.add_paragraph()
                p.text = f"• {bullet}"
                p.font.size = Pt(20)
                p.level = 0

        buf = io.BytesIO()
        prs.save(buf)
        total_duration = sum(s.duration for s in slides)
        return VideoResult(
            video_bytes=buf.getvalue(),
            slides=slides,
            format="pptx",
            duration_seconds=total_duration,
        )

    def _load_prompt(self, filename: str, key: str) -> str:
        import yaml
        path = Path(__file__).parent.parent.parent / "prompts" / "video_agent" / filename
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get(key, "")
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {path}")
            return ""

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        if self.llm_client is None:
            logger.warning("No LLM client configured, using mock data")
            return "{}"
        return await self.llm_client.chat(system_prompt, user_prompt)

    def _mock_slides(self, topic: str, num_slides: int) -> list[SlideData]:
        return [
            SlideData(
                title=f"{topic} 导论",
                bullets=[
                    "理解核心概念",
                    "掌握基本原理",
                    "应用于实际问题",
                ],
                image_description="概念图解",
                duration=5,
            ),
            SlideData(
                title="核心要点",
                bullets=[
                    "要点一：基础定义",
                    "要点二：关键性质",
                    "要点三：典型应用",
                ],
                image_description="流程图",
                duration=5,
            ),
            SlideData(
                title="总结与展望",
                bullets=[
                    "回顾核心内容",
                    "常见误区提醒",
                    "下一步学习方向",
                ],
                image_description="总结图",
                duration=5,
            ),
        ]

    def _mock_narration(self, slides: list[SlideData]) -> list[SlideData]:
        for i, slide in enumerate(slides):
            slide.narration = f"这是第{i+1}页的内容讲解。{slide.title}。主要包含：{'，'.join(slide.bullets[:2])}。"
            slide.duration = 5
        return slides

    async def _empty_tts_result(self) -> TTSResult:
        return TTSResult(audio_bytes=b"", duration_seconds=0.0, format="mp3")
