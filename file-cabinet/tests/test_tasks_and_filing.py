from filecabinet import Label
from filecabinet.temp import SCENARIOS, SimulatedNetwork

from .conftest import build


def test_checks_before_answering():
    cab = build(network=SCENARIOS["dns"])
    answer = cab.ask("Websites won't load but the wifi says connected")
    assert answer.label is Label.CHECKED
    assert "DNS failure" in answer.text
    assert any("DNS failing" in e for e in answer.evidence)


def test_a_suggestion_that_contradicts_the_checks_is_not_claimed():
    # The words sound like DNS trouble, but the router doesn't answer.
    cab = build(network=SCENARIOS["no-router"])
    answer = cab.ask("Websites won't load")
    assert answer.label is Label.CHECKED
    assert "Can't reach the router" in answer.text
    assert "DNS failure" not in answer.text


def test_unchecked_ideas_are_labelled_assumptions():
    blind = SimulatedNetwork(up=None, gateway_ip=None, gateway_ok=None, internet_ok=None, dns_ok=None)
    answer = build(network=blind).ask("Websites won't load, apps work by address")
    assert answer.label is Label.THINK
    assert "assumption" in answer.text


def test_filing_after_a_task_and_generalizing_to_a_new_case():
    cab = build(network=SCENARIOS["dns"])
    cab.ask("Websites won't load but the wifi says connected")
    report = cab.finish_task("Restarted the router after its nightly update")
    assert any("router address: drawer 1" in line for line in report)
    assert any("drawer 2 (new reference" in line for line in report)
    assert any("raw check output: discarded" in line for line in report)
    assert cab.active is None

    # A different-sounding problem with the same shape matches the filed reference.
    answer = cab.ask("Pages are not loading in my browser tonight")
    assert answer.label is Label.CHECKED
    assert "Restarted the router after its nightly update" in answer.text


def test_the_same_lesson_strengthens_a_reference_instead_of_copying_it():
    cab = build(network=SCENARIOS["dns"])
    cab.ask("Websites won't load")
    cab.finish_task("Restarted the router after its nightly update")
    count = len(cab.store.cases())
    cab.ask("Pages are not loading again")
    report = cab.finish_task("Restarted the router after the update")
    assert len(cab.store.cases()) == count
    assert any("strengthened reference" in line for line in report)
    assert any("router address: already in drawer 1" in line for line in report)


def test_unseen_pattern_is_reported_without_guessing():
    odd = SimulatedNetwork(up=True, gateway_ok=False, internet_ok=True, dns_ok=True)
    cab = build(network=odd, seed_cases=False)
    answer = cab.ask("The internet is slow")
    assert answer.label is Label.CHECKED
    assert "haven't seen this exact pattern" in answer.text


def test_done_without_a_task(cab):
    assert cab.finish_task("anything") == ["No task is open."]
