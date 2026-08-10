#!/usr/bin/env python3
"""
雷达系统服务器主入口
重构后的模块化架构
支持静态文件服务和WebSocket连接
"""

import asyncio
import sys
import os
import argparse
import sqlite3

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))
if __name__ == "__main__":
    # HTTP/WebSocket handlers import `main` lazily. When this file is executed as
    # a script, keep those imports bound to this process-owned module instead of
    # creating a second copy of the globals that own gaze/physio services.
    sys.modules.setdefault("main", sys.modules[__name__])

from env_loader import load_server_env
load_server_env()

from runtime_paths import DATA_DIR, RUNTIME_HOME, WEB_DIR, ensure_writable_directories
ensure_writable_directories()

from managers import config_manager, db_manager, info, warning, error
from network import websocket_server
from joystick.joystick_event_handler import JoystickEventHandler
from network.http_server import http_server
from services.ai_accuracy_curve import (
    AccuracyCurveConfigError,
    initialize_curves,
    resolve_curve_seed,
)

_initialized = False
_joystick_handler = None
_external_collectors = None
_gaze_svc = None  # 全局 GazeService 实例，供 main() finally 块清理
_physio_svc = None

# 眼动数据存储目录（相对本文件）
_RADAR_DB_PATH = str(DATA_DIR / "radar_operations.db")
_GAZE_DATA_DIR = str(DATA_DIR / "gaze")
_PHYSIO_DB_PATH = str(DATA_DIR / "physio" / "experiment_data.sqlite3")
_PHYSIO_START_STATUS_TIMEOUT_SEC = float(os.getenv("PHYSIO_START_STATUS_TIMEOUT_SEC", "5"))
_PHYSIO_NO_LIVE_SAMPLE_WARNING = "No live samples in the current vendor CSV session"
_PHYSIO_OPTIONAL_LSL_STREAMS = {"mark"}


def _cleanup_sqlite_wal(db_path):
    if not os.path.exists(db_path):
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        conn.execute("PRAGMA journal_mode=DELETE").fetchall()
    except sqlite3.Error as exc:
        info(f"SQLite WAL cleanup skipped for {db_path}: {exc}", "main")
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass


def _cleanup_known_sqlite_wal_files():
    _cleanup_sqlite_wal(_RADAR_DB_PATH)
    _cleanup_sqlite_wal(os.path.join(_GAZE_DATA_DIR, "gaze_records.db"))
    _cleanup_sqlite_wal(_PHYSIO_DB_PATH)


def _physio_total_live_hz(status_payload):
    collector = (status_payload or {}).get("collector") or {}
    streams = collector.get("streams") or {}
    total = 0
    for stream_status in streams.values():
        try:
            total += int((stream_status or {}).get("hz") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _physio_lsl_missing_live_streams(collector):
    streams = collector.get("streams") or {}
    expected = [name for name in sorted(streams) if name not in _PHYSIO_OPTIONAL_LSL_STREAMS]
    live_streams = set(collector.get("live_streams") or [])
    return [name for name in expected if name not in live_streams]


def _physio_has_required_start_data(status_payload):
    if _physio_total_live_hz(status_payload) <= 0:
        return False

    collector = (status_payload or {}).get("collector") or {}
    if collector.get("source_kind") == "lsl":
        return not _physio_lsl_missing_live_streams(collector)
    return True


def _physio_start_warnings(status_payload):
    collector = (status_payload or {}).get("collector") or {}
    warnings = [
        str(item)
        for item in (collector.get("warnings") or [])
        if item and _PHYSIO_NO_LIVE_SAMPLE_WARNING not in str(item)
    ]

    if collector.get("source_kind") == "lsl":
        missing_streams = _physio_lsl_missing_live_streams(collector)
        missing_text = f"缺少实时数据流: {', '.join(missing_streams)}" if missing_streams else ""

        if _physio_total_live_hz(status_payload) > 0:
            if missing_text:
                warnings.append(missing_text)
            return warnings

        if warnings:
            if missing_text:
                warnings.append(missing_text)
            return warnings
        if collector.get("discovered_streams"):
            warnings.append("LSL stream visible but no live samples")
        else:
            prefix = collector.get("lsl_prefix") or "DYN"
            warnings.append(f"No LSL streams matching prefix {prefix}")
        if missing_text:
            warnings.append(missing_text)
        return warnings

    if _physio_total_live_hz(status_payload) > 0:
        return warnings

    if collector.get("source_session_path"):
        warnings.append("当前手环/指环数据会话没有实时样本，请确认厂商采集软件已连接设备并开始采集")
    elif not warnings:
        vendor_root = collector.get("vendor_root") or "未知数据目录"
        warnings.append(f"未检测到手环/指环厂商数据会话: {vendor_root}")
    return warnings


async def _log_physio_start_status(physio_svc):
    status = {}
    deadline = asyncio.get_running_loop().time() + _PHYSIO_START_STATUS_TIMEOUT_SEC
    while True:
        try:
            status = physio_svc.status_payload()
        except Exception as exc:
            warning(f"⚠️ 手环/指环记录服务已启动，但启动状态检查失败: {exc}", "main")
            return

        if _physio_has_required_start_data(status) or asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.25)

    warnings = _physio_start_warnings(status)
    if warnings:
        warning(f"⚠️ 手环/指环记录服务已启动，但启动状态存在警告: {'; '.join(warnings)}", "main")
        warning("请确认 Eve DynCatch/厂商采集软件已连接手环并开始采集；可打开 /physio/check 查看详情", "main")
    else:
        collector = (status or {}).get("collector") or {}
        live_streams = collector.get("live_streams") or []
        if live_streams:
            info(f"✅ 手环/指环记录服务已启动（LSL 可用 {len(live_streams)} 路: {', '.join(live_streams)}）", "main")
        else:
            info("✅ 手环/指环记录服务已启动（已检测到实时数据）", "main")

async def initialize_system():
    """初始化系统组件（延迟调用，首次客户端连接时触发）"""
    global _initialized, _joystick_handler, _gaze_svc, _physio_svc, _external_collectors
    if _initialized:
        return _joystick_handler
    _initialized = True

    info("=== 雷达系统初始化 ===", "main")
    
    # 1. 初始化数据库
    info("1. 初始化数据库...", "main")
    db_manager.initialize_database()
    info("✅ 数据库初始化完成", "main")
    
    # 2. 初始化操纵杆事件处理器
    info("2. 初始化操纵杆事件处理器...", "main")
    _joystick_handler = JoystickEventHandler()
    
    # 3. 将操纵杆处理器集成到WebSocket服务器和HTTP服务器
    info("3. 集成操纵杆处理器到服务器...", "main")
    websocket_server.set_joystick_handler(_joystick_handler)
    http_server.set_joystick_handler(_joystick_handler)
    
    # 4. 启动操纵杆事件处理器（在异步上下文中启动）
    info("4. 启动操纵杆事件处理器...", "main")
    await asyncio.sleep(0.1)
    _joystick_handler.start()

    # 5. 初始化眼动追踪服务
    info("5. 初始化眼动追踪服务...", "main")
    try:
        from tobii.gaze_service import GazeService
        from core import message_handler as _mh
        _gaze_svc = GazeService(data_dir=_GAZE_DATA_DIR)
        # 注入到消息处理器和 HTTP 服务器（即使没有 Tobii 设备，任务元数据和 DB 仍然可用）
        _mh.set_gaze_service(_gaze_svc)
        http_server.set_gaze_service(_gaze_svc)
        websocket_server.set_gaze_service(_gaze_svc)
        # 尝试连接 Tobii 设备（可选：失败也不影响任务记录功能）
        try:
            _gaze_svc.connect()
            info("✅ 眼动追踪服务已启动（设备已连接）", "main")
        except Exception as e:
            info(f"⚠️ Tobii 设备未连接，眼动追踪仅记录任务元数据: {e}", "main")
    except Exception as e:
        error(f"眼动追踪服务初始化失败（已跳过）: {e}", "main")
        # 清理孤儿实例
        if _gaze_svc is not None:
            try:
                _gaze_svc.shutdown()
            except Exception:
                pass
            _gaze_svc = None

    info("6. 初始化手环/指环生理记录服务...", "main")
    try:
        from physio import create_physio_service_from_env
        from core import message_handler as _mh

        _physio_svc = create_physio_service_from_env()
        if _physio_svc is None:
            info("手环/指环记录服务已通过 PHYSIO_RING_ENABLED 关闭", "main")
        else:
            _physio_svc.start()
            _mh.set_physio_service(_physio_svc)
            http_server.set_physio_service(_physio_svc)
            websocket_server.set_physio_service(_physio_svc)
            await _log_physio_start_status(_physio_svc)
    except Exception as e:
        error(f"手环/指环记录服务初始化失败（已跳过）: {e}", "main", exc_info=True)
        if _physio_svc is not None:
            try:
                _physio_svc.stop()
            except Exception:
                pass
            _physio_svc = None

    info("7. 初始化外部生理采集服务调用...", "main")
    try:
        from collectors import create_external_collector_manager_from_env
        from core import message_handler as _mh

        _external_collectors = create_external_collector_manager_from_env(logger=getattr(http_server, "logger", None))
        if _external_collectors is None:
            info("外部采集服务调用未启用", "main")
        else:
            _external_collectors.start()
            _mh.set_external_collector_manager(_external_collectors)
            http_server.set_external_collector_manager(_external_collectors)
            websocket_server.set_external_collector_manager(_external_collectors)
            provider_names = ", ".join(adapter.name for adapter in _external_collectors.adapters)
            info(f"外部采集服务调用已启用: {provider_names}", "main")
    except Exception as e:
        error(f"外部采集服务调用初始化失败（已跳过）: {e}", "main", exc_info=True)
        _external_collectors = None

    info("=== 系统初始化完成 ===", "main")
    
    return _joystick_handler

def setup_static_directory(static_dir=None):
    """设置静态文件目录"""
    if static_dir:
        if not os.path.isabs(static_dir):
            static_dir = os.path.abspath(os.path.join(str(RUNTIME_HOME), static_dir))
    else:
        static_dir = str(WEB_DIR)
    
    info(f"静态文件目录设置为: {static_dir}", "main")
    
    if os.path.exists(static_dir):
        info("静态文件目录存在，可以提供前端文件服务", "main")
    else:
        info("静态文件目录不存在，请确保已将前端文件打包到该目录", "main")
        info("提示: 使用 'npm run build' 或 'pnpm build' 构建前端项目", "main")
    
    return static_dir

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='雷达系统服务器')
    parser.add_argument('--static-dir', type=str, help='静态文件目录路径 (默认: ../dist)')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP服务器端口 (默认: 8080)')
    parser.add_argument('--ws-only', action='store_true', help='仅启动WebSocket服务器（不提供静态文件服务）')
    parser.add_argument(
        '--ai-accuracy-curve-seed',
        type=int,
        help='AI准确率统计曲线随机种子（优先于 AI_ACCURACY_CURVE_SEED）',
    )
    args = parser.parse_args()
    
    try:
        curve_seed = resolve_curve_seed(
            args.ai_accuracy_curve_seed,
            os.getenv("AI_ACCURACY_CURVE_SEED"),
        )
        current_config = config_manager.get_config()
        curves = initialize_curves(current_config.get("levels", []), curve_seed)
        info(f"AI accuracy curve seed: {curve_seed}", "main")
        for ai_level in ("L1", "L2", "L3"):
            curve = curves[ai_level]
            info(
                f"{ai_level}: range={curve['lower_bound'] * 100:g}%-"
                f"{curve['upper_bound'] * 100:g}%, "
                f"mean={curve['accuracy'] * 100:g}%, "
                f"points={len(curve['series'])}",
                "main",
            )

        _cleanup_known_sqlite_wal_files()

        if args.ws_only:
            # 仅启动WebSocket服务器
            info("启动模式: 仅WebSocket服务器", "main")
            await websocket_server.start_server()
        else:
            # 启动HTTP服务器（包含静态文件服务和WebSocket）
            info("启动模式: HTTP服务器 (静态文件 + WebSocket)", "main")
            
            # 设置静态文件目录
            static_dir = setup_static_directory(args.static_dir)
            
            # 配置HTTP服务器
            http_server.port = args.http_port
            http_server.update_static_directory(static_dir)
            
            # 启动HTTP服务器
            await http_server.start_server()
        
    except KeyboardInterrupt:
        info("收到中断信号，正在关闭服务器...", "main")
    except AccuracyCurveConfigError as e:
        error(f"AI准确率曲线配置无效，服务拒绝启动: {e}", "main", exc_info=True)
        sys.exit(1)
    except Exception as e:
        error(f"服务器启动失败: {e}", "main", exc_info=True)
        sys.exit(1)
    finally:
        try:
            await websocket_server.close_clients()
        except Exception as e:
            error(f"鍏抽棴 WebSocket 瀹㈡埛绔繛鎺ユ椂鍑洪敊: {e}", "main")

        if _joystick_handler:
            info("正在清理操纵杆资源...", "main")
            try:
                _joystick_handler.stop()
            except Exception as e:
                error(f"清理操纵杆资源时出错: {e}", "main")

        if _gaze_svc is not None:
            info("正在关闭眼动追踪服务...", "main")
            try:
                # 若仍有活动任务，先正常结束它（写 summary.json）
                active_id = _gaze_svc.get_active_task_id()
                if active_id:
                    _gaze_svc.stop_task(task_id=active_id)
                # 关闭后台文件写入线程，确保数据落盘
                _gaze_svc.shutdown()
                info("✅ 眼动追踪服务已关闭", "main")
            except Exception as e:
                error(f"关闭眼动追踪服务时出错: {e}", "main")

        if _physio_svc is not None:
            info("正在关闭手环/指环记录服务...", "main")
            try:
                _physio_svc.stop()
                info("手环/指环记录服务已关闭", "main")
            except Exception as e:
                error(f"关闭手环/指环记录服务时出错: {e}", "main")

        if _external_collectors is not None:
            info("正在关闭外部采集服务调用...", "main")
            try:
                _external_collectors.stop()
                info("外部采集服务调用已关闭", "main")
            except Exception as e:
                error(f"关闭外部采集服务调用时出错: {e}", "main")

        try:
            db_manager.shutdown()
        except Exception as e:
            error(f"鍏抽棴涓绘暟鎹簱鍐欏叆绾跨▼鏃跺嚭閿? {e}", "main")

        _cleanup_known_sqlite_wal_files()

if __name__ == "__main__":
    info("雷达系统服务器 v2.0 - 模块化架构", "main")
    info("支持静态文件服务和WebSocket连接", "main")
    info("=" * 50, "main")
    asyncio.run(main())
