"""Local War Room HTTP server (loopback read + human dispatch API)."""

from cascade.war_room.serialize import (
    board_view_from_index,
    dispatch_result_to_dict,
    event_to_dict,
    work_doc_to_dict,
    work_meta_to_dict,
)
from cascade.war_room.server import (
    WarRoomHTTPServer,
    WarRoomRequestHandler,
    assert_loopback_host,
    serve,
)

__all__ = [
    "WarRoomHTTPServer",
    "WarRoomRequestHandler",
    "assert_loopback_host",
    "board_view_from_index",
    "dispatch_result_to_dict",
    "event_to_dict",
    "serve",
    "work_doc_to_dict",
    "work_meta_to_dict",
]
