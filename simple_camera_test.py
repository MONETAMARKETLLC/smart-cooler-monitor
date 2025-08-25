#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import threading
import time

class SimpleCameraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Test de Cámaras USB - Docker")
        self.root.geometry("800x600")
        
        self.camera = None
        self.camera_running = False
        self.current_camera = 0
        
        self.setup_ui()
        self.detect_cameras()
    
    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = ttk.Label(main_frame, text="Test de Cámaras USB", font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Frame de controles
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Lista de cámaras detectadas
        ttk.Label(control_frame, text="Cámara:").pack(side=tk.LEFT)
        self.camera_var = tk.StringVar()
        self.camera_combo = ttk.Combobox(control_frame, textvariable=self.camera_var, width=20, state="readonly")
        self.camera_combo.pack(side=tk.LEFT, padx=(5, 10))
        
        # Botones
        self.start_btn = ttk.Button(control_frame, text="Iniciar", command=self.start_camera)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="Detener", command=self.stop_camera, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.refresh_btn = ttk.Button(control_frame, text="Detectar Cámaras", command=self.detect_cameras)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Frame para el video
        self.video_frame = ttk.Frame(main_frame, relief="sunken")
        self.video_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Label para mostrar video
        self.video_label = ttk.Label(self.video_frame, text="Selecciona una cámara y presiona 'Iniciar'", 
                                    anchor="center", font=("Arial", 12))
        self.video_label.pack(expand=True)
        
        # Frame de información
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.info_text = tk.Text(info_frame, height=8, width=80)
        scrollbar = ttk.Scrollbar(info_frame, orient="vertical", command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scrollbar.set)
        
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log("Aplicación iniciada")
    
    def log(self, message):
        """Agregar mensaje al log"""
        timestamp = time.strftime("%H:%M:%S")
        self.info_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.info_text.see(tk.END)
        self.root.update_idletasks()
    
    def detect_cameras(self):
        """Detectar cámaras disponibles"""
        self.log("Detectando cámaras USB...")
        
        available_cameras = []
        
        # Probar índices 0-7
        for i in range(8):
            self.log(f"Probando cámara {i}...")
            
            try:
                # Probar con V4L2
                cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        # Obtener información de la cámara
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        
                        camera_info = f"Cámara {i} ({width}x{height})"
                        available_cameras.append((i, camera_info))
                        self.log(f"✓ Encontrada: {camera_info}")
                    else:
                        self.log(f"✗ Cámara {i}: Se abre pero no lee frames")
                else:
                    self.log(f"✗ Cámara {i}: No se puede abrir")
                
                cap.release()
                
            except Exception as e:
                self.log(f"✗ Error con cámara {i}: {str(e)}")
            
            time.sleep(0.1)  # Pausa breve
        
        # Actualizar combo
        if available_cameras:
            self.camera_combo['values'] = [info for _, info in available_cameras]
            self.camera_combo.set(available_cameras[0][1])
            self.camera_indices = {info: idx for idx, info in available_cameras}
            self.log(f"Total cámaras detectadas: {len(available_cameras)}")
        else:
            self.camera_combo['values'] = ["No se encontraron cámaras"]
            self.camera_combo.set("No se encontraron cámaras")
            self.camera_indices = {}
            self.log("⚠ No se detectaron cámaras funcionando")
    
    def start_camera(self):
        """Iniciar la cámara seleccionada"""
        if not hasattr(self, 'camera_indices') or not self.camera_indices:
            messagebox.showerror("Error", "No hay cámaras disponibles")
            return
        
        selected = self.camera_var.get()
        if selected not in self.camera_indices:
            messagebox.showerror("Error", "Selecciona una cámara válida")
            return
        
        self.current_camera = self.camera_indices[selected]
        self.log(f"Iniciando cámara {self.current_camera}...")
        
        try:
            # Configurar cámara
            self.camera = cv2.VideoCapture(self.current_camera, cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                raise Exception("No se pudo abrir la cámara")
            
            # Configurar propiedades
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.camera.set(cv2.CAP_PROP_FPS, 10)
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Probar lectura
            ret, frame = self.camera.read()
            if not ret or frame is None:
                raise Exception("La cámara no puede leer frames")
            
            self.camera_running = True
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.camera_combo.config(state=tk.DISABLED)
            
            # Iniciar hilo para captura de video
            self.video_thread = threading.Thread(target=self.update_video, daemon=True)
            self.video_thread.start()
            
            self.log(f"✓ Cámara {self.current_camera} iniciada correctamente")
            
        except Exception as e:
            self.log(f"✗ Error iniciando cámara: {str(e)}")
            messagebox.showerror("Error", f"No se pudo iniciar la cámara:\n{str(e)}")
            if self.camera:
                self.camera.release()
                self.camera = None
    
    def stop_camera(self):
        """Detener la cámara"""
        self.log("Deteniendo cámara...")
        
        self.camera_running = False
        
        if self.camera:
            self.camera.release()
            self.camera = None
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.camera_combo.config(state="readonly")
        
        # Limpiar video
        self.video_label.config(image="", text="Cámara detenida")
        
        self.log("✓ Cámara detenida")
    
    def update_video(self):
        """Actualizar frames de video en un hilo separado"""
        frame_count = 0
        
        while self.camera_running and self.camera:
            try:
                ret, frame = self.camera.read()
                
                if ret and frame is not None and frame.size > 0:
                    frame_count += 1
                    
                    # Redimensionar frame para mostrar
                    display_frame = cv2.resize(frame, (640, 480))
                    display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                    
                    # Convertir a formato Tkinter
                    pil_image = Image.fromarray(display_frame)
                    tk_image = ImageTk.PhotoImage(pil_image)
                    
                    # Actualizar UI en el hilo principal
                    self.root.after(0, self.update_video_label, tk_image, frame_count)
                    
                else:
                    self.log(f"⚠ Frame vacío en cámara {self.current_camera}")
                
                time.sleep(0.1)  # ~10 FPS
                
            except Exception as e:
                self.log(f"✗ Error capturando frame: {str(e)}")
                break
    
    def update_video_label(self, tk_image, frame_count):
        """Actualizar label de video (llamado desde hilo principal)"""
        if self.camera_running:
            self.video_label.config(image=tk_image, text="")
            self.video_label.image = tk_image  # Mantener referencia
            
            # Log periódico
            if frame_count % 50 == 0:
                self.log(f"Frames procesados: {frame_count}")
    
    def on_closing(self):
        """Manejar cierre de aplicación"""
        if self.camera_running:
            self.stop_camera()
        self.root.destroy()

if __name__ == "__main__":
    # Verificar que OpenCV está disponible
    print(f"OpenCV version: {cv2.__version__}")
    
    root = tk.Tk()
    app = SimpleCameraApp(root)
    
    # Manejar cierre de ventana
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()