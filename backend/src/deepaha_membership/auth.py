from dataclasses import dataclass
from .errors import require

@dataclass(frozen=True)
class Actor:
    name: str
    roles: frozenset[str] = frozenset()

    def has(self, role: str) -> bool:
        return role in self.roles or (role=='reviewer' and 'operator' in self.roles)

    def need(self, role: str):
        require(self.has(role),'没有执行此操作的权限',403,'FORBIDDEN')
