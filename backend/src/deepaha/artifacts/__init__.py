"""Artifact exports. Load ORM/service dependencies only when actually requested.
The byte store is shared by the current product and the historical pipeline.
"""
from importlib import import_module

__all__ = [
    'ImportRawArtifactCommand','ImportRawArtifactResult','RawArtifact',
    'RawArtifactProvenanceConflict','build_raw_object_key','import_raw_artifact',
]

def __getattr__(name):
    if name not in __all__:raise AttributeError(name)
    module='deepaha.artifacts.models' if name=='RawArtifact' else 'deepaha.artifacts.service'
    return getattr(import_module(module),name)
