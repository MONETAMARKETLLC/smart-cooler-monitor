#!/usr/bin/env python3
"""
Smart Cooler - Grabador de 4 Cámaras Simultáneas
Controles:
- SPACE: Iniciar/Parar grabación
- Q: Salir
- R: Reiniciar (si alguna cámara falla)
"""

import cv2
import threading
import time
import os
from datetime import datetime
import numpy as np

class MultiCameraRecorder:
    def __init__(self):
        # Dispositivos de las 4 cámaras
        self.camera_devices = [0, 2, 4, 6]
        self.cameras = {}
        self.writers = {}
        self.frames = {}
        self.recording = False
        self.running = True
        self.record_start_time = None
        
        # Configuración de video
        self.fps = 30
        self.width = 640
        self.height = 480
        self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # Crear carpeta para clips si no existe
        self.output_dir = "clips"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f" Carpeta creada: {self.output_dir}/")
    
    def initialize_single_camera(self, device_id, timeout=10):
        """Inicializa una sola cámara con timeout"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Timeout inicializando cámara {device_id}")
        
        try:
            print(f" Inicializando cámara /dev/video{device_id}...")
            
            # Configurar timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # Intentar con diferentes backends
            for backend in [cv2.CAP_V4L2, cv2.CAP_ANY]:
                try:
                    cap = cv2.VideoCapture(device_id, backend)
                    if cap.isOpened():
                        break
                    cap.release()
                except:
                    continue
            else:
                raise Exception("No se pudo abrir con ningún backend")
            
            # Configurar parámetros básicos
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
            
            # Probar captura rápida
            for _ in range(3):  # Intentar 3 veces
                ret, frame = cap.read()
                if ret and frame is not None:
                    signal.alarm(0)  # Cancelar timeout
                    return cap, frame
                time.sleep(0.1)
            
            cap.release()
            raise Exception("No puede capturar frames")
            
        except TimeoutError as e:
            print(f"⏰ {e}")
            return None, None
        except Exception as e:
            print(f"❌ Error cámara {device_id}: {e}")
            return None, None
        finally:
            signal.alarm(0)  # Asegurar que se cancele el timeout

    def initialize_cameras(self):
        """Inicializa todas las cámaras con timeouts"""
        print(" Inicializando cámaras...")
        
        for device_id in self.camera_devices:
            cap, frame = self.initialize_single_camera(device_id)
            
            if cap is not None and frame is not None:
                self.cameras[device_id] = cap
                self.frames[device_id] = frame
                print(f"✅ Cámara {device_id} OK - {frame.shape}")
            else:
                print(f"❌ Cámara {device_id} falló")
        
        if len(self.cameras) == 0:
            print("❌ No se inicializó ninguna cámara")
            return False
            
        print(f" {len(self.cameras)} cámaras inicializadas")
        return True
    
    def capture_thread(self, device_id):
        """Hilo de captura continua para una cámara"""
        cap = self.cameras[device_id]
        
        while self.running:
            ret, frame = cap.read()
            if ret:
                self.frames[device_id] = frame.copy()
                
                # Si está grabando, escribir al video
                if self.recording and device_id in self.writers:
                    self.writers[device_id].write(frame)
            
            time.sleep(1/self.fps)
    
    def start_capture_threads(self):
        """Inicia hilos de captura para todas las cámaras"""
        self.threads = []
        for device_id in self.cameras.keys():
            thread = threading.Thread(target=self.capture_thread, args=(device_id,))
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
            print(f" Hilo iniciado para cámara {device_id}")
    
    def start_recording(self):
        """Inicia la grabación"""
        if self.recording:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.writers = {}
        
        print(f"\n GRABANDO - {timestamp}")
        
        for device_id in self.cameras.keys():
            filename = os.path.join(self.output_dir, f"clip_cam{device_id}_{timestamp}.mp4")
            writer = cv2.VideoWriter(filename, self.fourcc, self.fps, (self.width, self.height))
            
            if writer.isOpened():
                self.writers[device_id] = writer
                print(f" Grabando: {filename}")
            else:
                print(f"❌ Error creando writer para cámara {device_id}")
        
        if self.writers:
            self.recording = True
            self.record_start_time = time.time()
    
    def stop_recording(self):
        """Detiene la grabación"""
        if not self.recording:
            return
            
        self.recording = False
        duration = time.time() - self.record_start_time
        
        # Cerrar todos los writers
        for device_id, writer in self.writers.items():
            writer.release()
            print(f" Guardado: clip_cam{device_id} ({duration:.1f}s)")
        
        self.writers = {}
        print(f"⏹️  Grabación terminada - Duración: {duration:.1f}s\n")
    
    def create_display_grid(self):
        """Crea la vista en grid de las 4 cámaras"""
        if len(self.frames) == 0:
            return None
        
        # Redimensionar frames para el display
        display_frames = []
        for device_id in sorted(self.cameras.keys()):
            if device_id in self.frames:
                frame = self.frames[device_id].copy()
                
                # Añadir información en el frame
                color = (0, 0, 255) if self.recording else (0, 255, 0)
                status = "REC" if self.recording else "LIVE"
                
                cv2.putText(frame, f'Cam {device_id} - {status}', (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                if self.recording and self.record_start_time:
                    duration = time.time() - self.record_start_time
                    cv2.putText(frame, f'{duration:.1f}s', (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                # Redimensionar para display
                frame_resized = cv2.resize(frame, (320, 240))
                display_frames.append(frame_resized)
        
        # Crear grid 2x2
        if len(display_frames) >= 4:
            top_row = np.hstack((display_frames[0], display_frames[1]))
            bottom_row = np.hstack((display_frames[2], display_frames[3]))
            grid = np.vstack((top_row, bottom_row))
        elif len(display_frames) == 3:
            top_row = np.hstack((display_frames[0], display_frames[1]))
            bottom_row = np.hstack((display_frames[2], np.zeros((240, 320, 3), dtype=np.uint8)))
            grid = np.vstack((top_row, bottom_row))
        elif len(display_frames) == 2:
            grid = np.hstack((display_frames[0], display_frames[1]))
        else:
            grid = display_frames[0]
        
        return grid
    
    def run(self):
        """Ejecuta la aplicación principal"""
        if not self.initialize_cameras():
            return
            
        self.start_capture_threads()
        
        print("\n" + "="*50)
        print(" SMART COOLER - GRABADOR DE 4 CÁMARAS")
        print("="*50)
        print("Controles:")
        print("  SPACE - Iniciar/Parar grabación")
        print("  Q     - Salir")
        print("  R     - Reiniciar cámaras")
        print("="*50)
        print(f" Clips se guardan en: {self.output_dir}/")
        print(" LISTO - Presiona SPACE para grabar\n")
        
        try:
            while self.running:
                grid = self.create_display_grid()
                if grid is not None:
                    cv2.imshow('Smart Cooler - 4 Cameras', grid)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    print("\n Saliendo...")
                    break
                elif key == ord(' '):  # SPACE
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
                elif key == ord('r'):
                    print("\n Reiniciando cámaras...")
                    self.cleanup_cameras()
                    time.sleep(1)
                    self.initialize_cameras()
                    self.start_capture_threads()
        
        except KeyboardInterrupt:
            print("\n⏹️  Detenido por usuario")
        
        finally:
            self.cleanup()
    
    def cleanup_cameras(self):
        """Limpia solo las cámaras"""
        for cap in self.cameras.values():
            cap.release()
        self.cameras = {}
        self.frames = {}
    
    def cleanup(self):
        """Limpia todos los recursos"""
        print("\n粒 Limpiando recursos...")
        
        self.running = False
        
        if self.recording:
            self.stop_recording()
        
        # Liberar cámaras
        self.cleanup_cameras()
        
        # Cerrar ventanas
        cv2.destroyAllWindows()
        
        print("✅ Limpieza completa")

def main():
    recorder = MultiCameraRecorder()
    recorder.run()

if __name__ == "__main__":
    main()#!/usr/bin/env python3
"""
Smart Cooler - Grabador de 4 Cámaras Simultáneas
Controles:
- SPACE: Iniciar/Parar grabación
- Q: Salir
- R: Reiniciar (si alguna cámara falla)
"""

import cv2
import threading
import time
import os
from datetime import datetime
import numpy as np

class MultiCameraRecorder:
    def __init__(self):
        # Dispositivos de las 4 cámaras
        self.camera_devices = [0, 2, 4, 6]
        self.cameras = {}
        self.writers = {}
        self.frames = {}
        self.recording = False
        self.running = True
        self.record_start_time = None
        
        # Configuración de video
        self.fps = 30
        self.width = 640
        self.height = 480
        self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # Crear carpeta para clips si no existe
        self.output_dir = "clips"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f" Carpeta creada: {self.output_dir}/")
    
    def initialize_single_camera(self, device_id, timeout=10):
        """Inicializa una sola cámara con timeout"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Timeout inicializando cámara {device_id}")
        
        try:
            print(f" Inicializando cámara /dev/video{device_id}...")
            
            # Configurar timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # Intentar con diferentes backends
            for backend in [cv2.CAP_V4L2, cv2.CAP_ANY]:
                try:
                    cap = cv2.VideoCapture(device_id, backend)
                    if cap.isOpened():
                        break
                    cap.release()
                except:
                    continue
            else:
                raise Exception("No se pudo abrir con ningún backend")
            
            # Configurar parámetros básicos
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
            
            # Probar captura rápida
            for _ in range(3):  # Intentar 3 veces
                ret, frame = cap.read()
                if ret and frame is not None:
                    signal.alarm(0)  # Cancelar timeout
                    return cap, frame
                time.sleep(0.1)
            
            cap.release()
            raise Exception("No puede capturar frames")
            
        except TimeoutError as e:
            print(f"⏰ {e}")
            return None, None
        except Exception as e:
            print(f"❌ Error cámara {device_id}: {e}")
            return None, None
        finally:
            signal.alarm(0)  # Asegurar que se cancele el timeout

    def initialize_cameras(self):
        """Inicializa todas las cámaras con timeouts"""
        print(" Inicializando cámaras...")
        
        for device_id in self.camera_devices:
            cap, frame = self.initialize_single_camera(device_id)
            
            if cap is not None and frame is not None:
                self.cameras[device_id] = cap
                self.frames[device_id] = frame
                print(f"✅ Cámara {device_id} OK - {frame.shape}")
            else:
                print(f"❌ Cámara {device_id} falló")
        
        if len(self.cameras) == 0:
            print("❌ No se inicializó ninguna cámara")
            return False
            
        print(f" {len(self.cameras)} cámaras inicializadas")
        return True
    
    def capture_thread(self, device_id):
        """Hilo de captura continua para una cámara"""
        cap = self.cameras[device_id]
        
        while self.running:
            ret, frame = cap.read()
            if ret:
                self.frames[device_id] = frame.copy()
                
                # Si está grabando, escribir al video
                if self.recording and device_id in self.writers:
                    self.writers[device_id].write(frame)
            
            time.sleep(1/self.fps)
    
    def start_capture_threads(self):
        """Inicia hilos de captura para todas las cámaras"""
        self.threads = []
        for device_id in self.cameras.keys():
            thread = threading.Thread(target=self.capture_thread, args=(device_id,))
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
            print(f" Hilo iniciado para cámara {device_id}")
    
    def start_recording(self):
        """Inicia la grabación"""
        if self.recording:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.writers = {}
        
        print(f"\n GRABANDO - {timestamp}")
        
        for device_id in self.cameras.keys():
            filename = os.path.join(self.output_dir, f"clip_cam{device_id}_{timestamp}.mp4")
            writer = cv2.VideoWriter(filename, self.fourcc, self.fps, (self.width, self.height))
            
            if writer.isOpened():
                self.writers[device_id] = writer
                print(f" Grabando: {filename}")
            else:
                print(f"❌ Error creando writer para cámara {device_id}")
        
        if self.writers:
            self.recording = True
            self.record_start_time = time.time()
    
    def stop_recording(self):
        """Detiene la grabación"""
        if not self.recording:
            return
            
        self.recording = False
        duration = time.time() - self.record_start_time
        
        # Cerrar todos los writers
        for device_id, writer in self.writers.items():
            writer.release()
            print(f" Guardado: clip_cam{device_id} ({duration:.1f}s)")
        
        self.writers = {}
        print(f"⏹️  Grabación terminada - Duración: {duration:.1f}s\n")
    
    def create_display_grid(self):
        """Crea la vista en grid de las 4 cámaras"""
        if len(self.frames) == 0:
            return None
        
        # Redimensionar frames para el display
        display_frames = []
        for device_id in sorted(self.cameras.keys()):
            if device_id in self.frames:
                frame = self.frames[device_id].copy()
                
                # Añadir información en el frame
                color = (0, 0, 255) if self.recording else (0, 255, 0)
                status = "REC" if self.recording else "LIVE"
                
                cv2.putText(frame, f'Cam {device_id} - {status}', (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                if self.recording and self.record_start_time:
                    duration = time.time() - self.record_start_time
                    cv2.putText(frame, f'{duration:.1f}s', (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                # Redimensionar para display
                frame_resized = cv2.resize(frame, (320, 240))
                display_frames.append(frame_resized)
        
        # Crear grid 2x2
        if len(display_frames) >= 4:
            top_row = np.hstack((display_frames[0], display_frames[1]))
            bottom_row = np.hstack((display_frames[2], display_frames[3]))
            grid = np.vstack((top_row, bottom_row))
        elif len(display_frames) == 3:
            top_row = np.hstack((display_frames[0], display_frames[1]))
            bottom_row = np.hstack((display_frames[2], np.zeros((240, 320, 3), dtype=np.uint8)))
            grid = np.vstack((top_row, bottom_row))
        elif len(display_frames) == 2:
            grid = np.hstack((display_frames[0], display_frames[1]))
        else:
            grid = display_frames[0]
        
        return grid
    
    def run(self):
        """Ejecuta la aplicación principal"""
        if not self.initialize_cameras():
            return
            
        self.start_capture_threads()
        
        print("\n" + "="*50)
        print(" SMART COOLER - GRABADOR DE 4 CÁMARAS")
        print("="*50)
        print("Controles:")
        print("  SPACE - Iniciar/Parar grabación")
        print("  Q     - Salir")
        print("  R     - Reiniciar cámaras")
        print("="*50)
        print(f" Clips se guardan en: {self.output_dir}/")
        print(" LISTO - Presiona SPACE para grabar\n")
        
        try:
            while self.running:
                grid = self.create_display_grid()
                if grid is not None:
                    cv2.imshow('Smart Cooler - 4 Cameras', grid)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    print("\n Saliendo...")
                    break
                elif key == ord(' '):  # SPACE
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
                elif key == ord('r'):
                    print("\n Reiniciando cámaras...")
                    self.cleanup_cameras()
                    time.sleep(1)
                    self.initialize_cameras()
                    self.start_capture_threads()
        
        except KeyboardInterrupt:
            print("\n⏹️  Detenido por usuario")
        
        finally:
            self.cleanup()
    
    def cleanup_cameras(self):
        """Limpia solo las cámaras"""
        for cap in self.cameras.values():
            cap.release()
        self.cameras = {}
        self.frames = {}
    
    def cleanup(self):
        """Limpia todos los recursos"""
        print("\n粒 Limpiando recursos...")
        
        self.running = False
        
        if self.recording:
            self.stop_recording()
        
        # Liberar cámaras
        self.cleanup_cameras()
        
        # Cerrar ventanas
        cv2.destroyAllWindows()
        
        print("✅ Limpieza completa")

def main():
    recorder = MultiCameraRecorder()
    recorder.run()

if __name__ == "__main__":
    main()