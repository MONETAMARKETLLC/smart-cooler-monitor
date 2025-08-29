import cv2
import time
import numpy as np
from config.settings import WindowConfig
from typing import Optional, Tuple, List
from core.camera_manager import CameraManager

from utils.logger import get_logger

logger = get_logger(__name__)

class DisplayManager:

    """Manages the display and user interface"""
    
    def __init__(self, camera_manager: CameraManager, window_config: WindowConfig):
        self.camera_manager = camera_manager
        self.window_config = window_config
        self.last_known_size = (window_config.width, window_config.height)
        self.size_check_interval = 0.1
        self.last_size_check = 0
        self.fullscreen = False
    
    def create_display_grid(self, window_name: Optional[str] = None, current_product: Optional[str] = None, recording: bool = False, record_start_time: Optional[float] = None) -> Optional[np.ndarray]:
        """Create display grid adapting to window size"""
        if not self.camera_manager.frames:
            return None
        
        # Get current window size
        if window_name:
            window_width, window_height = self._get_actual_window_size(window_name)
        else:
            window_width, window_height = self.window_config.width, self.window_config.height
        
        num_cameras = len(self.camera_manager.cameras)
        
        # Calculate dimensions with text margin
        text_margin = 60
        effective_width = max(self.window_config.max_width -20 ,window_width - 20, self.window_config.min_width - 20)
        effective_height = max(self.window_config.max_height - 20, window_height - text_margin, self.window_config.min_height - text_margin)
        
        # Calculate camera dimensions based on layout
        cam_width, cam_height = self._calculate_camera_dimensions(num_cameras, effective_width, effective_height)
        
        # Process camera frames
        display_frames = []
        for device_id in sorted(self.camera_manager.cameras.keys()):
            if device_id in self.camera_manager.frames:
                frame = self._process_frame(
                    self.camera_manager.frames[device_id].copy(),
                    device_id,
                    cam_width,
                    cam_height,
                    current_product,
                    recording,
                    record_start_time
                )
                display_frames.append(frame)
        
        # Create final grid
        return self._create_grid(display_frames, num_cameras, cam_width, cam_height)
    
    def _get_actual_window_size(self, window_name: str) -> Tuple[int, int]:
        """Get actual current window size"""
        current_time = time.time()
        
        if current_time - self.last_size_check < self.size_check_interval:
            return self.last_known_size
        
        self.last_size_check = current_time
        
        try:
            rect = cv2.getWindowImageRect(window_name)
            if rect and len(rect) >= 4:
                new_width, new_height = rect[2], rect[3]
                
                if (self.window_config.min_width <= new_width <= self.window_config.max_width and
                    self.window_config.min_height <= new_height <= self.window_config.max_height):
                    self.last_known_size = (new_width, new_height)
                    return self.last_known_size
        except Exception:
            pass
        
        return self.last_known_size
    
    def _calculate_camera_dimensions(self, num_cameras: int, effective_width: int, effective_height: int) -> Tuple[int, int]:
        """Calculate camera dimensions based on number of cameras"""
        if num_cameras == 1:
            cam_width, cam_height = effective_width, effective_height
        elif num_cameras == 2:
            cam_width, cam_height = effective_width // 2, effective_height
        elif num_cameras == 3:
            cam_width, cam_height = effective_width // 2, effective_height // 2
        else:  # 4 or more
            cam_width, cam_height = effective_width // 2, effective_height // 2
        
        # Ensure minimum dimensions
        min_cam_width, min_cam_height = 160, 120
        cam_width = max(cam_width, min_cam_width)
        cam_height = max(cam_height, min_cam_height)
        
        # Maintain aspect ratio
        aspect_ratio = 4/3
        if cam_width / cam_height > aspect_ratio * 1.2:
            cam_width = int(cam_height * aspect_ratio)
        elif cam_height / cam_width > (1/aspect_ratio) * 1.2:
            cam_height = int(cam_width / aspect_ratio)
        
        return cam_width, cam_height
    
    def _process_frame(self, frame: np.ndarray, device_id: int, cam_width: int, cam_height: int, 
                      current_product: Optional[str], recording: bool, record_start_time: Optional[float]) -> np.ndarray:
        """Process and annotate a single frame"""
        # Calculate dynamic font scale
        font_scale = max(0.4, min(1.5, (cam_width + cam_height) / 800.0))
        thickness = max(1, int(2 * font_scale))
        
        # Prepare text information
        if current_product:
            product_text = f'Cam {device_id} - {current_product}'
        else:
            product_text = f'Cam {device_id}'
        
        color = (0, 0, 255) if recording else (0, 255, 0)
        status = "REC" if recording else "LIVE"
        
        # Calculate text positions
        base_y = max(20, int(25 * font_scale))
        line_spacing = max(20, int(25 * font_scale))
        
        # Add text overlays
        cv2.putText(frame, product_text, (10, base_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
        cv2.putText(frame, status, (10, base_y + line_spacing), 
                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
        
        if recording and record_start_time:
            duration = time.time() - record_start_time
            cv2.putText(frame, f'{duration:.1f}s', (10, base_y + 2 * line_spacing), 
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
        
        # Resize frame
        return cv2.resize(frame, (cam_width, cam_height), interpolation=cv2.INTER_LINEAR)
    
    def _create_grid(self, display_frames: List[np.ndarray], num_cameras: int, cam_width: int, cam_height: int) -> Optional[np.ndarray]:
        """Create the final display grid"""
        if num_cameras == 1:
            return display_frames[0]
        elif num_cameras == 2:
            return np.hstack((display_frames[0], display_frames[1]))
        elif num_cameras == 3:
            # 2 on top, 1 on bottom centered
            top_row = np.hstack((display_frames[0], display_frames[1]))
            black_frame = np.zeros((cam_height, cam_width, 3), dtype=np.uint8)
            bottom_row = np.hstack((display_frames[2], black_frame))
            return np.vstack((top_row, bottom_row))
        elif num_cameras >= 4:
            # 2x2 grid
            top_row = np.hstack((display_frames[0], display_frames[1]))
            bottom_row = np.hstack((display_frames[2], display_frames[3]))
            return np.vstack((top_row, bottom_row))
        
        return None
    
    def toggle_fullscreen(self, window_name: str) -> bool:
        """Toggle fullscreen mode"""
        if not self.fullscreen:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            self.fullscreen = True
            logger.info("Switched to fullscreen mode")
        else:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, self.window_config.width, self.window_config.height)
            self.fullscreen = False
            logger.info("Switched to normal window mode")
        
        return self.fullscreen
    
    def resize_window(self, window_name: str, increase: bool) -> Tuple[int, int]:
        """Resize window by a factor"""
        if self.fullscreen:
            return self.window_config.width, self.window_config.height
        
        factor = 1.2 if increase else 0.8
        new_width = int(self.window_config.width * factor)
        new_height = int(self.window_config.height * factor)
        
        # Apply limits
        new_width = max(self.window_config.min_width, min(self.window_config.max_width, new_width))
        new_height = max(self.window_config.min_height, min(self.window_config.max_height, new_height))
        
        self.window_config.width = new_width
        self.window_config.height = new_height
        
        cv2.resizeWindow(window_name, new_width, new_height)
        self.last_known_size = (new_width, new_height)
        
        logger.info(f"Window resized to: {new_width}x{new_height}")
        return new_width, new_height
