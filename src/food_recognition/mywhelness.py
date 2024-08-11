import requests
import re
import datetime
import typing
BASE_URL:str = "https://www.mywellness.com"
TOKEN_URL:str = f"{BASE_URL}/cloud/User/Login/"
TRAINING_URL:str = f"{BASE_URL}/cloud/Training/"
DATE_RANGE_URL:str = f"{BASE_URL}/cloud/Training/LastPerformedWorkoutSession"
REGULAR_EXPRESION_TOKEN: re.Pattern = r'\\\"token\\\":\\\"([A-Za-z0-9._-]+)\\\"'
REGULAR_EXPRESION_ID: re.Pattern = r'\\\"id\\\":\\\"([A-Za-z0-9._-]+)\\\"'
REGULAR_EXPRESION_TRAINING: re.Pattern = r'https:\/\/[A-Za-z0-9.-]+\.[A-Za-z]{2,4}\/[^\s]*'

class MyWellness:
    def __init__(self) -> None:
        self.session = requests.Session()

    def _get_token(self, response_text: str)->str:
        match: re.Match = re.search(REGULAR_EXPRESION_TOKEN, response_text)
        if not match:
            raise Exception("Token not found")
        else:
            ret_token = match.group(1)
        return ret_token


    def _get_app_id(self, response_text: str)->str:
        match: re.Match = re.search(REGULAR_EXPRESION_ID, response_text)
        if not match:
            raise Exception("App Id not found")
        else:
            ret_app_id = match.group(1)

        return ret_app_id


    def get_token_and_app_id(self, username:str, password: str)->typing.Tuple[str, str]:
        header_info:dict = {
            "UserBinder.Username" : username,
            "UserBinder.Password": password,
            "UserBinder.IsFromLogin" : True,
            "UserBinder.KeepMeLogged" : False,

        }
        response: requests.Request = self.session.post(TOKEN_URL, data=header_info)
        ret_token:str = self._get_token(response.text)
        ret_app_id:str = self._get_app_id(response.text)
        
        return ret_token, ret_app_id


    def _get_trainnings(self, token:str, app_id: str,start_date:datetime.date, end_date:datetime.date)->list[str]:
        header_info:dict = {
            "token": token,
            "fromDate": start_date.strftime("%d/%m/%Y)"),
            "toDate": end_date.strftime("%d/%m/%Y)"),
            "appId": app_id,
            "_c": "es_ES",
        }
        response: requests.Request = self.session.get(DATE_RANGE_URL, headers=header_info)
        return response.text
 
    def get_trainning_urls(self, token:str, app_id: str,start_date:datetime.date, end_date:datetime.date)->list[str]:

        response_text: str = self._get_trainnings(token=token, app_id=app_id, start_date=start_date, end_date=end_date)
        ret_training_urls: list[str] = re.findall(REGULAR_EXPRESION_TRAINING, response_text)
        return ret_training_urls
    
    def get_training(self, url:str)->dict[str, str]:
        response: requests.Request = self.session.post(url)
        return response.text
