
from sqlalchemy.orm import configure_mappers

from app.db.base import Base

from app.models import (
    Role,
    User,
    Category,
    Ticket,
    TicketComment,
    TicketHistory,
)


def test_all_models_are_registered():

    configure_mappers()

    expected = {
        "roles",
        "users",
        "categories",
        "tickets",
        "ticket_comments",
        "ticket_histories",
        "ticket_attachments",
    }

    assert set(Base.metadata.tables.keys()) == expected


def test_ticket_relationships():

    configure_mappers()

    assert Ticket.category.property.back_populates == "tickets"

    assert Ticket.comments.property.back_populates == "ticket"

    assert Ticket.histories.property.back_populates == "ticket"


def test_ticket_constraints():

    constraints = {
        item.name
        for item in Ticket.__table__.constraints
        if item.name
    }

    expected = {
        "uk_tickets_ticket_no",
        "fk_tickets_creator",
        "fk_tickets_assignee",
        "fk_tickets_category",
        "chk_tickets_status",
        "chk_tickets_priority",
        "chk_tickets_assignee",
    }

    assert expected.issubset(constraints)


def test_ticket_indexes():

    indexes = {
        item.name
        for item in Ticket.__table__.indexes
    }

    expected = {
        "idx_tickets_creator_deleted_created",
        "idx_tickets_assignee_deleted_status_created",
        "idx_tickets_category_id",
        "idx_tickets_deleted_status_created",
    }

    assert expected.issubset(indexes)


def test_history_json_uses_sql_null():

    assert (
        TicketHistory.__table__.c.old_value.type.none_as_null
        is True
    )

    assert (
        TicketHistory.__table__.c.new_value.type.none_as_null
        is True
    )
