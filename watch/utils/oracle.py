from flask import session, abort
from cx_Oracle import SessionPool, makedsn, DatabaseError, OperationalError, Error, CLOB
from watch import app, target_pool, active_connections, lock
from uuid import uuid4
from datetime import datetime


def set_ora_pool(target):
    target_description = app.config['TARGETS'][target]
    target_pool[target] = SessionPool(user=target_description['user']
                                      , password=target_description['password']
                                      , encoding=target_description['encoding']
                                      , threaded=True
                                      , min=1
                                      , max=app.config['ORA_MAX_POOL_SIZE']
                                      , increment=1
                                      , dsn=makedsn(host=target_description['host']
                                                    , port=target_description['port']
                                                    , sid=target_description['sid']))


def execute(target, statement, parameters=None, fetch_mode='many', user_context=True):
    with lock:
        if user_context:
            if tuple(v[2] for v in active_connections.values()) \
                    .count(session['user_name']) == app.config['MAX_DB_SESSIONS_PER_USER']:
                abort(429)
        if not target_pool.get(target):
            set_ora_pool(target)

    connection = None
    try:
        connection = target_pool[target].acquire()
        connection.ping()
    except Error:
        if connection:
            target_pool[target].drop(connection)
        connection = target_pool[target].acquire()

    cursor = None
    result = None
    uuid = None
    try:
        uuid = uuid4().hex
        active_connections[uuid] = [connection
                                    , datetime.now()
                                    , session['user_name'] if user_context else 'system'
                                    , target
                                    , statement
                                    , '']
        cursor = connection.cursor()
        if fetch_mode == 'one':
            result = cursor.execute(statement, **parameters or {}).fetchone()
        elif fetch_mode == 'clob':
            result = cursor.execute(statement, **parameters or {}).fetchone()
            if result and result[0]:
                result = result[0].read()
        elif fetch_mode == 'func':
            result = cursor.callfunc(statement, CLOB, [], parameters or {}).read()
        elif fetch_mode == 'many':
            result = cursor.execute(statement, **parameters or {}).fetchmany(app.config['ORA_NUM_ROWS'])
        cursor.close()
    except OperationalError:
        raise
    except DatabaseError:
        if cursor:
            cursor.close()
        raise
    finally:
        if uuid:
            del active_connections[uuid]
        if connection:
            try:  # todo: https://github.com/oracle/python-cx_Oracle/issues/138
                target_pool[target].release(connection)
            except DatabaseError:
                pass
    return result


def get_tab_columns(target, owner, table_name):
    return {item[0]: item[1] for item in execute(target
                                                 , 'select column_name, data_type'
                                                   ' from dba_tab_columns'
                                                   ' where owner = :owner'
                                                   ' and table_name = :table_name'
                                                 , {'owner': owner, 'table_name': table_name}
                                                 , 'many'
                                                 , False)}


def ping(target):
    try:
        with lock:
            if not target_pool.get(target):
                set_ora_pool(target)
        connection = target_pool[target].acquire()
        connection.ping()
        return 0
    except Error:
        return -1
