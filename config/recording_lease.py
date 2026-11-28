"""Journal the qualified ALSA headroom for the lifetime of one WayDAW session."""
import json
import os
from pathlib import Path
import tempfile

ORIGINAL = 0
WORKING = 1024


class EndpointRetired(RuntimeError):
    """The original bound endpoint no longer exists."""


class MutationRefused(RuntimeError):
    """The bound operation reported refusal before submitting a write."""


def publish(path, record, *, initial=False):
    # Persist the recovery record before a write can change the endpoint.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.audio-lease-', mode='w',
                                     delete=False) as stream:
        candidate = Path(stream.name)
        try:
            json.dump(record, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            if initial:
                os.link(candidate, path)
            else:
                candidate.replace(path)
        finally:
            candidate.unlink(missing_ok=True)


def read_receipt(path, owner):
    try:
        record = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    if (record.get('version') != 1 or record.get('owner') != list(owner)
            or record.get('phase') not in ('applying', 'applied', 'restoring')
            or record.get('original') != ORIGINAL or record.get('working') != WORKING):
        raise RuntimeError('Audio lease receipt does not match the owned session')
    return record


def apply(path, owner, endpoint, connection):
    """Acquire the validated value. A raised uncertain write retains its journal."""
    if path.exists():
        raise RuntimeError('There is an outstanding audio lease')
    if connection.read(endpoint) != ORIGINAL:
        raise MutationRefused('The device started with a different headroom')
    record = {'version': 1, 'owner': list(owner), 'endpoint': endpoint,
              'original': ORIGINAL, 'working': WORKING, 'phase': 'applying'}
    publish(path, record, initial=True)
    try:
        connection.change(endpoint, ORIGINAL, WORKING, require_suspended=True)
    except (MutationRefused, EndpointRetired):
        path.unlink()
        raise
    # A successful bound change includes readback on the same connection.
    record['phase'] = 'applied'
    publish(path, record)


def restore(path, owner, connection):
    """Release the same endpoint or retain a receipt when a write is ambiguous."""
    record = read_receipt(path, owner)
    if record is None:
        return 'already released'
    endpoint, phase = record['endpoint'], record['phase']
    try:
        current = connection.read(endpoint)
        if phase == 'restoring':
            if current != ORIGINAL:
                raise RuntimeError('Previous restoration remains unconfirmed')
            outcome = 'restored'
        elif current == WORKING:
            record['phase'] = 'restoring'
            publish(path, record)
            try:
                connection.change(endpoint, WORKING, ORIGINAL, require_suspended=False)
            except MutationRefused:
                # Known refusal means no restoration request can arrive later.
                record['phase'] = phase
                publish(path, record)
                raise
            outcome = 'restored'
        elif phase == 'applying':
            raise RuntimeError('Previous activation remains unconfirmed')
        elif current == ORIGINAL:
            outcome = 'already restored'
        else:
            outcome = 'external value preserved'
    except EndpointRetired:
        outcome = 'endpoint retired'
    path.unlink()
    return outcome
