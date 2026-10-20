"""Fixed owner driver-only compile/link/run sequence; import performs no native action."""
import time

SHARED_SECONDS = 540
TAIL_SECONDS = 60
MIB = 1024**2


def need(ok, code):
    if not ok:
        raise ValueError(code)


def phase_limits(name):
    total, fsize, tree, log = {
        'compile': (120, 64, 256, 4),
        'link': (60, 64, 256, 4),
        'run': (300, 16, 2048, 1),
    }[name]
    return {'total_seconds': total, 'work_seconds': total - 15,
            'cpu_seconds': total - 15, 'as_bytes': 6 * 1024**3,
            'fsize_bytes': fsize * MIB, 'tree_bytes': tree * MIB,
            'log_bytes': log * MIB, 'sample_rows': total + 2,
            'file_count': 32768, 'entry_count': 65536}


def complete_window(stop, name):
    need(time.monotonic() + phase_limits(name)['total_seconds'] <= stop - TAIL_SECONDS,
         'INCOMPLETE_PHASE_WINDOW')


def natural_success(record, usage):
    need(type(record['exit_code']) is int and record['exit_code'] == 0 and
         record['status'] == 'PASS' and record['cleanup_confirmed'] is True and
         record['timed_out'] is False and record['reaped'] is True and
         record['parent_exception'] is None and record['group_state'] == 'absent' and
         record['exit_observed_while_unreaped']['code'] == 1 and
         record['exit_observed_while_unreaped']['status'] == 0,
         'NATURAL_EXIT_OR_CLEANUP')
    rss = usage['maxrss_kib_cumulative_parent_children']
    need(type(rss) is int and 0 <= rss <= 6 * 1024**2, 'CUMULATIVE_RSS_6G')


def observe_log(support, folder, cap):
    path = folder / 'native.log'
    if not path.exists():
        return {'present': False, 'complete_file_identity': None}
    return {'present': True, 'complete_file_identity': support.identity(path, cap),
            'whole_file_not_tail': True, 'capsule_or_progress_parsed': False}


def sequence(s, support, base, work, commands, env, stop, owner,
             preflight, after_phase, result, admit):
    need(set(commands) == {'compile', 'link', 'run'}, 'EXACT_THREE_COMMANDS')
    for name in ('compile', 'link', 'run'):
        complete_window(stop, name)
        preflight()
        result.setdefault('admissions', []).append({'phase': name, **admit()})
        complete_window(stop, name)
        stage = {'name': name, 'record': None, 'usage': None, 'diagnostics': {},
                 'log_observation': None, 'secondary_failure_types': []}
        failure = None
        folder = work / 'phases' / name
        try:
            record, raw, usage = s.run_phase(support, base, 'owner_local_' + name,
                commands[name], work, folder, env, phase_limits(name), stop, owner,
                stage['diagnostics'])
            stage['record'], stage['usage'] = record, usage
            natural_success(record, usage)
            preflight()
            after_phase(name, raw, stage)
            preflight()
        except BaseException as error:
            failure = error
        finally:
            try:
                need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_WORK_WINDOW')
                stage['log_observation'] = observe_log(support, folder, phase_limits(name)['log_bytes'])
                need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_WORK_WINDOW')
            except BaseException as error:
                stage['secondary_failure_types'].append(type(error).__name__ if type(error).__name__ in
                    ('ValueError', 'TimeoutError', 'OSError', 'FileNotFoundError', 'PermissionError') else 'OTHER')
                if failure is None:
                    failure = error
            result['stages'].append(stage)
        if failure is not None:
            raise failure
    return result


def finish(support, work, result, failure, stop, save, timer):
    """Bound report time and preserve the first exception, including native failures."""
    report_stop = min(stop, time.monotonic() + TAIL_SECONDS)
    try:
        timer(max(0.001, report_stop - time.monotonic()))
        need(time.monotonic() < report_stop, 'INCOMPLETE_REPORT_WINDOW')
        result['report_stop'] = report_stop
        if work is not None:
            save(work / 'EXECUTION_RESULT.json', result)
        need(time.monotonic() < report_stop, 'INCOMPLETE_REPORT_WINDOW')
    except BaseException as error:
        if failure is None:
            failure = error
    return failure
