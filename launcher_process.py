"""Windows-owned Server process tree. The worker waits until job assignment."""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import subprocess
import sys


class BasicLimits(ctypes.Structure):
    _fields_ = [('user_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                ('process_limit', w.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', ctypes.c_ulonglong * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [('times', ctypes.c_longlong * 4), ('faults', w.DWORD),
                ('total', w.DWORD), ('active', w.DWORD), ('terminated', w.DWORD)]


class ServerJob:
    def __init__(self):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in [
            ('CreateJobObjectW', [ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            ('SetInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            ('QueryInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
            ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
            ('CloseHandle', [w.HANDLE], w.BOOL),
        ]:
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def active(self):
        if not self.handle:
            return False
        value = Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(value), ctypes.sizeof(value), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return value.active > 0

    def spawn(self, command, **kwargs):
        # No task code runs until the parent has put the waiting worker in the job.
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve())],
                                   stdin=subprocess.PIPE, **kwargs)
        try:
            if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
            process.stdin.write((json.dumps(command) + '\n').encode('utf-8'))
            process.stdin.close()
            return process
        except BaseException:
            process.stdin.close()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            raise

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


if __name__ == '__main__':
    line = sys.stdin.buffer.readline()
    if not line:
        sys.exit(1)
    command = json.loads(line.decode('utf-8'))
    # This process and all descendants inherit the job. No breakaway is permitted.
    sys.exit(subprocess.call(command, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW))
