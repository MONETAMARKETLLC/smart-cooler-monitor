# app.py
import cv2
from flask import Flask, Response, render_template, jsonify
import threading
import time
import atexit
import logging
import psutil
import os
import subprocess
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('camera_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Variables globales
cameras = {}
camera_locks = {}
camera_stats = {}
debug_info = {
    'startup_time': datetime.now(),
    'frame_counts': {},
    'error_counts': {},
    'last_frame_times': {},
    'connection_attempts': {}
}

def check_system_devices():
    """Verificar dispositivos de video disponibles en el sistema"""
    logger.info("=== VERIFICANDO DISPOSITIVOS DEL SISTEMA ===")
    
    video_devices = []
    
    # Verificar dispositivos /dev/video*
    for i in range(10):
        device_path = f"/dev/video{i}"
        if os.path.exists(device_path):
            video_devices.append(i)
            logger.info(f"✓ Encontrado dispositivo: {device_path}")
    
    # Intentar usar v4l2-ctl para más información
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            logger.info("=== DISPOSITIVOS V4L2 ===")
            for line in result.stdout.split('\n'):
                if line.strip():
                    logger.info(f"V4L2: {line.strip()}")
        else:
            logger.warning("v4l2-ctl no devolvió información")
    except FileNotFoundError:
        logger.warning("v4l2-ctl no está disponible")
    except subprocess.TimeoutExpired:
        logger.warning("v4l2-ctl timeout")
    except Exception as e:
        logger.error(f"Error ejecutando v4l2-ctl: {e}")
    
    # Verificar permisos de dispositivos
    for device_num in video_devices:
        device_path = f"/dev/video{device_num}"
        try:
            stats = os.stat(device_path)
            perms = oct(stats.st_mode)[-3:]
            logger.info(f"Dispositivo {device_path} - Permisos: {perms}")
        except Exception as e:
            logger.error(f"Error verificando permisos de {device_path}: {e}")
    
    return video_devices

def detect_available_cameras():
    """Detectar cámaras disponibles con múltiples backends y configuraciones"""
    logger.info("=== DETECTANDO CÁMARAS CON MÚLTIPLES BACKENDS ===")
    
    system_devices = check_system_devices()
    available_cameras = []
    
    # Probar solo dispositivos pares (0, 2, 4, 6) que suelen ser las cámaras principales
    # Los impares (1, 3, 5, 7) suelen ser dispositivos de metadatos
    test_indices = [0, 2, 4, 6]
    
    backends_to_try = [
        cv2.CAP_ANY,     # Backend automático
        cv2.CAP_V4L2,    # V4L2 (Linux)
        cv2.CAP_GSTREAMER # GStreamer como alternativa
    ]
    
    for i in test_indices:
        if i not in system_devices:
            continue
            
        logger.info(f"Probando cámara {i} con diferentes backends...")
        
        for backend_idx, backend in enumerate(backends_to_try):
            backend_name = ["AUTO", "V4L2", "GSTREAMER"][backend_idx]
            
            try:
                logger.debug(f"  Backend {backend_name} para cámara {i}...")
                
                cap = cv2.VideoCapture(i, backend)
                
                if cap.isOpened():
                    # Configurar propiedades antes de leer
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 10)  # FPS muy bajo
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # Configurar formato específico para evitar timeouts
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
                    
                    # Múltiples intentos de lectura con timeout
                    success = False
                    for attempt in range(2):  # Solo 2 intentos para ser más rápido
                        logger.debug(f"    Intento {attempt+1} de lectura...")
                        
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            logger.info(f"✅ Cámara {i} con {backend_name}: {frame.shape}")
                            available_cameras.append(i)
                            success = True
                            break
                        else:
                            time.sleep(0.1)  # Pausa muy corta
                    
                    cap.release()
                    
                    if success:
                        break  # Si funciona con este backend, no probar otros
                else:
                    logger.debug(f"    {backend_name}: No se puede abrir")
                    
            except Exception as e:
                logger.debug(f"    {backend_name}: Error - {e}")
                continue
        
        time.sleep(0.1)  # Pausa breve entre cámaras
    
    logger.info(f"Cámaras funcionales detectadas: {available_cameras}")
    return available_cameras
def log_system_info():
    """Registra información del sistema al inicio"""
    logger.info("=== INFORMACIÓN DEL SISTEMA ===")
    logger.info(f"OS: {os.name}")
    logger.info(f"CPU: {psutil.cpu_percent()}%")
    logger.info(f"Memoria: {psutil.virtual_memory().percent}%")
    logger.info(f"OpenCV Version: {cv2.__version__}")
    
    # Información adicional para Docker
    if os.path.exists('/.dockerenv'):
        logger.info(" Ejecutándose en contenedor Docker")
    
    # Verificar si estamos en un contenedor privilegiado
    try:
        with open('/proc/1/status', 'r') as f:
            for line in f:
                if 'CapEff' in line:
                    logger.info(f"Capacidades efectivas: {line.strip()}")
                    break
    except:
        pass

def initialize_cameras():
    """Inicializar cámaras con configuración optimizada para Docker"""
    global cameras, camera_locks, camera_stats, debug_info
    
    logger.info("=== INICIALIZANDO CÁMARAS ===")
    
    # Detectar cámaras disponibles dinámicamente
    available_camera_indices = detect_available_cameras()
    
    if not available_camera_indices:
        logger.error("❌ No se detectaron cámaras disponibles")
        return
    
    for i in available_camera_indices:
        debug_info['connection_attempts'][i] = 0
        debug_info['frame_counts'][i] = 0
        debug_info['error_counts'][i] = 0
        debug_info['last_frame_times'][i] = None
        
        try:
            debug_info['connection_attempts'][i] += 1
            logger.info(f"Inicializando cámara {i} con configuración optimizada...")
            
            # Probar diferentes backends hasta encontrar uno que funcione
            cap = None
            backends = [cv2.CAP_ANY, cv2.CAP_V4L2, cv2.CAP_GSTREAMER]
            
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(i, backend)
                    if cap.isOpened():
                        # Configuración optimizada para Docker
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)   # Resolución más baja
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)  # Para mejor performance
                        cap.set(cv2.CAP_PROP_FPS, 5)             # FPS muy bajo
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)      # Buffer mínimo
                        
                        # Usar formato YUYV que es más compatible
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
                        
                        # Test de lectura
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None and test_frame.size > 0:
                            logger.info(f"✅ Cámara {i} configurada con backend exitoso")
                            break
                        else:
                            cap.release()
                            cap = None
                except:
                    if cap:
                        cap.release()
                    cap = None
                    continue
            
            if cap and cap.isOpened():
                # Verificar configuración aplicada
                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                fps = cap.get(cv2.CAP_PROP_FPS)
                
                logger.info(f"Cámara {i} final: {width}x{height} @ {fps}fps")
                
                # Test final
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    cameras[i] = cap
                    camera_locks[i] = threading.Lock()
                    
                    camera_stats[i] = {
                        'width': width,
                        'height': height,
                        'fps': fps,
                        'connected_at': datetime.now(),
                        'total_frames': 0,
                        'failed_reads': 0,
                        'last_successful_read': datetime.now()
                    }
                    
                    logger.info(f"✅ Cámara {i} lista para streaming")
                else:
                    logger.error(f"❌ Cámara {i}: Test final falló")
                    cap.release()
            else:
                logger.error(f"❌ No se pudo configurar cámara {i}")
                
        except Exception as e:
            logger.error(f"❌ Error inicializando cámara {i}: {str(e)}", exc_info=True)
            debug_info['error_counts'][i] += 1

def cleanup_cameras():
    """Función para limpiar recursos al cerrar con logging"""
    global cameras
    logger.info("=== CERRANDO CÁMARAS ===")
    
    for cam_id, camera in cameras.items():
        try:
            logger.debug(f"Liberando cámara {cam_id}")
            camera.release()
            logger.info(f"✅ Cámara {cam_id} liberada")
        except Exception as e:
            logger.error(f"❌ Error liberando cámara {cam_id}: {e}")
    
    cv2.destroyAllWindows()
    
    # Log estadísticas finales
    logger.info("=== ESTADÍSTICAS FINALES ===")
    for cam_id in camera_stats:
        stats = camera_stats[cam_id]
        logger.info(f"Cámara {cam_id}: {stats['total_frames']} frames, {stats['failed_reads']} errores")
    
    logger.info("Sistema cerrado correctamente")

atexit.register(cleanup_cameras)

def generate_frames(camera_id):
    """Genera frames para streaming con manejo robusto para Docker"""
    if camera_id not in cameras:
        logger.warning(f"Intento de streaming de cámara {camera_id} no disponible")
        return
    
    camera = cameras[camera_id]
    lock = camera_locks[camera_id]
    stats = camera_stats[camera_id]
    
    logger.info(f"Iniciando streaming para cámara {camera_id}")
    
    frame_count = 0
    last_log_time = time.time()
    consecutive_failures = 0
    max_consecutive_failures = 20  # Límite más alto para Docker
    
    while True:
        try:
            start_time = time.time()
            
            with lock:
                success, frame = camera.read()
            
            read_time = time.time() - start_time
            
            if not success or frame is None or frame.size == 0:
                consecutive_failures += 1
                stats['failed_reads'] += 1
                debug_info['error_counts'][camera_id] += 1
                
                if consecutive_failures <= 5 or consecutive_failures % 10 == 0:
                    logger.debug(f"Cámara {camera_id} - Error de lectura #{consecutive_failures}")
                
                # Si hay demasiados errores consecutivos, intentar reinicializar
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"Cámara {camera_id} - Demasiados errores, intentando reinicializar...")
                    try:
                        camera.release()
                        time.sleep(1)
                        new_cap = cv2.VideoCapture(camera_id, cv2.CAP_V4L2)
                        new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        new_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        
                        if new_cap.isOpened():
                            cameras[camera_id] = new_cap
                            camera = new_cap
                            consecutive_failures = 0
                            logger.info(f"Cámara {camera_id} reinicializada exitosamente")
                        else:
                            logger.error(f"No se pudo reinicializar cámara {camera_id}")
                            break
                    except Exception as e:
                        logger.error(f"Error reinicializando cámara {camera_id}: {e}")
                        break
                
                time.sleep(0.1)
                continue
            
            # Frame exitoso
            consecutive_failures = 0
            stats['failed_reads'] = 0
            stats['total_frames'] += 1
            stats['last_successful_read'] = datetime.now()
            frame_count += 1
            
            debug_info['frame_counts'][camera_id] += 1
            debug_info['last_frame_times'][camera_id] = datetime.now()
            
            # === Aquí es donde después podrás aplicar YOLO ===
            # processing_start = time.time()
            # with lock:
            #     results = model(frame)
            #     frame = results[0].plot()
            # processing_time = time.time() - processing_start
            
            # Codificar frame con calidad optimizada para Docker
            encode_start = time.time()
            ret, buffer = cv2.imencode('.jpg', frame, [
                cv2.IMWRITE_JPEG_QUALITY, 70,  # Calidad más baja para mejor performance
                cv2.IMWRITE_JPEG_OPTIMIZE, 1
            ])
            encode_time = time.time() - encode_start
            
            if not ret:
                logger.warning(f"Cámara {camera_id} - Error codificando frame")
                continue
            
            frame_bytes = buffer.tobytes()
            
            # Log estadísticas cada 30 segundos
            current_time = time.time()
            if current_time - last_log_time > 30:
                fps = frame_count / (current_time - last_log_time)
                logger.debug(f"Cámara {camera_id} - FPS: {fps:.1f}, Read: {read_time*1000:.1f}ms, Encode: {encode_time*1000:.1f}ms")
                frame_count = 0
                last_log_time = current_time
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"Error en generate_frames para cámara {camera_id}: {str(e)}", exc_info=True)
            debug_info['error_counts'][camera_id] += 1
            
            if consecutive_failures >= max_consecutive_failures:
                logger.error(f"Demasiados errores en streaming de cámara {camera_id}, cerrando...")
                break
                
            time.sleep(0.1)
            continue

# Mantener todas las rutas originales
@app.route('/')
def index():
    """Página principal con cámaras disponibles"""
    available_cameras = list(cameras.keys())
    logger.info(f"Página principal cargada - Cámaras disponibles: {available_cameras}")
    return render_template('index.html', cameras=available_cameras)

@app.route('/camera/<int:cam_id>')
def video_feed(cam_id):
    """Endpoint para streaming de video"""
    logger.debug(f"Solicitud de streaming para cámara {cam_id}")
    
    if cam_id in cameras:
        return Response(generate_frames(cam_id),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        logger.warning(f"Solicitud de cámara {cam_id} no disponible")
        return f"Cámara {cam_id} no encontrada o no disponible", 404

@app.route('/status')
def camera_status():
    """Endpoint para verificar estado detallado de cámaras"""
    logger.debug("Solicitud de estado de cámaras")
    
    status = {}
    for cam_id in cameras.keys():
        if cam_id in cameras:
            try:
                with camera_locks[cam_id]:
                    ret, _ = cameras[cam_id].read()
                
                stats = camera_stats.get(cam_id, {})
                status[cam_id] = {
                    "status": "Activa" if ret else "Error de lectura",
                    "total_frames": stats.get('total_frames', 0),
                    "failed_reads": stats.get('failed_reads', 0),
                    "last_read": str(stats.get('last_successful_read', 'N/A')),
                    "resolution": f"{stats.get('width', 'N/A')}x{stats.get('height', 'N/A')}",
                    "connected_since": str(stats.get('connected_at', 'N/A'))
                }
            except Exception as e:
                logger.error(f"Error verificando cámara {cam_id}: {e}")
                status[cam_id] = {
                    "status": "Error",
                    "error": str(e)
                }
    
    return jsonify(status)

@app.route('/debug')
def debug_page():
    """Página completa de debugging"""
    logger.debug("Solicitud de página de debug")
    
    system_info = {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "startup_time": str(debug_info['startup_time']),
        "opencv_version": cv2.__version__,
        "is_docker": os.path.exists('/.dockerenv')
    }
    
    return jsonify({
        "system": system_info,
        "cameras": {k: {**v, 'connected_at': str(v['connected_at']), 'last_successful_read': str(v['last_successful_read'])} 
                   for k, v in camera_stats.items()},
        "debug_counters": {**debug_info, 'startup_time': str(debug_info['startup_time'])},
        "available_cameras": list(cameras.keys())
    })

@app.route('/logs')
def get_logs():
    """Endpoint para obtener logs recientes"""
    try:
        with open('camera_debug.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_logs = lines[-100:] if len(lines) > 100 else lines
        return jsonify({"logs": recent_logs})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    print(" Iniciando sistema con debugging completo...")
    
    # Log información del sistema
    log_system_info()
    
    # Inicializar cámaras
    initialize_cameras()
    
    if not cameras:
        logger.critical("❌ ¡ADVERTENCIA! No se encontraron cámaras disponibles.")
        logger.info(" Sugerencias para Docker:")
        logger.info("   - Verifica que docker-compose.yml tiene 'privileged: true'")
        logger.info("   - Confirma que devices: /dev/video* están mapeados")
        logger.info("   - Asegúrate de que las cámaras no están siendo usadas por otras apps")
        logger.info("   - En el host, ejecuta: ls -la /dev/video*")
    else:
        logger.info(f"✅ Sistema iniciado con {len(cameras)} cámara(s) disponible(s)")
        logger.info(" Servidor disponible en: http://localhost:5000")
        logger.info(" Debug info en: http://localhost:5000/debug")
        logger.info(" Logs en: http://localhost:5000/logs")
    
    try:
        # Para producción en Docker, sin debug mode
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("⏹️  Deteniendo servidor...")
    except Exception as e:
        logger.critical(f" Error crítico: {e}", exc_info=True)
    finally:
        cleanup_cameras()