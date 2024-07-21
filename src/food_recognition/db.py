import mysql.connector
import datetime 
import os
from food_recognition.utils import app_logger


def insert_food_type(file_uid:str, food_type:str, glycemic_index:int, weight_grams:int, created_at:datetime.datetime=datetime.datetime.now()):

    cnx:mysql.connector.MySQLConnection = _connect_to_db()
    
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table
    query:str = f"INSERT INTO food_register (file_uid, food_type, glycemic_index, weight_grams, created_at) VALUES ('{file_uid}','{food_type}', {glycemic_index}, {weight_grams}, '{created_at.strftime('%Y-%m-%d %H:%M:%S')}')"
    app_logger.info(f"Query: {query}")

    
    # Execute the query with the provided values
    cursor.execute(query)
    app_logger.info("Record inserted successfully")

    # Commit the changes to the database
    cnx.commit()
    app_logger.info("Changes committed")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")

def insert_food_type_update(file_uid:str, food_type:str, glycemic_index:int, weight_grams:int, created_at:datetime.datetime=datetime.datetime.now()):

    cnx:mysql.connector.MySQLConnection = _connect_to_db()
    
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table
    query:str = f"INSERT INTO food_register_update (file_uid, food_type, glycemic_index, weight_grams, created_at) VALUES ('{file_uid}','{food_type}', {glycemic_index}, {weight_grams}, '{created_at.strftime('%Y-%m-%d %H:%M:%S')}')"
    app_logger.info(f"Query: {query}")

    
    # Execute the query with the provided values
    cursor.execute(query)
    app_logger.info("Record inserted successfully")

    # Commit the changes to the database
    cnx.commit()
    app_logger.info("Changes committed")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")


def _connect_to_db()-> mysql.connector.MySQLConnection:
    cnx: mysql.connector.MySQLConnection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    return cnx


def get_food_types()-> list[dict]:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve all records from the food_table
    query:str = "SELECT food_type, food_type_es, glycemic_index FROM glycemic_index order by food_type"
    app_logger.info(f"Query: {query}")

    # Execute the query
    cursor.execute(query)
    app_logger.info("Query executed successfully")

    # Fetch all the records
    records = cursor.fetchall()
    records_json = []
    for record in records:
        record_dict = {
            'food_type': record[0],
            'food_type_es': record[1],
            'glycemic_index': record[2],
        }
        records_json.append(record_dict)
    app_logger.info("Records fetched")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")

    # Return the records as JSON
    app_logger.info("Records fetched")
    return records_json
    

def get_food_registers(start_date: datetime.date=None,file_uid: str = None)-> list[dict]:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve all records from the food_table
    query:str = f"SELECT food_type, glycemic_index, weight_grams, created_at, file_uid, verified FROM food_register where 1=1"
    if file_uid:
        query += f" and file_uid = '{file_uid}'"
    if start_date:
        query += f" and created_at >= '{start_date.strftime('%Y-%m-%d')}'"
    query+=" order by created_at desc"
    app_logger.info(f"Query: {query}")

    # Execute the query
    cursor.execute(query)
    app_logger.info("Query executed successfully")

    # Fetch all the records
    records = cursor.fetchall()
    records_json = []
    for record in records:
        record_dict = {
            'food_type': record[0],
            'glycemic_index': record[1],
            'weight_grams': record[2],
            'created_at': record[3],
            'file_uid': record[4],
            'verified': record[5],
        }
        records_json.append(record_dict)
    app_logger.info("Records fetched")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")

    # Return the records as JSON
    app_logger.info("Records fetched")
    return records_json

def get_glycemic_index(food_type: str) -> int:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")
    ret_glycemic_index:int = 0

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve the glycemic index of a food type
    food_type = food_type.replace("'", "''")
    query:str = f"SELECT glycemic_index FROM glycemic_index WHERE food_type = '{food_type}'"
    app_logger.info(f"Query: {query}")

    # Execute the query
    cursor.execute(query)
    app_logger.info("Query executed successfully")

    # Fetch the record
    record = cursor.fetchone()
    if record:        
        ret_glycemic_index = record[0]
        app_logger.info("Record fetched")
        app_logger.info("Glycemic index fetched")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")


    return ret_glycemic_index


def get_food_types_list(food_type: str="")->list[str]:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve all records from the food_table
    query:str = "SELECT food_type FROM glycemic_index order by food_type"
    app_logger.info(f"Query: {query}")

    # Execute the query
    cursor.execute(query)
    app_logger.info("Query executed successfully")

    # Fetch all the records
    records = cursor.fetchall()
    ret_records = []
    for record in records:
        ret_records.append(record[0])
    if not food_type in records:
        ret_records.append(food_type)
    app_logger.info("Records fetched")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")

    # Return the records as JSON
    app_logger.info("Records fetched")
    return ",".join(ret_records)

def update_verfied(file_uid:str, food_type:str, verfied:int):
    cnx:mysql.connector.MySQLConnection = _connect_to_db()
    
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table
    query:str = f"update food_register set verified = {verfied} where file_uid = '{file_uid}' and food_type = '{food_type}'"
    app_logger.info(f"Query: {query}")

    
    # Execute the query with the provided values
    cursor.execute(query)
    app_logger.info("Record inserted successfully")

    # Commit the changes to the database
    cnx.commit()
    app_logger.info("Changes committed")

    # Close the cursor and the connection
    cursor.close()
    cnx.close()
    app_logger.info("Connection closed")