#!/usr/bin/env python3
"""
Script para verificar cámaras USB en el host antes de ejecutar Docker
Ejecutar este script FUERA del contenedor Docker
"""

import subprocess
import os
import sys

def check_host_cameras():
    """Verificar cámaras en el sistema host"""
    print(" VERIFICANDO CÁMARAS EN EL HOST")
    print("=" * 50)
    
    # 1. Verificar dispositivos /dev/video*
    print("\n1. Dispositivos de video:")
    video_devices = []
    
    for i in range(10):
        device_path = f"/dev/video{i}"
        if os.path.exists(device_path):
            video_devices.append(device_path)
            
            # Obtener permisos
            try:
                stat_info = os.stat(device_path)
                perms = oct(stat_info.st_mode)[-3:]
                print(f"   ✅ {device_path} (permisos: {perms})")
            except Exception as e:
                print(f"   ⚠️  {device_path} (error: {e})")
    
    if not video_devices:
        print("   ❌ No se encontraron dispositivos /dev/video*")
        return False
    
    # 2. Usar lsusb para verificar dispositivos USB
    print("\n2. Dispositivos USB de video:")
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True)
        usb_cameras = []
        for line in result.stdout.split('\n'):
            if any(keyword in line.lower() for keyword in ['camera', 'webcam', 'video']):
                usb_cameras.append(line.strip())
                print(f"   ✅ {line.strip()}")
        
        if not usb_cameras:
            print("   ⚠️  No se detectaron cámaras USB específicas")
    except FileNotFoundError:
        print("   ⚠️  lsusb no está disponible")
    except Exception as e:
        print(f"   ❌ Error ejecutando lsusb: {e}")
    
    # 3. Usar v4l2-ctl si está disponible
    print("\n3. Información V4L2:")
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("   Dispositivos V4L2 encontrados:")
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"   {line}")
        else:
            print(f"   ⚠️  v4l2-ctl retornó código: {result.returncode}")
    except FileNotFoundError:
        print("   ⚠️  v4l2-ctl no está instalado")
        print("    Instala con: sudo apt install v4l-utils")
    except subprocess.TimeoutExpired:
        print("   ❌ v4l2-ctl timeout")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return len(video_devices) > 0

def check_docker_setup():
    """Verificar configuración de Docker"""
    print("\n VERIFICANDO DOCKER")
    print("=" * 50)
    
    # Verificar si Docker está corriendo
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        print(f"✅ Docker: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ Docker no está instalado")
        return False
    
    # Verificar Docker Compose
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, text=True)
        print(f"✅ Docker Compose: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ Docker Compose no está instalado")
        return False
    
    return True

def provide_recommendations():
    """Proporcionar recomendaciones basadas en los hallazgos"""
    print("\n RECOMENDACIONES")
    print("=" * 50)
    
    print("\n1. Para el archivo docker-compose.yml asegúrate de tener:")
    print("   privileged: true")
    print("   devices:")
    for i in range(5):
        print(f"     - /dev/video{i}:/dev/video{i}")
    
    print("\n2. Si hay problemas de permisos, ejecuta:")
    print("   sudo chmod 666 /dev/video*")
    print("   sudo usermod -a -G video $USER")
    
    print("\n3. Para instalar herramientas útiles:")
    print("   sudo apt install v4l-utils")
    
    print("\n4. Para probar cámaras manualmente:")
    print("   v4l2-ctl --list-devices")
    print("   v4l2-ctl -d /dev/video0 --list-formats")
    
    print("\n5. Si las cámaras están siendo usadas por otras apps:")
    print("   sudo lsof /dev/video*")

def main():
    print(" DIAGNÓSTICO DE CÁMARAS USB PARA DOCKER")
    print("=" * 60)
    
    cameras_found = check_host_cameras()
    docker_ok = check_docker_setup()
    
    print("\n RESUMEN")
    print("=" * 50)
    
    if cameras_found:
        print("✅ Se encontraron dispositivos de cámara")
    else:
        print("❌ NO se encontraron dispositivos de cámara")
    
    if docker_ok:
        print("✅ Docker está configurado correctamente")
    else:
        print("❌ Problemas con la configuración de Docker")
    
    if cameras_found and docker_ok:
        print("\n ¡Todo parece estar listo para ejecutar el contenedor!")
        print("   Ejecuta: docker-compose up --build")
    else:
        print("\n⚠️  Hay problemas que deben resolverse antes de continuar")
    
    provide_recommendations()

if __name__ == "__main__":
    if os.name != 'posix':
        print("❌ Este script está diseñado para sistemas Linux/Unix")
        sys.exit(1)
    
    main()