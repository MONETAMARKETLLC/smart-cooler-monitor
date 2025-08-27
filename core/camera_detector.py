import cv2
import signal
import subprocess
import glob
from utils.logger import logger
from config.settings import CameraInfo
from typing import Dict, Optional


class CameraDetector:
    """Handles camera detection and initialization"""
    
    def __init__(self, max_cameras: int = 10):
        self.max_cameras = max_cameras
    
    def detect_available_cameras(self) -> Dict[int, CameraInfo]:
        """Detect available cameras using multiple methods"""
        logger.info("Detecting available cameras...")
        available_cameras = {}
        
        # Method 1: v4l2-ctl
        v4l2_cameras = self._detect_with_v4l2()
        if v4l2_cameras:
            available_cameras.update(v4l2_cameras)
        
        # Method 2: Sequential testing (fallback)
        if not available_cameras:
            logger.info("Falling back to sequential testing...")
            for device_id in range(self.max_cameras):
                if self._test_camera_quick(device_id):
                    available_cameras[device_id] = CameraInfo(
                        device_id=device_id,
                        name="Unknown Camera"
                    )
        
        # Method 3: Direct file search
        if not available_cameras:
            logger.info("Searching /dev/video* files...")
            for path in sorted(glob.glob("/dev/video*")):
                try:
                    device_id = int(path.replace("/dev/video", ""))
                    if self._test_camera_quick(device_id):
                        available_cameras[device_id] = CameraInfo(
                            device_id=device_id,
                            name="Unknown Camera"
                        )
                except ValueError:
                    continue
        
        logger.info(f"Detected {len(available_cameras)} cameras: {list(available_cameras.keys())}")
        return available_cameras
    
    def _detect_with_v4l2(self) -> Dict[int, CameraInfo]:
        """Detect cameras using v4l2-ctl"""
        cameras = {}
        
        try:
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("Using v4l2-ctl for camera detection")
                lines = result.stdout.splitlines()
                current_device_name = None
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if not line.startswith("/dev/video"):
                        current_device_name = line
                        continue
                    
                    if line.startswith("/dev/video"):
                        try:
                            device_id = int(line.replace("/dev/video", ""))
                            cameras[device_id] = CameraInfo(
                                device_id=device_id,
                                name=current_device_name or "Unknown"
                            )
                            logger.info(f"Found camera: {line} -> {current_device_name}")
                        except ValueError:
                            continue
        
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
            logger.warning(f"v4l2-ctl detection failed: {e}")
        
        return cameras
    
    def _test_camera_quick(self, device_id: int, timeout: int = 3) -> bool:
        """Quick test if camera is available"""
        def timeout_handler(signum, frame):
            raise TimeoutError()
        
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        
        try:
            signal.alarm(timeout)
            cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
            
            if not cap.isOpened():
                return False
            
            ret, frame = cap.read()
            cap.release()
            signal.alarm(0)
            
            return ret and frame is not None
        
        except (TimeoutError, Exception):
            return False
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    
    def get_camera_info(self, device_id: int) -> Optional[CameraInfo]:
        """Get detailed camera information"""
        try:
            cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
            if not cap.isOpened():
                return None
            
            info = CameraInfo(
                device_id=device_id,
                name="Camera",
                backend=cap.getBackendName(),
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=cap.get(cv2.CAP_PROP_FPS),
                fourcc=cap.get(cv2.CAP_PROP_FOURCC)
            )
            
            cap.release()
            return info
        
        except Exception as e:
            logger.error(f"Error getting camera {device_id} info: {e}")
            return None
