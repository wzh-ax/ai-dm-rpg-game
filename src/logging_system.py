"""
Logging System - 结构化日志模块

为游戏核心模块提供异步安全的结构化日志：
- 使用 queue.Queue + QueueHandler 实现异步写入
- 每次 new_game 创建新的日志文件
- 日志格式: {timestamp} [{level}] [{module}] {message}
- 支持 @log_call 装饰器简化关键函数日志
"""

import asyncio
import atexit
import functools
import logging
import logging.handlers
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Callable, Optional

# ============================================================================
# 日志格式器
# ============================================================================

class StructuredLogFormatter(logging.Formatter):
    """
    结构化日志格式器
    
    格式: {timestamp} [{level}] [{module}] {message}
    示例: 2026-04-11 21:30:00 [INFO] [game_master] Scene transition: 酒馆 → 森林
    """
    
    def __init__(self):
        super().__init__(
            fmt="%(timestamp)s [%(levellevel)s] [%(modulename)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    def format(self, record: logging.LogRecord) -> str:
        # 添加自定义字段
        record.timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        record.levellevel = record.levelname
        record.modulename = record.module
        return super().format(record)


class GameLogFilter(logging.Filter):
    """
    日志过滤器 - 脱敏敏感信息
    """
    
    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), '[API_KEY]'),
        (re.compile(r'secret["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), '[SECRET]'),
        (re.compile(r'token["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), '[TOKEN]'),
        (re.compile(r'password["\']?\s*[:=]\s*["\']?[^\s"\']+', re.IGNORECASE), '[PASSWORD]'),
        (re.compile(r'[\w\.\-]+@[\w\.\-]+\.\w+'), '[EMAIL]'),  # Email addresses
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg:
            record.msg = self._sanitize(str(record.msg))
        if record.args:
            record.args = tuple(
                self._sanitize(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True
    
    def _sanitize(self, text: str) -> str:
        """脱敏敏感信息"""
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


# ============================================================================
# 异步日志写入器
# ============================================================================

class AsyncFileHandler:
    """
    异步文件写入器 - 使用独立线程处理日志写入
    
    避免多线程写入冲突，使用 queue.Queue 缓冲
    """
    
    def __init__(self, log_file: str, max_queue_size: int = 1000):
        self.log_file = log_file
        self._queue: Queue = Queue(maxsize=max_queue_size)
        self._writer_thread: Optional[threading.Thread] = None
        self._running = False
        self._file_lock = threading.Lock()
        
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    def start(self):
        """启动写入线程"""
        if self._running:
            return
        self._running = True
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        atexit.register(self.stop)
    
    def stop(self):
        """停止写入线程"""
        if not self._running:
            return
        self._running = False
        # 添加哨兵标记
        self._queue.put_nowait(None)
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
    
    def write(self, message: str):
        """添加日志消息到队列"""
        try:
            self._queue.put_nowait(message)
        except Exception:
            # 队列满时丢弃日志（避免阻塞）
            pass
    
    def _writer_loop(self):
        """写入线程主循环"""
        while self._running:
            try:
                message = self._queue.get(timeout=0.1)
                if message is None:
                    break
                self._flush_message(message)
            except Empty:
                continue
            except Exception:
                pass
    
    def _flush_message(self, message: str):
        """将消息写入文件"""
        with self._file_lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(message)
                    f.write("\n")
            except Exception:
                pass


# ============================================================================
# 日志系统主类
# ============================================================================

class GameLogger:
    """
    游戏日志系统主类
    
    使用方式:
        logger = GameLogger()
        logger.init_game_log()  # new_game 时调用
        logger.info("game_master", "Combat started")
        logger.debug("scene_agent", "Generating scene: 酒馆")
    """
    
    _instance: Optional["GameLogger"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._current_log_file: Optional[str] = None
        self._async_handler: Optional[AsyncFileHandler] = None
        self._logger: Optional[logging.Logger] = None
        self._setup_complete = False
    
    def _get_log_dir(self) -> Path:
        """获取日志目录"""
        # 相对于项目根目录
        project_root = Path(__file__).parent.parent
        log_dir = project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def _get_log_file_path(self) -> str:
        """获取本次游戏的日志文件路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(self._get_log_dir() / f"game_{timestamp}.log")
    
    def init_game_log(self) -> str:
        """
        初始化新的游戏日志（new_game 时调用）
        
        Returns:
            日志文件路径
        """
        # 停止旧的写入器
        if self._async_handler:
            self._async_handler.stop()
        
        # 创建新的日志文件
        log_file = self._get_log_file_path()
        self._current_log_file = log_file
        
        # 创建异步写入器
        self._async_handler = AsyncFileHandler(log_file)
        self._async_handler.start()
        
        # 配置 logging
        self._setup_logger()
        self._setup_complete = True
        
        self.info("logging_system", f"=== New game started: {log_file} ===")
        return log_file
    
    def _setup_logger(self):
        """配置 logging 模块"""
        log_file = self._current_log_file
        if not log_file:
            return
        
        # 创建专用的 logger
        self._logger = logging.getLogger(f"game_{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()
        
        # 文件处理器（写入到队列）
        file_handler = _QueueHandler(self._get_log_queue())
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredLogFormatter())
        file_handler.addFilter(GameLogFilter())
        self._logger.addHandler(file_handler)
        
        # 同时输出到 stderr（DEBUG 级别以上）
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(StructuredLogFormatter())
        console_handler.addFilter(GameLogFilter())
        self._logger.addHandler(console_handler)
    
    def _get_log_queue(self) -> Queue:
        """获取日志队列"""
        if self._async_handler:
            return self._async_handler._queue
        return Queue()
    
    def _log(self, level: int, module: str, message: str, *args, **kwargs):
        """内部日志方法"""
        if not self._setup_complete or not self._logger:
            return
        
        # 构建带模块前缀的消息
        full_message = f"[{module}] {message}" if module else message
        self._logger.log(level, full_message, *args, **kwargs)
    
    def debug(self, module: str, message: str, *args, **kwargs):
        """DEBUG 级别日志"""
        self._log(logging.DEBUG, module, message, *args, **kwargs)
    
    def info(self, module: str, message: str, *args, **kwargs):
        """INFO 级别日志"""
        self._log(logging.INFO, module, message, *args, **kwargs)
    
    def warning(self, module: str, message: str, *args, **kwargs):
        """WARNING 级别日志"""
        self._log(logging.WARNING, module, message, *args, **kwargs)
    
    def error(self, module: str, message: str, *args, **kwargs):
        """ERROR 级别日志"""
        self._log(logging.ERROR, module, message, *args, **kwargs)
    
    def exception(self, module: str, message: str, *args, **kwargs):
        """ERROR 级别日志（包含异常堆栈）"""
        self._log(logging.ERROR, module, message, *args, **kwargs)
    
    def get_current_log_file(self) -> Optional[str]:
        """获取当前日志文件路径"""
        return self._current_log_file
    
    def flush(self):
        """刷新日志缓冲区"""
        if self._async_handler:
            # 清空队列中的所有消息
            try:
                while True:
                    self._async_handler._queue.get_nowait()
            except Empty:
                pass


# QueueHandler 实现（标准库中没有，我们自己实现）
class _QueueHandler(logging.Handler):
    """
    队列处理器 - 将日志消息写入队列而非直接写文件
    """
    
    def __init__(self, queue: Queue):
        super().__init__()
        self._queue = queue
    
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._queue.put_nowait(msg)
        except Exception:
            self.handleError(record)


# ============================================================================
# QueueHandler 兼容层（Python 3.7+ 标准库有 QueueHandler，这里提供兼容实现）
# ============================================================================

# 确保我们的 QueueHandler 优先使用
logging.handlers.QueueHandler = _QueueHandler


# ============================================================================
# @log_call 装饰器
# ============================================================================

def log_call(
    level: int = logging.INFO,
    module: Optional[str] = None,
    log_args: bool = False,
    log_result: bool = False,
    sanitize_args: bool = True,
):
    """
    日志装饰器 - 简化关键函数的日志记录
    
    Args:
        level: 日志级别（默认 INFO）
        module: 模块名称（默认从调用栈推断）
        log_args: 是否记录函数参数（默认 False，避免敏感信息泄露）
        log_result: 是否记录返回值（默认 False）
        sanitize_args: 是否对参数进行脱敏处理（默认 True）
    
    Example:
        @log_call(module="combat_system", log_args=True)
        async def start_combat(self, combat_id: str, combatants: list):
            ...
    
        @log_call(level=logging.DEBUG, module="scene_agent")
        async def generate_scene(self, scene_type: str):
            ...
    """
    
    # 敏感参数名
    SENSITIVE_PARAMS = {
        "api_key", "secret", "token", "password", "auth",
        "credential", "private_key", "access_token", "refresh_token",
    }
    
    def decorator(func: Callable) -> Callable:
        _module = module or func.__module__.split(".")[-1]
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 获取 logger
            logger = GameLogger()
            
            # 构建函数签名
            func_name = func.__name__
            sig = f"{_module}.{func_name}"
            
            # 记录函数调用
            if log_args and kwargs:
                safe_kwargs = _sanitize_dict(kwargs) if sanitize_args else kwargs
                logger.log(level, f"[{sig}] called with {safe_kwargs}")
            else:
                logger.log(level, f"[{sig}] called")
            
            # 执行函数
            try:
                result = await func(*args, **kwargs)
                
                if log_result and result is not None:
                    logger.log(level, f"[{sig}] returned: {result}")
                else:
                    logger.log(level, f"[{sig}] completed")
                
                return result
                
            except Exception as e:
                logger.exception(_module, f"[{sig}] raised {type(e).__name__}: {e}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 获取 logger
            logger = GameLogger()
            
            # 构建函数签名
            func_name = func.__name__
            sig = f"{_module}.{func_name}"
            
            # 记录函数调用
            if log_args and kwargs:
                safe_kwargs = _sanitize_dict(kwargs) if sanitize_args else kwargs
                logger.log(level, f"[{sig}] called with {safe_kwargs}")
            else:
                logger.log(level, f"[{sig}] called")
            
            # 执行函数
            try:
                result = func(*args, **kwargs)
                
                if log_result and result is not None:
                    logger.log(level, f"[{sig}] returned: {result}")
                else:
                    logger.log(level, f"[{sig}] completed")
                
                return result
                
            except Exception as e:
                logger.exception(_module, f"[{sig}] raised {type(e).__name__}: {e}")
                raise
        
        # 返回合适的装饰器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def _sanitize_dict(d: dict) -> dict:
    """对字典中的敏感信息进行脱敏"""
    SENSITIVE_KEYS = {
        "api_key", "secret", "token", "password", "auth",
        "credential", "private_key", "access_token", "refresh_token",
    }
    result = dict(d)
    for key in result:
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            result[key] = "[REDACTED]"
    return result


# ============================================================================
# 全局实例和便捷函数
# ============================================================================

_global_logger: Optional[GameLogger] = None


def get_logger() -> GameLogger:
    """获取全局日志系统实例"""
    global _global_logger
    if _global_logger is None:
        _global_logger = GameLogger()
    return _global_logger


def init_game_log() -> str:
    """初始化新的游戏日志（便捷函数）"""
    return get_logger().init_game_log()


def debug(module: str, message: str, *args, **kwargs):
    """DEBUG 级别日志（便捷函数）"""
    get_logger().debug(module, message, *args, **kwargs)


def info(module: str, message: str, *args, **kwargs):
    """INFO 级别日志（便捷函数）"""
    get_logger().info(module, message, *args, **kwargs)


def warning(module: str, message: str, *args, **kwargs):
    """WARNING 级别日志（便捷函数）"""
    get_logger().warning(module, message, *args, **kwargs)


def error(module: str, message: str, *args, **kwargs):
    """ERROR 级别日志（便捷函数）"""
    get_logger().error(module, message, *args, **kwargs)


def exception(module: str, message: str, *args, **kwargs):
    """ERROR 级别日志（包含异常堆栈）（便捷函数）"""
    get_logger().exception(module, message, *args, **kwargs)
