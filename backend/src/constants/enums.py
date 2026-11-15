from enum import StrEnum
class Role(StrEnum):
 ADMIN="admin"
 ANALYST="analyst"
 VIEWER="viewer"
class RunStatus(StrEnum):
 QUEUED="queued"
 RUNNING="running"
 COMPLETED="completed"
 FAILED="failed"
class ModelMode(StrEnum):
 FIT="fit"
 FIXED="fixed"
COORDINATE_SYSTEM="local_meters"
