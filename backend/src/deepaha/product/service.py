from pathlib import Path
from .db import Database
from .storage import ArchiveStore
from .auth import AuthMixin
from .sources import SourcesMixin
from .intake import IntakeMixin
from .catalog import CatalogMixin
from .models import Audit
from .personal import PersonalMixin
from .action_loop import ActionLoopMixin
from .tasks import TasksMixin
from .scout import ScoutMixin
from .lab import LabMixin
from .access import AccessMixin
from .experience import ExperienceMixin
from .dispatch_policy import DispatchPolicyMixin

class Product(DispatchPolicyMixin,ExperienceMixin,AccessMixin,AuthMixin,SourcesMixin,IntakeMixin,CatalogMixin,ActionLoopMixin,PersonalMixin,TasksMixin,ScoutMixin,LabMixin):
    def __init__(self,database_url,object_root):
        self.database_url=database_url;self.object_root=Path(object_root)
        self.db=Database(database_url);self.store=ArchiveStore(self.object_root)
    def initialize(self, allow_existing_upgrade=False):
        from sqlalchemy import inspect
        existing=set(inspect(self.db.engine).get_table_names())
        if 'product_meta' in existing and 'mbr_meta' not in existing and not allow_existing_upgrade:
            from .errors import Problem
            raise Problem('请先停止服务并运行 upgrade-services，备份后新增订阅结构',409,'SERVICES_UPGRADE_REQUIRED')
        from deepaha_membership.db import Store,metadata
        from deepaha_membership.errors import DomainError
        if set(metadata.tables)&existing:
            try:Store(self.db.engine).assert_ready()
            except DomainError as e:
                from .errors import Problem
                raise Problem(e.message,409,e.code) from None
        self.db.initialize(allow_existing_upgrade=allow_existing_upgrade)
        self._scout_init()
        from .membership import initialize
        initialize(self)
    def _audit(self,s,actor,action,target,summary):s.add(Audit(actor=actor,action=action,target=target,summary=summary))
