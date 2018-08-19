from flask import redirect, url_for
from watch import app
from watch.utils.render_page import render_page
from watch.utils.decorate_view import *


@app.route('/<target>/S/<sid>')
@title('Session')
@template('single')
@columns({"sid": 'int'
          , "serial#": 'int'
          , "username": 'str'
          , "status": 'str'
          , "schemaname": 'str'
          , "osuser": 'str'
          , "machine": 'str'
          , "terminal": 'str'
          , "program": 'str'
          , "type": 'str'
          , "sql_id": 'str'
          , "sql_child_number": 'int'
          , "sql_exec_start": 'datetime'
          , "prev_sql_id": 'str'
          , "prev_child_number": 'int'
          , "prev_exec_start": 'datetime'
          , "module": 'str'
          , "action": 'str'
          , "logon_time": 'datetime'
          , "event": 'str'
          , "wait_class": 'str'
          , "seconds_in_wait": 'int'
          , "state": 'str'
          })
@select("v$session where sid = :sid")
def get_session(target, sid):
    return render_page()


@app.route('/<target>/S/<sid>/notify_if_inactive')
@title('Notify if inactive')
def notify_if_inactive(target, sid):
    return redirect(url_for('wait_for_session', target=target, sid=sid))
