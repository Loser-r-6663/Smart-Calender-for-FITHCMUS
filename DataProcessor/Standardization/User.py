from pydantic import BaseModel, Field


class User(BaseModel):
    id: str | None = Field(
        default=None,
        description="ID người dùng trong hệ thống (UUID)"
    )
    username: str | None = Field(
        default=None,
        description="Tên đăng nhập hệ thống"
    )
    portal_username: str | None = Field(
        default=None,
        description="Tên đăng nhập hoặc MSSV trên Portal"
    )
    portal_password: str | None = Field(
        default=None,
        description="Mật khẩu Portal"
    )
    moodle_session: str | None = Field(
        default=None,
        description="Session string / cookies trên Moodle"
    )
    moodle_status: bool = Field(
        default=False,
        description="Trạng thái hợp lệ của session Moodle"
    )
    portal_session: str | None = Field(
        default=None,
        description="Session string / cookies trên Portal"
    )
    portal_status: bool = Field(
        default=False,
        description="Trạng thái hợp lệ của session Portal"
    )
    drl_scores: dict[str, int] = Field(
        default_factory=lambda: {
            "dieu_1": 0,
            "dieu_2": 0,
            "dieu_3": 0,
            "dieu_4": 0,
            "dieu_5": 0,
        },
        description="Điểm rèn luyện hiện có theo 5 tiêu chí (dieu_1..dieu_5)"
    )

    def update(self, **kwargs):
        """Cập nhật các thuộc tính của User với các keyword arguments được truyền vào."""
        fields = self.__class__.model_fields
        for key, value in kwargs.items():
            if key in fields:
                setattr(self, key, value)
        return self

    def __getitem__(self, item: str):
        if item in self.__class__.model_fields:
            return getattr(self, item)
        raise KeyError(item)

    def __setitem__(self, key: str, value):
        if key in self.__class__.model_fields:
            setattr(self, key, value)
        else:
            raise KeyError(f"'{self.__class__.__name__}' object has no field '{key}'")

    def __contains__(self, item: str):
        return item in self.__class__.model_fields

    def get(self, key: str, default=None):
        if key in self.__class__.model_fields:
            return getattr(self, key)
        return default

    def __repr__(self):
        fields = "\n".join(f"\t{k}: {repr(v)}" for k, v in self)
        return f"\n{self.__class__.__name__}(\n{fields}\n)"

    __str__ = __repr__
