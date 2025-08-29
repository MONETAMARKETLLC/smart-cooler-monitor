import cv2
import time
from pathlib import Path
from config.settings import VideoConfig
from typing import Dict, Optional
from core.camera_manager import CameraManager
from core.product_manager import ProductManager
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)

class VideoRecorder:
    """Handles video recording operations"""
    
    def __init__(self, camera_manager: CameraManager, product_manager: ProductManager, video_config: VideoConfig, clips_base_dir: Path):
        self.camera_manager = camera_manager
        self.product_manager = product_manager
        self.video_config = video_config
        self.clips_base_dir = clips_base_dir
        self.writers: Dict[int, cv2.VideoWriter] = {}
        self.recording = False
        self.record_start_time: Optional[float] = None
        self.current_product: Optional[str] = None
    
    def start_recording(self) -> bool:
        """Start recording after getting product name"""
        if self.recording:
            return False
        
        if not self.camera_manager.cameras:
            logger.error("No cameras available for recording")
            return False
        
        logger.info("Selecting product...")
        versioned_product_name = self.product_manager.get_product_input()
        
        if versioned_product_name is None:
            logger.info("Recording cancelled by user")
            return False
        
        self.current_product = versioned_product_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create product directory
        product_dir = self.clips_base_dir / versioned_product_name
        product_dir.mkdir(exist_ok=True)
        logger.info(f"Product directory ready: {product_dir}")
        
        self.writers = {}
        
        logger.info(f"RECORDING: {versioned_product_name} - {timestamp}")
        logger.info(f"Using {len(self.camera_manager.cameras)} cameras: {list(self.camera_manager.cameras.keys())}")
        
        for device_id in self.camera_manager.cameras:
            filename = f"clip_cam{device_id}_{versioned_product_name}_{timestamp}.mp4"
            filepath = product_dir / filename
            
            writer = cv2.VideoWriter(
                str(filepath),
                self.video_config.fourcc,
                self.video_config.fps,
                (self.video_config.width, self.video_config.height)
            )
            
            if writer.isOpened():
                self.writers[device_id] = writer
                logger.info(f"Recording: {filename}")
            else:
                logger.error(f"Error creating writer for camera {device_id}")
        
        if self.writers:
            self.recording = True
            self.record_start_time = time.time()
            return True
        
        return False
    
    def write_frames(self) -> None:
        """Write current frames to video files"""
        if not self.recording:
            return
        
        for device_id, writer in self.writers.items():
            if device_id in self.camera_manager.frames:
                frame = self.camera_manager.frames[device_id]
                writer.write(frame)
    
    def stop_recording(self) -> None:
        """Stop recording"""
        if not self.recording:
            return
        
        self.recording = False
        duration = time.time() - self.record_start_time if self.record_start_time else 0
        
        for device_id, writer in self.writers.items():
            writer.release()
            logger.info(f"Saved: clip_cam{device_id} ({duration:.1f}s)")
        
        self.writers.clear()
        logger.info(f"Recording finished - Duration: {duration:.1f}s")
        logger.info(f"Clips saved to: clips/{self.current_product}/")
    
    def cleanup(self) -> None:
        """Clean up recording resources"""
        if self.recording:
            self.stop_recording()

