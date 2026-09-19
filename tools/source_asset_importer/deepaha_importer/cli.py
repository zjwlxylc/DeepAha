"""Command-line entry; a human confirms the exact run and destination."""
from __future__ import annotations
import argparse
import getpass
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from .client import RemoteClient
from .config import default_data_dir, load_config
from .contract import Package, canonical_json, parse_json
from .controller import ImportSession
from .demo import demo_client
from .errors import ImporterError
from .receipts import immutable_write, save_pending, save_receipt


def parser():
    p = argparse.ArgumentParser(description='DeepAha 来源资产导入：可调用 Codex 从资料库取文件；入库仍为确定性程序并需人工确认。')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('gui', help='打开原单批执行契约兼容窗口')
    wb=sub.add_parser('workbench',help='打开本地批量研究资产工作台')
    wb.add_argument('--data-dir',type=Path,default=default_data_dir())
    wb.add_argument('--port',type=int,default=0)
    wb.add_argument('--no-browser',action='store_true')
    audit=sub.add_parser('research-audit',help='离线审核多个JSON/ZIP/目录，不提交系统')
    audit.add_argument('paths',nargs='+',type=Path)
    audit.add_argument('--output',required=True,type=Path)
    audit.add_argument('--namespace',default='AUTO')
    for name in ('library-list', 'library-fetch'):
        lib = sub.add_parser(name, help='程序在后台调用 Codex，只列出/取回资料库文件，不入库')
        lib.add_argument('--data-dir', type=Path, default=default_data_dir())
        lib.add_argument('--codex-config', type=Path, help='资料库获取专用设置，不是 DeepAha 导入设置')
        lib.add_argument('--codex', help='Codex 可执行文件路径')
        lib.add_argument('--profile', help='本机已有 Codex 配置名称')
        lib.add_argument('--model', help='可选：本次使用的 Codex 模型')
        lib.add_argument('--timeout', type=int, help='获取超时秒数，30–1800')
        lib.add_argument('--allow-network-downloads', action='store_true', help='允许 Codex 在下载阶段运行联网下载命令')
        if name == 'library-list':
            lib.add_argument('--max-results', type=int, default=50)
        else:
            lib.add_argument('--catalog', type=Path, required=True, help='library-list 生成的目录清单')
            lib.add_argument('--file-ref', required=True, help='清单中的精确资料库文件 ID')
            lib.add_argument('--file-version', help='同一 ID 有多个版本时必须指定')
    v = sub.add_parser('validate', help='只检查文件格式与完整性，不连接数据库')
    v.add_argument('file', type=Path)
    for name in ('preview', 'import', 'commit', 'receipt'):
        c = sub.add_parser(name, help={'preview':'只读预览', 'import':'预览后交互确认导入',
                                     'commit':'提交已保存的预览', 'receipt':'查询并恢复已保存回执'}[name])
        c.add_argument('file', type=Path)
        choice = c.add_mutually_exclusive_group()
        choice.add_argument('--demo', action='store_true', help='只写本机演练库，绝不是正式入库')
        choice.add_argument('--server', help='宿主服务地址（不是假定已上线的地址）')
        c.add_argument('--environment', choices=['DEMO','TEST','STAGING','PRODUCTION'])
        c.add_argument('--target-id', help='可选：固定已经确认的服务器存储目标 ID')
        c.add_argument('--config', type=Path, help='不含凭据的客户端配置')
        c.add_argument('--data-dir', type=Path, default=default_data_dir())
        c.add_argument('--allow-http-loopback', action='store_true', help='仅供本机 HTTP 演练')
        c.add_argument('--token-env', default='DEEPAHA_IMPORT_TOKEN', help='读取授权的环境变量名，不接收明文 token 参数')
        c.add_argument('--approve-source', action='append', default=[], help='可选且独立的来源批准；需要宿主已接入批准功能')
        if name in ('import', 'commit'):
            c.add_argument('--confirm-run', help='非交互确认的完整 run_key；不提供则要求人工输入')
            c.add_argument('--confirm-environment', help='非交互远程提交还需明确确认实际目标环境')
        if name == 'preview': c.add_argument('--output', type=Path, help='保存带短期令牌的本地预览，不上传资料库')
        if name == 'commit': c.add_argument('--preview', type=Path, required=True)
    return p


def make_client(args):
    if args.demo:
        if args.environment not in (None, 'DEMO'):
            raise ImporterError('ENVIRONMENT_MISMATCH', '--demo 不能搭配非 DEMO 环境。')
        return demo_client(args.data_dir / 'demo')
    config = load_config(args.config or args.data_dir / 'settings.json')
    if args.server is not None: config = replace(config, base_url=args.server)
    if args.environment is not None: config = replace(config, expected_environment=args.environment)
    if args.target_id is not None: config = replace(config, expected_target_id=args.target_id)
    if args.allow_http_loopback: config = replace(config, allow_http_loopback=True)
    config.validate()
    token = os.environ.get(args.token_env, '')
    if not token:
        if not sys.stdin.isatty():
            raise ImporterError('TOKEN_REQUIRED', '远程非交互运行需在本机环境变量中提供导入授权。', 401)
        token = getpass.getpass('请输入本机导入授权（不回显、不保存）：')
    return RemoteClient(config, token)


def show_preview(preview):
    print('\n目标环境：', preview['environment'])
    print('存储目标 ID：', preview['target_id'])
    print('批次：', preview['run_key'])
    if preview['environment'] != 'PRODUCTION': print('注意：这不是正式 DeepAha 入库。')
    print('计划：', json.dumps(preview.get('counts', {}), ensure_ascii=False))
    for item in preview['items']:
        # Escape control/terminal sequences in data supplied by an external research file.
        name = json.dumps(item['name'], ensure_ascii=False)
        print(f"  {item['action']:12} {item['kind']:14} {name}")
    for conflict in preview.get('conflicts', []):
        print('冲突：', json.dumps(conflict, ensure_ascii=False))
    print('当前操作只处理研究资产，不自动启动 WMA。')


def confirmation(args, package, environment):
    if args.confirm_run is not None:
        if args.confirm_run != package.run_key:
            raise ImporterError('CONFIRMATION_MISMATCH', '确认的批次与文件不一致。')
        if environment != 'DEMO' and args.confirm_environment != environment:
            raise ImporterError('CONFIRMATION_REQUIRED', '远程非交互提交需要 --confirm-environment 与实际环境一致。')
        return True
    phrase = f'IMPORT {package.run_key} TO {environment}'
    print('\n确认提交请输入以下完整内容（其他输入取消）：\n' + phrase)
    try: return input('> ').strip() == phrase
    except EOFError: return False


def library_command(args):
    from .codex_process import load_library_config
    from .library_pull import FOLDER, PROTOCOL, LibraryFile, LibraryPull
    config = load_library_config(args.codex_config or args.data_dir / 'codex-library.settings.json')
    for argument, field in (('codex', 'executable'), ('profile', 'profile'), ('model', 'model'), ('timeout', 'timeout_seconds')):
        if getattr(args, argument) is not None:
            config = replace(config, **{field: getattr(args, argument)})
    if args.allow_network_downloads:
        config = replace(config, allow_network_downloads=True)
    bridge = LibraryPull(config, args.data_dir)
    if args.command == 'library-list':
        result = bridge.list_files(max_results=args.max_results)
    else:
        catalog = parse_json(args.catalog.read_bytes(), 2 * 1024 * 1024)
        if (not isinstance(catalog, dict) or catalog.get('protocol') != PROTOCOL
                or catalog.get('folder_path') != FOLDER or not isinstance(catalog.get('files'), list)):
            raise ImporterError('LIBRARY_CATALOG_INVALID', '请选择本工具生成的有效资料库清单。')
        entries = [LibraryFile.from_dict(item) for item in catalog['files']]
        matches = [entry for entry in entries if entry.file_ref == args.file_ref
                   and (args.file_version is None or entry.version == args.file_version)]
        if len(matches) != 1:
            raise ImporterError('LIBRARY_SELECTION_REQUIRED', '文件 ID/版本未唯一匹配清单，请重新读取并明确选择。')
        result = bridge.fetch(matches[0], catalog.get('folder_ref'))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command=='workbench':
            from .workbench import main as workbench_main
            workbench_main(args.data_dir,args.port,not args.no_browser);return 0
        if args.command=='research-audit':
            from .research.ingest import load_inputs
            from .research.audit import analyze
            from .research.workspace import pretty
            result=analyze(load_inputs(args.paths,args.namespace))
            immutable_write(args.output,pretty(result))
            print(json.dumps(result['summary'],ensure_ascii=False,indent=2));return 0
        if args.command == 'gui':
            from .gui import main as gui_main
            gui_main(); return 0
        if args.command in ('library-list', 'library-fetch'):
            return library_command(args)
        package = Package.from_file(args.file)
        if args.command == 'validate':
            print(json.dumps({'status':'VALID', 'run_key':package.run_key,
                              'package_hash':package.package_hash, 'asset_count':len(package.assets()),
                              'note':'只验证结构与依赖；尚未检查数据库重复、官方真实性或批准状态。'}, ensure_ascii=False, indent=2))
            return 0
        client = make_client(args)
        session = ImportSession(args.data_dir / 'receipts'); session.load(args.file)
        if args.command == 'receipt':
            result = session.recover(client)
        elif args.command == 'commit':
            preview = parse_json(args.preview.read_bytes())
            show_preview(preview)
            if not confirmation(args, package, client.environment):
                print('已取消，未提交。'); return 0
            if preview.get('package_hash') != package.package_hash:
                raise ImporterError('INPUT_CHANGED', '文件与已保存预览不一致。', 409)
            save_pending(package, preview, session.results_dir)
            receipt = client.commit(package, preview, True)
            try: result = {'receipt':receipt} | save_receipt(receipt, session.results_dir)
            except Exception as exc:
                raise ImporterError('IMPORTED_RECEIPT_SAVE_FAILED', '服务端已确认入库但本机回执保存失败，请执行 receipt 恢复。', 500) from exc
        else:
            preview = session.preview(client, args.approve_source)
            show_preview(preview)
            if args.command == 'preview':
                if args.output:
                    immutable_write(args.output, canonical_json(preview) + b'\n')
                    print('本地预览已保存：', args.output)
                return 0 if preview['can_commit'] else 3
            if not preview['can_commit']: return 3
            if not confirmation(args, package, client.environment):
                print('已取消，未提交。'); return 0
            result = session.commit(True)
        print('\n服务器/演练库回读结果：', result['receipt']['status'])
        print('回执 JSON：', result['json_path'])
        print('阅读版回执：', result['markdown_path'])
        print('回传回执可选；演练/测试回执不要当正式反馈上传。')
        return 0
    except ImporterError as exc:
        print(f'[{exc.code}] {exc.message}', file=sys.stderr)
        if exc.details: print(json.dumps(exc.details, ensure_ascii=False), file=sys.stderr)
        return 3 if exc.status == 409 else 1
    except (OSError, ValueError) as exc:
        print('本机文件或配置处理失败：' + type(exc).__name__ + '。请检查路径及权限。', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\n操作已中断；若提交阶段中断，请查询回执。', file=sys.stderr)
        return 130
