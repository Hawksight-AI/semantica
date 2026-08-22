"""
Media Content Parsing Module

This module handles parsing of media files and content, including images, audio,
and video files, extracting metadata and analyzing media characteristics.

Key Features:
    - Image metadata extraction
    - Audio content processing
    - Video metadata analysis
    - Media file information extraction
    - Content type detection
    - Format support detection
    - Batch media processing

Main Classes:
    - MediaParser: Main media parsing class

Example Usage:
    >>> from semantica.parse import MediaParser
    >>> parser = MediaParser()
    >>> metadata = parser.parse("image.jpg")
    >>> info = parser.get_media_info("video.mp4")
    >>> formats = parser.get_supported_formats()

Author: Semantica Contributors
License: MIT
"""

from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .image_parser import ImageParser


def _safe_parse_fps(r_frame_rate: str) -> Optional[float]:
    """Parse a frame-rate fraction string (e.g. '30000/1001') without eval()."""
    try:
        return float(Fraction(r_frame_rate))
    except (ValueError, ZeroDivisionError):
        return None


class MediaParser:
    """
    Media content parsing handler.

    • Parses various media file formats
    • Extracts metadata and properties
    • Processes media content information
    • Handles different media types
    • Supports batch media processing
    • Analyzes media characteristics
    """

    def __init__(self, config=None, **kwargs):
        """Initialize media parser."""
        self.logger = get_logger("media_parser")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize parsers
        self.image_parser = ImageParser(**self.config.get("image", {}))

        # Supported formats
        self.supported_formats = {
            # Image formats
            ".jpg": "image",
            ".jpeg": "image",
            ".png": "image",
            ".gif": "image",
            ".bmp": "image",
            ".tiff": "image",
            ".webp": "image",
            # Audio formats (would need additional libraries)
            ".mp3": "audio",
            ".wav": "audio",
            ".flac": "audio",
            ".aac": "audio",
            # Video formats (would need additional libraries)
            ".mp4": "video",
            ".avi": "video",
            ".mov": "video",
            ".mkv": "video",
            ".webm": "video",
        }

    def parse_media(
        self, file_path: Union[str, Path], media_type: Optional[str] = None, **options
    ) -> Dict[str, Any]:
        """
        Parse media file of any supported type.

        Args:
            file_path: Path to media file
            media_type: Media type (auto-detected if None)
            **options: Parsing options

        Returns:
            dict: Parsed media data
        """
        file_path = Path(file_path)

        # Track media parsing
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="parse",
            submodule="MediaParser",
            message=f"Media: {file_path.name}",
        )

        try:
            if not file_path.exists():
                raise ValidationError(f"Media file not found: {file_path}")

            # Detect media type if not specified
            if media_type is None:
                media_type = self._detect_media_type(file_path)

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Parsing {media_type}..."
            )

            if media_type == "image":
                result = self.image_parser.parse(file_path, **options)
            elif media_type == "audio":
                result = self._parse_audio(file_path, **options)
            elif media_type == "video":
                result = self._parse_video(file_path, **options)
            else:
                raise ValidationError(f"Unsupported media type: {media_type}")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Parsed {media_type} successfully",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def extract_metadata(
        self, file_path: Union[str, Path], media_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract metadata from media file.

        Args:
            file_path: Path to media file
            media_type: Media type (auto-detected if None)

        Returns:
            dict: Media metadata
        """
        file_path = Path(file_path)

        if media_type is None:
            media_type = self._detect_media_type(file_path)

        if media_type == "image":
            return self.image_parser.extract_metadata(file_path).__dict__
        elif media_type == "audio":
            return self._extract_audio_metadata(file_path)
        elif media_type == "video":
            return self._extract_video_metadata(file_path)
        else:
            return {}

    def _detect_media_type(self, file_path: Path) -> str:
        """Detect media type from file extension."""
        suffix = file_path.suffix.lower()
        return self.supported_formats.get(suffix, "unknown")

    def _parse_audio(self, file_path: Path, **options) -> Dict[str, Any]:
        """Parse audio file."""
        metadata = self._extract_audio_metadata(file_path)

        return {"metadata": metadata, "type": "audio"}

    def _parse_video(self, file_path: Path, **options) -> Dict[str, Any]:
        """Parse video file."""
        metadata = self._extract_video_metadata(file_path)

        return {"metadata": metadata, "type": "video"}

    def _extract_audio_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract audio metadata."""
        metadata = {
            "file_path": str(file_path),
            "file_size": file_path.stat().st_size,
            "format": file_path.suffix.lower(),
        }

        # Try to extract metadata using mutagen if available
        try:
            from mutagen import File

            audio_file = File(str(file_path))
            if audio_file:
                metadata.update(
                    {
                        "title": audio_file.get("TIT2", [None])[0]
                        or audio_file.get("TITLE", [None])[0],
                        "artist": audio_file.get("TPE1", [None])[0]
                        or audio_file.get("ARTIST", [None])[0],
                        "album": audio_file.get("TALB", [None])[0]
                        or audio_file.get("ALBUM", [None])[0],
                        "duration": audio_file.info.length
                        if hasattr(audio_file.info, "length")
                        else None,
                        "bitrate": audio_file.info.bitrate
                        if hasattr(audio_file.info, "bitrate")
                        else None,
                        "sample_rate": audio_file.info.sample_rate
                        if hasattr(audio_file.info, "sample_rate")
                        else None,
                    }
                )
        except (ImportError, OSError):
            self.logger.warning("mutagen not available for audio metadata extraction")
        except Exception as e:
            self.logger.warning(f"Failed to extract audio metadata: {e}")

        return metadata

    def _extract_video_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract video metadata."""
        metadata = {
            "file_path": str(file_path),
            "file_size": file_path.stat().st_size,
            "format": file_path.suffix.lower(),
        }

        # Try to extract metadata using ffmpeg if available
        try:
            import subprocess

            # ffprobe's own argument parser doesn't reliably honor a bare
            # "--" end-of-options marker, so a filename starting with "-"
            # could otherwise be parsed as an option; neutralize that by
            # forcing a relative-path prefix ffprobe can't mistake for a flag.
            ffprobe_path = str(file_path)
            if ffprobe_path.startswith("-"):
                ffprobe_path = f"./{ffprobe_path}"

            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    ffprobe_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                import json

                video_data = json.loads(result.stdout)

                if "streams" in video_data:
                    for stream in video_data["streams"]:
                        if stream.get("codec_type") == "video":
                            metadata.update(
                                {
                                    "width": stream.get("width"),
                                    "height": stream.get("height"),
                                    "duration": float(
                                        video_data.get("format", {}).get("duration", 0)
                                    ),
                                    "codec": stream.get("codec_name"),
                                    "fps": _safe_parse_fps(stream.get("r_frame_rate"))
                                    if stream.get("r_frame_rate")
                                    else None,
                                }
                            )
                            break
        except FileNotFoundError:
            self.logger.warning("ffprobe not available for video metadata extraction")
        except Exception as e:
            self.logger.warning(f"Failed to extract video metadata: {e}")

        return metadata
