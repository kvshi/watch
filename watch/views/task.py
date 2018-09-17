from flask import render_template, session
from watch import app, task_pool, lock
from watch.utils.decorate_view import *
from watch.utils.oracle import execute, get_tab_columns, ping
from watch.utils.parse_args import dlm_str_to_list, upper_values, get_offset
from datetime import datetime
from collections import deque
from watch.utils.manage_message import t_link


@app.route('/<target>/task')
@title('Tasks')
def get_task(target):
    with lock:
        task_count = tuple(v.user_name for v in task_pool.values() if v.target == target).count(session['user_name'])
        t = render_template('layout.html', text=f'You have {task_count} active tasks for {target}.')
    return t


@app.route('/<target>/wait_for_execution')
@title('Wait for SQL execution')
@template('task')
@parameters({'sql_id': ' = str'})
@period('1m')
@command('/wait')
def wait_for_execution(t):
    if not t.data:
        e = execute(t.target
                    , "select max(sql_id) sql_id, max(sql_exec_id) exec_id, max(sql_exec_start) sql_exec_start"
                      " from v$sql_monitor where sql_id = :sql_id"
                    , t.parameters
                    , 'one'
                    , False)
        if not e[0]:
            return True, 'Not found'
        t.data = {'sql_id': e[0], 'exec_id': e[1], 'sql_exec_start': e[2]}
    r = execute(t.target
                , "select sql_id, status"
                  " from v$sql_monitor"
                  " where sql_id = :sql_id and sql_exec_id = :exec_id and sql_exec_start = :sql_exec_start"
                , t.data
                , 'one'
                , False)
    if not r:
        return True, 'Not found'
    if r[1] == 'EXECUTING':
        return False, ''
    if t.reply_to_message_id:
        return True, r[1].lower()
    return True, '{} on {} is {}.'.format(t_link(f'{t.target}/Q/{r[0]}', r[0])
                                          , t.target
                                          , r[1].lower())


@app.route('/<target>/wait_for_status')
@title('Wait for status')
@template('task')
@parameters({"owner": ' = str'
             , "table": ' = str'
             , "date_column": ' = str'
             , "status_column": ' = str'
             , "status_values": ' = s1;s2;sN str'
             , "info_column": ' = i1;i2;iN str'})
@optional({"filter_column": ' = str'
          , "filter_value": ' = str'})
@period('30m')
def wait_for_status(t):
    if not t.data:
        t.parameters = upper_values(t.parameters)
        t.parameters['status_values'] = dlm_str_to_list(t.parameters['status_values'])
        t.parameters['info_column'] = dlm_str_to_list(t.parameters['info_column'])
        table_columns = get_tab_columns(t.target, t.parameters['owner'], t.parameters['table'])
        for item in [t.parameters['date_column'], t.parameters['status_column']] + t.parameters['info_column']:
            if item not in table_columns.keys():
                return True, f'{t.parameters["owner"]}.{t.parameters["table"]}.{item} not found.'
        if 'DATE' not in table_columns[t.parameters['date_column']]:
            return True, f'{t.parameters["date_column"]} must be a date type.'

        status_type = table_columns[t.parameters['status_column']]
        if status_type != 'NUMBER' and 'CHAR' not in status_type:
            return True, f'Unsupported type of {t.parameters["status_column"]} (neither number nor char).'
        if status_type == 'NUMBER':
            try:
                t.parameters['status_values'] = [int(v) for v in t.parameters['status_values']]
            except ValueError:
                return True, f'All of status values ({t.parameters["status_values"]}) must be numbers.'

        t.parameters['info_column'] = {k: table_columns[k] for k in t.parameters['info_column']}

        filter_column_type = ''
        if t.optional.get('filter_column', False):
            if t.optional['filter_column'] not in table_columns.keys():
                return True, f'{t.parameters["owner"]}.{t.parameters["table"]}.{t.optional["filter_column"]} not found.'
            filter_column_type = table_columns[t.optional['filter_column']]
            if filter_column_type != 'NUMBER' and 'CHAR' not in filter_column_type:
                return True, f'Unsupported type of {t.optional["filter_column"]} (neither number nor char).'
            if not t.optional.get('filter_value', False):
                return True, 'Filter value is not set.'
            if filter_column_type == 'NUMBER':
                try:
                    t.optional['filter_value'] = int(t.optional['filter_value'])
                except ValueError:
                    return True, f'Filter value must be a number.'
        t.data = {'status_values': t.parameters['status_values']
                  , 'status_type': status_type
                  , 'start_date': t.create_date
                  , 'filter_column_type': filter_column_type}

    end_date = datetime.now()
    p = {str(k): v for k, v in enumerate(t.data['status_values'], start=1)}
    p['start_date'] = t.data['start_date']
    p['end_date'] = end_date
    p['filter_value'] = t.optional.get('filter_value', '1')
    info_column_list = []
    for c, ct in t.parameters['info_column'].items():
        if ct == 'CLOB':
            info_column_list.append(f"cast(dbms_lob.substr({c}, 255) as varchar2(255))")
        elif 'CHAR' in ct:
            info_column_list.append(f"substr(to_char({c}), 0, 255)")
        else:
            info_column_list.append(f"to_char({c})")
    info_column_sql_text = ' || \' \' || '.join(info_column_list)
    filter_column = t.optional.get('filter_column', '\'1\'')
    r = execute(t.target
                , f"select to_char({t.parameters['date_column']}, 'hh24:mi:ss')"
                  f", {info_column_sql_text}"
                  f", {t.parameters['status_column']}"
                  f" from {t.parameters['owner']}.{t.parameters['table']}"
                  f" where {t.parameters['date_column']} >= :start_date"
                  f" and {t.parameters['date_column']} < :end_date"
                  f" and {'upper' if t.data['status_type'] != 'NUMBER' else ''}"
                  f"({t.parameters['status_column']})"
                  f" in ({':' + ', :'.join(str(i) for i in range(1, len(t.data['status_values']) + 1))})"
                  f" and {filter_column} = :filter_value"
                , p
                , 'many'
                , False)
    t.data['start_date'] = end_date
    if not r:
        return False, ''
    else:
        message_text = f'{t.parameters["table"]} ({t.target}):\n'
        max_count = 10
        message_text += '\n'.join(f'{item[0]} {item[1]}'.replace('<', '&lt;').replace('>', '&gt;')
                                  for item in r[:max_count - 1])
        if len(r) > max_count:
            message_text += f'\n and {str(len(r) - max_count)} more...'
    return False, message_text


@app.route('/<target>/wait_for_heavy')
@title('Wait for heavy')
@template('task')
@parameters({'exec_time_min': ' >= int'
             , 'temp_usage_gb': ' >= int'})
@optional({'user_name': ' like str'
           , 'ignore_user': ' like str'})
@period('5m')
@command('/heavy')
def wait_for_heavy(t):
    r = execute(t.target
                , "select username, sql_id, exec_time_min, temp_usage_gb, exec_id, sid from"
                  " (select s.username, m.sql_id, to_char(round(elapsed_time / 60000000)) exec_time_min, s.sid,"
                  " m.sql_id || to_char(m.sql_exec_id) || to_char(m.sql_exec_start, 'yyyymmddhh24miss') exec_id,"
                  " rtrim(to_char(((nvl(sum(u.blocks), 0) * min(p.value)) / 1024 / 1024 / 1024), 'fm999990d99')"
                  ", to_char(0,'fmd'))  temp_usage_gb"
                  " from v$session s"
                  " left join v$sort_usage u on s.saddr = u.session_addr"
                  " join v$parameter p on p.name = 'db_block_size'"
                  " join v$sql_monitor m on m.sid = s.sid and m.session_serial# = s.serial#"
                  " where m.status = 'EXECUTING'{}{}"
                  " group by s.username, m.sql_id, round(elapsed_time / 60000000), s.sid,"
                  " m.sql_id || to_char(m.sql_exec_id) || to_char(m.sql_exec_start, 'yyyymmddhh24miss'))"
                  " where exec_time_min >= :exec_time_min or temp_usage_gb >= :temp_usage_gb"
                  .format(' and s.username like :user_name' if t.optional.get('user_name', None) else ''
                          , ' and s.username not like :ignore_user' if t.optional.get('ignore_user', None) else '')
                , {**t.parameters, **t.optional}
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if t.data is None:
            t.data = deque(maxlen=app.config['MAX_STORED_OBJECTS'])
        else:
            for item in t.data.copy():
                if item not in [r_item[4] for r_item in r]:
                    t.data.remove(item)
        message_text = '\n'.join('{} ({}, {}) on {} has been execute for {} minutes and consumes {} Gb of temp space.'
                                 .format(t_link(f'{t.target}/Q/{item[1]}', item[1])
                                         , item[5]
                                         , item[0]
                                         , t.target
                                         , item[2]
                                         , item[3])
                                 for item in r if item[4] not in t.data)
        for item in r:
            if item[4] not in t.data:
                t.data.appendleft(item[4])
        return False, message_text or ''


@app.route('/<target>/wait_for_temp')
@title('Critical temp usage')
@template('task')
@parameters({'pct_used': ' >= int'})
@period('10m')
@command('/temp')
def wait_for_temp(t):
    r = execute(t.target
                , "select tablespace_name, to_char(round((used_blocks / total_blocks) * 100)) pct_used"
                  " from v$sort_segment"
                  " where round((used_blocks / total_blocks) * 100) >= :pct_used"
                , t.parameters
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if t.data is None:
            t.data = tuple()
        message_text = '\n'.join(f'Tablespace {item[0]} on {t.target} is {item[1]}% used.' for item in r
                                 if item[0] not in t.data)
        t.data = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_expiry')
@title('Expired users')
@template('task')
@parameters({'expires_in_days': ' >= int'})
@period('1d')
@command('/exp')
def wait_for_expiry(t):
    r = execute(t.target
                , "select username, to_char(expiry_date, 'dd.mm.yyyy hh24:mi:ss') exp"
                  " from dba_users"
                  " where expiry_date between sysdate and sysdate + :expires_in_days"
                , t.parameters
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if t.data is None:
            t.data = ()
        message_text = '\n'.join(f'User account {item[0]} on {t.target}'
                                 f' expires at {item[1]}.' for item in r
                                 if item[0] not in t.data)
        t.data = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_uncommitted')
@title('Uncommitted trans')
@template('task')
@parameters({'idle_time_minutes': ' >= int'})
@optional({'ignore_tables': ' like str'})
@period('1h')
@command('/uncommitted')
def wait_for_uncommitted(t):
    r = execute(t.target
                , "select distinct s.osuser, s.machine, l.name"
                  " from dba_dml_locks l"
                  " inner join v$session s on s.sid = l.session_id"
                  " where s.status != 'ACTIVE'"
                  " and l.name not like :ignore_tables"
                  " and round(last_call_et / 60) >= :idle_time_minutes"
                , {'idle_time_minutes': t.parameters['idle_time_minutes']
                    , 'ignore_tables': t.optional.get('ignore_tables', '-')}
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if t.data is None:
            t.data = ()
        message_text = '\n'.join(f'It seems {item[0]} ({item[1]})'
                                 f' forgot to commit a transaction on {t.target} ({item[2]}).' for item in r
                                 if item[0] not in t.data)
        t.data = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_ts')
@title('Critical tabspace usage')
@template('task')
@parameters({'pct_used': ' >= int'})
@optional({'tablespace_name': ' like str'})
@period('6h')
@command('/ts')
@snail()
def wait_for_ts(t):
    r = execute(t.target
                , "select * from ("
                  "select files.tablespace_name"
                  ", round((max_files_size - (files.free_files_space + free.free_space)) / 1024 / 1024 / 1024) used_gb"
                  ", round(files.max_files_size / 1024 / 1024 / 1024) allocated_gb"
                  ", round(((max_files_size - (files.free_files_space + free.free_space))"
                  " / max_files_size) * 100) pct_used"
                  " from ("
                  "select tablespace_name"
                  ", sum(decode(maxbytes, 0, bytes, maxbytes)) max_files_size"
                  ", sum(decode(maxbytes, 0, bytes, maxbytes)) - sum(bytes) free_files_space"
                  " from dba_data_files"
                  " group by tablespace_name) files"
                  " inner join ("
                  "select tablespace_name"
                  ", sum(nvl(bytes,0)) free_space"
                  " from dba_free_space"
                  " group by tablespace_name) free on free.tablespace_name = files.tablespace_name"
                  ") where pct_used >= :pct_used and tablespace_name like :tablespace_name"
                , {'pct_used': t.parameters['pct_used'], 'tablespace_name': t.optional.get('tablespace_name', '%')}
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if t.data is None:
            t.data = ()
        max_count = 20
        message_text = '\n'.join(f'Tablespace {item[0]} on {t.target} is {item[3]}% used'
                                 f' ({item[1]} of {item[2]} Gb).'
                                 for item in
                                 tuple(r_item for r_item in r if r_item[0] not in t.data)[:max_count - 1])
        if message_text and len(r) > max_count:
            message_text += f'\n and {str(len(r) - max_count)} more...'
        t.data = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_session')
@title('Wait for session')
@template('task')
@parameters({'sid': ' = int'})
@period('1m')
@command('/waits')
def wait_for_session(t):
    if not t.data:
        e = execute(t.target
                    , "select sid, status from v$session where sid = :sid"
                    , t.parameters
                    , 'one'
                    , False)
        if not e:
            return True, 'Not found'
        t.data = {'sid': e[0]}
    r = execute(t.target
                , "select sid, status from v$session where sid = :sid"
                , t.data
                , 'one'
                , False)
    if not r:
        return True, f"Session {t.data['sid']} is not found on {t.target}."
    if r[1] != 'INACTIVE':
        return False, ''
    return True, f'Session {r[0]} on {t.target} is {r[1].lower()}.'


@app.route('/<target>/wait_for_queued')
@title('Wait for queued')
@template('task')
@parameters({'queued_time_sec': ' >= int'})
@optional({'ignore_event': ' like str'})
@period('5m')
def wait_for_queued(t):
    pt = t.period[-1:]
    pv = t.period[:-1]
    t.parameters['start_date'] = datetime.now() - get_offset(pv, pt)
    r = execute(t.target
                , "select nvl(sql_id, 'Unknown sql'), event, session_id, machine, count(1) waits"
                  " from v$active_session_history"
                  " where event like 'enq:%' and sample_time > :start_date"
                  " and event not like :ignore_event"
                  " group by sql_id, event, session_id, machine"
                  " having count(1) > :queued_time_sec"
                , {'start_date': t.parameters['start_date']
                    , 'queued_time_sec': t.parameters['queued_time_sec']
                    , 'ignore_event': t.optional.get('ignore_event', '---')}
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if t.data is None:
            t.data = deque(maxlen=app.config['MAX_STORED_OBJECTS'])
        else:
            for item in t.data.copy():
                if item not in [f'{r_item[0]} {r_item[1]} {r_item[2]}' for r_item in r]:
                    t.data.remove(item)
        message_text = '\n'.join('{} ({}, {}) on {} has been queued for {} seconds ({}).'
                                 .format(t_link(f'{t.target}/Q/{item[0]}', item[0])
                                         , item[3]
                                         , item[2]
                                         , t.target
                                         , item[4]
                                         , item[1])
                                 for item in r if item[0] not in t.data)
        for item in r:
            if item[0] not in t.data:
                t.data.appendleft(f'{item[0]} {item[1]} {item[2]}')
        return False, message_text or ''


@app.route('/<target>/wait_recycled')
@title('Wait for recycled')
@template('task')
@parameters({'space_gb': ' >= int'})
@period('1d')
def wait_for_recycled(t):
    r = execute(t.target
                , "select round(sum(r.space * p.value) / 1024 / 1024 / 1024) space_gb"
                  " from dba_recyclebin r join v$parameter p on p.name = 'db_block_size'"
                  " where r.can_purge = 'YES' and nvl(r.space, 0) <> 0"
                  " having round(sum(r.space * p.value) / 1024 / 1024 / 1024) >= :space_gb"
                , t.parameters
                , 'one'
                , False)
    if not r:
        t.data = 0
    else:
        if t.data is None or r[0] >= t.data * 2:  # to reduce excess messages
            t.data = r[0]
            return False, f'{r[0]} Gb can be purged from recycle bin on {t.target}.'
    return False, ''


@app.route('/<target>/check_size')
@title('Check segment size')
@template('task')
@parameters({'owner': ' = str'
             , 'segment_name': ' = str'
             , 'size_mb': ' >= int'})
@period('1d')
def check_size(t):
    if not t.data:
        t.data = t.parameters['size_mb']
    r = execute(t.target
                , "select round(nvl(sum(bytes) / 1024 / 1024, 0)) size_mb"
                  " from dba_segments"
                  " where owner = :owner and segment_name = :segment_name"
                , {'owner': t.parameters['owner'], 'segment_name': t.parameters['segment_name']}
                , 'one'
                , False)
    if not r:
        return True, f'Segment {t.parameters["owner"]}.{t.parameters["segment_name"]} not found.'
    if r[0] >= t.data:
        t.data = r[0] * 2  # to reduce excess messages
        return False, f'{t.parameters["owner"]}.{t.parameters["segment_name"]} size reached {r[0]} mb on {t.target}.'
    else:
        t.data = None
        return False, ''


@app.route('/<target>/check_resource_usage')
@title('Check res usage')
@template('task')
@parameters({'pct_used': ' 0..100% >= int'})
@period('1h')
def check_resource_usage(t):
    r = execute(t.target
                , "select resource_name, to_char(current_utilization), trim(limit_value)"
                  ", round((current_utilization / to_number(limit_value)) * 100)"
                  " from v$resource_limit"
                  " where trim(limit_value) not in ('0', 'UNLIMITED')"
                  " and round((current_utilization / to_number(limit_value)) * 100) >= :pct_used"
                , t.parameters
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        return False, '\n'.join(f'The resource {t.target}.{item[0]}'
                                f' is {item[3]}% used ({item[1]} of {item[2]}).' for item in r)


@app.route('/<target>/wait_for_sql_error')
@title('Wait for SQL error')
@template('task')
@optional({'ignore_user': ' like str'})
@period('5m')
def wait_for_sql_error(t):
    if not t.data:
        t.data = {'start_date': t.create_date}
    end_date = datetime.now()
    r = execute(t.target
                , "select username, sql_id, sid, error_message"
                  " from v$sql_monitor"
                  " where status = 'DONE (ERROR)' and error_number not in (1013, 28)"  # cancelled, killed
                  " and last_refresh_time between :start_date and :end_date and username not like :user_name"
                , {'start_date': t.data['start_date']
                   , 'end_date': end_date
                   , 'user_name': t.optional.get('ignore_user', '---')}
                , 'many'
                , False)
    t.data['start_date'] = end_date
    if not r:
        return False, ''
    else:
        return False, '\n'.join('{} ({}, {}) on {} is failed ({}).'
                                .format(t_link(f'{t.target}/Q/{item[1]}', item[1])
                                        , item[2]
                                        , item[0]
                                        , t.target
                                        , item[3].replace('\n', ' '))
                                for item in r[:10]) + ('' if len(r) <= 10 else f'\n and {str(len(r) - 10)} more...')


@app.route('/<target>/ping_target')
@title('Ping target')
@template('task')
@period('10m')
def ping_target(t):
    if ping(t.target) == -1 and t.data != -1:
        t.data = -1
        return False, f'Target {t.target} did not respond properly.'
    else:
        t.data = 0
    return False, ''
