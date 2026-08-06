"""Submit GetComics links to JD2 and watch for a final result."""

import datetime
import os
import queue as queue_module
import time

import mylar
from mylar import db, helpers, logger
from mylar.downloaders.jdownloader2 import JDownloader2


POLL_INTERVAL = 10


def _package_name(item, record_id):
    filename = (
        item.get('filename')
        or item.get('tmp_filename')
        or '%s (%s)' % (item.get('series'), item.get('year'))
    )
    filename = helpers.filesafe(filename)
    filename = filename.strip(' .') or 'JD2 download'
    return '%s - %s' % (filename, record_id)


def _set_status(myDB, record_id, status, job_id=None):
    values = {
        'status': status,
        'updated_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    if job_id is not None:
        values['jd2_job_id'] = job_id
    try:
        myDB.upsert('ddl_info', values, {'id': record_id})
        row = myDB.selectone(
            'SELECT status, jd2_job_id FROM ddl_info WHERE id=?', [record_id]
        ).fetchone()
        if row is None or row['status'] != status or (
            job_id is not None and row['jd2_job_id'] != job_id
        ):
            return False
    except Exception as err:
        logger.warn(
            '[JD2-QUEUE] Unable to save %s for record %s: %s', status, record_id, err
        )
        return False
    return True


def _destination(item, status, record_id):
    root = mylar.CONFIG.JD2_DEST_DIR
    if not root:
        return None
    candidate = status.get('save_to') or os.path.join(root, _package_name(item, record_id))
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)
    try:
        root = os.path.realpath(root)
        candidate = os.path.realpath(candidate)
        if candidate == root or os.path.commonpath([root, candidate]) != root:
            return None
    except (OSError, ValueError):
        return None
    return candidate


def _finish(myDB, item, status, record_id):
    if item.get('_pp_queued'):
        return _set_status(myDB, record_id, 'Completed', item.get('jd2_job_id'))

    folder = _destination(item, status, record_id)
    if mylar.CONFIG.POST_PROCESSING is True:
        if not folder:
            logger.warn(
                '[JD2-QUEUE] No usable post-processing path for record %s.',
                record_id,
            )
            return _set_status(
                myDB, record_id, 'Completed', item.get('jd2_job_id')
            )
        data = status.get('data') or {}
        try:
            mylar.PP_QUEUE.put(
                {
                    'nzb_name': data.get('name') or _package_name(item, record_id),
                    'nzb_folder': folder,
                    'failed': False,
                    'issueid': item.get('issueid'),
                    'comicid': item.get('comicid'),
                    'apicall': True,
                    'ddl': True,
                    'download_info': {
                        'provider': 'JD2', 'id': record_id,
                        'job_id': item.get('jd2_job_id')
                    },
                }
            )
        except Exception as err:
            logger.warn('[JD2-QUEUE] Unable to queue post-processing: %s', err)
            return False
        item['_pp_queued'] = True
        logger.info('[JD2-QUEUE] Submitted record %s for post-processing.', record_id)
    return _set_status(myDB, record_id, 'Completed', item.get('jd2_job_id'))


def _fallback(item):
    payload = dict(item)
    payload.pop('jd2_job_id', None)
    payload.pop('jd2_priority_links', None)
    mylar.DDL_QUEUE.put(payload)


def _poll_pending(client, myDB, pending):
    jobs = {record_id: item.get('jd2_job_id') for record_id, item in pending.items()}
    try:
        statuses = client.status_many(jobs)
    except Exception as err:
        logger.warn('[JD2-QUEUE] Poll failed; jobs remain queued: %s', err)
        return

    for record_id, item in list(pending.items()):
        if item.pop('_save_job_id', False) and not _set_status(
            myDB, record_id, 'Queued', item.get('jd2_job_id')
        ):
            item['_save_job_id'] = True
            continue
        status = statuses.get(record_id) or {'state': 'queued'}
        state = status.get('state')
        if state == 'completed':
            saved = _finish(myDB, item, status, record_id)
        elif state == 'failed':
            saved = _set_status(
                myDB,
                record_id,
                'Failed',
                item.get('jd2_job_id'),
            )
            logger.warn('[JD2-QUEUE] Record %s failed in JD2.', record_id)
        else:
            continue
        if saved:
            pending.pop(record_id, None)


def _start_download(client, myDB, item, record_id):
    links = item.get('jd2_priority_links')
    if not links and item.get('link'):
        links = {item['link']: 'DEFAULT'}
    if not links:
        logger.warn(
            '[JD2-QUEUE] Record %s has no JD2 links; using the DDL queue.',
            record_id,
        )
        _fallback(item)
        return False

    package_name = _package_name(item, record_id)
    result = client.submit(links, package_name)
    job_id = result.get('jobid')
    if not job_id:
        logger.warn(
            '[JD2-QUEUE] Submission failed for record %s; using the DDL queue: %s',
            record_id, result.get('error') or 'JD2 returned no job id',
        )
        _fallback(item)
        return False

    item['jd2_job_id'] = job_id
    if not _set_status(myDB, record_id, 'Queued', job_id):
        item['_save_job_id'] = True
        logger.warn('[JD2-QUEUE] Job %s accepted but not yet saved.', job_id)
    return True


def jd2_queue_monitor(queue):
    client = JDownloader2()
    myDB = db.DBConnection()
    pending = {}
    next_poll = time.monotonic() + POLL_INTERVAL

    while True:
        timeout = max(0, next_poll - time.monotonic()) if pending else None
        item = None
        try:
            item = queue.get(timeout=timeout)
        except queue_module.Empty:
            pass

        if item is not None:
            try:
                if item == 'exit':
                    logger.info('[JD2-QUEUE] Cleaning up worker for shutdown')
                    break
                if item == 'startup':
                    try:
                        rows = myDB.select(
                            "SELECT * FROM ddl_info WHERE jd2_job_id IS NOT NULL "
                            "AND status='Queued'"
                        )
                    except Exception as err:
                        logger.warn(
                            '[JD2-QUEUE] Unable to restore queued jobs: %s', err
                        )
                    else:
                        for row in rows or []:
                            restored = dict(row)
                            record_id = restored.get('ID') or restored.get('id')
                            if record_id:
                                restored['id'] = record_id
                                pending[record_id] = restored
                    continue
                if not isinstance(item, dict):
                    logger.warn('[JD2-QUEUE] Ignoring invalid queue item.')
                    continue

                record_id = item.get('ID') or item.get('id')
                if not record_id:
                    logger.warn('[JD2-QUEUE] Ignoring item without a record id.')
                    continue
                if item.get('jd2_job_id') in (0, '0'):
                    monitor = _start_download(client, myDB, item, record_id)
                    if monitor:
                        pending[record_id] = item
                    continue

                if item.get('jd2_job_id'):
                    pending[record_id] = item
            finally:
                try:
                    queue.task_done()
                except (AttributeError, ValueError):
                    pass

        if pending and time.monotonic() >= next_poll:
            _poll_pending(client, myDB, pending)
            next_poll = time.monotonic() + POLL_INTERVAL
