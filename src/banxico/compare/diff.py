"""Diff de dois comunicados: parágrafo -> frase -> palavra."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..text.sentences import split_sentences
from .align import align, similarity, words

PARA_THRESHOLD = 0.30        # similaridade mínima para parear parágrafos
SECTION_BONUS = 0.15         # mesma seção (exceto "other") ajuda a parear parágrafos reescritos
SENT_THRESHOLD = 0.45        # abaixo disso, frase é tratada como removida + nova (não como edição)

_TOKEN = re.compile(r"\S+\s*")


@dataclass
class Op:
    kind: str                # equal | insert | delete
    text: str


@dataclass
class SentenceDiff:
    status: str              # unchanged | modified | added | removed
    ops: list[Op]


@dataclass
class ParagraphDiff:
    status: str              # unchanged | modified | added | removed
    section: str | None
    old: str | None
    new: str | None
    sentences: list[SentenceDiff] = field(default_factory=list)
    similarity: float = 0.0


@dataclass
class DocDiff:
    paragraphs: list[ParagraphDiff]
    change_ratio: float      # fração das palavras alteradas (0 = idêntico)
    counts: dict[str, int]   # frases: added / removed / modified / unchanged


def word_ops(old: str, new: str) -> list[Op]:
    """Diff por palavra preservando o espaçamento original."""
    ta, tb = _TOKEN.findall(old), _TOKEN.findall(new)
    sm = SequenceMatcher(None, [t.strip() for t in ta], [t.strip() for t in tb], autojunk=False)
    ops: list[Op] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append(Op("equal", "".join(tb[j1:j2])))
        else:
            if i2 > i1:
                ops.append(Op("delete", "".join(ta[i1:i2])))
            if j2 > j1:
                ops.append(Op("insert", "".join(tb[j1:j2])))
    return ops


def _sentence_diffs(old: str, new: str) -> list[SentenceDiff]:
    sa, sb = split_sentences(old), split_sentences(new)
    pairs = align(sa, sb, lambda i, j: similarity(sa[i], sb[j]), SENT_THRESHOLD)
    out: list[SentenceDiff] = []
    for i, j in pairs:
        if i is not None and j is not None:
            if sa[i].strip() == sb[j].strip():
                out.append(SentenceDiff("unchanged", [Op("equal", sb[j])]))
            else:
                out.append(SentenceDiff("modified", word_ops(sa[i], sb[j])))
        elif i is not None:
            out.append(SentenceDiff("removed", [Op("delete", sa[i])]))
        else:
            out.append(SentenceDiff("added", [Op("insert", sb[j])]))
    return out


def diff_documents(old: list[tuple[str | None, str]], new: list[tuple[str | None, str]]) -> DocDiff:
    """old/new: listas de (section, texto) dos parágrafos, em ordem de leitura."""

    def score(i: int, j: int) -> float:
        s = similarity(old[i][1], new[j][1])
        if old[i][0] == new[j][0] and old[i][0] not in (None, "other"):
            s += SECTION_BONUS
        return s

    paragraphs: list[ParagraphDiff] = []
    for i, j in align(old, new, score, PARA_THRESHOLD):
        if i is not None and j is not None:
            (sec_a, a), (sec_b, b) = old[i], new[j]
            if a.strip() == b.strip():
                paragraphs.append(ParagraphDiff("unchanged", sec_b, a, b,
                                                [SentenceDiff("unchanged", [Op("equal", b)])], 1.0))
            else:
                paragraphs.append(ParagraphDiff("modified", sec_b or sec_a, a, b,
                                                _sentence_diffs(a, b), similarity(a, b)))
        elif i is not None:
            sec, a = old[i]
            paragraphs.append(ParagraphDiff("removed", sec, a, None,
                                            [SentenceDiff("removed", [Op("delete", s)]) for s in split_sentences(a)]))
        else:
            sec, b = new[j]
            paragraphs.append(ParagraphDiff("added", sec, None, b,
                                            [SentenceDiff("added", [Op("insert", s)]) for s in split_sentences(b)]))

    counts = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    for p in paragraphs:
        for s in p.sentences:
            counts[s.status] += 1

    all_old = [w for _, t in old for w in words(t)]
    all_new = [w for _, t in new for w in words(t)]
    ratio = SequenceMatcher(None, all_old, all_new, autojunk=False).ratio() if (all_old or all_new) else 1.0
    return DocDiff(paragraphs, change_ratio=1 - ratio, counts=counts)
