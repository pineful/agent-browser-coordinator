"""Conservative planning hints. This module never starts parallel UI execution."""

from .coordinator import Conflict, label

NON_UI = frozenset({'file-analysis', 'server-generation-wait', 'document-preparation',
                    'review-wait', 'publication-wait'})
SHARED_UI = frozenset({'shared-screen', 'keyboard', 'native-file-chooser', 'modal',
                       'browser-ui', 'unknown'})

def classify_work(kind, *, capability=None):
    """Return a scheduling hint; adapter verification remains the caller's duty.

    A tab_id alone is never evidence of focus, input, or session isolation.
    Unknown names and malformed claims fail closed to exclusive UI.
    """
    if not isinstance(kind, str): kind = 'unknown'
    if kind in NON_UI:
        return {'mode': 'outside-ui', 'parallel_candidate': True,
                'reason': 'No shared UI tool invocation'}
    if kind != 'tab-api' or not isinstance(capability, dict):
        return {'mode': 'exclusive-ui', 'parallel_candidate': False,
                'reason': 'Shared or unverified UI capability'}
    required = {'adapter', 'evidence', 'verified', 'isolated_sessions',
                'isolated_input', 'isolated_focus', 'no_shared_dialogs'}
    if set(capability) != required:
        return {'mode': 'exclusive-ui', 'parallel_candidate': False,
                'reason': 'Incomplete adapter capability evidence'}
    try:
        label(capability['adapter']); label(capability['evidence'])
    except Conflict:
        return {'mode': 'exclusive-ui', 'parallel_candidate': False,
                'reason': 'Invalid adapter capability evidence'}
    if all(capability[k] is True for k in required - {'adapter', 'evidence'}):
        return {'mode': 'parallel-candidate', 'parallel_candidate': True,
                'reason': 'Verified adapter claim; environment test still required'}
    return {'mode': 'exclusive-ui', 'parallel_candidate': False,
            'reason': 'Adapter isolation is unverified'}
