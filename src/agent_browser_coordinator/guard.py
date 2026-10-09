"""Fail-closed callback wrapper for a single cooperative UI invocation."""

from .coordinator import Conflict, label


def run_guarded(coordinator, *, actor, token, action, begin_request, end_request, call, kind='work'):
    """Run `call` only after a fresh matching begin permit.

    The callback must return ``(terminated, value)``. An exception or an
    uncertain termination leaves the action active for diagnosis; it is never
    automatically ended. A known failed tool invocation may return
    ``(True, failure_record)`` because it definitely terminated.
    """
    for value in (actor, token, action, begin_request, end_request): label(value)
    if kind not in ('observation','work'): raise Conflict('Guard kind must be observation or work')
    if not callable(call): raise Conflict('A callable tool adapter is required')
    permit = coordinator.execute('begin', begin_request, actor, token=token, action=action, kind=kind)
    owner = permit.get('owner') or {}
    active = permit.get('active') or {}
    if (permit.get('ok') is not True or permit.get('replay') is not False or
            permit.get('op') != 'begin' or permit.get('actor') != actor or
            owner.get('actor') != actor or owner.get('token') != token or
            active.get('actor') != actor or active.get('id') != action):
        raise Conflict('No fresh matching begin permit; tool callback was not run')
    terminated, value = call()
    if terminated is not True:
        raise Conflict('Tool termination unconfirmed; preserve active action')
    result = coordinator.execute('end', end_request, actor, token=token, action=action)
    if result.get('ok') is not True or result.get('op') != 'end' or result.get('actor') != actor:
        raise Conflict('Matching end not confirmed; inspect coordinator state')
    return value
