#!/usr/bin/env python3
"""ci_policy.py (t11) — the PUBLIC CI policy checks a generated project runs on its own pull requests.

WHY THIS EXISTS AS A SEPARATE, PURE MODULE. GitHub only runs a workflow that physically lives in the
repository being checked, so the governance checks must be centralised in a PUBLIC reusable-workflow
repository. The engine's own validators cannot go there: their measured transitive closure is 18 files
and ~10,300 lines, and it reaches lib/_common.sh and through it the router policy, role execution,
model identity and the notification channel. Publishing that to centralise a ticket-shape check would
be absurd.

So the rules a USER PROJECT needs are implemented here instead, with NO engine dependency at all —
this module imports io, os, re and sys and nothing else, and it is published verbatim.

THE TWO IMPLEMENTATIONS ARE BOUND BY A CONTRACT, NOT BY GOOD INTENTIONS. A second implementation of a
rule can drift from the first, which is exactly what this codebase avoids elsewhere. The engine
therefore carries an equivalence suite (test-t11-public-ci-policy-equivalence.sh) that runs BOTH the
private validator and this one over the same inputs and asserts identical pass/fail verdicts for every
rule listed in EXPORTED_RULES. If they ever disagree, that suite fails.

WHAT IS DELIBERATELY NOT EXPORTED. The engine's stricter delivery contracts — the comprehensive
testing matrix, the mandatory Database work section, fix-linkage validation, knowledge-base delivery
coverage, history/lifecycle consistency — are ENGINE governance, not user-project policy. They stay
private and are enforced engine-side before every push.
"""
import io
import os
import re
import sys

# The rules this module exports, and against which the equivalence suite holds it.
EXPORTED_RULES = (
    'PS-SECTIONS',     # every section the template defines is present, in the template's order
    'PS-STANDARD',     # [STANDARD — KEEP VERBATIM] sections and blocks match the template exactly
    'PS-PLACEHOLDER',  # no {{…}} slot survives
    'PS-INSTRUCTIONS', # the template's instruction comment block has been removed
    'PS-MEMBERSHIP',   # registry ticket set == docs/tickets specification set, both directions
    'PS-NEXT',         # exactly one ticket is marked **NEXT**
    'TT-SECTIONS',     # a ticket carries the sections its kind requires
    'TT-USER-ACTIONED' # a user-actioned ticket carries no build sections and keeps the escape hatch
)

# ── the ticket template, as published in the ticket standard ────────────────────────────────────
TICKET_SECTIONS = (
    '## Goal',
    '## Background context',
    '## What needs to be done for the code locally',
    '## What I need to do remotely',
    '## Testing',
    '## Doc Update (MANDATORY)',
    '## KB knowledge section (End User)',
    '## KB knowledge section (Internal support team)',
    '## Acceptance Criteria',
    '## Branch Name',
    '## PR title',
    '## PR Summary',
)
USER_ACTIONED_SECTIONS = (
    '## Goal',
    '## Background context',
    '## What you need to do',
    '## How this will be verified',
    '## If you get stuck',
    '## Acceptance Criteria',
)
USER_ACTIONED_FORBIDDEN = (
    '## What needs to be done for the code locally',
    '## Branch Name',
    '## PR title',
    '## PR Summary',
)
USER_ACTIONED_STUCK = 'take a screenshot of exactly where'
TICKET_FILE_RE = re.compile(r'^[tT](\d+)-.*\.md$')
REGISTRY_ROW_RE = re.compile(r'^\|[^|]*\|\s*[tT](\d+)\s*\|')
NEXT_ROW_RE = re.compile(r'^\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*\*\*NEXT\*\*')


def _read(path):
    return io.open(path, encoding='utf-8', errors='replace').read()


# ── project state ───────────────────────────────────────────────────────────────────────────────
def check_project_state(state_path, template_path, tickets_dir):
    """[(rule, message)] — empty means the project state passes every exported rule."""
    out = []
    try:
        state = _read(state_path)
    except Exception as exc:
        return [('PS-SECTIONS', 'the project state could not be read from %s (%s)' % (state_path, exc))]
    try:
        template = _read(template_path)
    except Exception as exc:
        # THE CONTRACT COMES FROM THE CALLER'S OWN REPOSITORY, and only from there. Genesis scaffolds
        # docs/templates/project-state.template.md into every project it creates, so the project owns
        # the contract its state is judged against — the published policy component supplies validation
        # CODE, not Mavenor's protocol documentation.
        #
        # FAIL CLOSED, and say what to do: without the contract there is nothing to compare against,
        # and passing would be the worst possible answer.
        return [('PS-SECTIONS',
                 'this project has no docs/templates/project-state.template.md, so its project state '
                 'cannot be checked against anything. The engine scaffolds that file into every project '
                 'it creates; restore it from your project history, or re-run the engine scaffold. (%s)'
                 % exc.__class__.__name__)]

    # The template contract is derived, never hard-coded — the same module the engine uses.
    conf = _conformance()
    for problem in conf.check(state, template, legacy=not conf.is_template_derived(state)):
        if 'instruction comment block' in problem:
            rule = 'PS-INSTRUCTIONS'
        elif 'placeholder' in problem:
            rule = 'PS-PLACEHOLDER'
        elif 'STANDARD' in problem:
            rule = 'PS-STANDARD'
        else:
            rule = 'PS-SECTIONS'
        out.append((rule, problem))

    reg = set()
    for line in state.split('\n'):
        m = REGISTRY_ROW_RE.match(line)
        if m:
            reg.add('t' + m.group(1))
    specs = set()
    if os.path.isdir(tickets_dir):
        for name in os.listdir(tickets_dir):
            m = TICKET_FILE_RE.match(name)
            if m:
                specs.add('t' + m.group(1))
    for tid in sorted(reg - specs, key=_num):
        out.append(('PS-MEMBERSHIP',
                    '%s has a registry row but no specification in %s/; the roadmap and the '
                    'specifications must describe the same tickets' % (tid, tickets_dir)))
    for tid in sorted(specs - reg, key=_num):
        out.append(('PS-MEMBERSHIP',
                    '%s has a specification in %s/ but no registry row; an unregistered ticket is '
                    'invisible to the engine and its board card would be archived on the next '
                    'reconcile' % (tid, tickets_dir)))

    n_next = sum(1 for line in state.split('\n') if NEXT_ROW_RE.match(line))
    if n_next == 0:
        out.append(('PS-NEXT', 'no ticket is marked **NEXT**; there is nothing to build next'))
    elif n_next != 1:
        out.append(('PS-NEXT', '%d tickets are marked **NEXT**; exactly one ticket may be next'
                    % n_next))
    return out


def _num(tid):
    return int(tid[1:])


def _conformance():
    """The pure conformance checker, which ships beside this file in the public package."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import project_state_conformance
    return project_state_conformance


# ── ticket specifications ───────────────────────────────────────────────────────────────────────
def is_user_actioned(text):
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return False
    for line in lines[1:]:
        if line.strip() == '---':
            return False
        if re.match(r'^ticket_kind:\s*user-actioned\s*$', line):
            return True
    return False


def check_ticket(path):
    """[(rule, message)] for one ticket specification."""
    out = []
    try:
        text = _read(path)
    except Exception as exc:
        return [('TT-SECTIONS', '%s could not be read (%s)' % (path, exc))]
    name = os.path.basename(path)
    if is_user_actioned(text):
        for sec in USER_ACTIONED_SECTIONS:
            if not re.search(r'^%s' % re.escape(sec), text, re.M):
                out.append(('TT-SECTIONS', "%s: missing required section heading '%s'" % (name, sec)))
        for sec in USER_ACTIONED_FORBIDDEN:
            if re.search(r'^%s' % re.escape(sec), text, re.M):
                out.append(('TT-USER-ACTIONED',
                            "%s: a user-actioned ticket must not carry '%s' — there is no branch, no "
                            "PR and no code" % (name, sec)))
        if USER_ACTIONED_STUCK not in text:
            out.append(('TT-USER-ACTIONED',
                        "%s: a user-actioned ticket must carry the mandatory '## If you get stuck' "
                        "note verbatim" % name))
        return out
    for sec in TICKET_SECTIONS:
        if not re.search(r'^%s' % re.escape(sec), text, re.M):
            out.append(('TT-SECTIONS', "%s: missing required section heading '%s'" % (name, sec)))
    return out


def check_tickets(tickets_dir):
    out = []
    if not os.path.isdir(tickets_dir):
        return out
    for name in sorted(os.listdir(tickets_dir)):
        if TICKET_FILE_RE.match(name):
            out.extend(check_ticket(os.path.join(tickets_dir, name)))
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────────
def main(argv):
    root = '.'
    only = None
    i = 1
    while i < len(argv):
        if argv[i] == '--root' and i + 1 < len(argv):
            root = argv[i + 1]; i += 2
        elif argv[i] == '--only' and i + 1 < len(argv):
            only = argv[i + 1]; i += 2
        elif argv[i] == '--list-rules':
            for r in EXPORTED_RULES:
                sys.stdout.write('%s\n' % r)
            return 0
        else:
            sys.stderr.write('usage: ci_policy.py [--root DIR] [--only project-state|tickets] '
                             '[--list-rules]\n')
            return 2
    state = os.path.join(root, 'docs', 'project_state.md')
    template = os.path.join(root, 'docs', 'templates', 'project-state.template.md')
    tickets = os.path.join(root, 'docs', 'tickets')

    problems = []
    if only in (None, 'project-state'):
        problems.extend(check_project_state(state, template, tickets))
    if only in (None, 'tickets'):
        problems.extend(check_tickets(tickets))

    if not problems:
        sys.stdout.write('ci-policy: the project satisfies every public governance rule\n')
        return 0
    sys.stdout.write('ci-policy: the project does NOT satisfy the public governance rules\n\n')
    for rule, msg in problems:
        sys.stdout.write('  [%s] %s\n' % (rule, msg))
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
