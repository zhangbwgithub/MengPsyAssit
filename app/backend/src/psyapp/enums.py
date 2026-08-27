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


class SpeakerCode:
    """转写阶段说话人代号（T-S1.1 起不再预设角色，未知代号兜底用 U）。"""

    UNKNOWN = "U"


class Role:
    """清理阶段由 LLM 判定的具体角色。"""

    THERAPIST = "T"
    PATIENT = "P"


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
