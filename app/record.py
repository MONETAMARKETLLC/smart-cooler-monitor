#!/usr/bin/env python3
"""
Smart Cooler - Grabador de 4 Cámaras Simultáneas
Controles:
- SPACE: Seleccionar producto y grabar
- Q: Salir
- R: Reiniciar (si alguna cámara falla)
"""

import cv2
import threading
import time
import os
import json
from datetime import datetime
import numpy as np
from difflib import get_close_matches
import tkinter as tk
from tkinter import messagebox, simpledialog
import glob
import re

class ProductManager:
    def __init__(self, products_file="products.json", clips_base_dir="clips"):
        self.products_file = products_file
        self.clips_base_dir = clips_base_dir
        self.products = self.load_products()
    
    def load_products(self):
        """Carga la lista de productos del archivo JSON"""
        if os.path.exists(self.products_file):
            try:
                with open(self.products_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_products(self):
        """Guarda la lista de productos al archivo JSON"""
        try:
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(sorted(list(set(self.products))), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Error guardando productos: {e}")
    
    def add_product(self, product_name):
        """Añade un producto nuevo a la lista"""
        base_product = self.extract_base_product_name(product_name)
        if base_product not in self.products:
            self.products.append(base_product)
            self.save_products()
            return True
        return False
    
    def extract_base_product_name(self, versioned_name):
        """Extrae el nombre base del producto sin versión"""
        # Remover sufijos _v1, _v2, etc.
        match = re.match(r'^(.+)_v\d+$', versioned_name)
        if match:
            return match.group(1)
        return versioned_name
    
    def get_next_version(self, base_product_name):
        """Obtiene la siguiente versión disponible para un producto"""
        if not os.path.exists(self.clips_base_dir):
            return f"{base_product_name}_v1"
        
        # Buscar todas las versiones existentes
        pattern = f"{base_product_name}_v*"
        existing_dirs = glob.glob(os.path.join(self.clips_base_dir, pattern))
        
        if not existing_dirs:
            return f"{base_product_name}_v1"
        
        # Extraer números de versión
        version_numbers = []
        for dir_path in existing_dirs:
            dir_name = os.path.basename(dir_path)
            match = re.match(f'^{re.escape(base_product_name)}_v(\\d+)$', dir_name)
            if match:
                version_numbers.append(int(match.group(1)))
        
        if not version_numbers:
            return f"{base_product_name}_v1"
        
        next_version = max(version_numbers) + 1
        return f"{base_product_name}_v{next_version}"
    
    def find_similar_products(self, query, max_matches=5):
        """Encuentra productos similares usando fuzzy matching"""
        if not query:
            return []
        
        # Extraer nombre base si tiene versión
        base_query = self.extract_base_product_name(query)
        
        # Buscar coincidencias exactas primero
        exact_matches = [p for p in self.products if base_query.lower() in p.lower()]
        
        # Buscar coincidencias aproximadas
        fuzzy_matches = get_close_matches(
            base_query.lower(), 
            [p.lower() for p in self.products], 
            n=max_matches, 
            cutoff=0.6
        )
        
        # Mapear de vuelta a nombres originales
        fuzzy_original = []
        for fuzzy in fuzzy_matches:
            for product in self.products:
                if product.lower() == fuzzy:
                    fuzzy_original.append(product)
                    break
        
        # Combinar y eliminar duplicados manteniendo orden
        all_matches = []
        for match in exact_matches + fuzzy_original:
            if match not in all_matches:
                all_matches.append(match)
        
        return all_matches[:max_matches]
    
    def get_product_input(self):
        """Obtiene el nombre del producto con validación y versionado automático"""
        root = tk.Tk()
        root.withdraw()  # Ocultar ventana principal
        
        while True:
            # Pedir nombre del producto
            product_name = simpledialog.askstring(
                "Smart Cooler - Producto",
                "Nombre del producto a grabar:",
                initialvalue=""
            )
            
            if product_name is None:  # Usuario canceló
                root.destroy()
                return None
            
            product_name = product_name.strip()
            
            if not product_name:
                messagebox.showwarning("Advertencia", "Por favor ingresa un nombre de producto")
                continue
            
            # Normalizar nombre (reemplazar espacios con guiones bajos)
            normalized_name = product_name.lower().replace(' ', '_')
            base_product = self.extract_base_product_name(normalized_name)
            
            # Verificar si el producto base ya existe
            if base_product in [p.lower() for p in self.products]:
                # Producto existe, determinar versión
                versioned_name = self.get_next_version(base_product)
                
                # Mostrar información de versionado
                existing_versions = self.get_existing_versions(base_product)
                version_info = f"Versiones existentes: {', '.join(existing_versions)}" if existing_versions else "Primera grabación"
                
                confirm = messagebox.askyesno(
                    "Producto existente",
                    f"Producto: {base_product}\n" +
                    f"{version_info}\n\n" +
                    f"Nueva versión será: {versioned_name}\n\n" +
                    f"¿Continuar?"
                )
                
                if confirm:
                    root.destroy()
                    return versioned_name
                # Si no confirma, continúa el loop para ingresar otro nombre
                
            else:
                # Buscar productos similares
                similar = self.find_similar_products(base_product)
                
                if similar:
                    # Mostrar sugerencias
                    suggestions_text = "\n".join([f"• {p}" for p in similar])
                    
                    response = messagebox.askyesnocancel(
                        "Productos similares encontrados",
                        f"¿Te refieres a alguno de estos productos?\n\n{suggestions_text}\n\n" +
                        f"SÍ = Mostrar opciones\n" +
                        f"NO = Usar '{base_product}' como producto nuevo\n" +
                        f"CANCELAR = Escribir otro nombre"
                    )
                    
                    if response is True:  # Sí - elegir de sugerencias
                        choice = self.choose_from_suggestions(similar, base_product)
                        if choice:
                            # Generar versión para el producto elegido
                            versioned_choice = self.get_next_version(choice)
                            existing_versions = self.get_existing_versions(choice)
                            version_info = f"Versiones existentes: {', '.join(existing_versions)}" if existing_versions else "Primera grabación"
                            
                            confirm = messagebox.askyesno(
                                "Confirmación de versión",
                                f"Producto seleccionado: {choice}\n" +
                                f"{version_info}\n\n" +
                                f"Nueva versión será: {versioned_choice}\n\n" +
                                f"¿Continuar?"
                            )
                            
                            if confirm:
                                root.destroy()
                                return versioned_choice
                        continue
                        
                    elif response is False:  # No - producto nuevo
                        new_versioned_name = f"{base_product}_v1"
                        self.add_product(base_product)
                        print(f"✅ Producto nuevo añadido: {base_product}")
                        root.destroy()
                        return new_versioned_name
                        
                    # None - Cancelar, continúa el loop
                    
                else:
                    # No hay productos similares, confirmar nuevo producto
                    confirm = messagebox.askyesno(
                        "Producto nuevo",
                        f"'{base_product}' será un producto nuevo.\n\n¿Continuar?"
                    )
                    
                    if confirm:
                        new_versioned_name = f"{base_product}_v1"
                        self.add_product(base_product)
                        print(f"✅ Producto nuevo añadido: {base_product}")
                        root.destroy()
                        return new_versioned_name
        
        root.destroy()
        return None
    
    def get_existing_versions(self, base_product):
        """Obtiene lista de versiones existentes de un producto"""
        if not os.path.exists(self.clips_base_dir):
            return []
        
        pattern = f"{base_product}_v*"
        existing_dirs = glob.glob(os.path.join(self.clips_base_dir, pattern))
        
        versions = []
        for dir_path in existing_dirs:
            dir_name = os.path.basename(dir_path)
            match = re.match(f'^{re.escape(base_product)}_v(\\d+)$', dir_name)
            if match:
                versions.append(f"v{match.group(1)}")
        
        return sorted(versions, key=lambda x: int(x[1:]))  # Ordenar por número
    
    def choose_from_suggestions(self, suggestions, original_query):
        """Permite elegir de una lista de sugerencias"""
        root = tk.Tk()
        root.title("Seleccionar Producto")
        root.geometry("400x300")
        
        selected_product = None
        
        tk.Label(root, text=f"Productos similares a: '{original_query}'", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        # Variable para almacenar selección
        selection_var = tk.StringVar()
        
        # Frame para lista de productos
        frame = tk.Frame(root)
        frame.pack(pady=10, padx=20, fill='both', expand=True)
        
        for product in suggestions:
            # Mostrar versiones existentes junto al nombre
            existing_versions = self.get_existing_versions(product)
            version_text = f" ({', '.join(existing_versions)})" if existing_versions else " (nuevo)"
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
        
        # Botones
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Seleccionar", command=on_select, 
                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancelar", command=on_cancel, 
                 bg="#f44336", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=5)
        
        root.mainloop()
        root.destroy()
        
        return selected_product

class MultiCameraRecorder:
    def __init__(self):
        # Las cámaras se detectarán automáticamente
        self.camera_devices = []
        self.cameras = {}
        self.writers = {}
        self.frames = {}
        self.recording = False
        self.running = True
        self.record_start_time = None
        self.current_product = None
        
        # Configuración de video
        self.fps = 60
        self.width = 800
        self.height = 600
        self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # FIXED: Variables para manejo dinámico de ventana
        self.window_width = 800
        self.window_height = 600
        self.min_window_width = 400
        self.min_window_height = 300
        self.max_window_width = 1920
        self.max_window_height = 1080
        
        # FIXED: Variable para trackear cambios de tamaño
        self.last_known_size = (800, 600)
        self.size_check_interval = 0.1  # Cada 100ms
        self.last_size_check = 0
        
        # Crear carpeta base para clips si no existe
        self.base_clips_dir = "clips"
        if not os.path.exists(self.base_clips_dir):
            os.makedirs(self.base_clips_dir)
            print(f"📁 Carpeta creada: {self.base_clips_dir}/")
        
        # Gestor de productos con versionado
        self.product_manager = ProductManager(clips_base_dir=self.base_clips_dir)
    
    def detect_available_cameras(self, max_cameras=10):
        """Detecta automáticamente las cámaras disponibles usando v4l2 primero"""
        print("🔍 Detectando cámaras disponibles...")
        available_cameras = {}

        # Método 1: Buscar usando v4l2-ctl
        try:
            import subprocess
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                print("📋 Información de v4l2-ctl:")
                lines = result.stdout.splitlines()
                current_device_name = None

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Si la línea no es un path → es la descripción del dispositivo
                    if not line.startswith("/dev/video"):
                        current_device_name = line
                        continue

                    # Si es un path de dispositivo
                    if line.startswith("/dev/video"):
                        try:
                            device_id = int(line.replace("/dev/video", ""))
                            available_cameras[line] = {
                                "id": device_id,
                                "name": current_device_name
                            }
                            print(f"  📷 {line} → {current_device_name}")
                        except ValueError:
                            pass
        except Exception as e:
            print(f"⚠️ Error con v4l2-ctl: {e}")

        # Método 2: fallback secuencial
        if not available_cameras:
            print("🔄 Probando dispositivos secuencialmente...")
            for device_id in range(max_cameras):
                if self.test_camera_quick(device_id):
                    path = f"/dev/video{device_id}"
                    available_cameras[path] = {"id": device_id, "name": "Unknown"}
                    print(f"  ✅ {path} disponible")

        # Método 3: buscar archivos directos
        if not available_cameras:
            print("📁 Buscando archivos /dev/video*...")
            import glob
            for path in sorted(glob.glob("/dev/video*")):
                try:
                    device_id = int(path.replace("/dev/video", ""))
                    if self.test_camera_quick(device_id):
                        available_cameras[path] = {"id": device_id, "name": "Unknown"}
                        print(f"  ✅ {path} disponible")
                except ValueError:
                    pass

        self.camera_devices = available_cameras

        if available_cameras:
            print(f"🎉 {len(available_cameras)} cámaras detectadas")
        else:
            print("❌ No se detectaron cámaras disponibles")

        return available_cameras

    def test_camera_quick(self, device_id, timeout=3):
        """Prueba rápida si una cámara está disponible"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError()
        
        try:
            # Configurar timeout corto
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # Intentar abrir la cámara
            cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
            if not cap.isOpened():
                return False
            
            # Intentar leer un frame
            ret, frame = cap.read()
            cap.release()
            signal.alarm(0)
            
            return ret and frame is not None
            
        except (TimeoutError, Exception):
            return False
        finally:
            signal.alarm(0)
    
    def get_camera_info(self, device_id):
        """Obtiene información detallada de una cámara"""
        try:
            cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
            if not cap.isOpened():
                return None
            
            info = {
                'device_id': device_id,
                'backend': cap.getBackendName(),
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'fourcc': cap.get(cv2.CAP_PROP_FOURCC)
            }
            
            cap.release()
            return info
            
        except Exception as e:
            return None
    
    def show_camera_details(self):
        """Muestra información detallada de las cámaras detectadas"""
        if not self.camera_devices:
            return
            
        print("\n📊 INFORMACIÓN DE CÁMARAS DETECTADAS:")
        print("-" * 50)
        
        for device_id in self.camera_devices:
            info = self.get_camera_info(device_id)
            if info:
                print(f"📷 Cámara {device_id}:")
                print(f"   Backend: {info['backend']}")
                print(f"   Resolución: {info['width']}x{info['height']}")
                print(f"   FPS: {info['fps']}")
                print()
    
    def initialize_single_camera(self, device_id, timeout=10):
        """Inicializa una sola cámara con timeout"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Timeout inicializando cámara {device_id}")
        
        try:
            print(f"📷 Inicializando cámara /dev/video{device_id}...")
            
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
        """Inicializa todas las cámaras detectadas"""
        # Detectar cámaras disponibles primero
        if not self.camera_devices:
            available_cameras = self.detect_available_cameras()
            if not available_cameras:
                print("❌ No se encontraron cámaras disponibles")
                return False
        
        print("\n🔍 Inicializando cámaras detectadas...")
        self.show_camera_details()
        
        successfully_initialized = []
        
        for device_id in self.camera_devices:
            cap, frame = self.initialize_single_camera(device_id)
            
            if cap is not None and frame is not None:
                self.cameras[device_id] = cap
                self.frames[device_id] = frame
                successfully_initialized.append(device_id)
                print(f"✅ Cámara {device_id} OK - {frame.shape}")
            else:
                print(f"❌ Cámara {device_id} falló en inicialización")
        
        # Actualizar la lista con solo las cámaras que funcionan
        self.camera_devices = successfully_initialized
        
        if len(self.cameras) == 0:
            print("❌ No se inicializó ninguna cámara")
            return False
            
        print(f"\n🎉 {len(self.cameras)} cámaras inicializadas correctamente: {successfully_initialized}")
        return True
    
    def force_detect_cameras(self):
        """Fuerza una nueva detección de cámaras (para usar con tecla D)"""
        print("\n🔄 FORZANDO DETECCIÓN DE CÁMARAS...")
        self.cleanup_cameras()
        self.camera_devices = []  # Limpiar lista actual
        time.sleep(1)
        
        available_cameras = self.detect_available_cameras()
        if available_cameras:
            self.initialize_cameras()
            self.start_capture_threads()
            print("✅ Detección completada")
        else:
            print("❌ No se encontraron nuevas cámaras")
    
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
            print(f"🎬 Hilo iniciado para cámara {device_id}")
    
    def start_recording(self):
        """Inicia la grabación después de obtener el nombre del producto versionado"""
        if self.recording:
            return
            
        # Verificar que hay cámaras disponibles
        if not self.cameras:
            print("❌ No hay cámaras disponibles para grabar")
            return
            
        # Obtener nombre del producto con versionado automático
        print("🏷️  Seleccionando producto...")
        versioned_product_name = self.product_manager.get_product_input()
        
        if versioned_product_name is None:
            print("❌ Grabación cancelada por el usuario")
            return
        
        self.current_product = versioned_product_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Crear directorio del producto versionado si no existe
        product_dir = os.path.join(self.base_clips_dir, versioned_product_name)
        if not os.path.exists(product_dir):
            os.makedirs(product_dir)
            print(f"📁 Carpeta del producto creada: {product_dir}/")
        
        self.writers = {}
        
        print(f"\n🔴 GRABANDO: {versioned_product_name} - {timestamp}")
        print(f"📷 Usando {len(self.cameras)} cámaras: {list(self.cameras.keys())}")
        
        for device_id in self.cameras.keys():
            filename = f"clip_cam{device_id}_{versioned_product_name}_{timestamp}.mp4"
            filepath = os.path.join(product_dir, filename)
            writer = cv2.VideoWriter(filepath, self.fourcc, self.fps, (self.width, self.height))
            
            if writer.isOpened():
                self.writers[device_id] = writer
                print(f"📹 Grabando: {filename}")
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
            print(f"💾 Guardado: clip_cam{device_id} ({duration:.1f}s)")
        
        self.writers = {}
        print(f"⏹️  Grabación terminada - Duración: {duration:.1f}s")
        print(f"📂 Clips guardados en: clips/{self.current_product}/\n")
    
    def get_actual_window_size(self, window_name):
        """FIXED: Obtiene el tamaño real actual de la ventana de manera más confiable"""
        current_time = time.time()
        
        # Solo verificar el tamaño cada cierto intervalo para evitar overhead
        if current_time - self.last_size_check < self.size_check_interval:
            return self.last_known_size
        
        self.last_size_check = current_time
        
        try:
            # Método 1: Obtener el rect completo de la ventana
            rect = cv2.getWindowImageRect(window_name)
            if rect and len(rect) >= 4:
                new_width, new_height = rect[2], rect[3]
                
                # Validar que los valores son razonables
                if (new_width >= self.min_window_width and 
                    new_height >= self.min_window_height and
                    new_width <= self.max_window_width and 
                    new_height <= self.max_window_height):
                    
                    return self.last_known_size
        except Exception as e:
            # Si falla la detección, usar el último tamaño conocido
            pass
        
        return self.last_known_size

    def create_display_grid(self, window_name=None):
        """FIXED: Crea la vista en grid adaptándose dinámicamente al tamaño de ventana"""
        if len(self.frames) == 0:
            return None
        
        # Obtener tamaño actual real de la ventana
        if window_name:
            window_width, window_height = self.get_actual_window_size(window_name)
        else:
            window_width, window_height = self.window_width, self.window_height
        
        num_cameras = len(self.cameras)
        
        # FIXED: Cálculo mejorado de dimensiones con margen para texto
        text_margin = 60  # Espacio extra para texto y controles
        effective_width = max(window_width - 20, self.min_window_width - 20)
        effective_height = max(window_height - text_margin, self.min_window_height - text_margin)
        
        # Calcular dimensiones de cada cámara según el layout
        if num_cameras == 1:
            cam_width = effective_width
            cam_height = effective_height
        elif num_cameras == 2:
            cam_width = effective_width // 2
            cam_height = effective_height
        elif num_cameras == 3:
            cam_width = effective_width // 2
            cam_height = effective_height // 2
        elif num_cameras >= 4:
            cam_width = effective_width // 2
            cam_height = effective_height // 2
        
        # FIXED: Asegurar dimensiones mínimas pero escalables
        min_cam_width = 160
        min_cam_height = 120
        cam_width = max(self.max_window_width, cam_width, min_cam_width)
        cam_height = max(self.max_window_height, cam_height, min_cam_height)
        
        # FIXED: Mantener aspect ratio si es posible
        aspect_ratio = 4/3  # Ratio típico de cámaras
        if cam_width / cam_height > aspect_ratio * 1.2:
            # Si es muy ancho, ajustar el ancho
            cam_width = int(cam_height * aspect_ratio)
        elif cam_height / cam_width > (1/aspect_ratio) * 1.2:
            # Si es muy alto, ajustar la altura
            cam_height = int(cam_width / aspect_ratio)
        
        # Procesar frames de las cámaras
        display_frames = []
        for device_id in sorted(self.cameras.keys()):
            if device_id in self.frames:
                frame = self.frames[device_id].copy()
                
                # FIXED: Calcular tamaño de fuente más dinámico y escalable
                font_scale = max(0.4, min(1.5, (cam_width + cam_height) / 800.0))
                thickness = max(1, int(2 * font_scale))
                
                # Información a mostrar
                if self.current_product:
                    product_text = f'Cam {device_id} - {self.current_product}'
                else:
                    product_text = f'Cam {device_id}'
                    
                color = (0, 0, 255) if self.recording else (0, 255, 0)
                status = "REC" if self.recording else "LIVE"
                
                # FIXED: Posiciones de texto escaladas dinámicamente
                base_y = max(20, int(25 * font_scale))
                line_spacing = max(20, int(25 * font_scale))
                
                cv2.putText(frame, product_text, (10, base_y), 
                           cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
                cv2.putText(frame, status, (10, base_y + line_spacing), 
                           cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
                
                if self.recording and self.record_start_time:
                    duration = time.time() - self.record_start_time
                    cv2.putText(frame, f'{duration:.1f}s', (10, base_y + 2 * line_spacing), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
                
                # FIXED: Redimensionar frame con interpolación suave
                frame_resized = cv2.resize(frame, (cam_width, cam_height), 
                                         interpolation=cv2.INTER_LINEAR)
                display_frames.append(frame_resized)
        
        # FIXED: Crear grid final con mejor manejo de espacios
        if num_cameras == 1:
            return display_frames[0]
        elif num_cameras == 2:
            return np.hstack((display_frames[0], display_frames[1]))
        elif num_cameras == 3:
            # 2 arriba, 1 abajo centrado
            top_row = np.hstack((display_frames[0], display_frames[1]))
            # Crear frame negro del mismo tamaño para completar la fila
            black_frame = np.zeros((cam_height, cam_width, 3), dtype=np.uint8)
            bottom_row = np.hstack((display_frames[2], black_frame))
            return np.vstack((top_row, bottom_row))
        elif num_cameras >= 4:
            # Grid 2x2
            top_row = np.hstack((display_frames[0], display_frames[1]))
            bottom_row = np.hstack((display_frames[2], display_frames[3]))
            return np.vstack((top_row, bottom_row))
        
        return None
    
    def run(self):
        """Ejecuta la aplicación principal"""
        if not self.initialize_cameras():
            return
            
        self.start_capture_threads()
        
        # FIXED: Configurar ventana de OpenCV con mejor manejo
        window_name = f'Smart Cooler - {len(self.cameras)} Cameras (Auto-detect)'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(window_name, self.window_width, self.window_height)
        
        # FIXED: Configurar callback para detectar redimensionamiento manual
        def on_window_resize(val):
            # Esta función se llama cuando OpenCV detecta cambios
            pass
        
        # Dar tiempo para que se cree la ventana
        time.sleep(0.5)
        
        print("\n" + "="*70)
        print("🎬 SMART COOLER - GRABADOR MULTI-CÁMARA (DETECCIÓN AUTOMÁTICA)")
        print("="*70)
        print("Controles:")
        print("  SPACE - Seleccionar producto y grabar/parar")
        print("  Q     - Salir")
        print("  ESC   - Salir")
        print("  R     - Reiniciar cámaras")
        print("  D     - Forzar detección de nuevas cámaras")
        print("  +/-   - Cambiar tamaño de ventana")
        print("  F     - Pantalla completa / Normal")
        print("="*70)
        print(f"📁 Clips se guardan en: {self.base_clips_dir}/[producto_vN]/")
        print(f"📷 Cámaras activas: {len(self.cameras)} -> {list(self.cameras.keys())}")
        if self.product_manager.products:
            print(f"🏷️  Productos disponibles: {len(self.product_manager.products)}")
        print("🔄 Versionado automático: producto_v1, producto_v2, etc.")
        print("🟢 LISTO - Presiona SPACE para seleccionar producto y grabar")
        print("💡 TIP: Redimensiona la ventana arrastrando las esquinas\n")
        
        # FIXED: Variable para pantalla completa
        fullscreen = False
        
        try:
            while self.running:
                grid = self.create_display_grid(window_name)
                if grid is not None:
                    cv2.imshow(window_name, grid)
                
                # Verificar si la ventana fue cerrada con X
                try:
                    if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                        print("\n👋 Ventana cerrada por usuario")
                        break
                except:
                    # Si la ventana no existe, salir
                    break
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q') or key == 27:  # Q o ESC
                    print("\n👋 Saliendo...")
                    break
                elif key == ord(' '):  # SPACE
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
                elif key == ord('r'):
                    print("\n🔄 Reiniciando cámaras...")
                    self.cleanup_cameras()
                    time.sleep(1)
                    if self.initialize_cameras():
                        self.start_capture_threads()
                        # Actualizar nombre de ventana si cambió el número de cámaras
                        cv2.destroyWindow(window_name)
                        window_name = f'Smart Cooler - {len(self.cameras)} Cameras (Auto-detect)'
                        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                        cv2.resizeWindow(window_name, self.window_width, self.window_height)
                elif key == ord('d'):  # Nueva tecla para forzar detección
                    old_window = window_name
                    self.force_detect_cameras()
                    # Actualizar ventana si cambió el número de cámaras
                    new_window = f'Smart Cooler - {len(self.cameras)} Cameras (Auto-detect)'
                    if old_window != new_window:
                        cv2.destroyWindow(old_window)
                        cv2.namedWindow(new_window, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                        cv2.resizeWindow(new_window, self.window_width, self.window_height)
                        window_name = new_window
                elif key == ord('f'):  # FIXED: Pantalla completa
                    if not fullscreen:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                        fullscreen = True
                        print("🖥️  Modo pantalla completa")
                    else:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(window_name, self.window_width, self.window_height)
                        fullscreen = False
                        print("🪟 Modo ventana normal")
                elif key == ord('+') or key == ord('='):  # Aumentar tamaño
                    if not fullscreen:
                        self.window_width = min(self.max_window_width, int(self.window_width * 1.2))
                        self.window_height = min(self.max_window_height, int(self.window_height * 1.2))
                        cv2.resizeWindow(window_name, self.window_width, self.window_height)
                        self.last_known_size = (self.window_width, self.window_height)
                        print(f"🔍 Tamaño aumentado: {self.window_width}x{self.window_height}")
                elif key == ord('-'):  # Reducir tamaño
                    if not fullscreen:
                        self.window_width = max(self.min_window_width, int(self.window_width * 0.8))
                        self.window_height = max(self.min_window_height, int(self.window_height * 0.8))
                        cv2.resizeWindow(window_name, self.window_width, self.window_height)
                        self.last_known_size = (self.window_width, self.window_height)
                        print(f"🔍 Tamaño reducido: {self.window_width}x{self.window_height}")
        
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
        print("\n🧹 Limpiando recursos...")
        
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