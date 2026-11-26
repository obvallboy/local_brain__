from filecabinet import Label


def test_direct_recall(cab):
    answer = cab.ask("Do you remember where we ate yesterday?")
    assert answer.label is Label.REMEMBER
    assert "Rosa's Tacos" in answer.text


def test_recall_by_cue_rebuilds_the_scene(cab):
    # The car and its color were logged as separate moments, so a direct look fails.
    answer = cab.ask("Do you remember what color the car was that we saw earlier?")
    assert answer.label is Label.REMEMBER
    assert "bright red" in answer.text
    assert "cue: Where were we?" in answer.evidence
    assert any("episode #1" in e for e in answer.evidence)
    assert any("episode #2" in e for e in answer.evidence)


def test_recall_who(cab):
    answer = cab.ask("Who was with us at dinner yesterday?")
    assert answer.label is Label.REMEMBER
    assert "Maya" in answer.text


def test_never_invents_a_memory(cab):
    answer = cab.ask("Do you remember the boat we saw earlier?")
    assert answer.label is Label.DONT_REMEMBER
    assert "boat" in answer.text
    assert "Riverside Park" in answer.text  # it went back through where we were


def test_remembers_the_thing_but_not_the_missing_detail(cab):
    answer = cab.ask("Do you remember what color the truck was earlier?")
    assert answer.label is Label.DONT_REMEMBER
    assert "truck" in answer.text
    assert "don't remember its color" in answer.text


def test_time_window_is_respected(cab):
    # The car was today, not yesterday.
    answer = cab.ask("Do you remember the car we saw yesterday?")
    assert answer.label is Label.DONT_REMEMBER
