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

class Product(AuthMixin,SourcesMixin,IntakeMixin,CatalogMixin,ActionLoopMixin,PersonalMixin,TasksMixin,ScoutMixin,LabMixin):
    def __init__(self,database_url,object_root):
        self.database_url=database_url;self.object_root=Path(object_root)
        self.db=Database(database_url);self.store=ArchiveStore(self.object_root)
    def initialize(self, allow_existing_upgrade=False):
        self.db.initialize(allow_existing_upgrade=allow_existing_upgrade)
        self._scout_init()
    def _audit(self,s,actor,action,target,summary):s.add(Audit(actor=actor,action=action,target=target,summary=summary))
