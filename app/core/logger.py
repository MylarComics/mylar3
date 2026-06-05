import logging
import sys
import ctypes
try:
    import resource
except ImportError:
    resource = None
from app.core.config import settings

def setup_logger():
    logger = logging.getLogger("mylar")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)-7s :: %(name)s.%(funcName)s.%(lineno)s : %(message)s', 
            '%d-%b-%Y %H:%M:%S'
        )
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logger()

def log_memory(context_msg="Memory Check"):
    try:
        alloc_mb = 0
        if sys.platform == 'win32':
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_uint),
                            ("PageFaultCount", ctypes.c_uint),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            counters = PROCESS_MEMORY_COUNTERS()
            GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(counters), ctypes.sizeof(counters))
            alloc_mb = counters.WorkingSetSize / (1024 * 1024)
        elif resource:
            alloc_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        
        if alloc_mb > 0:
            logger.info(f"[MEMORY] {context_msg}: process is using ~{alloc_mb:.2f} MB")
    except Exception:
        pass
