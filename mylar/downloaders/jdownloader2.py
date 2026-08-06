#  This file is part of Mylar.
#
#  Provides a lightweight wrapper around the JDownloader2 remote API so
#  GetComics links can be handed off for downloading.

import json
import os
from collections import defaultdict

import requests

import mylar
from mylar import logger


class JDownloaderError(RuntimeError):
    """JD2 did not return a response that Mylar can trust."""


class JDownloader2(object):
    LINKGRABBER_ENDPOINT = 'linkgrabberv2/addLinks'
    DOWNLOADS_ENDPOINT = 'downloadsV2/queryLinks'
    PACKAGES_ENDPOINT = 'downloadsV2/queryPackages'

    COMPLETE_STATUSES = {
        'DONE', 'EXTRACTION OK', 'FINISHED', 'FINISHED(MIRROR)', '[SHA256] CRC OK'}
    ACTIVE_EXTRACTION = {'IDLE', 'RUNNING', 'QUEUED'}
    FAILED_STATUSES = {
        'ERROR', 'ERROR_CRC', 'ERROR_NOT_ENOUGH_SPACE', 'ERROR_PW',
        'ERROR_FILE_NOT_FOUND', 'FAILED', 'FILE_NOT_FOUND', 'NOT_ENOUGH_SPACE'}

    def __init__(self, base_url=None, timeout=30, session=None):
        self.base_url = (base_url or mylar.CONFIG.JD2_URL or '').rstrip('/')
        if not self.base_url:
            raise ValueError('JD2 URL is not configured')
        self.timeout = timeout
        self.session = session or requests.Session()
        self.destination = mylar.CONFIG.JD2_DEST_DIR or None

    def _request(self, endpoint, parameter, query):
        url = '%s/%s' % (self.base_url, endpoint)
        params = {parameter: json.dumps(query, separators=(',', ':'))}
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as err:
            raise JDownloaderError(
                'JD2 request failed (url=%s params=%s): %s' % (url, params, err)
            ) from err

        if isinstance(payload, dict) and payload.get('type') and (
            payload.get('src') or 'data' in payload
        ):
            raise JDownloaderError(
                'JD2 returned %s from %s: %s'
                % (payload.get('type'), url, payload.get('data'))
            )
        return payload.get('data', payload) if isinstance(payload, dict) else payload

    def _query_list(self, endpoint, query):
        result = []
        while True:
            page_query = dict(query, startAt=len(result), maxResults=1000)
            page = self._request(endpoint, 'queryParams', page_query)
            if not isinstance(page, list):
                raise JDownloaderError('JD2 returned an invalid list from %s' % endpoint)
            result.extend(page)
            if len(page) < page_query['maxResults']:
                return result

    @staticmethod
    def normalize_ids(values):
        if values is None:
            return []
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except ValueError:
                values = [values]
        if not isinstance(values, (list, tuple, set)):
            values = [values]

        result = []
        for value in values:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value not in result:
                result.append(value)
        return result

    @classmethod
    def serialize_ids(cls, values):
        values = cls.normalize_ids(values)
        if not values:
            return None
        if len(values) == 1:
            return str(values[0])
        return json.dumps(values)

    def submit(self, links, package_name):
        """Send every mirror to JD2 and return its crawler job IDs."""
        groups = defaultdict(list)
        for url, priority in (links or {}).items():
            if url:
                groups[priority or 'DEFAULT'].append(url)
        if not groups:
            return {'status': False, 'jobid': None, 'error': 'No links supplied'}

        job_ids = []
        errors = []
        for priority, urls in groups.items():
            query = {
                'assignJobID': True,
                'autostart': True,
                'links': '\n'.join(urls),
                'packageName': package_name,
                'priority': priority,
            }
            if self.destination:
                query['destinationFolder'] = os.path.join(
                    self.destination, package_name
                )
            try:
                payload = self._request(self.LINKGRABBER_ENDPOINT, 'query', query)
            except JDownloaderError as err:
                errors.append(str(err))
                continue
            if isinstance(payload, dict):
                job_ids.extend(
                    self.normalize_ids(payload.get('id') or payload.get('jobID'))
                )

        stored_ids = self.serialize_ids(job_ids)
        if not stored_ids:
            error = '; '.join(errors) or 'JD2 returned no job id'
            logger.error('[JD2] Failed to submit %s: %s', package_name, error)
            return {'status': False, 'jobid': None, 'error': error}
        if errors:
            logger.warn(
                '[JD2] %s was accepted with %s mirror submission error(s).',
                package_name, len(errors),
            )
        return {'status': True, 'jobid': stored_ids}

    def _packages(self, package_ids):
        package_ids = self.normalize_ids(package_ids)
        if not package_ids:
            return []
        query = dict.fromkeys(('saveTo', 'uuid'), True)
        query['packageUUIDs'] = package_ids
        return self._query_list(
            self.PACKAGES_ENDPOINT,
            query,
        )

    def _links(self, job_ids):
        job_ids = self.normalize_ids(job_ids)
        if not job_ids:
            return []
        query = dict.fromkeys(
            ('advancedStatus', 'extractionStatus', 'finished', 'jobUUID', 'name',
             'packageUUID', 'skipped', 'status'),
            True,
        )
        query['jobUUIDs'] = job_ids
        return self._query_list(self.DOWNLOADS_ENDPOINT, query)

    @classmethod
    def _advanced_id(cls, item, name):
        status = (item.get('advancedStatus') or {}).get(name) or {}
        return str(status.get('id') or '').upper()

    @classmethod
    def _extraction_id(cls, item):
        return cls._advanced_id(item, 'ExtractionStatus') or str(
            item.get('extractionStatus') or ''
        ).upper()

    @classmethod
    def _state(cls, item):
        raw_status = str(item.get('status') or '').upper()
        status = raw_status.replace(' ', '_')
        extraction = cls._extraction_id(item)
        final_state = cls._advanced_id(item, 'FinalLinkState')
        failed = (
            item.get('skipped') is True
            or final_state.startswith('FAILED')
            or final_state in {'OFFLINE', 'PLUGIN_DEFECT'}
            or status in cls.FAILED_STATUSES
            or status.startswith('ERROR:')
        )
        if extraction in cls.FAILED_STATUSES:
            return 'failed'
        if extraction in cls.ACTIVE_EXTRACTION:
            return 'failed' if failed else 'queued'
        if final_state:
            if final_state.startswith('FINISHED'):
                return 'completed'
            return 'failed' if failed else 'queued'
        if (
            item.get('finished') is True
            or extraction == 'SUCCESSFUL'
            or raw_status in cls.COMPLETE_STATUSES
        ):
            return 'completed'
        return 'failed' if failed else 'queued'

    @classmethod
    def _job_state(cls, links):
        states = [(cls._state(link), link) for link in links]
        for wanted in ('completed', 'queued'):
            for state, link in states:
                if state == wanted:
                    return state, link
        if links:
            return 'failed', links[0]
        return 'queued', None

    def status_many(self, jobs):
        """Return only the durable states Mylar needs to act on."""
        record_jobs = {
            record_id: self.normalize_ids(job_ids)
            for record_id, job_ids in jobs.items()
        }
        job_ids = {
            job_id for values in record_jobs.values() for job_id in values
        }

        links_by_job = defaultdict(list)
        package_ids = set()
        for link in self._links(job_ids):
            link_job_ids = self.normalize_ids(link.get('jobUUID'))
            if not link_job_ids or link_job_ids[0] not in job_ids:
                continue
            links_by_job[link_job_ids[0]].append(link)
            package_ids.update(self.normalize_ids(link.get('packageUUID')))

        packages = {}
        for package in self._packages(package_ids):
            ids = self.normalize_ids(package.get('uuid'))
            if ids:
                packages[ids[0]] = package

        result = {}
        for record_id, job_ids in record_jobs.items():
            candidates = [
                self._job_state(links_by_job.get(job_id, []))
                for job_id in job_ids
            ]

            completed = next(
                (item for item in candidates if item[0] == 'completed'), None
            )
            if completed:
                state = 'completed'
                chosen = completed
            else:
                queued = next(
                    (item for item in candidates if item[0] == 'queued'), None
                )
                if queued:
                    state = 'queued'
                    chosen = queued
                elif candidates:
                    state = 'failed'
                    chosen = candidates[0]
                else:
                    state = 'queued'
                    chosen = ('queued', None)
            selected_package_ids = self.normalize_ids(
                chosen[1].get('packageUUID') if chosen[1] else None
            )
            package = (
                packages.get(selected_package_ids[0])
                if selected_package_ids else None
            )
            result[record_id] = dict(
                state=state,
                data=chosen[1],
                save_to=package.get('saveTo') if package else None,
            )
        return result
