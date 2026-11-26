from filecabinet import Label


def test_surface_opinion_from_drawer1(cab):
    answer = cab.ask("Do you think pizza is cool?")
    assert answer.label is Label.KNOW
    assert answer.drawers_opened == ("drawer1",)


def test_disliked_item(cab):
    assert cab.ask("Is brown a pretty color?").text.startswith("Not really")


def test_cannot_see_what_is_shown(cab):
    assert cab.ask("Is this funny?").label is Label.NOT_SURE


def test_deep_goes_through_drawer3(cab):
    answer = cab.ask("I lost my best friend last month")
    assert answer.label is Label.CORE
    assert answer.drawers_opened == ("drawer3",)
    assert "988" not in answer.text


def test_crisis_always_adds_help(cab):
    answer = cab.ask("I want to die")
    assert answer.label is Label.CORE
    assert "988" in answer.text


def test_unclear_depth_is_treated_as_deep(cab):
    assert cab.ask("I feel weird today").label is Label.CORE


def test_good_news_is_met_warmly(cab):
    assert "good to hear" in cab.ask("I'm so excited about my new job").text


def test_deep_recall_finds_a_core_memory(cab):
    pid = cab.store.propose_core("Grandpa taught you to fish at Lake Tahoe the summer before he died.")
    cab.core.approve(pid, "owner")
    answer = cab.ask("Do you remember the summer before grandpa died?")
    assert answer.label is Label.REMEMBER
    assert "Lake Tahoe" in answer.text
