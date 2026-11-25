
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User

from app.schemas.ticket_attachment import (
    TicketAttachmentRead,
    TicketAttachmentListResponse,
)

from app.services.file_storage_service import (
    EmptyUploadFileError,
    UploadFileTooLargeError,
)

from app.services.attachment_service import (
    AttachmentDeleteForbiddenError,
    AttachmentNotFoundError,
    AttachmentPermissionDeniedError,
    AttachmentTicketClosedError,
    AttachmentTicketNotFoundError,
    InvalidAttachmentContentError,
    InvalidAttachmentTypeError,
    create_ticket_attachment,
    delete_ticket_attachment,
    list_ticket_attachments,
    AttachmentStorageFileNotFoundError,
    get_ticket_attachment_for_download,
)
from fastapi.responses import FileResponse

# ============================================
# FlowDesk Attachment Router
# ============================================

router = APIRouter(
    tags=["Attachments"],
)


# ============================================
# 1. 上传工单附件
# ============================================

@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=TicketAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="上传工单附件",
)
async def create_ticket_attachment_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    upload_file: Annotated[
        UploadFile,
        File(
            description="PNG、JPG、JPEG、PDF 或 TXT，最大 10MB"
        ),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> TicketAttachmentRead:

    try:

        return await create_ticket_attachment(
            db=db,
            ticket_id=ticket_id,
            upload_file=upload_file,
            current_user=current_user,
        )

    except AttachmentTicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except AttachmentPermissionDeniedError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to upload attachments",
        ) from exc

    except AttachmentTicketClosedError as exc:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed ticket does not accept new attachments",
        ) from exc

    except UploadFileTooLargeError as exc:

        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Attachment exceeds the 10MB limit",
        ) from exc

    except InvalidAttachmentTypeError as exc:

        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc

    except (
        EmptyUploadFileError,
        InvalidAttachmentContentError,
    ) as exc:

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc


# ============================================
# 2. 查询工单附件
# ============================================

@router.get(
    "/tickets/{ticket_id}/attachments",
    response_model=TicketAttachmentListResponse,
    summary="查询工单附件",
)
def list_ticket_attachments_endpoint(

    ticket_id: Annotated[
        int,
        Path(gt=0),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,

    page_size: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,

) -> TicketAttachmentListResponse:

    try:

        attachments, total = list_ticket_attachments(
            db=db,
            current_user=current_user,
            ticket_id=ticket_id,
            page=page,
            page_size=page_size,
        )

    except AttachmentTicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except AttachmentPermissionDeniedError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to view these attachments",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc

    # 计算总页数
    total_pages = (
        total + page_size - 1
    ) // page_size

    return TicketAttachmentListResponse(
        items=attachments,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )





# ============================================
# 3. 删除工单附件
# ============================================

@router.delete(
    "/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除工单附件",
)
def delete_ticket_attachment_endpoint(

    attachment_id: Annotated[
        int,
        Path(gt=0),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> None:

    try:

        delete_ticket_attachment(
            db=db,
            attachment_id=attachment_id,
            current_user=current_user,
        )

    except AttachmentNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        ) from exc

    except AttachmentTicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except (
        AttachmentPermissionDeniedError,
        AttachmentDeleteForbiddenError,
    ) as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to delete this attachment",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc


# ============================================
# 4. 下载工单附件
# ============================================

@router.get(
    "/attachments/{attachment_id}/download",
    response_class=FileResponse,
    summary="下载工单附件",
)
def download_ticket_attachment_endpoint(

    attachment_id: Annotated[
        int,
        Path(gt=0),
    ],

    db: Annotated[
        Session,
        Depends(get_db),
    ],

    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],

) -> FileResponse:

    """
    下载工单附件。

    1. 验证附件 ID。
    2. 获取当前登录用户。
    3. 验证附件访问权限。
    4. 验证附件是否存在。
    5. 获取服务器内部文件路径。
    6. 返回文件下载响应。
    """

    try:

        attachment, file_path = (
            get_ticket_attachment_for_download(
                db=db,
                attachment_id=attachment_id,
                current_user=current_user,
            )
        )

        return FileResponse(
            path=file_path,
            media_type=attachment.content_type,
            filename=attachment.original_filename,
            content_disposition_type="attachment",
            headers={
                "X-Content-Type-Options": "nosniff",
            },
        )

    except AttachmentNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        ) from exc

    except AttachmentTicketNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from exc

    except AttachmentPermissionDeniedError as exc:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to download this attachment",
        ) from exc

    except AttachmentStorageFileNotFoundError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        ) from exc

    except SQLAlchemyError as exc:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed",
        ) from exc
