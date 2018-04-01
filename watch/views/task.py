from flask import render_template, session
from watch import app, task_pool, lock
from watch.utils.decorate_view import *
from watch.utils.oracle import execute
from datetime import datetime
from collections import deque
from watch.utils.manage_message import t_pre, t_link


@app.route('/<target>/task')
@title('Tasks')
def get_task(target):
    with lock:
        task_count = tuple(v[3] for v in task_pool.values() if v[4] == target).count(session['user_name'])
        t = render_template('layout.html', text=f'You have {task_count} active tasks for {target}.')
    return t


@app.route('/<target>/wait_for_execution')
@title('Wait for SQL execution')
@template('task')
@parameters({'sql_id': ' = str'})
@period('1m')
@command('/wait')
def wait_for_execution(uuid):
    if not task_pool[uuid][12]:
        e = execute(task_pool[uuid][4]
                    , "select max(sql_id) sql_id, max(sql_exec_id) exec_id, max(sql_exec_start) sql_exec_start"
                      " from v$sql_monitor where sql_id = :sql_id"
                    , task_pool[uuid][8]
                    , 'one'
                    , False)
        if not e[0]:
            return True, 'Not found'
        task_pool[uuid][12] = {'sql_id': e[0], 'exec_id': e[1], 'sql_exec_start': e[2]}
    r = execute(task_pool[uuid][4]
                , "select sql_id, status"
                  " from v$sql_monitor"
                  " where sql_id = :sql_id and sql_exec_id = :exec_id and sql_exec_start = :sql_exec_start"
                , task_pool[uuid][12]
                , 'one'
                , False)
    if not r:
        return True, 'Not found'
    if r[1] == 'EXECUTING':
        return False, ''
    if task_pool[uuid][11]:
        return True, r[1].lower()
    return True, '{} on {} is {}'.format(t_link(f'{task_pool[uuid][4]}/Q/{r[0]}', r[0])
                                         , task_pool[uuid][4]
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
@period('30m')
def wait_for_status(uuid):
    if not task_pool[uuid][12]:
        task_pool[uuid][8] = {k: v.strip().upper() for k, v in task_pool[uuid][8].items()}
        r = execute(task_pool[uuid][4]
                    , "select distinct column_name, data_type"
                      " from dba_tab_columns"
                      " where owner = :owner"
                      " and table_name = :p_table"
                      " and column_name in (:date_column, :status_column, :info_column)"
                    , {'owner': task_pool[uuid][8]['owner']
                       , 'p_table': task_pool[uuid][8]['table']
                       , 'date_column': task_pool[uuid][8]['date_column']
                       , 'status_column': task_pool[uuid][8]['status_column']
                       , 'info_column': task_pool[uuid][8]['info_column']}
                    , 'many'
                    , False)
        if len(r) != 3:
            return True, 'Table or some columns not found. Column names must be unique.'
        status_type = ''
        for c in r:
            if c[0] == task_pool[uuid][8]['date_column'] and c[1] != 'DATE':
                return True, f'{task_pool[uuid][8]["date_column"]} is not a date.'
            if c[0] == task_pool[uuid][8]['status_column'] and c[1] != 'NUMBER' and 'CHAR' not in c[1]:
                return True, f'Unsupported type of {task_pool[uuid][8]["status_column"]} (neither number nor char).'
            else:
                status_type = c[1]
        status_values = tuple(v.strip() for v in task_pool[uuid][8]['status_values'].split(';'))
        if status_type == 'NUMBER':
            try:
                status_values = tuple(int(v) for v in status_values)
            except ValueError:
                return True, f'All of status values ({task_pool[uuid][8]["status_values"]}) must be numbers.'
        task_pool[uuid][12] = {'status_values': status_values
                               , 'status_type': status_type
                               , 'start_date': task_pool[uuid][2]}

    end_date = datetime.now()
    p = {str(k): v for k, v in enumerate(task_pool[uuid][12]["status_values"], start=1)}
    p['start_date'] = task_pool[uuid][12]["start_date"]
    p['end_date'] = end_date
    r = execute(task_pool[uuid][4]
                , f"select to_char({task_pool[uuid][8]['date_column']}, 'hh24:mi:ss')"
                  f", to_char({task_pool[uuid][8]['info_column']})"
                  f", {task_pool[uuid][8]['status_column']}"
                  f" from {task_pool[uuid][8]['owner']}.{task_pool[uuid][8]['table']}"
                  f" where {task_pool[uuid][8]['date_column']} >= :start_date"
                  f" and {task_pool[uuid][8]['date_column']} < :end_date"
                  f" and {'upper' if task_pool[uuid][12]['status_type'] != 'NUMBER' else ''}"
                  f"({task_pool[uuid][8]['status_column']})"
                  f" in ({':' + ', :'.join(str(i) for i in range(1, len(task_pool[uuid][12]['status_values']) + 1))})"
                , p
                , 'many'
                , False)
    task_pool[uuid][12]['start_date'] = end_date
    if not r:
        return False, ''
    else:
        message_text = f'{task_pool[uuid][8]["table"]}:\n'
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
def wait_for_heavy(uuid):
    r = execute(task_pool[uuid][4]
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
                , task_pool[uuid][8]
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if task_pool[uuid][12] is None:
            task_pool[uuid][12] = deque(maxlen=1000)  # todo: replace by set()
        else:
            for item in task_pool[uuid][12].copy():
                if item not in [r_item[4] for r_item in r]:
                    task_pool[uuid][12].remove(item)
        message_text = '\n'.join('{} ({}, {}) on {} has been execute for {} minutes and consumes {} Gb of temp space.'
                                 .format(t_link(f'{task_pool[uuid][4]}/Q/{item[1]}', item[1])
                                         , item[5]
                                         , item[0]
                                         , task_pool[uuid][4]
                                         , item[2]
                                         , item[3])
                                 for item in r if item[4] not in task_pool[uuid][12])
        for item in r:
            if item[4] not in task_pool[uuid][12]:
                task_pool[uuid][12].appendleft(item[4])
        return False, message_text or ''


@app.route('/<target>/wait_for_temp')
@title('Critical temp usage')
@template('task')
@parameters({'pct_used': ' >= int'})
@period('10m')
@command('/temp')
def wait_for_temp(uuid):
    r = execute(task_pool[uuid][4]
                , "select tablespace_name, to_char(round((used_blocks / total_blocks) * 100)) pct_used"
                  " from v$sort_segment"
                  " where round((used_blocks / total_blocks) * 100) >= :pct_used"
                , task_pool[uuid][8]
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if task_pool[uuid][12] is None:
            task_pool[uuid][12] = ()
        message_text = '\n'.join(f'Tablespace {item[0]} on {task_pool[uuid][4]} is {item[1]}% used.' for item in r
                                 if item[0] not in task_pool[uuid][12])
        task_pool[uuid][12] = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_expiry')
@title('Expired users')
@template('task')
@parameters({'expires_in_days': ' >= int'})
@period('1d')
@command('/exp')
def wait_for_expiry(uuid):
    r = execute(task_pool[uuid][4]
                , "select username, to_char(expiry_date, 'dd.mm.yyyy hh24:mi:ss') exp"
                  " from dba_users"
                  " where expiry_date between sysdate and sysdate + :expires_in_days"
                , task_pool[uuid][8]
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if task_pool[uuid][12] is None:
            task_pool[uuid][12] = ()
        message_text = '\n'.join(f'User account {item[0]} on {task_pool[uuid][4]}'
                                 f' expires at {item[1]}.' for item in r
                                 if item[0] not in task_pool[uuid][12])
        task_pool[uuid][12] = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_uncommitted')
@title('Uncommitted trans')
@template('task')
@parameters({'idle_time_minutes': ' >= int'})
@period('1h')
@command('/uncommitted')
def wait_for_uncommitted(uuid):
    r = execute(task_pool[uuid][4]
                , "select distinct s.osuser, s.machine, l.name"
                  " from dba_dml_locks l"
                  " inner join v$session s on s.sid = l.session_id"
                  " where s.status != 'ACTIVE'"
                  " and round(last_call_et / 60) >= :idle_time_minutes"
                , task_pool[uuid][8]
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if task_pool[uuid][12] is None:
            task_pool[uuid][12] = ()
        message_text = '\n'.join(f'It seems {item[0]} ({item[1]})'
                                 f' forgot to commit a transaction on {task_pool[uuid][4]} ({item[2]}).' for item in r
                                 if item[0] not in task_pool[uuid][12])
        task_pool[uuid][12] = tuple(item[0] for item in r)
        return False, message_text


@app.route('/<target>/wait_for_ts')
@title('Critical tabspace usage')
@template('task')
@parameters({'pct_used': ' >= int'
             , 'tablespace_name': ' like str'})
@period('6h')
@command('/ts')
def wait_for_ts(uuid):
    r = execute(task_pool[uuid][4]
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
                , task_pool[uuid][8]
                , 'many'
                , False)
    if not r:
        return False, ''
    else:
        if task_pool[uuid][12] is None:
            task_pool[uuid][12] = ()
        max_count = 20
        message_text = '\n'.join(f'Tablespace {item[0]} on {task_pool[uuid][4]} is {item[3]}% used'
                                 f' ({item[1]} of {item[2]} Gb).'
                                 for item in
                                 tuple(r_item for r_item in r if r_item[0] not in task_pool[uuid][12])[:max_count - 1])
        if message_text and len(r) > max_count:
            message_text += f'\n and {str(len(r) - max_count)} more...'
        task_pool[uuid][12] = tuple(item[0] for item in r)
        return False, message_text
