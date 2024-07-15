import logging 
import re
import json



logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
app_logger:logging.Logger = logging.getLogger("food_classification")


def extract_json_from_openai(response)->dict:
    ret_output_json:dict = {}
    message_response:str = response.to_dict()['choices'][0]['message']['content'].lower().replace("json", "").replace("```", "")
    app_logger.info(f"Message response: {message_response}")
    json_files:list[str] = re.findall(r'\[[\s\S]*?\]',message_response)
    if len(json_files) == 0 or json_files is None:
        message_parseds: list [str] = re.findall(r'\{[\s\S]*?\}',message_response)
        if message_parseds:
            try:
                ret_output_json =  json.loads(message_parseds[0])
            except Exception as e:
                ret_output_json = {}
                app_logger.error(f"Error: {e}")
        else:
            ret_output_json = {}
            app_logger.error("No json files found")
    else:        
        try:
            message_json:str = json_files[0]
            app_logger.info(f"Message json: {message_json}")
            ret_output_json = json.loads(message_json)
        except Exception as e:
            ret_output_json = {}
            app_logger.error(f"Error: {e}")
    return ret_output_json

