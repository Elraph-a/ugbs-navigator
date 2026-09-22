"""A room belongs to the procedure it was published for, not to the office."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import router


def service(service_id: str) -> dict:
    services, _ = router.load_catalogue()
    return services[service_id]


def test_transcript_answers_name_room_d2():
    office = router.office_for_service(service("transcript_standard"))
    assert office["name"] == "Academic Affairs Directorate"
    assert "Room D2" in office["location"]


def test_other_academic_affairs_answers_do_not():
    # Deferment is owned by the same office, but Room D2 is only published for
    # transcripts. Sending a deferment enquiry there is the bug this guards.
    office = router.office_for_service(service("deferment"))
    assert office["name"] == "Academic Affairs Directorate"
    assert not office.get("location")


def test_office_record_itself_is_not_mutated():
    router.office_for_service(service("transcript_standard"))
    _, offices = router.load_catalogue()
    assert not offices["aad"].get("location")
