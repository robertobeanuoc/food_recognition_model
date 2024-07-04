import mysql.connector
import datetime 
import os
from utils import app_logger


def insert_food_type(file_uid:str, food_type:str, glycemic_index:int, weight_grams:int, created_at:datetime.datetime=datetime.datetime.now()):

    cnx: mysql.connector.MySQLConnection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    
    app_logger.info("Connected to the database")

    # Create a cursor object to execute SQL queries
    cursor = cnx.cursor()

    # Define the SQL query to insert a record into the food_table
    query:str = f"INSERT INTO food_register (file_uid, food_type, glycemic_index, weight_grams, created_at) VALUES ('{file_uid}','{food_type}', {glycemic_index}, {weight_grams}, '{created_at.strftime('%Y-%m-%d %H:%M:%S')}')"

    
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