import os
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from utils import logger

_TASKS = {}
_TASK_LOCK = threading.Lock()
_MAX_WORKERS = int(os.environ.get('PERSON_INFO_TASK_WORKERS', '1'))
_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, _MAX_WORKERS))


def _update_task(task_id, **updates):
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task:
            task.update(updates)


def _create_result_context(person_info, results, report_files):
    return {
        'person_info': person_info,
        'results': results,
        'report_files': {key: Path(value).name for key, value in report_files.items()},
    }


def _run_search_task(task_id, payload):
    try:
        _update_task(task_id, status='running')

        from main import PersonInfoSearcher

        searcher = PersonInfoSearcher()
        kind = payload.get('kind')

        if kind == 'resume_file':
            filepath = payload['filepath']
            person_info = searcher.parse_resume_file(filepath)
            name_override = (payload.get('name_override') or '').strip()

            if not person_info.get('name') and name_override:
                person_info['name'] = name_override

            if not person_info.get('name'):
                raise ValueError('无法从简历中识别姓名，请手动输入')

            person_info['source'] = payload.get('source', 'file_upload')
            person_info['filename'] = payload.get('filename', Path(filepath).name)
        else:
            person_info = payload['person_info']

        results = searcher.search(person_info)
        report_files = searcher.generate_report(person_info, results, formats=['excel', 'word'])
        result_context = _create_result_context(person_info, results, report_files)

        _update_task(task_id, status='done', **result_context)
    except Exception as exc:
        logger.exception('后台搜索任务失败')
        _update_task(task_id, status='error', error=str(exc), traceback=traceback.format_exc())
    finally:
        if payload.get('filepath'):
            try:
                Path(payload['filepath']).unlink(missing_ok=True)
            except OSError:
                logger.warning('清理上传文件失败: %s', payload['filepath'])


def create_search_task(payload):
    task_id = uuid.uuid4().hex
    with _TASK_LOCK:
        _TASKS[task_id] = {
            'status': 'pending',
            'payload': payload,
        }

    _EXECUTOR.submit(_run_search_task, task_id, payload)
    return task_id


def get_task(task_id):
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return None
        return dict(task)