from flask import flash, render_template, url_for
from pygal import HorizontalStackedBar, StackedLine, Pie
from watch import app
from watch.utils.decorate_view import *
from watch.utils.oracle import execute
from copy import deepcopy


@app.route('/<target>/top')
@title('Top activity')
def get_top_activity(target):
    r = execute(target, "with h as (select sample_id, sample_time, sql_id, o.object_name, event"
                        ", case when wait_class is null then 'CPU' else wait_class end wait_class"
                        ", nvl(wait_class_id, -1) wait_class_id"
                        ", wait_time, time_waited from v$active_session_history ash"
                        " left join dba_objects o on o.object_id = ash.current_obj#"
                        " where sample_time > trunc(sysdate - 1/24, 'mi') and sample_time > trunc(sysdate)"
                        " and sample_time < trunc(sysdate, 'mi'))"
                        " select 1 t, to_char(sample_time, 'hh24:mi') s, wait_class v1, wait_class_id v2, count(1) c"
                        " from h group by to_char(sample_time, 'hh24:mi'), wait_class, wait_class_id union all"
                        " select 2 t, sql_id s, wait_class v1, wait_class_id v2, count(1) c from h"
                        " where sql_id is not null and sql_id in (select sql_id"
                        " from (select sql_id, row_number() over (order by tc desc) rn"
                        " from (select sql_id, count(1) tc from h"
                        " where sql_id is not null group by sql_id)) where rn <= 10)"
                        " group by sql_id, wait_class, wait_class_id union all"
                        " select 3 t, object_name s, wait_class v1, wait_class_id v2, count(1) c from h"
                        " where object_name is not null and object_name in (select object_name"
                        " from (select object_name, row_number() over (order by tc desc) rn"
                        " from (select object_name, count(1) tc from h"
                        " where object_name is not null group by object_name))"
                        " where rn <= 10) group by object_name, wait_class, wait_class_id union all"
                        " select 4 t, null s, wait_class v1, wait_class_id v2, count(1) c"
                        " from h group by wait_class, wait_class_id order by 1, 4, 2")
    if not r:
        flash('Not found')
        return render_template('top_activity.html')
    colors = {'Other': '#F06EAA'
              , 'Application': '#C02800'
              , 'Configuration': '#5C440B'
              , 'Administrative': '#717354'
              , 'Concurrency': '#8B1A00'
              , 'Commit': '#E46800'
              , 'Idle': '#FFFFFF'
              , 'Network': '#9F9371'
              , 'User I/O': '#004AE7'
              , 'System I/O': '#0094E7'
              , 'Scheduler': '#CCFFCC'
              , 'Queueing': '#C2B79B'
              , 'CPU': '#00CC00'}

    series = {k[1]: [] for k in sorted(set((item[3], item[2]) for item in r if item[0] == 1), key=lambda x: x[0])}
    p = deepcopy(app.config['CHART_CONFIG'])
    p['style'].colors = tuple(colors[wait_class] for wait_class in series.keys())
    p['height'] = 220
    top_activity = StackedLine(**p)
    top_activity.fill = True
    top_activity.x_labels = sorted(set(item[1] for item in r if item[0] == 1))
    top_activity.x_labels_major_every = 5
    top_activity.truncate_label = 5
    top_activity.show_minor_x_labels = False
    for label in top_activity.x_labels:
        for serie in series.keys():
            v = tuple(item[4] for item in r if item[0] == 1 and item[1] == label and item[2] == serie)
            series[serie].append(v[0] if len(v) > 0 else 0)
    for serie in series.keys():
        top_activity.add(serie,  series[serie], show_dots=False)

    top_sql = HorizontalStackedBar(**p)
    top_sql.show_legend = False
    top_sql.width = 400
    top_sql.show_x_labels = False
    top_sql.x_labels = sorted(set(item[1] for item in r if item[0] == 2))
    series = {k[1]: [] for k in sorted(set((item[3], item[2]) for item in r if item[0] == 2), key=lambda x: x[0])}
    for label in top_sql.x_labels:
        for serie in series.keys():
            v = tuple(item[4] for item in r if item[0] == 2 and item[1] == label and item[2] == serie)
            series[serie].append(v[0] if len(v) > 0 else 0)
    for serie in series.keys():
        # todo https://github.com/Kozea/pygal/issues/18
        top_sql.add(serie,  [dict(value=item
                                  , color=colors[serie]
                                  , xlink=dict(href=url_for('get_query'
                                                            , target=target
                                                            , query=top_sql.x_labels[i]
                                                            , _external=True)
                                               , target='_blank')) for i, item in enumerate(series[serie])])

    top_objects = HorizontalStackedBar(**p)
    top_objects.show_legend = False
    top_objects.width = 400
    top_objects.show_x_labels = False
    top_objects.x_labels = sorted(set(item[1] for item in r if item[0] == 3))
    series = {k[1]: [] for k in sorted(set((item[3], item[2]) for item in r if item[0] == 3), key=lambda x: x[0])}
    for label in top_objects.x_labels:
        for serie in series.keys():
            v = tuple(item[4] for item in r if item[0] == 3 and item[1] == label and item[2] == serie)
            series[serie].append(v[0] if len(v) > 0 else 0)
    for serie in series.keys():
        top_objects.add(serie,  [dict(value=item, color=colors[serie]) for item in series[serie]])

    top_waits = Pie(**p)
    top_waits.show_legend = False
    top_waits.width = 300
    top_waits.inner_radius = 0.6
    labels = tuple(k[1] for k in sorted(set((item[3], item[2]) for item in r if item[0] == 4), key=lambda x: x[0]))
    for label in labels:
        top_waits.add(label, tuple(item[4] for item in r if item[0] == 4 and item[2] == label)[0])

    return render_template('top_activity.html'
                           , top_activity=top_activity.render_data_uri()
                           , top_sql=top_sql.render_data_uri()
                           , top_objects=top_objects.render_data_uri()
                           , top_waits=top_waits.render_data_uri()
                           )
