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
import json
from datetime import datetime
import numpy as np
from difflib import get_close_matches
import tkinter as tk
from tkinter import messagebox, simpledialog

class ProductManager:
    def __init__(self, products_file="products.json"):
        self.products_file = products_file
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
        if product_name not in self.products:
            self.products.append(product_name)
            self.save_products()
            return True
        return False
    
    def find_similar_products(self, query, max_matches=5):
        """Encuentra productos similares usando fuzzy matching"""
        if not query:
            return []
        
        # Buscar coincidencias exactas primero
        exact_matches = [p for p in self.products if query.lower() in p.lower()]
        
        # Buscar coincidencias aproximadas
        fuzzy_matches = get_close_matches(
            query.lower(), 
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
        """Obtiene el nombre del producto con validación y sugerencias"""
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
            
            # Verificar si el producto ya existe exactamente
            if normalized_name in [p.lower() for p in self.products]:
                root.destroy()
                return normalized_name
            
            # Buscar productos similares
            similar = self.find_similar_products(normalized_name)
            
            if similar:
                # Mostrar sugerencias
                suggestions_text = "\n".join([f"• {p}" for p in similar])
                
                response = messagebox.askyesnocancel(
                    "Productos similares encontrados",
                    f"¿Te refieres a alguno de estos productos?\n\n{suggestions_text}\n\n" +
                    f"SÍ = Mostrar opciones\n" +
                    f"NO = Usar '{normalized_name}' como producto nuevo\n" +
                    f"CANCELAR = Escribir otro nombre"
                )
                
                if response is True:  # Sí - elegir de sugerencias
                    choice = self.choose_from_suggestions(similar, normalized_name)
                    if choice:
                        root.destroy()
                        return choice
                    continue
                    
                elif response is False:  # No - producto nuevo
                    self.add_product(normalized_name)
                    print(f"✅ Producto nuevo añadido: {normalized_name}")
                    root.destroy()
                    return normalized_name
                    
                # None - Cancelar, continúa el loop
                
            else:
                # No hay productos similares, confirmar nuevo producto
                confirm = messagebox.askyesno(
                    "Producto nuevo",
                    f"'{normalized_name}' será un producto nuevo.\n\n¿Continuar?"
                )
                
                if confirm:
                    self.add_product(normalized_name)
                    print(f"✅ Producto nuevo añadido: {normalized_name}")
                    root.destroy()
                    return normalized_name
        
        root.destroy()
        return None
    
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
            tk.Radiobutton(
                frame, 
                text=product, 
                variable=selection_var, 
                value=product,
                font=("Arial", 11)
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
        # Dispositivos de las 4 cámaras
        self.camera_devices = [0, 2, 4, 6]
        self.cameras = {}
        self.writers = {}
        self.frames = {}
        self.recording = False
        self.running = True
        self.record_start_time = None
        self.current_product = None
        
        # Configuración de video
        self.fps = 30
        self.width = 640
        self.height = 480
        self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        # Gestor de productos
        self.product_manager = ProductManager()
        
        # Crear carpeta base para clips si no existe
        self.base_clips_dir = "clips"
        if not os.path.exists(self.base_clips_dir):
            os.makedirs(self.base_clips_dir)
            print(f" Carpeta creada: {self.base_clips_dir}/")
    
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
        """Inicia la grabación después de obtener el nombre del producto"""
        if self.recording:
            return
            
        # Obtener nombre del producto
        print("️  Seleccionando producto...")
        product_name = self.product_manager.get_product_input()
        
        if product_name is None:
            print("❌ Grabación cancelada por el usuario")
            return
        
        self.current_product = product_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Crear directorio del producto si no existe
        product_dir = os.path.join(self.base_clips_dir, product_name)
        if not os.path.exists(product_dir):
            os.makedirs(product_dir)
            print(f" Carpeta del producto creada: {product_dir}/")
        
        self.writers = {}
        
        print(f"\n GRABANDO: {product_name} - {timestamp}")
        
        for device_id in self.cameras.keys():
            filename = f"clip_cam{device_id}_{product_name}_{timestamp}.mp4"
            filepath = os.path.join(product_dir, filename)
            writer = cv2.VideoWriter(filepath, self.fourcc, self.fps, (self.width, self.height))
            
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
                if self.current_product:
                    product_text = f'Cam {device_id} - {self.current_product}'
                else:
                    product_text = f'Cam {device_id}'
                    
                color = (0, 0, 255) if self.recording else (0, 255, 0)
                status = "REC" if self.recording else "LIVE"
                
                cv2.putText(frame, product_text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                cv2.putText(frame, status, (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
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
        print(f" Clips se guardan en: {self.base_clips_dir}/")
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