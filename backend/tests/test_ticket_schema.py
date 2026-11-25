
import pytest

from pydantic import ValidationError

from app.schemas.ticket import TicketCreate


def test_ticket_create_normalizes_data():

    data = TicketCreate(
        title="  网络故障  ",
        description="  无法连接公司网络  ",
        priority=" high ",
        category_id=10,
    )

    assert data.title == "网络故障"
    assert data.description == "无法连接公司网络"
    assert data.priority == "HIGH"


def test_ticket_create_default_priority():

    data = TicketCreate(
        title="网络故障",
        description="无法连接网络",
        category_id=10,
    )

    assert data.priority == "NORMAL"


def test_ticket_create_max_title_length():

    data = TicketCreate(
        title="x" * 200,
        description="网络故障",
        category_id=10,
    )

    assert len(data.title) == 200


@pytest.mark.parametrize(
    "payload",
    [
        {
            "title": "   ",
            "description": "网络故障",
            "category_id": 10,
        },
        {
            "title": "网络故障",
            "description": "   ",
            "category_id": 10,
        },
        {
            "title": "网络故障",
            "description": "网络故障",
            "category_id": 0,
        },
        {
            "title": "网络故障",
            "description": "网络故障",
            "category_id": -1,
        },
        {
            "title": "网络故障",
            "description": "网络故障",
            "category_id": "10",
        },
        {
            "title": "网络故障",
            "description": "网络故障",
            "priority": "URGENT",
            "category_id": 10,
        },
        {
            "title": "x" * 201,
            "description": "网络故障",
            "category_id": 10,
        },
        {
            "title": "网络故障",
            "description": "网络故障",
            "category_id": 10,
            "creator_id": 5,
        },
        {
            "title": "网络故障",
            "description": "网络故障",
            "category_id": 10,
            "ticket_no": "FD-001",
        },
    ],
)
def test_ticket_create_rejects_invalid_data(payload):

    with pytest.raises(ValidationError):
        TicketCreate(**payload)
