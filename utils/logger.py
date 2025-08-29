import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime
import sys

class LoggerSetup:
    """Configuración centralizada y mejorada de logging para la aplicación"""
    
    def __init__(self, 
                 app_name: str = "smart_cooler",
                 log_dir: str = "logs",
                 console_level: int = logging.INFO,
                 file_level: int = logging.DEBUG,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5):
        
        self.app_name = app_name
        self.log_dir = Path(log_dir)
        self.console_level = console_level
        self.file_level = file_level
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # Crear directorio de logs si no existe
        self.log_dir.mkdir(exist_ok=True)
        
        self.setup_logging()
    
    def setup_logging(self):
        """Configura el sistema de logging con múltiples handlers y formatters"""
        
        # Obtener el logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)  # Nivel más bajo para capturar todo
        
        # Limpiar handlers existentes para evitar duplicados
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 1. Handler para archivo con rotación
        file_handler = self._create_file_handler()
        root_logger.addHandler(file_handler)
        
        # 2. Handler para consola
        console_handler = self._create_console_handler()
        root_logger.addHandler(console_handler)
        
        # 3. Handler para errores críticos (archivo separado)
        error_handler = self._create_error_handler()
        root_logger.addHandler(error_handler)
        
        # Log inicial del sistema
        logger = logging.getLogger(__name__)
        logger.info("=" * 60)
        logger.info("Logging system initialized for %s", self.app_name)
        logger.info("Log directory: %s", self.log_dir.absolute())
        logger.info("Console level: %s, File level: %s", 
                   logging.getLevelName(self.console_level),
                   logging.getLevelName(self.file_level))
        logger.info("=" * 60)
    
    def _create_file_handler(self):
        """Crea handler para archivo principal con rotación"""
        log_file = self.log_dir / f"{self.app_name}.log"
        
        # RotatingFileHandler para manejar el tamaño de archivos
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        
        handler.setLevel(self.file_level)
        
        # Formatter detallado para archivos
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)-20s:%(lineno)-4d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        return handler
    
    def _create_console_handler(self):
        """Crea handler para consola con formato simplificado"""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(self.console_level)
        
        # Formatter simplificado para consola con colores si está disponible
        if self._supports_color():
            formatter = ColoredFormatter(
                '%(asctime)s | %(levelname_colored)s | %(name_short)s | %(message)s',
                datefmt='%H:%M:%S'
            )
        else:
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%H:%M:%S'
            )
        
        handler.setFormatter(formatter)
        return handler
    
    def _create_error_handler(self):
        """Crea handler específico para errores y warnings"""
        error_log = self.log_dir / f"{self.app_name}_errors.log"
        
        handler = logging.handlers.RotatingFileHandler(
            error_log,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        
        handler.setLevel(logging.WARNING)  # Solo warnings y errores
        
        # Formatter muy detallado para errores
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(pathname)s:%(lineno)d\n'
            'Function: %(funcName)s\n'
            'Message: %(message)s\n'
            '%(dash_separator)s\n',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Añadir separador visual
        original_format = formatter.format
        def format_with_separator(record):
            record.dash_separator = '-' * 80
            return original_format(record)
        formatter.format = format_with_separator
        
        handler.setFormatter(formatter)
        return handler
    
    def _supports_color(self):
        """Detecta si la terminal soporta colores"""
        return (
            hasattr(sys.stdout, 'isatty') and 
            sys.stdout.isatty() and
            os.environ.get('TERM') != 'dumb'
        )
    
    def get_logger(self, name: str = None):
        """Obtiene un logger configurado para un módulo específico"""
        if name is None:
            name = __name__
        return logging.getLogger(name)
    
    def set_module_level(self, module_name: str, level: int):
        """Configura el nivel de logging para un módulo específico"""
        logger = logging.getLogger(module_name)
        logger.setLevel(level)
        logging.getLogger(__name__).info(
            "Set logging level for '%s' to %s", 
            module_name, logging.getLevelName(level)
        )


class ColoredFormatter(logging.Formatter):
    """Formatter que añade colores a los logs en la consola"""
    
    # Códigos de color ANSI
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[1;31m', # Bold Red
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        # Crear versión coloreada del level
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname_colored = (
                f"{self.COLORS[levelname]}{levelname:8s}{self.COLORS['RESET']}"
            )
        else:
            record.levelname_colored = f"{levelname:8s}"
        
        # Crear versión corta del nombre del módulo
        name_parts = record.name.split('.')
        if len(name_parts) > 2:
            record.name_short = f"{name_parts[0]}...{name_parts[-1]}"
        else:
            record.name_short = record.name
        
        return super().format(record)


# Funciones de conveniencia para usar en otros módulos
def setup_logging(app_name: str = "smart_cooler", 
                  console_level: str = "INFO", 
                  file_level: str = "DEBUG",
                  log_dir: str = "logs"):
    """
    Función de conveniencia para configurar logging rápidamente
    
    Args:
        app_name: Nombre de la aplicación
        console_level: Nivel para consola (DEBUG, INFO, WARNING, ERROR)
        file_level: Nivel para archivo (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directorio donde guardar logs
    """
    
    level_mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    console_level_int = level_mapping.get(console_level.upper(), logging.INFO)
    file_level_int = level_mapping.get(file_level.upper(), logging.DEBUG)
    
    return LoggerSetup(
        app_name=app_name,
        log_dir=log_dir,
        console_level=console_level_int,
        file_level=file_level_int
    )


def get_logger(name: str = None):
    """
    Obtiene un logger configurado
    
    Args:
        name: Nombre del logger (usa __name__ del módulo llamador si no se especifica)
    """
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    return logging.getLogger(name)


# Ejemplo de uso y configuraciones predefinidas
class LoggingProfiles:
    """Perfiles predefinidos de configuración de logging"""
    
    @staticmethod
    def development():
        """Configuración para desarrollo - más verbose"""
        return setup_logging(
            console_level="DEBUG",
            file_level="DEBUG"
        )
    
    @staticmethod
    def production():
        """Configuración para producción - menos verbose"""
        return setup_logging(
            console_level="INFO",
            file_level="INFO"
        )
    
    @staticmethod
    def testing():
        """Configuración para testing - mínimo logging"""
        return setup_logging(
            console_level="WARNING",
            file_level="DEBUG"
        )