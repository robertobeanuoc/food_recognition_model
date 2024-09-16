import mysql.connector
import datetime
import os
import pytz
from food_recognition.utils import app_logger

ENV_VAR_DB_TZ_DATES: str = os.getenv("DB_TZ_DATES", "UTC")


def convert_utc_to_db_datetime(utc_datetime: datetime.datetime) -> datetime.datetime:
    tz = pytz.timezone(ENV_VAR_DB_TZ_DATES)
    ret_db_datetime: datetime.datetime = utc_datetime.astimezone(tz)
    return ret_db_datetime


def insert_food_type(
    file_uid: str,
    food_type: str,
    glycemic_index: int,
    weight_grams: int,
    created_at: datetime.datetime = None,
):
    if created_at is None:
        created_at = convert_utc_to_db_datetime(datetime.datetime.now(tz=pytz.utc))

    cnx: mysql.connector.MySQLConnection = _connect_to_db()

    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table
    query: str = f"""INSERT INTO food_register 
             (file_uid,
              food_type,
              original_food_type,
              glycemic_index,
              original_glycemic_index,
              weight_grams,
              created_at 
            ) VALUES ( 
              '{file_uid}', 
              '{food_type}', 
             '{food_type}',               
               {glycemic_index},
               {glycemic_index},               
               {weight_grams}, 
              '{created_at.strftime('%Y-%m-%d %H:%M:%S')}' 
            )"""
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


def update_food_register(
    uuid: str,
    food_type: str = None,
    glycemic_index: int = None,
    weight_grams: int = None,
    verified: int = None,
    updated_at: datetime.datetime = None,
):
    if updated_at is None:
        updated_at = datetime.datetime.now()

    cnx: mysql.connector.MySQLConnection = _connect_to_db()

    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table

    query: str = (
        f" UPDATE food_register  set updated_at='{updated_at.strftime('%Y-%m-%d %H:%M:%S')}'"
    )
    if food_type != None and food_type != "":
        query = query + f", food_type = '{food_type}'"
    if glycemic_index != None:
        query = query + f", glycemic_index = {glycemic_index}"
    if weight_grams != None:
        query = query + f", weight_grams = {weight_grams}"
    if verified != None:
        query = query + f", verified = {verified}"
    query = query + f" WHERE uuid = '{uuid}'"

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


def _connect_to_db() -> mysql.connector.MySQLConnection:
    cnx: mysql.connector.MySQLConnection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )
    return cnx


def get_food_types(food_type: str = "") -> list[dict]:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve all records from the food_table
    query: str = "SELECT food_type, food_type_es, glycemic_index FROM glycemic_index "
    if food_type:
        query = query + f"where food_type = '{food_type}' "
    query = query + "order by food_type"
    app_logger.info(f"Query: {query}")

    # Execute the query
    cursor.execute(query)
    app_logger.info("Query executed successfully")

    # Fetch all the records
    records = cursor.fetchall()
    records_json = []
    for record in records:
        record_dict = {
            "food_type": record[0],
            "food_type_es": record[1],
            "glycemic_index": record[2],
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


def get_food_registers(
    start_date: datetime.date = None, file_uid: str = None
) -> list[dict]:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve all records from the food_table
    query: str = (
        f"SELECT food_type, glycemic_index, weight_grams, created_at, file_uid, verified, uuid FROM food_register where 1=1"
    )
    if file_uid:
        query += f" and file_uid = '{file_uid}'"
    if start_date:
        query += f" and created_at >= '{start_date.strftime('%Y-%m-%d')}'"
    query += " order by created_at desc"
    app_logger.info(f"Query: {query}")

    # Execute the query
    cursor.execute(query)
    app_logger.info("Query executed successfully")

    # Fetch all the records
    records = cursor.fetchall()
    records_json = []
    for record in records:
        record_dict = {
            "food_type": record[0],
            "glycemic_index": record[1],
            "weight_grams": record[2],
            "created_at": record[3],
            "file_uid": record[4],
            "verified": record[5],
            "uuid": record[6],
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
    ret_glycemic_index: int = 0

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve the glycemic index of a food type
    food_type = food_type.replace("'", "''")
    query: str = (
        f"SELECT glycemic_index FROM glycemic_index WHERE food_type = '{food_type}'"
    )
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


def get_food_types_list(food_type: str = "") -> list[str]:
    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to retrieve all records from the food_table
    query: str = "SELECT food_type FROM glycemic_index order by food_type"
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


def update_verfied(
    verfied: int, uuid: str = "", file_uid: str = "", food_type: str = ""
):

    filter: str = f" file_uid = '{file_uid}' and food_type = '{food_type}'"
    if uuid == "":
        if file_uid == "" or food_type == "":
            error_message = "Either uid or file_uid and food_type must be provided"
            app_logger.error(error_message)
            raise Exception(error_message)
    else:
        filter: str = f" uuid = '{uuid}' "

    cnx: mysql.connector.MySQLConnection = _connect_to_db()
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table
    query: str = f"update food_register set verified = {verfied} where {filter}"
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
