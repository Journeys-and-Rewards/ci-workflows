#!/usr/bin/env python3
"""project_state_conformance.py (t11) — does a project_state.md conform to the canonical template?

AC3's rules live here as pure functions over text so they can be tested one at a time without a
repository, a wizard, or a provider.

THE TEMPLATE IS THE SINGLE SOURCE OF TRUTH. Nothing in this module hard-codes a section name, a
section order, or the wording of a standard section: every expectation is derived from
docs/templates/project-state.template.md at the moment of the check. Editing the template therefore
changes the contract, which is the whole point — a copy of the rules here would drift from it.

WHY SECTIONS ARE KEYED BY ORDINAL. The template's headings carry a trailing tag
("## 5. Conventions (locked) — [STANDARD — KEEP VERBATIM; …]") and a project may legitimately word
the rest of a PROJECT heading differently. The ordinal ("1", "2a", "5b") is the part that is
genuinely structural, so presence and ORDER are judged on ordinals while verbatim-ness is judged on
body text. Keying on full heading text would reject conforming projects for cosmetic reasons.

STANDARD BLOCKS INSIDE PROJECT SECTIONS. Section 3 is tagged PROJECT — the roadmap is per-project —
but it embeds two paragraphs tagged "[STANDARD — KEEP VERBATIM]" (the status legend and the
"This registry IS the board" rules). Those are the engine's own contract with the board publisher, so
they are checked verbatim even though their containing section is not.
"""
import io
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
# "## 5b. Working protocol" -> "5b" ; "# Project — Project State" -> None
ORDINAL_RE = re.compile(r'^(\d+[a-z]?)\.\s')
STANDARD_MARK = '[STANDARD'
PROJECT_MARK = '[PROJECT'
VERBATIM_MARK = 'KEEP VERBATIM'
# An unfilled placeholder is a non-conforming write, not a style issue.
#
# The template does NOT limit itself to named {{LIKE_THIS}} slots — most of its placeholders are
# free prose ({{why it is better than the obvious alternatives}}), and a few nest
# ({{; domain {{domain}}}}). An ALL-CAPS-only pattern matched four of them and silently passed the
# other ~60, so a barely-filled file would have validated. Detection is therefore on the BRACES:
# any surviving {{ is an unwritten slot, whatever is inside it.
PLACEHOLDER_RE = re.compile(r'\{\{[^{}]{0,400}\}\}')
PLACEHOLDER_OPEN = '{{'


def placeholder_examples(text, limit=3):
    """Up to `limit` short, readable samples of what is still unfilled."""
    found, seen = [], set()
    for m in PLACEHOLDER_RE.finditer(text):
        sample = re.sub(r'\s+', ' ', m.group(0)).strip()
        if len(sample) > 56:
            sample = sample[:53] + '…}}'
        if sample not in seen:
            seen.add(sample)
            found.append(sample)
        if len(found) >= limit:
            break
    if not found and PLACEHOLDER_OPEN in text:
        found.append('{{…}}')
    return found


def strip_instruction_block(text):
    """Remove the template's leading instruction comment block, if present.

    The block is the template's own authoring guide and must not survive into a generated file
    (AC2). It is identified positionally — the comment that opens the file — so a legitimate HTML
    comment later in the document is never mistaken for it.
    """
    lines = text.split('\n')
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not lines[i].lstrip().startswith('<!--'):
        return text, False
    for j in range(i, len(lines)):
        if '-->' in lines[j]:
            return '\n'.join(lines[:i] + lines[j + 1:]), True
    return text, False


def has_instruction_block(text):
    _, found = strip_instruction_block(text)
    return found


def sections(text):
    """Ordered [(ordinal, level, heading, body_lines)] for every heading in the document.

    The pre-heading preamble is returned under ordinal None so a caller can still see the title.
    """
    out = []
    cur = {'ordinal': None, 'level': 0, 'heading': '', 'body': []}
    for line in text.split('\n'):
        m = HEADING_RE.match(line)
        if m:
            out.append(cur)
            title = m.group(2).strip()
            lvl = len(m.group(1))
            cur = {'ordinal': section_key(lvl, title),
                   'level': lvl, 'heading': title, 'body': []}
        else:
            cur['body'].append(line)
    out.append(cur)
    return [s for s in out if s['heading'] or s['body']]


def _label(heading):
    """The heading as a human would name it: the tag removed, and no dangling bracket left behind.

    "## 2a. Business / monetization model (OPTIONAL — [PROJECT])" would otherwise be reported as
    "2a. Business / monetization model (OPTIONAL", which reads like the message itself is truncated.
    """
    bare = heading.split(' — [')[0].split('— [')[0].strip()
    if bare.count('(') > bare.count(')'):
        bare = bare[:bare.rindex('(')].strip()
    return bare.rstrip(' —-')


def section_key(level, heading):
    """The stable identity of a section.

    Ordinals ("1", "2a", "5b") are the structural part of a numbered heading. But the template also
    carries UNNUMBERED subsections that are tagged STANDARD — "### Engine-standard lessons" — and
    keying on ordinals alone silently skipped them, so a generated file could drop or reword the
    engine's own lessons block and still pass. Those are keyed by their heading text with the tag
    stripped, which is exactly the part the template fixes.

    The level-1 document title is excluded: it legitimately names the project and is therefore never
    a required section (it is still scanned for unfilled placeholders).
    """
    if level <= 1:
        return None
    om = ORDINAL_RE.match(heading)
    if om:
        return om.group(1)
    bare = heading.split(' — [')[0].split('— [')[0]
    bare = re.sub(r'\s+', ' ', bare).strip().lower().rstrip('.')
    return ('h:' + bare) if bare else None


def _tag_of(heading):
    if STANDARD_MARK in heading:
        return 'STANDARD'
    if PROJECT_MARK in heading:
        return 'PROJECT'
    return None


def _norm(lines):
    """Compare on content, not on incidental whitespace.

    Trailing spaces and a different number of blank lines at the edges are not a rewording of a
    standard section, and treating them as one would make the check a nuisance that projects learn
    to route around. Interior blank lines ARE preserved: they are paragraph structure.
    """
    out = [l.rstrip() for l in lines]
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return '\n'.join(out)


def standard_blocks(body_lines):
    """Paragraphs inside a section that carry the verbatim marker.

    A "block" is a run of non-blank lines, which is exactly how these paragraphs are written in the
    template. Returning them separately lets a PROJECT section be freely authored around content
    the engine still owns.
    """
    blocks, cur = [], []
    for line in list(body_lines) + ['']:
        if line.strip():
            cur.append(line)
        else:
            if cur and any(STANDARD_MARK in l and VERBATIM_MARK in l for l in cur):
                blocks.append(_norm(cur))
            cur = []
    return blocks


def template_contract(template_text):
    """What the template requires: ordered ordinals, standard bodies, and embedded standard blocks."""
    body, _ = strip_instruction_block(template_text)
    secs = sections(body)
    order, std_bodies, std_blocks, labels = [], {}, {}, {}
    for s in secs:
        if s['ordinal'] is None:
            continue
        order.append(s['ordinal'])
        labels[s['ordinal']] = _label(s['heading'])
        if _tag_of(s['heading']) == 'STANDARD':
            std_bodies[s['ordinal']] = _norm(s['body'])
        blocks = standard_blocks(s['body'])
        if blocks:
            std_blocks[s['ordinal']] = blocks
    return {'order': order, 'standard_bodies': std_bodies, 'standard_blocks': std_blocks,
            'labels': labels}


def is_template_derived(text):
    """Does this file descend from the canonical template?

    A generated file keeps the template's tagged headings, so the markers are present. A state file
    written before the template existed carries none of them. This decides WHICH rules can honestly
    be applied to a given file, and it is deliberately a property of the FILE rather than a flag a
    caller can pass: there is no switch that turns conformance off.
    """
    return (STANDARD_MARK in text) or (PROJECT_MARK in text)


def check(state_text, template_text, legacy=False):
    """Plain-English violations. Empty list means the file conforms.

    `legacy` restricts the check to the rules that are TRUE of a pre-template file — structure,
    ordering, placeholders, and the instruction block. It never relaxes those, and the caller is
    required to say out loud that it is in use.
    """
    contract = template_contract(template_text)
    problems = []

    if has_instruction_block(state_text):
        problems.append(
            "the template's instruction comment block is still at the top of the file; "
            "it is authoring guidance for whoever fills the template in and must be deleted "
            "from the generated project state")

    secs = sections(state_text)
    present = [s['ordinal'] for s in secs if s['ordinal'] is not None]
    by_ord = {}
    for s in secs:
        if s['ordinal'] is not None:
            by_ord.setdefault(s['ordinal'], s)

    # In legacy mode the contract is narrowed to the NUMBERED sections. The template also fixes
    # unnumbered tagged subsections ("### Engine-standard lessons"), but a state file written before
    # the template existed never had them, and demanding one is template conformance rather than a
    # structural guarantee — which is precisely what legacy mode exists to separate.
    required = [o for o in contract['order'] if not (legacy and o.startswith('h:'))]
    label = lambda o: contract['labels'].get(o, o)

    missing = [o for o in required if o not in by_ord]
    for o in missing:
        problems.append(
            "the section \"%s\" is missing; the project state must carry every section the "
            "template defines, in the template's order" % label(o))

    # Order is judged only over the sections both documents have, so a missing section is reported
    # once as missing rather than again as a reordering.
    shared_expected = [o for o in required if o in by_ord]
    shared_actual = [o for o in present if o in required]
    seen, deduped = set(), []
    for o in shared_actual:
        if o not in seen:
            seen.add(o)
            deduped.append(o)
    if deduped != shared_expected:
        problems.append(
            "the sections are out of order: the template's order is %s but this file has %s; "
            "reordering sections breaks every tool that reads the state file by position"
            % (' → '.join(label(o) for o in shared_expected),
                 ' → '.join(label(o) for o in deduped)))

    # The status line above section 1 ("_Last updated: … **NEXT: tN**_") is PROJECT content with no
    # heading of its own, so keying placeholders by section would have skipped it entirely — and an
    # unfilled NEXT marker there is exactly the kind of half-written file this rule exists to stop.
    for sec in secs:
        if sec['ordinal'] is not None or sec['level'] > 1:
            continue
        blob = '\n'.join(sec['body']) + '\n' + sec['heading']
        if PLACEHOLDER_OPEN in blob:
            problems.append(
                "the document's opening status line still contains unfilled placeholder(s) — %s; it "
                "must name the current milestone and the single NEXT ticket"
                % ', '.join(placeholder_examples(blob)))

    for o in [k for k in required if k in by_ord] + [k for k in by_ord if k not in required]:
        sec = by_ord[o]
        blob = '\n'.join(sec['body']) + '\n' + sec['heading']
        if PLACEHOLDER_OPEN in blob:
            ex = placeholder_examples(blob)
            problems.append(
                "the section \"%s\" still contains unfilled placeholder(s) — %s; every PROJECT "
                "section must be written for this specific project at genesis"
                % (label(o), ', '.join(ex)))

    if legacy:
        return problems

    for o, want in sorted(contract['standard_bodies'].items()):
        if o not in by_ord:
            continue
        got = _norm(by_ord[o]['body'])
        if got != want:
            problems.append(
                "the section \"%s\" is a STANDARD section and has been reworded; it must match "
                "the template exactly, because the engine relies on its wording. Restore it from "
                "docs/templates/project-state.template.md" % label(o))

    for o, blocks in sorted(contract['standard_blocks'].items()):
        if o not in by_ord:
            continue
        got = standard_blocks(by_ord[o]['body'])
        for want in blocks:
            if want not in got:
                first = want.split('\n')[0][:70]
                problems.append(
                    "the section \"%s\" is missing or has reworded a STANDARD block that must be "
                    "kept verbatim (\"%s…\"); the surrounding section is yours to write, that "
                    "block is not" % (label(o), first))
    return problems


def main(argv):
    if len(argv) < 3:
        sys.stderr.write('usage: project_state_conformance.py <state.md> <template.md> [--legacy]\n')
        return 2
    legacy = '--legacy' in argv[3:]
    state = io.open(argv[1], encoding='utf-8').read()
    template = io.open(argv[2], encoding='utf-8').read()
    problems = check(state, template, legacy=legacy)
    for p in problems:
        sys.stdout.write('%s\n' % p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
