"""UI-independent workflow state. Editing input or target invalidates preview."""
from pathlib import Path
from .contract import Package
from .errors import ImporterError
from .receipts import save_pending, save_receipt


class ImportSession:
    def __init__(self, results_dir):
        self.results_dir = Path(results_dir)
        self.path = None; self.package = None; self.client = None; self.preview_result = None

    def invalidate(self):
        self.preview_result = None; self.client = None

    def load(self, path):
        self.invalidate()
        self.path = None; self.package = None
        package = Package.from_file(path)
        self.path = Path(path).expanduser().resolve(); self.package = package
        return package

    def preview(self, client, approve_sources=None):
        self.invalidate()
        if self.path is None: raise ImporterError('FILE_REQUIRED', '请先选择 Handoff.json。')
        self.package = Package.from_file(self.path)
        result = client.preview(self.package, approve_sources)
        self.client, self.preview_result = client, result
        return result

    def commit(self, confirmed=False):
        if confirmed is not True or not self.preview_result or not self.client or not self.preview_result['can_commit']:
            raise ImporterError('CONFIRMATION_REQUIRED', '请先预览，再明确确认导入。')
        current = Package.from_file(self.path)
        if current.package_hash != self.package.package_hash:
            self.invalidate()
            raise ImporterError('INPUT_CHANGED', '所选文件或附件已变化，请重新预览。', 409)
        save_pending(current, self.preview_result, self.results_dir)
        receipt = self.client.commit(current, self.preview_result, True)
        # Once a server success is known, never describe a local save error as failed import.
        try:
            paths = save_receipt(receipt, self.results_dir)
        except Exception as exc:
            self.invalidate()
            raise ImporterError('IMPORTED_RECEIPT_SAVE_FAILED', '服务器已确认导入，但本机回执保存失败。请更换结果目录并查询回执，不要重新生成批次。', 500) from exc
        self.invalidate()
        return {'receipt': receipt} | paths

    def recover(self, client):
        if self.path is None: raise ImporterError('FILE_REQUIRED', '请先选择原 Handoff.json。')
        package = Package.from_file(self.path)
        receipt = client.receipt(package)
        paths = save_receipt(receipt, self.results_dir)
        self.invalidate()
        return {'receipt': receipt} | paths
