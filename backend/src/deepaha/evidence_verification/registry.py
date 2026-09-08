from collections.abc import Sequence

from deepaha.evidence_verification.contracts import EvidenceAdapter, ReaderIdentity


class AdapterRegistry:
    """Only application-registered objects; no import path or code from a delivery."""

    def __init__(
        self, active: Sequence[EvidenceAdapter], *, historical: Sequence[EvidenceAdapter] = ()
    ) -> None:
        self._active: dict[str, EvidenceAdapter] = {}
        self._versions: dict[ReaderIdentity, EvidenceAdapter] = {}
        for adapter in active:
            for media in adapter.media_types:
                media = self.media_type(media)
                if media in self._active:
                    raise ValueError("multiple active readers for one media type")
                self._active[media] = adapter
        for adapter in (*active, *historical):
            if adapter.identity in self._versions:
                raise ValueError("duplicate reader version identity")
            self._versions[adapter.identity] = adapter

    @staticmethod
    def media_type(media: str) -> str:
        return media.partition(";")[0].strip().lower()

    def select(self, media: str, identity: ReaderIdentity | None = None) -> EvidenceAdapter | None:
        media = self.media_type(media)
        if identity is None:
            return self._active.get(media)
        adapter = self._versions.get(identity)
        if adapter is None or media not in tuple(self.media_type(m) for m in adapter.media_types):
            return None
        return adapter
