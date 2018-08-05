from flask import render_template, session
from watch import app, task_pool, lock
from watch.utils.decorate_view import *
from watch.utils.oracle import execute
from datetime import datetime, timedelta
from collections import deque
from watch.utils.manage_message import t_pre, t_link


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
             , "status_values": ' = s1;s2;sn str'
             , "info_column": ' = str'})
@optional({"filter_column": ' = str'
          , "filter_value": ' = str'})
@period('30m')
def wait_for_status(t):
    if not t.data:
        t.parameters = {k: v.strip().upper() for k, v in t.parameters.items()}
        r = execute(t.target
                    , "select distinct column_name, data_type"
                      " from dba_tab_columns"
                      " where owner = :owner"
                      " and table_name = :p_table"
                      " and column_name in (:date_column, :status_column, :info_column, :filter_column)"
                    , {'owner': t.parameters['owner']
                       , 'p_table': t.parameters['table']
                       , 'date_column': t.parameters['date_column']
                       , 'status_column': t.parameters['status_column']
                       , 'info_column': t.parameters['info_column']
                       , 'filter_column': t.optional.get('filter_column', '')}
                    , 'many'
                    , False)
        if len(r) != (4 if 'filter_column' in t.optional.keys() else 3):
            return True, 'Table or some columns not found. Column names must be unique.'
        status_type = ''
        info_column_type = ''
        filter_column_type = ''
        for c in r:
            if c[0] == t.parameters['date_column'] and c[1] != 'DATE':
                return True, f'{t.parameters["date_column"]} is not a date.'
            if c[0] == t.parameters['status_column'] and c[1] != 'NUMBER' and 'CHAR' not in c[1]:
                return True, f'Unsupported type of {t.parameters["status_column"]} (neither number nor char).'
            else:
                status_type = c[1]
            if c[0] == t.parameters['info_column']:
                info_column_type = c[1]
            if c[0] == t.optional.get('filter_column', ''):
                if c[1] != 'NUMBER' and 'CHAR' not in c[1]:
                    return True, f'Unsupported type of {t.optional["filter_column"]}' \
                                 f' (neither number nor char).'
                filter_column_type = c[1]
                if not t.optional.get('filter_value', False):
                    return True, 'Filter value is not set.'
        status_values = tuple(v.strip() for v in t.parameters['status_values'].split(';'))
        if status_type == 'NUMBER':
            try:
                status_values = tuple(int(v) for v in status_values)
            except ValueError:
                return True, f'All of status values ({t.parameters["status_values"]}) must be numbers.'
        t.data = {'status_values': status_values
                  , 'status_type': status_type
                  , 'start_date': t.create_date
                  , 'info_column_type': info_column_type
                  , 'filter_column_type': filter_column_type}

    end_date = datetime.now()
    p = {str(k): v for k, v in enumerate(t.data["status_values"], start=1)}
    p['start_date'] = t.data['start_date']
    p['end_date'] = end_date
    p['filter_value'] = t.optional.get('filter_value', '1')
    info_column_type = t.data['info_column_type']
    info_column_convert = ''
    if info_column_type == 'CLOB':
        info_column_convert = f"cast(dbms_lob.substr({t.parameters['info_column']}, 255) as varchar2(100))"
    elif 'CHAR' in info_column_convert:
        info_column_convert = f"substr(to_char({t.parameters['info_column']}), 0, 255)"
    else:
        info_column_convert = f"to_char({t.parameters['info_column']})"

    r = execute(t.target
                , f"select to_char({t.parameters['date_column']}, 'hh24:mi:ss')"
                  f", {info_column_convert}"
                  f", {t.parameters['status_column']}"
                  f" from {t.parameters['owner']}.{t.parameters['table']}"
                  f" where {t.parameters['date_column']} >= :start_date"
                  f" and {t.parameters['date_column']} < :end_date"
                  f" and {'upper' if t.data['status_type'] != 'NUMBER' else ''}"
                  f"({t.parameters['status_column']})"
                  f" in ({':' + ', :'.join(str(i) for i in range(1, len(t.data['status_values']) + 1))})"
                  f" and to_char({t.optional.get('filter_column', '1')})"
                  f" = :filter_value"
                , p
                , 'many'
                , False)
    t.data['start_date'] = end_date
    if not r:
        return False, ''
    else:
        message_text = f'{t.parameters["table"]} ({t.target}):\n'
        max_count = 10
        message_text += t_pre('\n'.join(f'{item[0]} {item[1]} {item[2]}' for item in r[:max_count - 1]))
        if len(r) > max_count:
            message_text += f'\n and {str(len(r) - max_count)} more...'
    return False, message_text


@app.route('/<target>/wait_for_heavy')
@title('Wait for heavy')
@template('task')
@parameters({'exec_time_min': ' >= int'
             , 'temp_usage_gb': ' >= int'})
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
                  " where m.status = 'EXECUTING'"
                  " group by s.username, m.sql_id, round(elapsed_time / 60000000), s.sid,"
                  " m.sql_id || to_char(m.sql_exec_id) || to_char(m.sql_exec_start, 'yyyymmddhh24miss'))"
                  " where exec_time_min >= :exec_time_min or temp_usage_gb >= :temp_usage_gb"
                , t.parameters
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
@parameters({'idle_time_minutes': ' >= int'
             , 'ignore_tables': ' - like str'})
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
                , t.parameters
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
@parameters({'pct_used': ' >= int'
             , 'tablespace_name': ' like str'})
@period('6h')
@command('/ts')
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
                , t.parameters
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
@parameters({'queued_time_sec': ' >= int'
             , 'ignore_event': ' like str'})
@period('5m')
def wait_for_queued(t):
    pt = t.period[-1:]
    pv = t.period[:-1]
    t.parameters['start_date'] = datetime.now() - timedelta(weeks=int(pv) if pt == 'w' else 0
                                                            , days=int(pv) if pt == 'd' else 0
                                                            , hours=int(pv) if pt == 'h' else 0
                                                            , minutes=int(pv) if pt == 'm' else 0
                                                            , seconds=int(pv) if pt == 's' else 0)
    r = execute(t.target
                , "select nvl(sql_id, 'Unknown sql'), event, session_id, machine, count(1) waits"
                  " from v$active_session_history"
                  " where event like 'enq:%' and sample_time > :start_date"
                  " and event not like :ignore_event"
                  " group by sql_id, event, session_id, machine"
                  " having count(1) > :queued_time_sec"
                , t.parameters
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
