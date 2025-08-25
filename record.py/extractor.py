
"""
Smart Cooler - Extractor de Frames Sincronizados
Extrae frames de los clips grabados por las 4 cámaras
"""

import cv2
import os
import glob
import argparse
from datetime import datetime
import re

class FrameExtractor:
    def __init__(self, clips_dir="clips", frames_dir="frames"):
        self.clips_dir = clips_dir
        self.frames_dir = frames_dir
        self.camera_devices = [0, 2, 4, 6]
        
        # Crear directorio de frames si no existe
        if not os.path.exists(self.frames_dir):
            os.makedirs(self.frames_dir)
            print(f" Carpeta creada: {self.frames_dir}/")
    
    def find_clip_groups(self):
        """Encuentra grupos de clips organizados por producto"""
        all_groups = {}
        
        # Buscar en subdirectorios de productos
        for product_dir in os.listdir(self.clips_dir):
            product_path = os.path.join(self.clips_dir, product_dir)
            
            if not os.path.isdir(product_path):
                continue
            
            clip_files = glob.glob(os.path.join(product_path, "clip_cam*.mp4"))
            timestamp_groups = {}
            
            for clip_path in clip_files:
                filename = os.path.basename(clip_path)
                
                # Buscar patrón: clip_cam{N}_{product}_{timestamp}.mp4
                match = re.match(r'clip_cam(\d+)_(.+)_(\d{8}_\d{6})\.mp4', filename)
                if match:
                    cam_id = int(match.group(1))
                    product_name = match.group(2)
                    timestamp = match.group(3)
                    
                    if timestamp not in timestamp_groups:
                        timestamp_groups[timestamp] = {'product': product_name, 'clips': {}}
                    
                    timestamp_groups[timestamp]['clips'][cam_id] = clip_path
            
            # Filtrar solo grupos completos (4 cámaras)
            for timestamp, group_data in timestamp_groups.items():
                clips = group_data['clips']
                if len(clips) == 4 and all(cam_id in clips for cam_id in self.camera_devices):
                    group_key = f"{group_data['product']}_{timestamp}"
                    all_groups[group_key] = {
                        'product': group_data['product'],
                        'timestamp': timestamp,
                        'clips': clips
                    }
        
        return all_groups
    
    def extract_frames_from_group(self, group_key, group_data, fps_extract=5, max_frames=None):
        """Extrae frames sincronizados de un grupo de clips"""
        product = group_data['product']
        timestamp = group_data['timestamp']
        clip_paths = group_data['clips']
        
        print(f"\n Procesando: {product} - {timestamp}")
        
        # Abrir todos los videos
        caps = {}
        frame_counts = {}
        
        for cam_id, clip_path in clip_paths.items():
            cap = cv2.VideoCapture(clip_path)
            if not cap.isOpened():
                print(f"❌ No se pudo abrir: {clip_path}")
                return False
            
            caps[cam_id] = cap
            frame_counts[cam_id] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            print(f" Cam {cam_id}: {frame_counts[cam_id]} frames @ {fps:.1f} FPS")
        
        # Calcular intervalo de extracción
        min_frames = min(frame_counts.values())
        original_fps = caps[self.camera_devices[0]].get(cv2.CAP_PROP_FPS)
        frame_interval = max(1, int(original_fps / fps_extract))
        
        print(f" Extrayendo cada {frame_interval} frames ({fps_extract} FPS efectivo)")
        
        # Crear estructura de directorios: frames/producto/cam{X}/
        product_frames_dir = os.path.join(self.frames_dir, product)
        if not os.path.exists(product_frames_dir):
            os.makedirs(product_frames_dir)
        
        # Crear subdirectorios para cada cámara
        cam_dirs = {}
        for cam_id in self.camera_devices:
            cam_dir = os.path.join(product_frames_dir, f"cam{cam_id}")
            if not os.path.exists(cam_dir):
                os.makedirs(cam_dir)
            cam_dirs[cam_id] = cam_dir
        
        extracted_count = 0
        frame_index = 0
        
        while True:
            # Leer frame de todas las cámaras
            frames = {}
            all_success = True
            
            for cam_id in self.camera_devices:
                if cam_id not in caps:
                    continue
                    
                # Ir al frame específico
                caps[cam_id].set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ret, frame = caps[cam_id].read()
                
                if not ret:
                    all_success = False
                    break
                
                frames[cam_id] = frame
            
            if not all_success:
                break
            
            # Guardar frames en directorios de cámara correspondientes
            for cam_id, frame in frames.items():
                filename = f"{timestamp}_frame_{extracted_count:04d}.jpg"
                filepath = os.path.join(cam_dirs[cam_id], filename)
                cv2.imwrite(filepath, frame)
            
            extracted_count += 1
            frame_index += frame_interval
            
            # Límite de frames si se especifica
            if max_frames and extracted_count >= max_frames:
                break
            
            # Verificar si llegamos al final
            if frame_index >= min_frames:
                break
        
        # Liberar recursos
        for cap in caps.values():
            cap.release()
        
        print(f"✅ Extraídos {extracted_count} frames sincronizados en: {product_frames_dir}")
        return True
    
    def extract_all_clips(self, fps_extract=5, max_frames_per_clip=None):
        """Extrae frames de todos los grupos de clips organizados por producto"""
        clip_groups = self.find_clip_groups()
        
        if not clip_groups:
            print("❌ No se encontraron grupos completos de clips (4 cámaras)")
            print(" Verifica que los clips estén en subdirectorios de productos")
            return
        
        # Organizar por producto
        products = {}
        for group_key, group_data in clip_groups.items():
            product = group_data['product']
            if product not in products:
                products[product] = []
            products[product].append((group_key, group_data))
        
        print(f" Encontrados clips de {len(products)} productos:")
        for product, groups in products.items():
            print(f"   {product}: {len(groups)} clips")
        
        print(f"\n⚙️  Configuración:")
        print(f"   FPS extracción: {fps_extract}")
        print(f"   Max frames por clip: {max_frames_per_clip or 'Sin límite'}")
        
        successful_extractions = 0
        
        for group_key in sorted(clip_groups.keys()):
            group_data = clip_groups[group_key]
            if self.extract_frames_from_group(
                group_key, 
                group_data, 
                fps_extract, 
                max_frames_per_clip
            ):
                successful_extractions += 1
        
        print(f"\n Resumen:")
        print(f"   Grupos procesados: {successful_extractions}/{len(clip_groups)}")
        print(f"   Estructura: {self.frames_dir}/[producto]/cam[X]/")
        
        # Mostrar estructura final
        if os.path.exists(self.frames_dir):
            print(f"\n Estructura creada:")
            for product in os.listdir(self.frames_dir):
                product_path = os.path.join(self.frames_dir, product)
                if os.path.isdir(product_path):
                    cam_dirs = [d for d in os.listdir(product_path) if d.startswith('cam')]
                    print(f"   {product}/ ({len(cam_dirs)} cámaras)")
                    for cam_dir in sorted(cam_dirs):
                        cam_path = os.path.join(product_path, cam_dir)
                        if os.path.isdir(cam_path):
                            frame_count = len([f for f in os.listdir(cam_path) if f.endswith('.jpg')])
                            print(f"     {cam_dir}/: {frame_count} frames")
    
    def list_available_clips(self):
        """Lista los clips disponibles organizados por producto"""
        clip_groups = self.find_clip_groups()
        
        if not clip_groups:
            print("❌ No se encontraron grupos completos de clips")
            return
        
        # Organizar por producto
        products = {}
        for group_key, group_data in clip_groups.items():
            product = group_data['product']
            timestamp = group_data['timestamp']
            if product not in products:
                products[product] = []
            products[product].append((timestamp, group_data))
        
        print(" Clips disponibles por producto:")
        
        for product in sorted(products.keys()):
            clips = products[product]
            print(f"\n {product} ({len(clips)} clips):")
            
            for timestamp, group_data in sorted(clips):
                print(f"   {timestamp}:")
                for cam_id in sorted(group_data['clips'].keys()):
                    clip_path = group_data['clips'][cam_id]
                    # Obtener duración del video
                    cap = cv2.VideoCapture(clip_path)
                    if cap.isOpened():
                        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        duration = frame_count / fps if fps > 0 else 0
                        print(f"       Cam {cam_id}: {duration:.1f}s ({frame_count} frames)")
                        cap.release()
                    else:
                        print(f"       Cam {cam_id}: Error al leer")

def main():
    parser = argparse.ArgumentParser(description="Extractor de frames para Smart Cooler")
    parser.add_argument("--clips-dir", default="clips", help="Directorio de clips (default: clips)")
    parser.add_argument("--frames-dir", default="frames", help="Directorio de frames (default: frames)")
    parser.add_argument("--fps", type=int, default=5, help="FPS para extraer (default: 5)")
    parser.add_argument("--max-frames", type=int, help="Máximo frames por clip")
    parser.add_argument("--list", action="store_true", help="Solo listar clips disponibles")
    
    args = parser.parse_args()
    
    extractor = FrameExtractor(args.clips_dir, args.frames_dir)
    
    if args.list:
        extractor.list_available_clips()
    else:
        extractor.extract_all_clips(args.fps, args.max_frames)

if __name__ == "__main__":
    main()