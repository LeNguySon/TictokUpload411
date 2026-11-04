"""
Video Validation Policy enforcing format, size, duration, and integrity standards before TikTok upload.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoValidationResult:
    is_valid: bool
    file_path: Path
    file_size_bytes: int
    duration_sec: float
    error_message: str | None = None


class VideoValidationPolicy:
    """
    Validates local video files according to TikTok publisher constraints:
    - Supported extensions (.mp4, .mov, .webm, .mkv)
    - Minimum & Maximum size limits
    - Minimum & Maximum duration limits
    """

    def __init__(
        self,
        min_size_bytes: int = 1024,  # 1 KB
        max_size_bytes: int = 500 * 1024 * 1024,  # 500 MB
        min_duration_sec: float = 3.0,
        max_duration_sec: float = 600.0,  # 10 minutes
        allowed_extensions: set[str] | None = None,
    ) -> None:
        self.min_size_bytes = min_size_bytes
        self.max_size_bytes = max_size_bytes
        self.min_duration_sec = min_duration_sec
        self.max_duration_sec = max_duration_sec
        self.allowed_extensions = {ext.lower() for ext in (allowed_extensions or {".mp4", ".mov", ".webm", ".mkv"})}

    def validate_file(
        self,
        file_path: str | Path,
        duration_sec: float = 0.0,
    ) -> VideoValidationResult:
        p = Path(file_path).resolve()

        if not p.exists() or not p.is_file():
            return VideoValidationResult(
                is_valid=False,
                file_path=p,
                file_size_bytes=0,
                duration_sec=duration_sec,
                error_message=f"Video file not found or is not a regular file: {p}",
            )

        if p.suffix.lower() not in self.allowed_extensions:
            return VideoValidationResult(
                is_valid=False,
                file_path=p,
                file_size_bytes=0,
                duration_sec=duration_sec,
                error_message=f"Unsupported file format '{p.suffix}'. Allowed: {', '.join(sorted(self.allowed_extensions))}",
            )

        try:
            file_size = p.stat().st_size
        except OSError as e:
            return VideoValidationResult(
                is_valid=False,
                file_path=p,
                file_size_bytes=0,
                duration_sec=duration_sec,
                error_message=f"Cannot read file metadata: {e}",
            )

        if file_size < self.min_size_bytes:
            return VideoValidationResult(
                is_valid=False,
                file_path=p,
                file_size_bytes=file_size,
                duration_sec=duration_sec,
                error_message=f"File is too small ({file_size} bytes). Minimum required: {self.min_size_bytes} bytes.",
            )

        if file_size > self.max_size_bytes:
            max_mb = self.max_size_bytes // (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            return VideoValidationResult(
                is_valid=False,
                file_path=p,
                file_size_bytes=file_size,
                duration_sec=duration_sec,
                error_message=f"File is too large ({actual_mb:.1f} MB). Maximum limit: {max_mb} MB.",
            )

        if duration_sec > 0:
            if duration_sec < self.min_duration_sec:
                return VideoValidationResult(
                    is_valid=False,
                    file_path=p,
                    file_size_bytes=file_size,
                    duration_sec=duration_sec,
                    error_message=f"Video duration ({duration_sec:.1f}s) is shorter than minimum allowed {self.min_duration_sec}s.",
                )

            if duration_sec > self.max_duration_sec:
                return VideoValidationResult(
                    is_valid=False,
                    file_path=p,
                    file_size_bytes=file_size,
                    duration_sec=duration_sec,
                    error_message=f"Video duration ({duration_sec:.1f}s) exceeds maximum allowed {self.max_duration_sec}s.",
                )

        return VideoValidationResult(
            is_valid=True,
            file_path=p,
            file_size_bytes=file_size,
            duration_sec=duration_sec,
        )
