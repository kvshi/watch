from flask import render_template, request, flash
from watch import app
from watch.utils.decorate_view import *
from watch.utils.render_page import render_page
from watch.utils.oracle import execute
from watch.utils.parse_args import parse_parameters


@app.route('/<target>/T/<owner>/<table>')
@title('Table')
@template('single')
@columns({"num_rows": 'int'
          , "last_analyzed": 'datetime'
          , "partitioned": 'str'})
@select("all_tables where owner = :owner and table_name = :p_table")
def get_table(target, owner, table):
    return render_page()


@app.route('/<target>/T/<owner>/<table>/ddl')
@title('Get DDL')
@template('single')
@content('text')
@function("dbms_metadata.get_ddl")
@parameters({"object_type": 'TABLE'
             , "name": ':table'
             , "schema": ':owner'})
def get_table_ddl(target, owner, table):
    return render_page()


@app.route('/<target>/T/<owner>/<table>/row_count')
@title('Row count')
@columns({'date_column': 'datetime'
          , 'row_count': 'int'})
def get_row_count(target, owner, table):
    date_columns = execute(target, "select column_name from all_tab_columns"
                                   " where owner = :o and table_name = :t and data_type = 'DATE'"
                                   " order by column_name", {'o': owner, 't': table})
    if 'do' not in request.args:
        return render_template('row_count.html', date_columns=date_columns, data=None)

    check_for_column = execute(target, "select owner, table_name, column_name from all_tab_columns"
                                       " where owner = :o and table_name = :t and data_type = 'DATE'"
                                       " and column_name = :c"
                               , {'o': owner, 't': table, 'c': request.args.get('column_name', '')}
                               , fetch_mode='one')
    if not check_for_column:
        flash('No such column')
        return render_template('row_count.html', date_columns=date_columns, data=None)

    rr, required_values = parse_parameters(request.args, {'date_from': 'datetime'})
    if rr:
        flash(f'Incorrect value for required parameter: {rr}')
        return render_template('row_count.html', date_columns=date_columns, data=None)
    data = execute(target, f"select trunc({check_for_column[2]}) date_column, count({check_for_column[2]}) row_count"
                           f" from {check_for_column[0]}.{check_for_column[1]}"
                           f" where {check_for_column[2]} >= :date_from"
                           f" group by trunc({check_for_column[2]})"
                           f" order by trunc({check_for_column[2]})", required_values)
    if not data:
        flash('No rows found for this period')
    return render_template('row_count.html', date_columns=date_columns, data=data)


@app.route('/<target>/T/<owner>/<table>/columns')
@title('Columns')
@template('list')
@auto()
@columns({"c.column_id": 'int'
          , "c.column_name": 'str'
          , "c.data_type": 'str'
          , "c.data_length": 'int'
          , "c.data_precision": 'int'
          , "c.data_scale": 'int'
          , "c.nullable": 'str'
          , "c.data_default": 'str'
          , "c.num_distinct": 'int'
          , "c.num_nulls": 'int'
          , "c.last_analyzed": 'datetime'
          , "c.histogram": 'str'
          , "p.column_position part_pos": 'int'
          , "sp.column_position subpart_pos": 'int'})
@select("all_tab_columns c"
        " left join all_part_key_columns p"
        " on p.owner = c.owner and p.name = c.table_name"
        " and p.object_type = 'TABLE' and p.column_name = c.column_name"
        " left join all_subpart_key_columns sp"
        " on sp.owner = c.owner and sp.name = c.table_name"
        " and sp.object_type = 'TABLE' and p.column_name = c.column_name"
        " where c.owner = :owner and c.table_name = :p_table")
@default_sort("column_id")
def get_table_columns(target, owner, table):
    return render_page()


@app.route('/<target>/T/<owner>/<table>/indexes')
@title('Indexes')
@template('list')
@auto()
@columns({"i.index_name": 'str'
          , "i.index_type": 'str'
          , "i.partitioned": 'str'
          , "i.uniqueness": 'str'
          , "i.distinct_keys": 'int'
          , "i.clustering_factor": 'int'
          , "i.status": 'str'
          , "i.num_rows": 'int'
          , "i.last_analyzed": 'datetime'
          , "i.degree": 'str'
          , "i.join_index": 'str'
          , "i.visibility": 'str'
          , "c.columns": 'str'})
@select("all_indexes i"
        " join (select index_owner, index_name, listagg(column_name, ', ')"
        " within group (order by column_position) columns"
        " from all_ind_columns group by index_owner, index_name) c"
        " on c.index_owner = i.owner and c.index_name = i.index_name"
        " where i.owner = :owner and i.table_name = :p_table")
def get_table_indexes(target, owner, table):
    return render_page()


@app.route('/<target>/T/<owner>/<table>/partitions')
@title('Partitions')
@template('list')
@auto()
@columns({"tablespace_name": 'str'
          , "partition_name": 'str'
          , "subpartition_count": 'int'
          , "high_value": 'str'
          , "num_rows": 'int'
          , "last_analyzed": 'int'})
@select("all_tab_partitions"
        " where table_owner = :owner and table_name = :p_table")
def get_table_partitions(target, owner, table):
    return render_page()
