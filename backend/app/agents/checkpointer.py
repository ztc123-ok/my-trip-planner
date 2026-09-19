"""Checkpointer 管理模块，提供状态持久化存储。"""

import os
import sqlite3
from typing import Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from ..config import get_settings

_global_checkpointer: Optional[BaseCheckpointSaver] = None


def create_checkpointer(
    checkpointer_type: Optional[str] = None,
    sqlite_db_path: Optional[str] = None,
) -> BaseCheckpointSaver:
    """创建并初始化 Checkpointer 实例。"""
    settings = get_settings()
    c_type = (checkpointer_type or getattr(settings, "checkpointer_type", "sqlite")).lower()

    if c_type == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            db_path = sqlite_db_path or getattr(settings, "sqlite_db_path", "data/trip_checkpoints.db")
            if not os.path.isabs(db_path) and db_path != ":memory:":
                backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.join(backend_dir, db_path)

            if db_path != ":memory:":
                os.makedirs(os.path.dirname(db_path), exist_ok=True)

            conn = sqlite3.connect(db_path, check_same_thread=False)
            saver = SqliteSaver(conn)
            saver.setup()
            return saver
        except Exception as e:
            print(f"⚠️ SqliteSaver 初始化失败 ({e})，自动回退到 MemorySaver")
            return MemorySaver()
    else:
        return MemorySaver()


def get_checkpointer() -> BaseCheckpointSaver:
    """获取全局 Checkpointer 单例。"""
    global _global_checkpointer
    if _global_checkpointer is None:
        _global_checkpointer = create_checkpointer()
    return _global_checkpointer


def reset_checkpointer():
    """重置全局 Checkpointer（主要用于测试）。"""
    global _global_checkpointer
    if _global_checkpointer is not None and hasattr(_global_checkpointer, "conn"):
        try:
            _global_checkpointer.conn.close()
        except Exception:
            pass
    _global_checkpointer = None
