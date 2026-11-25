
from __future__ import annotations

import codecs
import logging
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.ticket_attachment import TicketAttachment
from app.models.user import User

from app.services.file_storage_service import (
    CHUNK_SIZE,
    MAX_FILE_SIZE,
    EmptyUploadFileError,
    InvalidStorageKeyError,
    UploadFileTooLargeError,
    delete_stored_file,
    get_stored_file_path,
    save_upload_file,
)

from pathlib import Path
logger = logging.getLogger(__name__)


# ============================================
# 1. 自定义业务异常
# ============================================

class AttachmentTicketNotFoundError(Exception):
    """工单不存在或当前用户无权访问。"""


class AttachmentPermissionDeniedError(Exception):
    """当前用户没有附件操作权限。"""


class AttachmentTicketClosedError(Exception):
    """已关闭工单不允许新增附件。"""


class InvalidAttachmentTypeError(Exception):
    """附件类型不允许。"""


class InvalidAttachmentContentError(Exception):
    """附件实际内容不符合文件类型要求。"""


class AttachmentNotFoundError(Exception):
    """附件不存在或已经删除。"""


class AttachmentDeleteForbiddenError(Exception):
    """当前用户无权删除该附件。"""

class AttachmentStorageFileNotFoundError(Exception):
    """附件数据库记录存在，但服务器上的实际文件不存在。"""

# ============================================
# 2. 文件类型白名单
# ============================================

_ALLOWED_FILE_TYPES = {
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".pdf": ("application/pdf", b"%PDF-"),
    ".txt": ("text/plain", None),
}

_GENERIC_MIME_TYPE = "application/octet-stream"


# ============================================
# 3. 获取用户角色
# ============================================

def _get_role_code(
    current_user: User,
) -> str | None:

    role = current_user.role

    if role is None or not isinstance(role.code, str):
        return None

    return role.code.strip().upper()


# ============================================
# 4. 获取当前用户有权访问的工单
# ============================================

def _get_accessible_ticket(
    db: Session,
    ticket_id: int,
    current_user: User,
    *,
    for_update: bool = False,
) -> Ticket:

    role_code = _get_role_code(current_user)

    conditions = [
        Ticket.id == ticket_id,
        Ticket.deleted_at.is_(None),
    ]

    if role_code == "ADMIN":

        pass

    elif role_code == "AGENT":

        conditions.append(
            Ticket.assignee_id == current_user.id
        )

    elif role_code == "USER":

        conditions.append(
            Ticket.creator_id == current_user.id
        )

    else:

        raise AttachmentPermissionDeniedError(
            "Unsupported role for attachment operation"
        )

    statement = select(Ticket).where(*conditions)

    if for_update:
        statement = statement.with_for_update()

    ticket = db.scalar(statement)

    if ticket is None:

        raise AttachmentTicketNotFoundError(
            "Ticket not found"
        )

    return ticket


# ============================================
# 5. 验证上传文件
# ============================================

async def _validate_upload_file(
    upload_file: UploadFile,
) -> str:
    """
    验证文件扩展名、MIME 类型和实际内容。

    TXT:
        UTF-8 编码，不允许 NUL 字节。

    PNG/JPG/PDF:
        检查文件签名。

    返回规范化 MIME 类型。
    """

    filename = upload_file.filename

    if not isinstance(filename, str) or not filename.strip():

        raise InvalidAttachmentTypeError(
            "A filename is required"
        )

    # 兼容 Windows 和 Linux 路径
    basename = (
        filename
        .replace("\\", "/")
        .rsplit("/", 1)[-1]
        .strip()
    )

    extension = (
        f".{basename.rsplit('.', 1)[-1].lower()}"
        if "." in basename
        else ""
    )

    file_type = _ALLOWED_FILE_TYPES.get(extension)

    if file_type is None:

        raise InvalidAttachmentTypeError(
            "Only PNG, JPG, JPEG, PDF and TXT files are allowed"
        )

    expected_mime, expected_signature = file_type

    declared_mime = (
        upload_file.content_type or _GENERIC_MIME_TYPE
    ).split(";", 1)[0].strip().lower()

    if declared_mime not in {
        expected_mime,
        _GENERIC_MIME_TYPE,
    }:

        raise InvalidAttachmentTypeError(
            "Content-Type does not match the filename extension"
        )

    await upload_file.seek(0)

    file_size = 0
    prefix = bytearray()

    decoder = (
        codecs.getincrementaldecoder("utf-8-sig")("strict")
        if extension == ".txt"
        else None
    )

    try:

        while True:

            chunk = await upload_file.read(CHUNK_SIZE)

            if not chunk:
                break

            file_size += len(chunk)

            if file_size > MAX_FILE_SIZE:

                raise UploadFileTooLargeError(
                    f"File exceeds the {MAX_FILE_SIZE}-byte limit"
                )

            if len(prefix) < 16:

                remaining = 16 - len(prefix)

                prefix.extend(
                    chunk[:remaining]
                )

            if decoder is not None:

                if b"\x00" in chunk:

                    raise InvalidAttachmentContentError(
                        "TXT files must not contain NUL bytes"
                    )

                decoder.decode(
                    chunk,
                    final=False,
                )

        if file_size == 0:

            raise EmptyUploadFileError(
                "Uploaded file must not be empty"
            )

        if decoder is not None:

            decoder.decode(
                b"",
                final=True,
            )

        elif not prefix.startswith(expected_signature):

            raise InvalidAttachmentContentError(
                "File signature does not match the declared file type"
            )

    except UnicodeDecodeError as exc:

        raise InvalidAttachmentContentError(
            "TXT files must use UTF-8 encoding"
        ) from exc

    finally:

        await upload_file.seek(0)

    return expected_mime


# ============================================
# 6. 文件清理辅助函数
# ============================================

def _cleanup_stored_file(
    storage_key: str,
) -> None:
    """
    尽力清理磁盘文件。

    清理失败不能覆盖原始数据库异常。
    """

    try:

        deleted = delete_stored_file(
            storage_key
        )

        if not deleted:

            logger.warning(
                "Stored attachment file was not found: %s",
                storage_key,
            )

    except Exception:

        logger.exception(
            "Failed to clean up attachment file: %s",
            storage_key,
        )


# ============================================
# 7. 创建工单附件
# ============================================

async def create_ticket_attachment(
    db: Session,
    ticket_id: int,
    upload_file: UploadFile,
    current_user: User,
) -> TicketAttachment:
    """
    创建工单附件。

    1. 验证工单访问权限。
    2. 锁定工单。
    3. 检查工单状态。
    4. 验证上传文件。
    5. 保存实际文件。
    6. 创建数据库附件记录。
    7. 提交事务。
    8. 数据库失败时清理磁盘文件。
    """

    try:

        ticket = _get_accessible_ticket(
            db=db,
            ticket_id=ticket_id,
            current_user=current_user,
            for_update=True,
        )

        if ticket.status == "CLOSED":

            raise AttachmentTicketClosedError(
                "Closed ticket does not accept new attachments"
            )

        content_type = await _validate_upload_file(
            upload_file
        )

        stored_file = await save_upload_file(
            upload_file
        )

    except Exception:

        # 释放工单行锁
        db.rollback()

        raise

    # ----------------------------------------
    # 保存附件数据库记录
    # ----------------------------------------

    try:

        attachment = TicketAttachment(
            ticket_id=ticket.id,
            uploader_id=current_user.id,

            original_filename=stored_file.original_filename,
            storage_key=stored_file.storage_key,

            content_type=content_type,
            file_size=stored_file.file_size,
        )

        db.add(attachment)

        db.flush()

        db.commit()

    except Exception:

        db.rollback()

        # 数据库失败，清理已经保存的实际文件
        _cleanup_stored_file(
            stored_file.storage_key
        )

        raise

    # 数据库提交成功后再刷新对象
    db.refresh(attachment)

    return attachment


# ============================================
# 8. 查询工单附件
# ============================================

def list_ticket_attachments(
    db: Session,
    current_user: User,
    ticket_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[TicketAttachment], int]:
    """
    查询当前用户有权访问的工单附件。

    1. 检查分页参数。
    2. 验证工单访问权限。
    3. 排除逻辑删除的附件。
    4. 统计附件数量。
    5. 执行分页查询。
    """

    if page < 1 or not 1 <= page_size <= 100:

        raise ValueError(
            "Invalid pagination parameters"
        )

    ticket = _get_accessible_ticket(
        db=db,
        ticket_id=ticket_id,
        current_user=current_user,
    )

    conditions = [
        TicketAttachment.ticket_id == ticket.id,
        TicketAttachment.deleted_at.is_(None),
    ]

    # 统计附件数量
    total = db.scalar(
        select(
            func.count(TicketAttachment.id)
        ).where(*conditions)
    ) or 0

    # 分页查询
    statement = (
        select(TicketAttachment)
        .where(*conditions)
        .order_by(
            TicketAttachment.created_at.asc(),
            TicketAttachment.id.asc(),
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
    )

    attachments = db.scalars(
        statement
    ).all()

    return list(attachments), int(total)


# ============================================
# 10. 下载工单附件
# ============================================

def get_ticket_attachment_for_download(
    db: Session,
    attachment_id: int,
    current_user: User,
) -> tuple[TicketAttachment, Path]:
    """
    获取当前用户有权下载的附件及其实际文件路径。

    1. 查询未逻辑删除的附件并锁定记录。
    2. 验证用户是否有权访问所属工单。
    3. 验证 storage_key。
    4. 验证磁盘文件存在且位于附件存储目录内。

    成功时保留当前事务，使附件行锁在响应发送期间继续有效。
    失败时回滚，立即释放数据库锁。
    """

    try:

        # ------------------------------------
        # 1. 验证附件 ID
        # ------------------------------------

        if attachment_id <= 0:

            raise ValueError(
                "Invalid attachment ID"
            )

        # ------------------------------------
        # 2. 查询并锁定附件
        # ------------------------------------

        attachment = db.scalar(
            select(TicketAttachment)
            .where(
                TicketAttachment.id == attachment_id,
                TicketAttachment.deleted_at.is_(None),
            )
            .with_for_update()
        )

        if attachment is None:

            raise AttachmentNotFoundError(
                "Attachment not found"
            )

        # ------------------------------------
        # 3. 验证工单访问权限
        # ------------------------------------

        _get_accessible_ticket(
            db=db,
            ticket_id=attachment.ticket_id,
            current_user=current_user,
        )

        # ------------------------------------
        # 4. 获取安全的文件路径
        # ------------------------------------

        try:

            file_path = get_stored_file_path(
                attachment.storage_key
            )

        except (
            FileNotFoundError,
            InvalidStorageKeyError,
        ) as exc:

            logger.error(
                "Attachment file is unavailable: attachment_id=%s",
                attachment.id,
            )

            raise AttachmentStorageFileNotFoundError(
                "Attachment file is unavailable"
            ) from exc

        # ------------------------------------
        # 5. 返回附件和文件路径
        # ------------------------------------

        return attachment, file_path

    except Exception:

        db.rollback()

        raise

# ============================================
# 9. 删除工单附件
# ============================================

def delete_ticket_attachment(
    db: Session,
    attachment_id: int,
    current_user: User,
) -> None:
    """
    删除工单附件。

    1. 查询附件。
    2. 验证工单访问权限。
    3. 验证删除权限。
    4. 逻辑删除数据库记录。
    5. 提交数据库事务。
    6. 删除磁盘文件。
    """

    if attachment_id <= 0:

        raise ValueError(
            "Invalid attachment ID"
        )

    try:

        attachment = db.scalar(
            select(TicketAttachment)
            .where(
                TicketAttachment.id == attachment_id,
                TicketAttachment.deleted_at.is_(None),
            )
            .with_for_update()
        )

        if attachment is None:

            raise AttachmentNotFoundError(
                "Attachment not found"
            )

        _get_accessible_ticket(
            db=db,
            ticket_id=attachment.ticket_id,
            current_user=current_user,
            for_update=True,
        )

        role_code = _get_role_code(current_user)

        # ADMIN 可以删除所有附件
        # 其他角色只能删除自己上传的附件
        if (
            role_code != "ADMIN"
            and attachment.uploader_id != current_user.id
        ):

            raise AttachmentDeleteForbiddenError(
                "You can only delete attachments uploaded by yourself"
            )

        storage_key = attachment.storage_key

        # 逻辑删除
        attachment.deleted_at = datetime.now(
            timezone.utc
        ).replace(tzinfo=None)

        db.flush()

        db.commit()

    except Exception:

        db.rollback()

        raise

    # 数据库提交成功后，再删除磁盘文件
    _cleanup_stored_file(
        storage_key
    )
