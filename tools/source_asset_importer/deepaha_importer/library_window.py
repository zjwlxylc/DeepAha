"""Chinese Library picker. Runs Codex in a background thread, not a terminal UI."""
from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .codex_process import CodexLibraryConfig, load_library_config, save_library_config
from .errors import ImporterError
from .library_pull import FOLDER, LibraryFile, LibraryPull


class LibraryWindow:
    def __init__(self, parent, data_dir: Path, on_ready):
        self.window = tk.Toplevel(parent)
        self.window.title('从资料库获取 · 程序调用 Codex CLI')
        self.window.geometry('900x640')
        self.window.minsize(760, 580)
        self.window.transient(parent)
        self.window.grab_set()
        self.data_dir, self.on_ready = Path(data_dir), on_ready
        self.config_path = self.data_dir / 'codex-library.settings.json'
        self.events, self.cancel = queue.Queue(), threading.Event()
        self.busy, self.closed, self.catalog = False, False, None
        self.entries, self.controls = {}, []
        try:
            cfg = load_library_config(self.config_path)
            initial = '点击“读取资料库”，列出指定目录的资产包；选择后由程序自动取回。'
        except (ImporterError, OSError) as exc:
            cfg = CodexLibraryConfig()
            initial = '获取配置无法读取，请检查并保存设置。'
        self.executable = tk.StringVar(value=cfg.executable)
        self.profile = tk.StringVar(value=cfg.profile)
        self.model = tk.StringVar(value=cfg.model)
        self.timeout = tk.StringVar(value=str(cfg.timeout_seconds))
        self.limit = tk.StringVar(value='50')
        self.network = tk.BooleanVar(value=cfg.allow_network_downloads)
        self.status = tk.StringVar(value=initial)
        self._build()
        self.window.protocol('WM_DELETE_WINDOW', self._close)
        self.window.bind('<Destroy>', self._destroyed, add='+')
        self.timer = self.window.after(100, self._poll)

    def _build(self):
        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='从“DeepAha网络资源”取回资产包', font=('', 16, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='程序会在后台调用本机 Codex，无需另开 Codex 窗口或手动下载。', wraplength=830).pack(anchor='w', pady=(6, 3))
        ttk.Label(outer, text='前提：本机 Codex 已登录，且拥有该个人资料库的读取/原件导出工具。调用可能消耗 Codex 额度。', wraplength=830).pack(anchor='w', pady=(0, 8))
        settings = ttk.LabelFrame(outer, text='获取设置（与 DeepAha 导入授权完全分开）', padding=8)
        settings.pack(fill='x')
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text='Codex 程序').grid(row=0, column=0, sticky='w')
        exe = ttk.Entry(settings, textvariable=self.executable)
        exe.grid(row=0, column=1, columnspan=3, sticky='ew', padx=6)
        browse = ttk.Button(settings, text='选择程序', command=self._browse)
        browse.grid(row=0, column=4)
        ttk.Label(settings, text='配置名称（可空）').grid(row=1, column=0, sticky='w', pady=6)
        profile = ttk.Entry(settings, textvariable=self.profile, width=20)
        profile.grid(row=1, column=1, sticky='ew', padx=6)
        ttk.Label(settings, text='模型（可空）').grid(row=1, column=2)
        model = ttk.Entry(settings, textvariable=self.model, width=18)
        model.grid(row=1, column=3, columnspan=2, sticky='ew', padx=6)
        ttk.Label(settings, text='超时（秒）').grid(row=2, column=0, sticky='w')
        timeout = ttk.Spinbox(settings, from_=30, to=1800, textvariable=self.timeout, width=8)
        timeout.grid(row=2, column=1, sticky='w', padx=6)
        ttk.Label(settings, text='最多列出').grid(row=2, column=2)
        limit = ttk.Spinbox(settings, from_=1, to=200, textvariable=self.limit, width=8)
        limit.grid(row=2, column=3, sticky='w', padx=6)
        save = ttk.Button(settings, text='保存设置', command=self._save)
        save.grid(row=2, column=4)
        network = ttk.Checkbutton(settings, text='允许下载原件时使用网络命令（只有导出工具确需下载地址时开启）', variable=self.network)
        network.grid(row=3, column=0, columnspan=5, sticky='w', pady=(6, 0))
        self.controls.extend([exe, browse, profile, model, timeout, limit, save, network])
        # Fixed footer first: fetching and cancellation controls remain visible.
        footer = ttk.Frame(outer)
        footer.pack(side='bottom', fill='x', pady=(8, 0))
        bar = ttk.Frame(footer)
        bar.pack(fill='x')
        refresh = ttk.Button(bar, text='1. 读取资料库', command=self._list)
        refresh.pack(side='left')
        self.fetch_button = ttk.Button(bar, text='2. 取回选中文件并载入', command=self._fetch, state='disabled')
        self.fetch_button.pack(side='left', padx=8)
        self.cancel_button = ttk.Button(bar, text='取消获取', command=self._cancel, state='disabled')
        self.cancel_button.pack(side='left')
        self.close_button = ttk.Button(bar, text='关闭', command=self._close)
        self.close_button.pack(side='right')
        self.controls.append(refresh)
        self.progress = ttk.Progressbar(footer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(8, 4))
        ttk.Label(footer, textvariable=self.status, wraplength=830).pack(anchor='w')
        ttk.Label(footer, text='只取文件，不提交、不批准、不启动 WMA；回执不会自动上传。').pack(anchor='w', pady=(4, 0))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(body, columns=('name', 'modified', 'size'), show='headings', selectmode='browse', height=7)
        for key, label, width in [('name', '资产包文件名', 450), ('modified', '资料库修改时间', 210), ('size', '大小', 80)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=60)
        scroll = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self._selection)
        self.notes = ScrolledText(outer, height=3, wrap='word', font=('', 10))
        self.notes.pack(fill='x', pady=(6, 0))
        self._note('位置：ChatGPT 个人资料库 ' + FOLDER + '\n没有访问权限时会明确报告；不会用演练样本或模型生成内容冒充下载结果。')

    def _config(self):
        try:
            cfg = CodexLibraryConfig(self.executable.get().strip(), self.profile.get().strip(),
                                     self.model.get().strip(), int(self.timeout.get()), self.network.get())
        except ValueError as exc:
            raise ImporterError('CODEX_CONFIG_INVALID', '超时必须填写整数秒。') from exc
        cfg.validate()
        return cfg

    def _browse(self):
        path = filedialog.askopenfilename(parent=self.window, title='选择 Codex CLI 程序')
        if path:
            self.executable.set(path)

    def _save(self):
        try:
            save_library_config(self._config(), self.config_path)
            self.status.set('设置已保存；未保存任何登录凭据。')
        except (ImporterError, OSError) as exc:
            self._error(exc)

    def _list(self):
        try:
            bridge = LibraryPull(self._config(), self.data_dir)
            maximum = int(self.limit.get())
            if not 1 <= maximum <= 200:
                raise ValueError
        except (ImporterError, ValueError) as exc:
            self._error(exc)
            return
        self.catalog = None
        self.entries.clear()
        self.tree.delete(*self.tree.get_children())
        self._start(lambda: bridge.list_files(self.cancel, maximum), self._listed, '正在由程序调用 Codex 读取资料库……')

    def _listed(self, catalog):
        self.catalog = catalog
        for number, data in enumerate(catalog['files']):
            entry = LibraryFile.from_dict(data)
            iid = str(number)
            self.entries[iid] = entry
            size = '未知' if entry.size_bytes is None else f'{entry.size_bytes / 1024:.1f} KB'
            self.tree.insert('', 'end', iid=iid, values=(entry.name, entry.modified_at or '未知', size))
        count = len(self.entries)
        suffix = '目录已枚举完成。' if catalog['listing_complete'] else '列表尚未枚举完整，可提高数量上限后重新读取。'
        self.status.set(f'已列出 {count} 个资产包。' + suffix)
        self._note('请选择需要取回的批次。文件不会自动导入。\n列表记录已保存：' + catalog['catalog_path'])
        if count:
            self.tree.selection_set('0')
            self._selection()

    def _selection(self, _event=None):
        self.fetch_button.configure(state='normal' if not self.busy and self.tree.selection() and self.catalog else 'disabled')

    def _fetch(self):
        selected = self.tree.selection()
        if self.busy or not self.catalog or not selected:
            return
        entry = self.entries[selected[0]]
        try:
            bridge = LibraryPull(self._config(), self.data_dir)
        except ImporterError as exc:
            self._error(exc)
            return
        folder_ref = self.catalog['folder_ref']
        self._start(lambda: bridge.fetch(entry, folder_ref, self.cancel), self._fetched,
                    '正在由 Codex 取回原件及必需依赖；完成后载入，不会自动提交……')

    def _fetched(self, result):
        path = result['file_path']
        self._close()
        self.on_ready(path)

    def _start(self, work, done, status):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        for control in self.controls:
            control.configure(state='disabled')
        self.fetch_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.close_button.configure(state='disabled')
        self.progress.start(12)
        self.status.set(status)
        def worker():
            try:
                self.events.put((True, work(), done))
            except Exception as exc:
                self.events.put((False, exc, done))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        if self.closed:
            return
        try:
            success, value, done = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            for control in self.controls:
                control.configure(state='normal')
            self.cancel_button.configure(state='disabled')
            self.close_button.configure(state='normal')
            if success and self.cancel.is_set():
                self._error(ImporterError('LIBRARY_CANCELLED', '获取已取消；不会载入文件或提交数据库。'))
            elif success:
                try:
                    done(value)
                except Exception as exc:
                    self._error(exc)
            else:
                self._error(value)
            if not self.closed:
                self._selection()
        if not self.closed:
            self.timer = self.window.after(100, self._poll)

    def _note(self, message):
        self.notes.configure(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', message)
        self.notes.configure(state='disabled')

    def _error(self, exc):
        message = f'[{exc.code}] {exc.message}' if isinstance(exc, ImporterError) else '获取失败。请检查数字设置、文件权限及 Codex 本机配置。'
        self.status.set(message)
        self._note(message + '\n本次没有提交 DeepAha；自动获取失败不会自动改走人工下载。')
        if not isinstance(exc, ImporterError) or exc.code != 'LIBRARY_CANCELLED':
            messagebox.showerror('尚未取得可用资产包', message, parent=self.window)

    def _cancel(self):
        self.cancel.set()
        self.cancel_button.configure(state='disabled')
        self.status.set('正在取消获取并结束后台进程……')

    def _destroyed(self, event):
        if event.widget is self.window:
            self.cancel.set()
            self.closed = True
            try:
                self.window.after_cancel(self.timer)
            except tk.TclError:
                pass

    def _close(self):
        if self.busy:
            self._cancel()
            return
        self.closed = True
        self.window.after_cancel(self.timer)
        self.window.grab_release()
        self.window.destroy()
