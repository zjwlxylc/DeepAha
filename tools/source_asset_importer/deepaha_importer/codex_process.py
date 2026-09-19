"""Run a bounded Codex job. This module has no DeepAha/database client.

The user supplies an installed, authenticated Codex CLI. No installation, login,
permission escalation, private API discovery, or production-token forwarding.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .contract import parse_json
from .errors import ImporterError

MAX_PROCESS_OUTPUT = 8 * 1024 * 1024
MAX_RESULT = 2 * 1024 * 1024


@dataclass(frozen=True)
class CodexLibraryConfig:
    executable: str = 'codex'
    profile: str = ''
    model: str = ''
    timeout_seconds: int = 300
    allow_network_downloads: bool = False

    def validate(self):
        if (not isinstance(self.executable, str) or not self.executable.strip()
                or any(ord(c) < 32 for c in self.executable)):
            raise ImporterError('CODEX_CONFIG_INVALID', '请填写 Codex 可执行文件路径或 codex。')
        for value in (self.profile, self.model):
            if not isinstance(value, str) or (value and not re.fullmatch(r'[A-Za-z0-9_./:@+-]{1,160}', value)):
                raise ImporterError('CODEX_CONFIG_INVALID', 'Codex 配置名称或模型名称格式无效。')
        if type(self.timeout_seconds) is not int or not 30 <= self.timeout_seconds <= 1800:
            raise ImporterError('CODEX_CONFIG_INVALID', '获取超时需为 30–1800 秒。')
        if type(self.allow_network_downloads) is not bool:
            raise ImporterError('CODEX_CONFIG_INVALID', '联网下载选项必须是布尔值。')


def load_library_config(path: Path) -> CodexLibraryConfig:
    if not path.is_file():
        return CodexLibraryConfig()
    raw = parse_json(path.read_bytes(), 10000)
    if not isinstance(raw, dict) or set(raw) - set(CodexLibraryConfig.__dataclass_fields__):
        raise ImporterError('CODEX_CONFIG_INVALID', '资料库获取配置存在不支持的字段。')
    result = CodexLibraryConfig(**raw)
    result.validate()
    return result


def save_library_config(config: CodexLibraryConfig, path: Path):
    config.validate()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.codex-settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _executable_prefix(config: CodexLibraryConfig) -> list[str]:
    """Avoid passing an arbitrary command line to a shell, including on Windows."""
    requested = os.path.expanduser(os.path.expandvars(config.executable.strip()))
    located = shutil.which(requested)
    if not located:
        p = Path(requested)
        if p.is_file() and (os.name == 'nt' or os.access(p, os.X_OK)):
            located = str(p.resolve())
    if not located:
        raise ImporterError('CODEX_NOT_FOUND', '没有找到 Codex CLI。请安装并登录后，在获取设置中选择实际程序路径。')
    path = Path(located).resolve()
    if path.suffix.lower() in {'.cmd', '.bat'}:
        # Standard npm global-install layout. Do not execute a user-generated
        # command string through cmd.exe or silently weaken security settings.
        script = path.parent / 'node_modules' / '@openai' / 'codex' / 'bin' / 'codex.js'
        local_node = path.parent / 'node.exe'
        node = str(local_node) if local_node.is_file() else shutil.which('node')
        if script.is_file() and node:
            return [node, str(script)]
        raise ImporterError('CODEX_LAUNCHER_UNSUPPORTED',
                            '找到 Windows 命令包装器，但未找到对应的 Codex Node 程序。请选择原生 codex.exe，或修复 CLI 安装。')
    if path.suffix.lower() in {'.ps1', '.sh'}:
        raise ImporterError('CODEX_LAUNCHER_UNSUPPORTED', '请选择 Codex 原生程序或标准 npm 的 codex.cmd，不使用任意脚本。')
    return [str(path)]


def _child_environment() -> dict[str, str]:
    """Keep Codex's own login/tool configuration, not the importer credentials."""
    excluded = {'DATABASE_URL', 'DATABASE_DSN', 'PGPASSWORD', 'PGPASSFILE',
                'MYSQL_PWD', 'PGSERVICE', 'PGSERVICEFILE', 'PYTHONPATH',
                'PYTHONSTARTUP', 'BASH_ENV', 'ENV'}
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith('DEEPAHA_') and key.upper() not in excluded}
    environment['NO_COLOR'] = '1'
    environment['PYTHONUTF8'] = '1'
    return environment


def _stop_process_tree(process: subprocess.Popen):
    if os.name == 'nt':
        if process.poll() is None:
            executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
            try:
                subprocess.run([str(executable), '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except (OSError, subprocess.SubprocessError):
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            if process.poll() is None:
                process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _completed_tools(events: bytes) -> list[dict]:
    """Capture tool metadata, not file text, command arguments, or reasoning."""
    found = []
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(event, dict) or event.get('type') != 'item.completed':
            continue
        item = event.get('item')
        if not isinstance(item, dict) or item.get('type') != 'mcp_tool_call':
            continue
        result = item.get('result')
        if item.get('status') != 'completed' or item.get('error'):
            continue
        if isinstance(result, dict) and (result.get('isError') or result.get('is_error')):
            continue
        server, tool = item.get('server'), item.get('tool')
        if isinstance(server, str) and isinstance(tool, str):
            record = {'server': server[:200], 'tool': tool[:200]}
            if record not in found:
                found.append(record)
    return found


def _failure_category(text: str) -> str:
    """Classify locally; raw error messages may contain credentials, never save."""
    categories = (
        ('AUTH_REQUIRED', ('unauthorized', 'not logged in', 'please login', '401')),
        ('RATE_LIMIT', ('rate limit', 'quota', '429', 'usage limit')),
        ('UNSUPPORTED_ARGUMENT', ('unexpected argument', 'unknown option', 'unrecognized')),
        ('MODEL_OR_CONFIGURATION', ('model not found', 'unknown model', 'profile not found')),
        ('NETWORK', ('connection refused', 'connection reset', 'dns', 'network', 'connect timeout')),
    )
    lowered = text.casefold()
    return next((name for name, terms in categories if any(t in lowered for t in terms)), 'UNCLASSIFIED')


class CodexProcess:
    def __init__(self, config: CodexLibraryConfig):
        config.validate()
        self.config = config
        self.on_progress = None
        self.last_diagnostic = {}
        self.supports_ephemeral = True

    def _progress(self, message):
        if self.on_progress:
            self.on_progress(message)

    def _metadata_command(self, prefix, arguments, cancel, timeout_seconds=8):
        """Read CLI metadata, without a model request or credential-file reads.

        Outputs can contain account data. Only the allowlisted classifications
        produced by preflight() may be persisted or displayed.
        """
        if cancel.is_set():
            raise ImporterError('LIBRARY_CANCELLED', '已取消连接检查。')
        process = None
        with tempfile.TemporaryFile() as out:
            try:
                options = ({'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
                           if os.name == 'nt' else {'start_new_session': True})
                process = subprocess.Popen(prefix + arguments, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=subprocess.STDOUT, env=_child_environment(),
                    shell=False, **options)
                deadline = time.monotonic() + timeout_seconds
                while process.poll() is None:
                    if cancel.is_set():
                        raise ImporterError('LIBRARY_CANCELLED', '已取消连接检查。')
                    if time.monotonic() >= deadline:
                        raise ImporterError('CODEX_PREFLIGHT_TIMEOUT', 'Codex本机检查未及时响应，已停止；不会继续启动资料库任务。')
                    if os.fstat(out.fileno()).st_size > 256 * 1024:
                        raise ImporterError('CODEX_OUTPUT_LIMIT', '本机检查输出异常，已停止。')
                    cancel.wait(0.05)
                if os.fstat(out.fileno()).st_size > 256 * 1024:
                    raise ImporterError('CODEX_OUTPUT_LIMIT', '本机检查输出异常，已停止。')
                out.seek(0)
                return process.returncode, out.read(256 * 1024)
            except OSError as exc:
                raise ImporterError('CODEX_PROCESS_ERROR', '无法启动Codex，请核对程序位置或安装情况。') from exc
            finally:
                if process is not None:
                    _stop_process_tree(process)

    def preflight(self, cancel):
        """CLI health is not a proof of Library access, even after ChatGPT login."""
        result = {'status': 'BLOCKED', 'checks': [], 'cli_version': None,
                  'auth_mode': 'UNKNOWN', 'apps_flag': 'UNKNOWN',
                  'library_access': 'UNVERIFIED', 'raw_export': 'UNVERIFIED',
                  'model_calls': 0, 'error_code': None}
        if cancel.is_set():
            raise ImporterError('LIBRARY_CANCELLED', '已取消连接检查。')
        try:
            self._progress('1/3 检查本机Codex程序与参数（不调用模型）')
            prefix = _executable_prefix(self.config)
            code, raw = self._metadata_command(prefix, ['--version'], cancel)
            if code:
                raise ImporterError('CODEX_VERSION_FAILED', 'Codex程序没有正常响应版本查询。')
            # A version token only: never persist arbitrary stdout.
            match = re.search(rb'(?i)codex(?:-cli)?\s+([0-9][0-9A-Za-z.+_-]{0,60})', raw)
            result['cli_version'] = match.group(1).decode('ascii') if match else None
            result['checks'].append({'check': 'executable', 'status': 'PASS'})
            context = ['--profile', self.config.profile] if self.config.profile else []
            code, raw = self._metadata_command(prefix, context + ['exec', '--help'], cancel)
            required = ['--json', '--output-schema', '--output-last-message', '--skip-git-repo-check', '--sandbox']
            missing = [flag for flag in required if flag.encode() not in raw]
            if code or missing:
                result['missing_flags'] = missing
                raise ImporterError('CODEX_FLAGS_UNSUPPORTED', '当前Codex不支持所需参数。请更新本机CLI；不会绕过沙盒继续运行。')
            self.supports_ephemeral = b'--ephemeral' in raw
            result['checks'].append({'check': 'exec_flags', 'status': 'PASS'})
            self._progress('2/3 检查登录状态与连接器开关（不读取密钥）')
            code, raw = self._metadata_command(prefix, context + ['login', 'status'], cancel)
            text = raw.decode('utf-8', errors='replace').casefold()
            if 'not logged in' in text or 'please login' in text or 'unauthorized' in text:
                raise ImporterError('CODEX_AUTH_REQUIRED', 'Codex尚未登录或登录已失效。请在Codex完成登录，再回来重试；此处不要填写密码。')
            result['auth_mode'] = ('CHATGPT' if not code and 'chatgpt' in text
                                   else 'API_KEY' if not code and ('api key' in text or 'api_key' in text)
                                   else 'UNKNOWN')
            result['checks'].append({'check': 'login_status', 'status': result['auth_mode']})
            # Some CLI versions lack features/list. That is not proof of no MCP.
            code, raw = self._metadata_command(prefix, context + ['features', 'list'], cancel)
            match = re.search(rb'(?m)^apps\s+[^\r\n]*?\b(true|false)\s*$', raw)
            if not code and match:
                result['apps_flag'] = 'ENABLED' if match.group(1) == b'true' else 'DISABLED'
            result['checks'].append({'check': 'apps_flag', 'status': result['apps_flag']})
            result['status'] = 'CODEX_READY_LIBRARY_UNVERIFIED'
            return result
        except ImporterError as exc:
            if exc.code == 'LIBRARY_CANCELLED':
                raise
            result['error_code'] = exc.code
            result['message'] = exc.message
            return result

    def run(self, prompt: str, schema: dict, workspace: Path,
            action: str, cancel: threading.Event) -> tuple[dict, list[dict]]:
        if cancel.is_set():
            raise ImporterError('LIBRARY_CANCELLED', '已取消资料库获取，未导入。')
        schema_path, result_path = workspace / 'response.schema.json', workspace / 'result.json'
        schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding='utf-8')
        command = _executable_prefix(self.config) + [
            '--ask-for-approval', 'never', 'exec', '--skip-git-repo-check',
            '--sandbox', 'workspace-write' if action == 'fetch' else 'read-only',
            '--color', 'never', '--json',
            '--output-schema', str(schema_path), '--output-last-message', str(result_path),
        ]
        if self.supports_ephemeral:
            command += ['--ephemeral']
        if self.config.profile:
            command += ['--profile', self.config.profile]
        if self.config.model:
            command += ['--model', self.config.model]
        command += ['-c', 'approval_policy="never"', '-c', 'web_search="disabled"',
                    '-c', 'sandbox_workspace_write.network_access=' +
                    ('true' if self.config.allow_network_downloads and action == 'fetch' else 'false'), '-']
        process = None
        started = time.monotonic()
        timeout = min(self.config.timeout_seconds, 60) if action == 'list' else self.config.timeout_seconds
        self.last_diagnostic = {'action': action, 'status': 'STARTING', 'timeout_seconds': timeout,
                                'observed_event_types': [], 'successful_tool_count': 0}
        self._progress('3/3 读取真实资料库目录（最多60秒，不代表已取得原件）' if action == 'list'
                       else '正在取得所选原件，并核对大小与哈希')
        # Spools are owned by the host and do not occupy the model's work folder.
        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            stdin.write(prompt.encode('utf-8'))
            stdin.seek(0)
            try:
                options = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)} if os.name == 'nt' else {'start_new_session': True}
                process = subprocess.Popen(command, cwd=workspace, env=_child_environment(),
                                           stdin=stdin, stdout=stdout, stderr=stderr,
                                           shell=False, **options)
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    if cancel.is_set():
                        raise ImporterError('LIBRARY_CANCELLED', '已取消资料库获取，未导入。')
                    if time.monotonic() >= deadline:
                        raise ImporterError('CODEX_TIMEOUT', 'Codex未在限定时间内完成。本次已停止，没有取回或提交文件。请下载连接诊断；也可选择已下载文件继续审核。')
                    if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > MAX_PROCESS_OUTPUT:
                        raise ImporterError('CODEX_OUTPUT_LIMIT', 'Codex 输出超过上限，本次获取已停止。')
                    cancel.wait(0.15)
                if cancel.is_set():
                    raise ImporterError('LIBRARY_CANCELLED', '已取消资料库获取，未导入。')
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > MAX_PROCESS_OUTPUT:
                    raise ImporterError('CODEX_OUTPUT_LIMIT', 'Codex 输出超过上限，本次获取已停止。')
                if process.returncode != 0:
                    stderr.seek(0)
                    hint = stderr.read(MAX_PROCESS_OUTPUT).decode('utf-8', errors='replace').casefold()
                    self.last_diagnostic['failure_category'] = _failure_category(hint)
                    if any(x in hint for x in ('unauthorized', 'not logged in', 'please login', '401')):
                        message = 'Codex 或资料库授权不可用，请先在本机完成相应登录/授权。'
                    elif self.last_diagnostic['failure_category'] == 'RATE_LIMIT':
                        message = 'Codex报告额度或请求频率限制，本次已停止；请在Codex检查可用额度。'
                    elif self.last_diagnostic['failure_category'] == 'NETWORK':
                        message = 'Codex报告网络连接失败，本次已停止；请检查本机连接后重试。'
                    elif any(x in hint for x in ('unexpected argument', 'unknown option', 'unrecognized')):
                        message = '当前 Codex CLI 不支持本次调用参数；请检查 CLI 版本和接续说明。'
                    else:
                        message = f'Codex 进程退出码为 {process.returncode}。可能是登录、工具权限、沙盒或 CLI 配置问题；没有取得可使用文件。'
                    raise ImporterError('CODEX_EXEC_FAILED', message)
                if (not result_path.is_file() or result_path.is_symlink()
                        or result_path.stat().st_size > MAX_RESULT):
                    raise ImporterError('CODEX_RESULT_MISSING', 'Codex 未交付有效的结构化获取结果。')
                with result_path.open('rb') as stream:
                    result = parse_json(stream.read(MAX_RESULT + 1), MAX_RESULT)
                if not isinstance(result, dict):
                    raise ImporterError('CODEX_RESULT_INVALID', 'Codex 的获取结果必须是 JSON 对象。')
                stdout.seek(0)
                events = stdout.read(MAX_PROCESS_OUTPUT)
                tools = _completed_tools(events)
                self.last_diagnostic.update(status='RESULT_RECEIVED', successful_tool_count=len(tools))
                return result, tools
            except ImporterError as exc:
                self.last_diagnostic.update(status='FAILED', error_code=exc.code)
                raise
            except (OSError, subprocess.SubprocessError) as exc:
                self.last_diagnostic.update(status='FAILED',error_code='CODEX_PROCESS_ERROR')
                raise ImporterError('CODEX_PROCESS_ERROR', '无法启动或读取 Codex 进程，请检查可执行文件、权限与本机配置。') from exc
            finally:
                self.last_diagnostic['elapsed_seconds'] = round(time.monotonic() - started, 2)
                self.last_diagnostic['exit_code'] = process.poll() if process is not None else None
                if process is not None:
                    _stop_process_tree(process)
                stdout.seek(0)
                types = set()
                for line in stdout.read(MAX_PROCESS_OUTPUT).splitlines():
                    try:
                        event = json.loads(line)
                        if isinstance(event, dict) and event.get('type') in {
                            'thread.started','turn.started','turn.completed','turn.failed',
                            'item.started','item.updated','item.completed','error'}:
                            types.add(event['type'])
                    except (ValueError, UnicodeError):
                        pass
                self.last_diagnostic['observed_event_types'] = sorted(types)
