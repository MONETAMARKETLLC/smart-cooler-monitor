#!/usr/bin/env python3
"""
Smart Cooler - Multi-Camera Recorder with Auto-Detection
Refactored version following Python best practices

Controls:
- SPACE: Select product and record
- Q: Exit  
- R: Restart cameras
- D: Force camera detection
- F: Toggle fullscreen
- +/-: Resize window
"""

import cv2
import threading
import time
import os
import json
import logging
import signal
import subprocess
import glob
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
from difflib import get_close_matches
import tkinter as tk
from tkinter import messagebox, simpledialog
import numpy as np


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smart_cooler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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


class CameraError(Exception):
    """Custom exception for camera-related errors"""
    pass


class ProductManager:
    """Manages product database and versioning"""
    
    def __init__(self, products_file: str = "products.json", clips_base_dir: str = "clips"):
        self.products_file = Path(products_file)
        self.clips_base_dir = Path(clips_base_dir)
        self.products = self._load_products()
        self._ensure_clips_directory()
    
    def _load_products(self) -> List[str]:
        """Load products from JSON file"""
        if not self.products_file.exists():
            return []
        
        try:
            with open(self.products_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading products file: {e}")
            return []
    
    def _save_products(self) -> None:
        """Save products to JSON file"""
        try:
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(sorted(list(set(self.products))), f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Error saving products: {e}")
    
    def _ensure_clips_directory(self) -> None:
        """Ensure clips directory exists"""
        self.clips_base_dir.mkdir(exist_ok=True)
        logger.info(f"Clips directory ready: {self.clips_base_dir}")
    
    def add_product(self, product_name: str) -> bool:
        """Add a new product to the list"""
        base_product = self._extract_base_product_name(product_name)
        if base_product not in self.products:
            self.products.append(base_product)
            self._save_products()
            logger.info(f"New product added: {base_product}")
            return True
        return False
    
    def _extract_base_product_name(self, versioned_name: str) -> str:
        """Extract base product name without version suffix"""
        match = re.match(r'^(.+)_v\d+$', versioned_name)
        return match.group(1) if match else versioned_name
    
    def get_next_version(self, base_product_name: str) -> str:
        """Get next available version for a product"""
        if not self.clips_base_dir.exists():
            return f"{base_product_name}_v1"
        
        pattern = f"{base_product_name}_v*"
        existing_dirs = list(self.clips_base_dir.glob(pattern))
        
        if not existing_dirs:
            return f"{base_product_name}_v1"
        
        version_numbers = []
        for dir_path in existing_dirs:
            match = re.match(f'^{re.escape(base_product_name)}_v(\\d+)$', dir_path.name)
            if match:
                version_numbers.append(int(match.group(1)))
        
        if not version_numbers:
            return f"{base_product_name}_v1"
        
        next_version = max(version_numbers) + 1
        return f"{base_product_name}_v{next_version}"
    
    def find_similar_products(self, query: str, max_matches: int = 5) -> List[str]:
        """Find similar products using fuzzy matching"""
        if not query:
            return []
        
        base_query = self._extract_base_product_name(query)
        
        # Exact matches first
        exact_matches = [p for p in self.products if base_query.lower() in p.lower()]
        
        # Fuzzy matches
        fuzzy_matches = get_close_matches(
            base_query.lower(),
            [p.lower() for p in self.products],
            n=max_matches,
            cutoff=0.6
        )
        
        # Map back to original names
        fuzzy_original = []
        for fuzzy in fuzzy_matches:
            for product in self.products:
                if product.lower() == fuzzy:
                    fuzzy_original.append(product)
                    break
        
        # Combine and remove duplicates
        all_matches = []
        for match in exact_matches + fuzzy_original:
            if match not in all_matches:
                all_matches.append(match)
        
        return all_matches[:max_matches]
    
    def get_existing_versions(self, base_product: str) -> List[str]:
        """Get list of existing versions for a product"""
        if not self.clips_base_dir.exists():
            return []
        
        pattern = f"{base_product}_v*"
        existing_dirs = list(self.clips_base_dir.glob(pattern))
        
        versions = []
        for dir_path in existing_dirs:
            match = re.match(f'^{re.escape(base_product)}_v(\\d+)$', dir_path.name)
            if match:
                versions.append(f"v{match.group(1)}")
        
        return sorted(versions, key=lambda x: int(x[1:]))
    
    def get_product_input(self) -> Optional[str]:
        """Get product name with validation and automatic versioning"""
        root = tk.Tk()
        root.withdraw()
        
        try:
            while True:
                product_name = simpledialog.askstring(
                    "Smart Cooler - Product",
                    "Product name to record:",
                    initialvalue=""
                )
                
                if product_name is None:
                    return None
                
                product_name = product_name.strip()
                if not product_name:
                    messagebox.showwarning("Warning", "Please enter a product name")
                    continue
                
                normalized_name = product_name.lower().replace(' ', '_')
                base_product = self._extract_base_product_name(normalized_name)
                
                if base_product in [p.lower() for p in self.products]:
                    return self._handle_existing_product(base_product)
                else:
                    return self._handle_new_product(base_product, normalized_name)
        
        finally:
            root.destroy()
    
    def _handle_existing_product(self, base_product: str) -> Optional[str]:
        """Handle existing product logic"""
        versioned_name = self.get_next_version(base_product)
        existing_versions = self.get_existing_versions(base_product)
        
        version_info = f"Existing versions: {', '.join(existing_versions)}" if existing_versions else "First recording"
        
        confirm = messagebox.askyesno(
            "Existing Product",
            f"Product: {base_product}\n{version_info}\n\n"
            f"New version will be: {versioned_name}\n\nContinue?"
        )
        
        return versioned_name if confirm else None
    
    def _handle_new_product(self, base_product: str, normalized_name: str) -> Optional[str]:
        """Handle new product logic"""
        similar = self.find_similar_products(base_product)
        
        if similar:
            return self._handle_similar_products(similar, base_product)
        else:
            confirm = messagebox.askyesno(
                "New Product",
                f"'{base_product}' will be a new product.\n\nContinue?"
            )
            
            if confirm:
                new_versioned_name = f"{base_product}_v1"
                self.add_product(base_product)
                return new_versioned_name
        
        return None
    
    def _handle_similar_products(self, similar: List[str], base_product: str) -> Optional[str]:
        """Handle similar products logic"""
        suggestions_text = "\n".join([f"• {p}" for p in similar])
        
        response = messagebox.askyesnocancel(
            "Similar Products Found",
            f"Do you mean one of these products?\n\n{suggestions_text}\n\n"
            f"YES = Show options\nNO = Use '{base_product}' as new product\nCANCEL = Enter different name"
        )
        
        if response is True:
            choice = self._choose_from_suggestions(similar, base_product)
            if choice:
                versioned_choice = self.get_next_version(choice)
                existing_versions = self.get_existing_versions(choice)
                version_info = f"Existing versions: {', '.join(existing_versions)}" if existing_versions else "First recording"
                
                confirm = messagebox.askyesno(
                    "Version Confirmation",
                    f"Selected product: {choice}\n{version_info}\n\n"
                    f"New version will be: {versioned_choice}\n\nContinue?"
                )
                
                return versioned_choice if confirm else None
        elif response is False:
            new_versioned_name = f"{base_product}_v1"
            self.add_product(base_product)
            return new_versioned_name
        
        return None
    
    def _choose_from_suggestions(self, suggestions: List[str], original_query: str) -> Optional[str]:
        """Allow choosing from a list of suggestions"""
        root = tk.Tk()
        root.title("Select Product")
        root.geometry("400x300")
        
        selected_product = None
        
        tk.Label(root, text=f"Products similar to: '{original_query}'",
                font=("Arial", 12, "bold")).pack(pady=10)
        
        selection_var = tk.StringVar()
        
        frame = tk.Frame(root)
        frame.pack(pady=10, padx=20, fill='both', expand=True)
        
        for product in suggestions:
            existing_versions = self.get_existing_versions(product)
            version_text = f" ({', '.join(existing_versions)})" if existing_versions else " (new)"
            display_text = f"{product}{version_text}"
            
            tk.Radiobutton(
                frame,
                text=display_text,
                variable=selection_var,
                value=product,
                font=("Arial", 10)
            ).pack(anchor='w', pady=2)
        
        def on_select():
            nonlocal selected_product
            selected_product = selection_var.get()
            root.quit()
        
        def on_cancel():
            nonlocal selected_product
            selected_product = None
            root.quit()
        
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Select", command=on_select,
                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", command=on_cancel,
                 bg="#f44336", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=5)
        
        try:
            root.mainloop()
            return selected_product
        finally:
            root.destroy()


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