import cv2
import signal
import subprocess
import glob
import threading
import time
import numpy as np
from utils.logger import logger
from utils.exceptions import CameraError
from core.camera_detector import CameraDetector
from config.settings import CameraInfo, VideoConfig
from typing import Dict, Optional, List, Tuple

class CameraManager:
    """Manages camera operations and capture threads"""
    
    def __init__(self, video_config: VideoConfig):
        self.video_config = video_config
        self.cameras: Dict[int, cv2.VideoCapture] = {}
        self.frames: Dict[int, np.ndarray] = {}
        self.capture_threads: List[threading.Thread] = []
        self.running = False
        self.detector = CameraDetector()
    
    def initialize_cameras(self, camera_infos: Dict[int, CameraInfo]) -> bool:
        """Initialize cameras from detected camera info"""
        logger.info("Initializing cameras...")
        
        successfully_initialized = []
        
        for device_id, camera_info in camera_infos.items():
            cap, frame = self._initialize_single_camera(device_id)
            
            if cap is not None and frame is not None:
                self.cameras[device_id] = cap
                self.frames[device_id] = frame
                successfully_initialized.append(device_id)
                logger.info(f"Camera {device_id} initialized successfully - {frame.shape}")
            else:
                logger.error(f"Camera {device_id} initialization failed")
        
        if not successfully_initialized:
            logger.error("No cameras were initialized successfully")
            return False
        
        logger.info(f"Successfully initialized {len(successfully_initialized)} cameras: {successfully_initialized}")
        return True
    
    def _initialize_single_camera(self, device_id: int, timeout: int = 10) -> Tuple[Optional[cv2.VideoCapture], Optional[np.ndarray]]:
        """Initialize a single camera with timeout"""
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Timeout initializing camera {device_id}")
        
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        
        try:
            logger.info(f"Initializing camera /dev/video{device_id}...")
            signal.alarm(timeout)
            
            # Try different backends
            for backend in [cv2.CAP_V4L2, cv2.CAP_ANY]:
                try:
                    cap = cv2.VideoCapture(device_id, backend)
                    if cap.isOpened():
                        break
                    cap.release()
                except Exception:
                    continue
            else:
                raise CameraError("Could not open with any backend")
            
            # Configure camera
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.video_config.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.video_config.height)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            
            # Test capture
            for _ in range(3):
                ret, frame = cap.read()
                if ret and frame is not None:
                    signal.alarm(0)
                    return cap, frame
                time.sleep(0.1)
            
            cap.release()
            raise CameraError("Cannot capture frames")
        
        except (TimeoutError, CameraError) as e:
            logger.error(f"Camera {device_id}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error with camera {device_id}: {e}")
            return None, None
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    
    def start_capture_threads(self) -> None:
        """Start capture threads for all cameras"""
        if self.running:
            return
        
        self.running = True
        self.capture_threads = []
        
        for device_id in self.cameras:
            thread = threading.Thread(target=self._capture_thread, args=(device_id,), daemon=True)
            thread.start()
            self.capture_threads.append(thread)
            logger.info(f"Capture thread started for camera {device_id}")
    
    def _capture_thread(self, device_id: int) -> None:
        """Capture thread for a single camera"""
        cap = self.cameras[device_id]
        
        while self.running:
            try:
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.frames[device_id] = frame.copy()
                else:
                    logger.warning(f"Failed to read from camera {device_id}")
                
                time.sleep(1 / self.video_config.fps)
            except Exception as e:
                logger.error(f"Error in capture thread for camera {device_id}: {e}")
                break
    
    def stop_capture_threads(self) -> None:
        """Stop all capture threads"""
        self.running = False
        
        for thread in self.capture_threads:
            thread.join(timeout=2.0)
        
        self.capture_threads = []
        logger.info("All capture threads stopped")
    
    def cleanup(self) -> None:
        """Clean up camera resources"""
        self.stop_capture_threads()
        
        for cap in self.cameras.values():
            cap.release()
        
        self.cameras.clear()
        self.frames.clear()
        logger.info("Camera resources cleaned up")
