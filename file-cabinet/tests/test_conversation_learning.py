from filecabinet import Label
from filecabinet.teach import extract_event, extract_fact, second_person

from .conftest import build


def test_learns_a_fact_from_conversation(cab):
    filed = cab.ask("my brother's name is leo")
    assert filed.label is Label.FILED
    answer = cab.ask("what's my brother's name")
    assert answer.label is Label.KNOW and "leo" in answer.text


def test_newer_fact_replaces_older(cab):
    filed = cab.ask("my sister's name is mia")
    assert "replaces" in filed.text and "Maya" in filed.text
    assert "mia" in cab.ask("what's my sister's name").text


def test_first_person_becomes_second_person():
    assert second_person("i was born in chicago") == "You were born in chicago."
    assert extract_fact("my favorite color is green").fact == "Your favorite color is green."
    assert extract_fact("i really like the color blue").subject == "likes"
    assert extract_fact("hello there") is None


def test_learns_where_i_was_born(cab):
    cab.ask("i was born in chicago")
    answer = cab.ask("where was i born")
    assert answer.label is Label.KNOW and "chicago" in answer.text


def test_logs_an_event_from_conversation(cab):
    filed = cab.ask("we just saw a blue bike at the library")
    assert filed.label is Label.FILED
    episode = cab.store.episodes()[-1]
    assert episode.place == "Library"
    answer = cab.ask("what color was the bike we saw")
    assert answer.label is Label.REMEMBER and "blue" in answer.text


def test_event_people_and_place():
    ev = extract_event("just had lunch with sam at the noodle bar")
    assert ev.people == "Sam" and ev.place == "Noodle Bar" and ev.activity == "lunch"


def test_who_was_there_after_an_event(cab):
    cab.ask("just had lunch with sam at the noodle bar")
    answer = cab.ask("who did we have lunch with")
    assert answer.label is Label.REMEMBER and "Sam" in answer.text


def test_past_tense_question_steps_down_to_the_log():
    cab = build()
    answer = cab.ask("what was the truck at the market selling")
    assert answer.label is Label.REMEMBER and "peaches" in answer.text
