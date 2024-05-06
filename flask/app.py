from flask import Flask, jsonify, request, render_template, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from config import Config
import base64
from decimal import Decimal
import json
from urllib.parse import urlparse
from kafka import KafkaProducer
from kafka import KafkaConsumer
from datetime import datetime
from sqlalchemy import create_engine, text
from datetime import datetime
from uuid import uuid4




app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)




producer = KafkaProducer(
    bootstrap_servers=['kafka:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)



    
    
def reload_config():
    print("Chargement de la configuration...")
    with open('config.json', 'r') as file:
        config_data = json.load(file)
    app.config['SQLALCHEMY_DATABASE_URI'] = {
        str(dept_id): details['connection']
        for dept_id, details in config_data['databases'].items()
    }
    app.config['TABLE_SELECTIONS'] = {
        str(dept_id): details.get('tables', [])
        for dept_id, details in config_data['databases'].items()
    }
    print("Configuration chargée : ", app.config['TABLE_SELECTIONS'])


@app.before_first_request
def initialize_config():
    reload_config()



def paginate_items(items, page, per_page):
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end]

@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    per_page = 5
    with open('config.json', 'r') as file:
        config_data = json.load(file)
        all_databases = config_data['databases']
        databases = list(all_databases.items())  # Cela devrait être une liste de tuples
    
    paginated_databases = paginate_items(databases, page, per_page)
    total_pages = (len(databases) + per_page - 1) // per_page
    return render_template('home.html', configurations=paginated_databases, page=page, total_pages=total_pages)



@app.route('/edit/<department_id>', methods=['GET'])
def edit_config(department_id):
    with open('config.json', 'r') as file:
        config_data = json.load(file)
    entry = config_data['databases'][department_id]
    parsed = urlparse(entry["connection"])
    config_details = {
        'id': department_id,
        'name': entry["name"],
        'host': parsed.hostname,
        'port': parsed.port,
        'db': parsed.path[1:],
        'user': parsed.username,
        'password': parsed.password
    }

    
    log_data = {
    'department_id': department_id,
    'timestamp': datetime.utcnow().isoformat(),  
    'action': 'view_config',
    'status': 'accessed'
}
    producer.send('config_access_logs', log_data)
    producer.flush()

    return render_template('update.html', **config_details)
    
    
    

def get_kafka_producer():
    return KafkaProducer(
        bootstrap_servers=['kafka:9092'],  
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

producer = get_kafka_producer()

@app.route('/update', methods=['POST'])
def update_config():
    department_id = request.form['id']
    new_name = request.form['name']
    
    
    
    with open('config.json', 'r+') as file:
        config = json.load(file)
        config['databases'][department_id]['name'] = new_name
        
        file.seek(0)
        json.dump(config, file, indent=4)
        file.truncate()

    
    data = {'id': department_id, 'name': new_name}
    
    
    try:
        producer.send('updates', data).get(timeout=10)  
    except KafkaError as e:
        
        app.logger.error("Erreur Kafka lors de la mise à jour de la configuration: %s", e)
    
    return redirect('/')



def get_kafka_consumer():
    return KafkaConsumer(
        'updates',
        bootstrap_servers=['kafka:9092'],
        auto_offset_reset='earliest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )

consumer = get_kafka_consumer()



@app.route('/delete/<department>', methods=['POST'])
def delete_config(department):
    with open('config.json', 'r+') as file:
        config = json.load(file)
        del config['databases'][department]
        file.seek(0)
        json.dump(config, file, indent=4)
        file.truncate()

    reorganize_ids()

    
    data = {'id': department, 'action': 'delete'}
    producer.send('config_changes', data)
    producer.flush()

    return redirect('/')

def reorganize_ids():
    with open('config.json', 'r+') as file:
        config = json.load(file)
        new_config = {}
        new_id = 1
        for old_id in sorted(config['databases'].keys(), key=int):
            new_config[str(new_id)] = config['databases'][old_id]
            new_id += 1
        config['databases'] = new_config
        file.seek(0)
        json.dump(config, file, indent=4)
        file.truncate()

    reload_config()  






@app.route('/configure', methods=['GET'])
def config_form():
    return render_template('configure.html')


@app.route('/configure', methods=['POST'])
def handle_form():
    department_name = request.form['department']
    host = request.form['host']
    port = request.form['port']
    db_name = request.form['db']
    user = request.form['user']
    password = request.form['password']

    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(connection_string)

    
    try:
        connection = engine.connect()
        connection.close()  
    except Exception as e:
        return f"Failed to connect to the database: {str(e)}", 500

    table_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = engine.execute(table_query).fetchall()
    tables_list = [table[0] for table in tables]

    
    return render_template('select_tables.html', tables=tables_list, connection_string=connection_string, department_name=department_name)



@app.route('/get-tables', methods=['POST'])
def get_tables():
    
    user = request.form['user']
    password = request.form['password']
    host = request.form['host']
    port = request.form['port']
    db_name = request.form['db']

    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(connection_string)
    connection = engine.connect()

    
    table_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = connection.execute(table_query).fetchall()
    tables_list = [table[0] for table in tables]

    
    return render_template('select_tables.html', tables=tables_list, connection_string=connection_string)

    
def assign_new_id():
    with open('config.json', 'r') as file:
        config = json.load(file)
        current_ids = [int(key) for key in config['databases'].keys()]
        new_id = max(current_ids) + 1 if current_ids else 1  # Assign ID 1 if list is empty
    return new_id
    
@app.route('/save-configuration', methods=['POST'])
def save_configuration():
    connection_string = request.form['connection_string']
    department_name = request.form['department_name']
    selected_tables = request.form.getlist('tables[]')  

    
    new_id = assign_new_id()  

    
    config_data = {
        "name": department_name,
        "connection": connection_string,
        "tables": selected_tables
    }

    
    with open('config.json', 'r+') as file:
        config = json.load(file)
        config['databases'][str(new_id)] = config_data
        file.seek(0)
        json.dump(config, file, indent=4)
        file.truncate()

    reload_config()  

    
    return render_template('configuration_saved.html', api_url=f"/api/{new_id}")










def get_tables_and_content(engine, page, page_size):
    table_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
    tables = engine.execute(table_query).fetchall()
    result = {}
    for table_name, in tables:
        query = text(f"SELECT * FROM \"{table_name}\" LIMIT :limit OFFSET :offset")
        offset = (page - 1) * page_size
        content = engine.execute(query, {'limit': page_size, 'offset': offset}).fetchall()
        records = []
        for row in content:
            record = {}
            for column, value in row._mapping.items():
                if isinstance(value, (memoryview, bytearray)):
                    record[column] = base64.b64encode(value).decode('utf-8')
                elif isinstance(value, Decimal):
                    record[column] = str(value)
                else:
                    record[column] = value
            records.append(record)
        result[table_name] = records
    return result


from datetime import datetime, date


def custom_json_encoder(o):
    if isinstance(o, Decimal):
        return float(o)  
    elif isinstance(o, datetime):
        return o.isoformat()  
    elif isinstance(o, date):
        return o.isoformat()  
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
    
@app.route('/api/<department_id>')
def department_data(department_id):
    if str(department_id) in app.config['TABLE_SELECTIONS']:
        selected_tables = app.config['TABLE_SELECTIONS'][str(department_id)]
        if not selected_tables:
            return jsonify({"error": "No tables selected for this department"}), 404
        
        connection_string = app.config['SQLALCHEMY_DATABASE_URI'][str(department_id)]
        engine = create_engine(connection_string)
        connection = engine.connect()

        data = {}
        for table_name in selected_tables:
            query = text(f"SELECT * FROM \"{table_name}\"")
            result = connection.execute(query)
            data[table_name] = [dict(row) for row in result]

        connection.close()
        
        response = make_response(json.dumps(data, default=custom_json_encoder))
        response.mimetype = 'application/json'
        return response
    else:
        return jsonify({"error": "Department ID not found"}), 404



@app.route('/select-apis', methods=['POST'])
def select_apis():
    selected_api_ids = request.form.getlist('selected_apis')
    tables_info = {}

    for api_id in selected_api_ids:
        selected_tables = app.config['TABLE_SELECTIONS'].get(api_id, [])
        if selected_tables:
            connection_string = app.config['SQLALCHEMY_DATABASE_URI'].get(api_id)
            if connection_string:
                engine = create_engine(connection_string)
                connection = engine.connect()

                tables_info[api_id] = {
                    'connection_string': connection_string,
                    'tables': selected_tables
                }
                connection.close()

    return render_template('select_tables_multi.html', tables_info=tables_info)





@app.route('/create-persistent-combined-api', methods=['POST'])
def create_persistent_combined_api():
    selected_tables = request.form.getlist('selected_tables')
    combined_api_data = {}
    combined_config = {}

    for table_selection in selected_tables:
        api_id, table_name = table_selection.split('__')
        connection_string = app.config['SQLALCHEMY_DATABASE_URI'][api_id]
        engine = create_engine(connection_string)
        connection = engine.connect()

        query = text(f"SELECT * FROM \"{table_name}\"")
        result = connection.execute(query)
        combined_api_data[f"{api_id}_{table_name}"] = [dict(row) for row in result]

        if api_id not in combined_config:
            combined_config[api_id] = {
                'connection': connection_string,
                'tables': []
            }
        combined_config[api_id]['tables'].append(table_name)

        connection.close()

    
    with open('apiCombined.json', 'w') as file:
        json.dump(combined_config, file, indent=4)

    
    return render_template('api_created.html', api_url="/api/combined")

def get_next_api_id():
    try:
        with open('last_api_id.txt', 'r') as file:
            last_id = int(file.read().strip())
    except (FileNotFoundError, ValueError):
        last_id = 0  

    next_id = last_id + 1
    with open('last_api_id.txt', 'w') as file:
        file.write(str(next_id))

    return next_id


@app.route('/create-combined-api', methods=['POST'])
def handle_create_combined_api():
    selected_tables = request.form.getlist('selected_tables')
    api_id = get_next_api_id()  
    connections = {}

    for table_selection in selected_tables:
        dept_id, table_name = table_selection.split('__')
        connection_string = app.config['SQLALCHEMY_DATABASE_URI'][dept_id]
        engine = create_engine(connection_string)
        connection = engine.connect()

        query = text(f"SELECT * FROM \"{table_name}\"")
        result = connection.execute(query)

        
        if dept_id not in connections:
            connections[dept_id] = {
                "connection": connection_string,
                "tables": []
            }
        connections[dept_id]['tables'].append(table_name)

        connection.close()

    
    combined_api_data = {
        "api_id": api_id,
        "connections": list(connections.values())
    }

    
    with open('apiCombined.json', 'r+') as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError:
            data = {}

        data[str(api_id)] = combined_api_data
        file.seek(0)
        json.dump(data, file, indent=4)
        file.truncate()

    return render_template('api_created.html', api_url=f"/api/combined/{api_id}")



@app.route('/api/combined/<api_id>')
def serve_combined_api_with_id(api_id):
    try:
        with open('apiCombined.json', 'r') as file:
            combined_apis = json.load(file)
        
        api_data = combined_apis.get(str(api_id))
        if not api_data:
            return jsonify({"error": "API with ID {} not found".format(api_id)}), 404
        
        
        result_data = {}

        
        for connection_info in api_data['connections']:
            connection_string = connection_info['connection']
            engine = create_engine(connection_string)
            connection = engine.connect()

            
            for table_name in connection_info['tables']:
                query = text(f"SELECT * FROM \"{table_name}\"")
                query_result = connection.execute(query)
                
                if table_name not in result_data:
                    result_data[table_name] = [dict(row) for row in query_result]
                else:
                    result_data[table_name].extend([dict(row) for row in query_result])

            connection.close()
        
        return jsonify(result_data)
        
    except FileNotFoundError:
        return jsonify({"error": "Combined API data not found"}), 404
    except Exception as e:
        return jsonify({"error": "Error processing your request: {}".format(str(e))}), 500







@app.route('/api/combined')
def serve_combined_api():
    try:
        with open('apiCombined.json', 'r') as file:
            combined_config = json.load(file)
        combined_data = {}
        for api_id, config in combined_config.items():
            engine = create_engine(config['connection'])
            connection = engine.connect()
            for table in config['tables']:
                query = text(f"SELECT * FROM \"{table}\"")
                result = connection.execute(query)
                combined_data[f"{api_id}_{table}"] = [dict(row) for row in result]
            connection.close()
        response = make_response(json.dumps(combined_data, default=custom_json_encoder))
        response.mimetype = 'application/json'
        return response
    except FileNotFoundError:
        return jsonify({"error": "Combined API data not found"}), 404






@app.route('/create-temporary-combined-api', methods=['POST'])
def create_temporary_combined_api():
    selected_tables = request.form.getlist('selected_tables')
    api_id = str(uuid4())  
    combined_api_data = {}

    for table_selection in selected_tables:
        dept_id, table_name = table_selection.split('__')
        connection_string = app.config['SQLALCHEMY_DATABASE_URI'][dept_id]
        engine = create_engine(connection_string)
        connection = engine.connect()

        query = text(f"SELECT * FROM \"{table_name}\"")
        result = connection.execute(query)
        combined_api_data[f"{dept_id}_{table_name}"] = [dict(row) for row in result]

        connection.close()

    
    with open('apiCombined.json', 'r+') as file:
        try:
            apis = json.load(file)
        except json.JSONDecodeError:
            apis = {}

        apis[api_id] = combined_api_data
        file.seek(0)
        json.dump(apis, file, default=custom_json_encoder, indent=4)
        file.truncate()

    response = make_response(json.dumps({"api_url": f"/api/{api_id}"}))
    response.mimetype = 'application/json'
    return response




@app.route('/select-apis-page')
def select_apis_page():
    page_size = 10  
    current_page = request.args.get('page', 1, type=int)  
    
    with open('config.json', 'r') as file:
        config_data = json.load(file)
        databases = config_data.get('databases', {})
        items = list(databases.items())  

    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size

    start = (current_page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    
    num_pages_to_display = 5  
    start_page = max(1, current_page - num_pages_to_display // 2)
    end_page = min(total_pages, start_page + num_pages_to_display - 1)
    pagination_range = range(start_page, end_page + 1)

    return render_template(
        'SelectAPIstoCombine.html',
        configurations=page_items,
        current_page=current_page,
        total_pages=total_pages,
        pagination_range=pagination_range
    )






@app.route('/api/<api_id>')
def serve_api(api_id):
    try:
        with open('apiCombined.json', 'r') as file:
            apis = json.load(file)
        api_data = apis.get(api_id, {})
        return jsonify(api_data)
    except FileNotFoundError:
        return jsonify({"error": "API data not found"}), 404


@app.route('/show-api-combined')
def show_api_combined():
    try:
        with open('apiCombined.json', 'r') as file:
            combined_apis = json.load(file)
        return render_template('ShowapiCombined.html', combined_apis=combined_apis)
    except FileNotFoundError:
        return "File not found", 404
    except json.JSONDecodeError:
        return "Error decoding JSON", 500


@app.route('/delete-combined-api/<api_id>', methods=['POST'])
def delete_combined_api(api_id):
    try:
        with open('apiCombined.json', 'r+') as file:
            data = json.load(file)
            if api_id in data:
                
                del data[api_id]

                
                new_data = {}
                new_id = 1
                for key in sorted(data.keys(), key=int):
                    new_data[str(new_id)] = data[key]
                    new_data[str(new_id)]['api_id'] = new_id  # Mise à jour de l'api_id dans les données
                    new_id += 1

                file.seek(0)
                json.dump(new_data, file, indent=4)
                file.truncate()
                
        return redirect('/show-api-combined')
    except Exception as e:
        return f"An error occurred: {str(e)}"



if __name__ == '__main__':
    reload_config()  
    app.run(debug=True)

