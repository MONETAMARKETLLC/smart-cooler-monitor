#!/usr/bin/env python3
import cv2
import time

def test_cameras_wsl():
    print("=== PROBANDO CÁMARAS USB EN WSL ===")
    print()
    
    working_cameras = []
    
    # Solo probar dispositivos pares (las cámaras reales)
    camera_indices = [0, 2, 4, 6]
    
    for i in camera_indices:
        print(f"Cámara {i}: ", end="", flush=True)
        
        try:
            # Probar diferentes backends
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
            success = False
            
            for backend in backends:
                cap = cv2.VideoCapture(i, backend)
                
                if cap.isOpened():
                    # Configuración específica para WSL
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)  # Resolución muy baja
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                    cap.set(cv2.CAP_PROP_FPS, 5)  # FPS muy bajo
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # Configurar formato YUYV (más compatible)
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
                    
                    # Esperar más tiempo para inicialización
                    time.sleep(1)
                    
                    # Múltiples intentos de lectura
                    for attempt in range(3):
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            h, w = frame.shape[:2]
                            print(f"✓ FUNCIONA ({w}x{h})")
                            working_cameras.append(i)
                            
                            # Guardar foto
                            cv2.imwrite(f"camera_{i}_test.jpg", frame)
                            success = True
                            break
                        time.sleep(0.5)
                    
                    if success:
                        break
                
                cap.release()
                time.sleep(0.2)
            
            if not success:
                print("✗ Timeout leyendo frames")
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print()
    print("=== RESUMEN ===")
    if working_cameras:
        print(f"Cámaras funcionando: {working_cameras}")
        print("Fotos guardadas:")
        for cam in working_cameras:
            print(f"  camera_{cam}_test.jpg")
    else:
        print("Ninguna cámara pudo leer frames exitosamente")
        print("Esto puede deberse a:")
        print("- Incompatibilidad de drivers en WSL")
        print("- Formato de video no soportado") 
        print("- Necesidad de usar Docker para mejor compatibilidad")
    
    return working_cameras

def test_v4l2_info():
    """Mostrar información detallada de V4L2"""
    print("\n=== INFORMACIÓN V4L2 ===")
    
    import subprocess
    
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("Dispositivos V4L2:")
            print(result.stdout)
        
        # Información específica de cada cámara
        for i in [0, 2, 4, 6]:
            print(f"\nCámara {i} - Formatos soportados:")
            try:
                result = subprocess.run(['v4l2-ctl', '-d', f'/dev/video{i}', '--list-formats'], 
                                      capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    print(result.stdout[:300])  # Primeras líneas
                else:
                    print("  No disponible")
            except:
                print("  Error obteniendo formatos")
                
    except:
        print("v4l2-ctl no disponible")

if __name__ == "__main__":
    test_cameras_wsl()
    test_v4l2_info()
    
    print("\nSi ninguna cámara funciona, prueba:")
    print("1. docker-compose run --rm camera-monitor python test_cameras_console.py")
    print("2. Ejecutar desde Windows PowerShell directamente")