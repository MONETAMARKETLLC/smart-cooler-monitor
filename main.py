import cv2
import time
import numpy as np
from pathlib import Path
from typing import Tuple

from utils.logger import logger
from config.settings import WindowConfig, VideoConfig
from core.product_manager import ProductManager
from core.video_recorder import VideoRecorder
from core.display_manager import DisplayManager
from core.camera_detector import CameraDetector
from core.camera_manager import CameraManager

class MultiCameraRecorder:
    """Main application class that orchestrates all components"""
    
    def __init__(self, clips_base_dir: str = "clips"):
        # Configuration
        self.clips_base_dir = Path(clips_base_dir)
        self.video_config = VideoConfig()
        self.window_config = WindowConfig()
        
        # Components
        self.product_manager = ProductManager(clips_base_dir=str(self.clips_base_dir))
        self.camera_manager = CameraManager(self.video_config)
        self.video_recorder = VideoRecorder(
            self.camera_manager, 
            self.product_manager, 
            self.video_config, 
            self.clips_base_dir
        )
        self.display_manager = DisplayManager(self.camera_manager, self.window_config)
        
        # State
        self.running = True
        
        # Ensure clips directory exists
        self.clips_base_dir.mkdir(exist_ok=True)
    
    def initialize_system(self) -> bool:
        """Initialize the camera system"""
        detector = CameraDetector()
        available_cameras = detector.detect_available_cameras()
        
        if not available_cameras:
            logger.error("No cameras found")
            return False
        
        if not self.camera_manager.initialize_cameras(available_cameras):
            logger.error("Failed to initialize cameras")
            return False
        
        self.camera_manager.start_capture_threads()
        return True
    
    def force_camera_detection(self, window_name: str) -> str:
        """Force new camera detection and return updated window name"""
        logger.info("Forcing camera detection...")
        old_camera_count = len(self.camera_manager.cameras)
        
        # Clean up current cameras
        self.camera_manager.cleanup()
        time.sleep(1)
        
        # Re-initialize
        if self.initialize_system():
            new_camera_count = len(self.camera_manager.cameras)
            logger.info("Camera detection completed")
            
            if new_camera_count != old_camera_count:
                # Update window name if camera count changed
                new_window_name = f'Smart Cooler - {new_camera_count} Cameras (Auto-detect)'
                cv2.destroyWindow(window_name)
                cv2.namedWindow(new_window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                cv2.resizeWindow(new_window_name, self.window_config.width, self.window_config.height)
                return new_window_name
        else:
            logger.error("Failed to re-initialize cameras")
        
        return window_name
    
    def restart_cameras(self, window_name: str) -> str:
        """Restart cameras and return updated window name"""
        logger.info("Restarting cameras...")
        old_camera_count = len(self.camera_manager.cameras)
        
        # Get current camera info before cleanup
        current_cameras = list(self.camera_manager.cameras.keys())
        
        # Clean up and re-initialize with same cameras
        self.camera_manager.cleanup()
        time.sleep(1)
        
        # Try to re-initialize the same cameras
        detector = CameraDetector()
        camera_infos = {}
        for device_id in current_cameras:
            info = detector.get_camera_info(device_id)
            if info:
                camera_infos[device_id] = info
        
        if camera_infos and self.camera_manager.initialize_cameras(camera_infos):
            self.camera_manager.start_capture_threads()
            new_camera_count = len(self.camera_manager.cameras)
            logger.info("Camera restart completed")
            
            if new_camera_count != old_camera_count:
                new_window_name = f'Smart Cooler - {new_camera_count} Cameras (Auto-detect)'
                cv2.destroyWindow(window_name)
                cv2.namedWindow(new_window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                cv2.resizeWindow(new_window_name, self.window_config.width, self.window_config.height)
                return new_window_name
        else:
            logger.error("Failed to restart cameras")
        
        return window_name
    
    def print_startup_info(self) -> None:
        """Print startup information"""
        print("\n" + "="*70)
        print("SMART COOLER - MULTI-CAMERA RECORDER (AUTO-DETECT)")
        print("="*70)
        print("Controls:")
        print("  SPACE - Select product and record/stop")
        print("  Q     - Exit")
        print("  ESC   - Exit")
        print("  R     - Restart cameras")
        print("  D     - Force detection of new cameras")
        print("  +/-   - Change window size")
        print("  F     - Toggle fullscreen")
        print("="*70)
        print(f"Clips saved to: {self.clips_base_dir}/[product_vN]/")
        print(f"Active cameras: {len(self.camera_manager.cameras)} -> {list(self.camera_manager.cameras.keys())}")
        if self.product_manager.products:
            print(f"Available products: {len(self.product_manager.products)}")
        print("Automatic versioning: product_v1, product_v2, etc.")
        print("READY - Press SPACE to select product and record")
        print("TIP: Resize window by dragging corners\n")
    
    def handle_key_input(self, key: int, window_name: str) -> Tuple[bool, str]:
        """Handle keyboard input and return (continue_running, window_name)"""
        if key == ord('q') or key == 27:  # Q or ESC
            logger.info("Exit requested by user")
            return False, window_name
        
        elif key == ord(' '):  # SPACE
            if self.video_recorder.recording:
                self.video_recorder.stop_recording()
            else:
                self.video_recorder.start_recording()
        
        elif key == ord('r'):  # Restart cameras
            window_name = self.restart_cameras(window_name)
        
        elif key == ord('d'):  # Force detection
            window_name = self.force_camera_detection(window_name)
        
        elif key == ord('f'):  # Toggle fullscreen
            self.display_manager.toggle_fullscreen(window_name)
        
        elif key == ord('+') or key == ord('='):  # Increase size
            self.display_manager.resize_window(window_name, increase=True)
        
        elif key == ord('-'):  # Decrease size
            self.display_manager.resize_window(window_name, increase=False)
        
        return True, window_name
    
    def run(self) -> None:
        """Main application loop"""
        if not self.initialize_system():
            logger.error("System initialization failed")
            return
        
        # Setup window
        window_name = f'Smart Cooler - {len(self.camera_manager.cameras)} Cameras (Auto-detect)'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(window_name, self.window_config.width, self.window_config.height)
        time.sleep(0.5)  # Let window initialize
        
        self.print_startup_info()
        
        try:
            while self.running:
                # Update video recording with current frames
                self.video_recorder.write_frames()
                
                # Create and display grid
                grid = self.display_manager.create_display_grid(
                    window_name=window_name,
                    current_product=self.video_recorder.current_product,
                    recording=self.video_recorder.recording,
                    record_start_time=self.video_recorder.record_start_time
                )
                
                if grid is not None:
                    cv2.imshow(window_name, grid)
                
                # Check if window was closed
                try:
                    if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                        logger.info("Window closed by user")
                        break
                except cv2.error:
                    logger.info("Window no longer exists")
                    break
                
                # Handle keyboard input
                key = cv2.waitKey(1) & 0xFF
                if key != 255:  # Key was pressed
                    continue_running, window_name = self.handle_key_input(key, window_name)
                    if not continue_running:
                        break
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up all resources"""
        logger.info("Cleaning up resources...")
        
        self.running = False
        
        # Stop recording if active
        self.video_recorder.cleanup()
        
        # Clean up camera resources
        self.camera_manager.cleanup()
        
        # Close all OpenCV windows
        cv2.destroyAllWindows()
        
        logger.info("Cleanup completed")


def main():
    """Entry point of the application"""
    try:
        recorder = MultiCameraRecorder()
        recorder.run()
    except Exception as e:
        logger.error(f"Application failed to start: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())