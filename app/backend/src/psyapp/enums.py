"""业务枚举值——字符串常量集中定义，模型与代码不散落魔法字符串。"""


class ClientStatus:
    ACTIVE = "active"
    DISABLED = "disabled"


class SessionMode:
    IN_PERSON = "in_person"
    MEETING = "meeting"


class SessionStatus:
    RECORDING = "recording"
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    DONE = "done"
    FAILED = "failed"


class Speaker:
    THERAPIST = "T"
    PATIENT = "P"
    UNKNOWN = "U"


class SegmentSource:
    ASR = "asr"
    USER = "user"


class RecordStatus:
    DRAFT = "draft"
    SAVED = "saved"


class ThemeType:
    DREAM = "dream"
    GROWTH = "growth"
    TRAUMA = "trauma"


class JobType:
    TRANSCRIBE = "transcribe"
    CLEAN = "clean"
    RECORD = "record"
    THEMES = "themes"


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
