#!/usr/bin/env python3
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
        """Encuentra grupos de clips con el mismo timestamp"""
        clip_files = glob.glob(os.path.join(self.clips_dir, "clip_cam*.mp4"))
        
        # Extraer timestamps de los nombres de archivo
        timestamp_groups = {}
        
        for clip_path in clip_files:
            filename = os.path.basename(clip_path)
            
            # Buscar patrón: clip_cam{N}_{timestamp}.mp4
            match = re.match(r'clip_cam(\d+)_(\d{8}_\d{6})\.mp4', filename)
            if match:
                cam_id = int(match.group(1))
                timestamp = match.group(2)
                
                if timestamp not in timestamp_groups:
                    timestamp_groups[timestamp] = {}
                
                timestamp_groups[timestamp][cam_id] = clip_path
        
        # Filtrar solo grupos completos (4 cámaras)
        complete_groups = {}
        for timestamp, clips in timestamp_groups.items():
            if len(clips) == 4 and all(cam_id in clips for cam_id in self.camera_devices):
                complete_groups[timestamp] = clips
        
        return complete_groups
    
    def extract_frames_from_group(self, timestamp, clip_paths, fps_extract=5, max_frames=None):
        """Extrae frames sincronizados de un grupo de clips"""
        print(f"\n Procesando grupo: {timestamp}")
        
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
        
        # Crear subdirectorio para este grupo
        group_dir = os.path.join(self.frames_dir, f"group_{timestamp}")
        if not os.path.exists(group_dir):
            os.makedirs(group_dir)
        
        extracted_count = 0
        frame_index = 0
        
        while True:
            # Leer frame de todas las cámaras
            frames = {}
            all_success = True
            
            for cam_id in self.camera_devices:
                # Ir al frame específico
                caps[cam_id].set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ret, frame = caps[cam_id].read()
                
                if not ret:
                    all_success = False
                    break
                
                frames[cam_id] = frame
            
            if not all_success:
                break
            
            # Guardar frames sincronizados
            for cam_id, frame in frames.items():
                filename = f"frame_{extracted_count:04d}_cam{cam_id}.jpg"
                filepath = os.path.join(group_dir, filename)
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
        
        print(f"✅ Extraídos {extracted_count} frames sincronizados en: {group_dir}")
        return True
    
    def extract_all_clips(self, fps_extract=5, max_frames_per_clip=None):
        """Extrae frames de todos los grupos de clips"""
        clip_groups = self.find_clip_groups()
        
        if not clip_groups:
            print("❌ No se encontraron grupos completos de clips (4 cámaras)")
            return
        
        print(f" Encontrados {len(clip_groups)} grupos de clips completos:")
        for timestamp in sorted(clip_groups.keys()):
            print(f"  - {timestamp}")
        
        print(f"\n⚙️  Configuración:")
        print(f"   FPS extracción: {fps_extract}")
        print(f"   Max frames por clip: {max_frames_per_clip or 'Sin límite'}")
        
        successful_extractions = 0
        
        for timestamp in sorted(clip_groups.keys()):
            if self.extract_frames_from_group(
                timestamp, 
                clip_groups[timestamp], 
                fps_extract, 
                max_frames_per_clip
            ):
                successful_extractions += 1
        
        print(f"\n Resumen:")
        print(f"   Grupos procesados: {successful_extractions}/{len(clip_groups)}")
        print(f"   Frames guardados en: {self.frames_dir}/")
    
    def list_available_clips(self):
        """Lista los clips disponibles"""
        clip_groups = self.find_clip_groups()
        
        if not clip_groups:
            print("❌ No se encontraron grupos completos de clips")
            return
        
        print(" Clips disponibles:")
        for timestamp in sorted(clip_groups.keys()):
            print(f"\n {timestamp}:")
            for cam_id in sorted(clip_groups[timestamp].keys()):
                clip_path = clip_groups[timestamp][cam_id]
                # Obtener duración del video
                cap = cv2.VideoCapture(clip_path)
                if cap.isOpened():
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    duration = frame_count / fps if fps > 0 else 0
                    print(f"     Cam {cam_id}: {duration:.1f}s ({frame_count} frames)")
                    cap.release()
                else:
                    print(f"     Cam {cam_id}: Error al leer")

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