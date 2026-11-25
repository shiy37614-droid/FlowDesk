
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import unicodedata
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import BACKEND_DIR


# ============================================
# 1. 文件存储配置
# ============================================

# 文件实际保存目录
STORAGE_DIR = (
    BACKEND_DIR / "storage" / "attachments"
)

# 单个附件最大 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# 每次读取 1MB，避免一次性加载整个文件
CHUNK_SIZE = 1024 * 1024

# storage_key 必须是 32 位小写十六进制字符串
_STORAGE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{32}$"
)


# ============================================
# 2. 自定义文件异常
# ============================================

class EmptyUploadFileError(ValueError):
    """上传文件为空。"""


class UploadFileTooLargeError(ValueError):
    """上传文件超过大小限制。"""


class InvalidUploadFilenameError(ValueError):
    """上传文件名无效。"""


class InvalidStorageKeyError(ValueError):
    """内部存储标识无效。"""


# ============================================
# 3. 文件保存结果
# ============================================

@dataclass(frozen=True, slots=True)
class StoredFile:
    """
    文件保存成功后返回的元数据。
    """

    storage_key: str

    original_filename: str

    content_type: str

    file_size: int


# ============================================
# 4. 规范化原始文件名
# ============================================

def _normalize_filename(
    filename: str | None,
) -> str:
    """
    清理文件名。

    1. 移除路径信息。
    2. 移除控制字符。
    3. 去除首尾空格。
    4. 限制为 255 个字符。
    """

    if not isinstance(filename, str):

        raise InvalidUploadFilenameError(
            "A filename is required"
        )

    # 同时处理 Windows 和 Linux 路径分隔符
    normalized = (
        filename
        .replace("\\", "/")
        .rsplit("/", 1)[-1]
    )

    # 移除控制字符
    normalized = "".join(
        char
        for char in normalized
        if unicodedata.category(char) != "Cc"
    ).strip()

    if normalized in {"", ".", ".."}:

        raise InvalidUploadFilenameError(
            "Invalid filename"
        )

    return normalized[:255]


# ============================================
# 5. 获取服务器文件路径
# ============================================

def _get_storage_path(
    storage_key: str,
) -> Path:
    """
    根据 storage_key 获取实际文件路径。

    不允许客户端传入任意文件路径。
    """

    if (
        not isinstance(storage_key, str)
        or _STORAGE_KEY_PATTERN.fullmatch(
            storage_key
        ) is None
    ):

        raise InvalidStorageKeyError(
            "Invalid storage key"
        )

    return STORAGE_DIR / storage_key


# ============================================
# 6. 保存上传文件
# ============================================

async def save_upload_file(
    upload_file: UploadFile,
) -> StoredFile:
    """
    保存上传文件。

    1. 规范化原始文件名。
    2. 获取 MIME 类型。
    3. 创建文件存储目录。
    4. 生成随机 storage_key。
    5. 分块读取上传文件。
    6. 检查文件大小。
    7. 写入临时文件。
    8. 成功后移动为正式文件。
    9. 返回文件元数据。
    """

    # ----------------------------------------
    # 1. 处理原始文件名
    # ----------------------------------------

    original_filename = _normalize_filename(
        upload_file.filename
    )

    # ----------------------------------------
    # 2. 获取 MIME 类型
    # ----------------------------------------

    content_type = (
        upload_file.content_type
        or "application/octet-stream"
    ).strip()

    if not content_type:
        content_type = "application/octet-stream"

    if len(content_type) > 100:

        raise ValueError(
            "Content type exceeds 100 characters"
        )

    # ----------------------------------------
    # 3. 创建存储目录
    # ----------------------------------------

    STORAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ----------------------------------------
    # 4. 生成随机存储标识
    # ----------------------------------------

    storage_key = uuid4().hex

    destination = _get_storage_path(
        storage_key
    )

    # 临时文件
    temporary_path = (
        STORAGE_DIR / f".{storage_key}.tmp"
    )

    file_size = 0

    moved_to_destination = False

    try:

        # ------------------------------------
        # 5. 分块保存文件
        # ------------------------------------

        with temporary_path.open("xb") as output_file:

            while True:

                chunk = await upload_file.read(
                    CHUNK_SIZE
                )

                if not chunk:
                    break

                file_size += len(chunk)

                # --------------------------------
                # 检查文件大小
                # --------------------------------

                if file_size > MAX_FILE_SIZE:

                    raise UploadFileTooLargeError(
                        f"File exceeds the "
                        f"{MAX_FILE_SIZE}-byte limit"
                    )

                output_file.write(chunk)

        # ------------------------------------
        # 6. 检查空文件
        # ------------------------------------

        if file_size == 0:

            raise EmptyUploadFileError(
                "Uploaded file must not be empty"
            )

        # ------------------------------------
        # 7. 临时文件移动为正式文件
        # ------------------------------------

        os.replace(
            temporary_path,
            destination,
        )

        moved_to_destination = True

        # ------------------------------------
        # 8. 返回文件元数据
        # ------------------------------------

        return StoredFile(
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            file_size=file_size,
        )

    except Exception:

        # 任意步骤失败，清理临时文件
        temporary_path.unlink(
            missing_ok=True
        )

        if moved_to_destination:

            destination.unlink(
                missing_ok=True
            )

        raise


# ============================================
# 7. 删除服务器文件
# ============================================

def delete_stored_file(
    storage_key: str,
) -> bool:
    """
    根据 storage_key 删除实际文件。

    文件不存在时返回 False。
    """

    path = _get_storage_path(
        storage_key
    )

    try:

        path.unlink()

    except FileNotFoundError:

        return False

    return True


# ============================================
# 8. 检查文件是否存在
# ============================================

def stored_file_exists(
    storage_key: str,
) -> bool:
    """
    检查服务器文件是否存在。
    """

    return _get_storage_path(
        storage_key
    ).is_file()


# ============================================
# 9. 获取已存在的附件文件路径
# ============================================

def get_stored_file_path(
    storage_key: str,
) -> Path:
    """
    获取服务器上已经存在的附件文件路径。

    1. 验证 storage_key 格式。
    2. 检查文件是否存在。
    3. 验证文件仍然位于附件存储目录中。
    4. 防止通过符号链接访问存储目录以外的文件。
    """

    path = _get_storage_path(
        storage_key
    )

    # 文件必须真实存在
    resolved_path = path.resolve(
        strict=True
    )

    # 获取附件存储目录的真实路径
    storage_root = STORAGE_DIR.resolve()

    # 防止路径逃逸
    if (
        resolved_path.parent != storage_root
        or not resolved_path.is_file()
    ):

        raise InvalidStorageKeyError(
            "Invalid attachment storage path"
        )

    return resolved_path


# ============================================
# 9. 获取安全的文件路径
# ============================================

def get_stored_file_path(
    storage_key: str,
) -> Path:
    """
    获取已经存在的附件文件路径。

    1. 验证 storage_key。
    2. 解析实际文件路径。
    3. 确保文件位于附件存储目录内。
    4. 确保文件真实存在。
    """

    path = _get_storage_path(storage_key)

    resolved_root = STORAGE_DIR.resolve(
        strict=True
    )

    resolved_path = path.resolve(
        strict=True
    )

    try:

        resolved_path.relative_to(
            resolved_root
        )

    except ValueError as exc:

        raise InvalidStorageKeyError(
            "Invalid storage path"
        ) from exc

    if not resolved_path.is_file():

        raise FileNotFoundError(
            "Stored file not found"
        )

    return resolved_path