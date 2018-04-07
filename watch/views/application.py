from flask import session, request, redirect, url_for, render_template, flash, send_file, abort
from watch import app, active_connections, target_pool, notification_pool, worker, task_pool, bot, lock
from watch.utils.decorate_view import *
from watch.utils.manage_task import cancel_task, reset_task
from cx_Oracle import clientversion
from platform import platform
from time import sleep
from os import path
from pickle import dump as pickle, HIGHEST_PROTOCOL


@app.route('/login', methods=['GET', 'POST'])
@title('Login')
def login():
    if not app.config['TARGETS'] or not app.config['USERS']:
        flash('It seems the app is not configured.')
    if request.method == 'GET':
        if 'user_name' in session:
            return redirect(request.args.get('link', url_for('app_ui')))
        else:
            return render_template('login.html')
    if request.method == 'POST':
        if request.form['name'] and request.form['password']:
            user = app.config['USERS'].get(request.form['name'].lower())
            if user is None or user[0] != request.form['password']:
                flash('Incorrect login or password')
                return render_template('login.html')
            else:
                session['user_name'] = request.form['name'].lower()
                session.permanent = app.config['PERMANENT_USER_SESSION']
                return redirect(request.args.get('link', url_for('app_ui')))
        else:
            return render_template('login.html')


@app.route('/')
def app_ui():
    return render_template('about.html')


@app.route('/get_user')
def get_user():
    return render_template('layout.html'
                           , text=f'Hello, {session["user_name"]}! Someday you will see here your profile settings...')


@app.route('/adm')
@title('Administration')
def get_app():
    info = ['Oracle client version ' + '.'.join((str(x) for x in clientversion()))
            , 'OS version ' + platform()]
    with lock:
        if target_pool:
            info.append('Session pools ' + ', '.join(target_pool.keys()))

        info.append('Background task worker is {}active'.format('' if worker.is_alive() else 'not '))
        info.append('Chat bot is {}active'.format('' if bot.is_alive() else 'not '))

        t = render_template('administration.html'
                            , info=info
                            , active_connections=active_connections
                            , task_pool=task_pool
                            , task_id=request.args.get('task_id', ''))
    return t


@app.route('/cancel_sql')
def cancel_sql():
    try:
        with lock:
            active_connections[request.args['id']][5] = 'Cancelling...'
            active_connections[request.args['id']][0].cancel()
    except KeyError:
        pass
    sleep(1)
    return redirect(url_for('get_app'))


@app.route('/task/<action>')
def manage_task(action):
    with lock:
        if task_pool[request.args['id']][7] == 'run':
            flash(f'Can\'t {action} an active task.')
        elif action == 'cancel':
            cancel_task(request.args['id'])
        elif action == 'reset':
            reset_task(request.args['id'])
        else:
            abort(400)
    return redirect(url_for('get_app'))


@app.route('/logout')
@title('Log out')
def logout():
    session.pop('user_name', None)
    return redirect(url_for('login'))


@app.route('/stop_server')
@title('Shutdown server')
def stop_server():
    if session['user_name'] not in app.config['ADMIN_GROUP']:
        abort(403)
    if worker.is_alive():
        worker.shutdown()
    if bot.is_alive():
        bot.shutdown()
    if app.config['STORE_FILE']:
        with open(app.config['STORE_FILE'], 'wb') as f:
            pickle(task_pool, f, HIGHEST_PROTOCOL)
    f = request.environ.get('werkzeug.server.shutdown')
    if f:
        if worker.is_alive():
            worker.join()
        if bot.is_alive():
            bot.join()
        f()
        return str(request.environ)
    elif request.environ.get('uwsgi.version'):
        import uwsgi
        pipe = uwsgi.opt.get('master-fifo')
        if pipe:
            with open(pipe, 'wb') as p:
                p.write(b'q')
        else:
            uwsgi.stop()
    else:
        return 'Web server does not recognized, kill it manually.'


@app.route('/error_log')
@title('View error log')
def get_error_log():
    file = path.join(path.dirname(path.dirname(path.abspath(__file__))), 'logs', app.config['ERROR_LOG_NAME'])
    if not path.exists(file):
        abort(404)
    return send_file(file, mimetype='text/plain')


@app.route('/notifications')
@title('Tasks notifications')
@columns({'time': 'datetime'
          , 'user': 'str'
          , 'task_name': 'str'
          , 'parameters': 'str'
          , 'message': 'str'})
def get_notifications():
    with lock:
        task_count = len(tuple(1 for v in task_pool.values() if v[7] in ('wait', 'run')))
        t = render_template('static_list.html'
                            , text=f'{task_count} tasks are active. '
                                   f'Only last {app.config["MAX_KEPT_NOTIFICATIONS"]} task messages will be kept.'
                            , data=notification_pool)
    return t


@app.route('/<target>/get_ext')
@title('Extensions')
def get_ext(target):
    return render_template('layout.html')
