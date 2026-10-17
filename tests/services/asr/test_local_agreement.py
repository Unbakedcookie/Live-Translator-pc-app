"""T044 — LocalAgreement-n on scripted hypotheses (Tier A, expectations written by hand)."""

import pytest

from livetranslator.services.asr.base import Word
from livetranslator.services.asr.local_agreement import AgreementState, LocalAgreement


def hyp(*items: tuple[str, float, float]) -> list[Word]:
    return [Word(text, start, end) for text, start, end in items]


W_I = (" I", 0.0, 0.2)
THINK = (" think", 0.2, 0.5)
WE = (" we", 0.5, 0.7)
SHOULD = (" should", 0.7, 1.0)
GO = (" go.", 1.0, 1.3)


def test_first_hypothesis_commits_nothing():
    la = LocalAgreement()
    assert la.update(hyp(W_I, THINK)) == AgreementState("", "I think", "")


def test_agreement_commits_common_prefix():
    la = LocalAgreement()
    la.update(hyp(W_I, THINK))
    assert la.update(hyp(W_I, THINK, WE)) == AgreementState("I think", "we", "I think")
    # Next hypothesis re-decodes from the start; committed words are skipped by timestamp.
    assert la.update(hyp(W_I, THINK, WE, SHOULD, GO)) == AgreementState(
        "I think we", "should go.", "we"
    )


def test_revised_word_stays_tentative():
    la = LocalAgreement()
    la.update(hyp((" the", 0.0, 0.2), (" cat", 0.2, 0.5), (" sad", 0.5, 0.8)))
    state = la.update(
        hyp((" the", 0.0, 0.2), (" cat", 0.2, 0.5), (" sat", 0.5, 0.8), (" on", 0.8, 1.0))
    )
    assert state == AgreementState("the cat", "sat on", "the cat")


def test_punctuation_and_case_differences_still_agree():
    la = LocalAgreement()
    la.update(hyp((" Hello,", 0.0, 0.4)))
    state = la.update(hyp((" hello", 0.0, 0.4), (" there.", 0.4, 0.8)))
    assert state.committed == "hello"  # the newest hypothesis's spelling is kept
    assert state.tentative == "there."


def test_committed_words_are_never_revoked():
    la = LocalAgreement()
    la.update(hyp(W_I, THINK))
    la.update(hyp(W_I, THINK, WE))
    # The decoder now hears "I thought" at the start, but "I think" is already committed.
    state = la.update(hyp((" I", 0.0, 0.2), (" thought", 0.2, 0.5), WE, SHOULD))
    assert state.committed.startswith("I think")


def test_finalize_commits_the_rest_and_resets_history():
    la = LocalAgreement()
    la.update(hyp(W_I, THINK))
    la.update(hyp(W_I, THINK, WE))
    final = la.finalize(hyp(W_I, THINK, WE, SHOULD, GO))
    assert final == AgreementState("I think we should go.", "", "we should go.")
    la.reset()
    assert la.update(hyp(W_I)) == AgreementState("", "I", "")


def test_cjk_words_join_without_spaces():
    la = LocalAgreement()
    first = hyp(("こんにちは", 0.0, 0.6), ("、", 0.6, 0.7), ("世界", 0.7, 1.1))
    la.update(first)
    state = la.update([*first, Word("です", 1.1, 1.4)])
    # The bare "、" is punctuation-only, so it is not a word for agreement purposes.
    assert state.committed == "こんにちは世界"
    assert state.tentative == "です"


def test_n3_needs_three_agreeing_hypotheses():
    la = LocalAgreement(n=3)
    la.update(hyp(W_I))
    assert la.update(hyp(W_I, THINK)).committed == ""
    assert la.update(hyp(W_I, THINK, WE)).committed == "I"
    assert la.update(hyp(W_I, THINK, WE)).committed == "I think"
    with pytest.raises(ValueError):
        LocalAgreement(n=1)
