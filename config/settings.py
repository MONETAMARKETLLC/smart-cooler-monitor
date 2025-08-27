from dataclasses import  dataclass
from typing import Optional
import cv2

@dataclass
class CameraInfo:
    """Camera information data class"""
    device_id: int
    name: str
    backend: Optional[str] = None
    width: int = 0
    height: int = 0
    fps: float = 0.0
    fourcc: float = 0.0


@dataclass
class VideoConfig:
    """Video configuration settings"""
    fps: int = 60
    width: int = 800
    height: int = 600
    fourcc: int = cv2.VideoWriter_fourcc(*'mp4v')


@dataclass
class WindowConfig:
    """Window configuration settings"""
    width: int = 800
    height: int = 600
    min_width: int = 400
    min_height: int = 300
    max_width: int = 1920
    max_height: int = 1080