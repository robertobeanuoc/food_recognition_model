import requests
import re
import datetime
import typing
from lxml import html 
BASE_URL:str = "https://www.mywellness.com"
TOKEN_URL:str = f"{BASE_URL}/cloud/User/Login/"
TRAINING_URL:str = f"{BASE_URL}/cloud/Training/"
DATE_RANGE_URL:str = f"{BASE_URL}/cloud/Training/LastPerformedWorkoutSession"
EXERCISE_DETAIL_URL:str = f"{BASE_URL}/cloud/Training/PerformedExerciseDetail"
REGULAR_EXPRESION_TOKEN: re.Pattern = r'\\\"token\\\":\\\"([A-Za-z0-9._-]+)\\\"'
REGULAR_EXPRESION_ID: re.Pattern = r'\\\"id\\\":\\\"([A-Za-z0-9._-]+)\\\"'
REGULAR_EXPRESION_ID_CR: re.Pattern = r'id="([0-9]+)"'
REGULAR_EXPRESION_DATE: re.Pattern = r'20\d{6}'
REGULAR_EXPRESION_TRAINING: re.Pattern = r'https:\/\/[A-Za-z0-9.-]+\.[A-Za-z]{2,4}\/[^\s]*'
REGULAR_EXPRESSION_DATA_POSITION: re.Pattern = r'data\-position=\"([0-9]+)\"'

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
    
    def _getids_cr(self, response_text: str)->list[str]:
        ret_idr_crs: list[str]= re.findall(REGULAR_EXPRESION_ID_CR, response_text)
        return ret_idr_crs
    
    def _get_dates(self, response_text: str)->list[str]:
        ret_dates: list[str] = list(set(re.findall(REGULAR_EXPRESION_DATE, response_text)))

        return ret_dates
    
    def _get_data_position(self, response_text: str)->list[str]:
        ret_positions: list[str] = re.findall(REGULAR_EXPRESSION_DATA_POSITION, response_text)
        return ret_positions
    
    def get_trainning_urls_and_id_cr(self, token:str, app_id: str,start_date:datetime.date, end_date:datetime.date)->typing.Tuple[list[str],list[str],list[str],list[str]]:

        response_text: str = self._get_trainnings(token=token, app_id=app_id, start_date=start_date, end_date=end_date)
        ret_training_urls: list[str] = re.findall(REGULAR_EXPRESION_TRAINING, response_text)
        ret_idr_crs: list[str] = self._getids_cr(response_text)
        ret_dates: list[str] = self._get_dates(response_text)
        ret_positions: list[str] = self._get_data_position(response_text)
        return ret_training_urls, ret_idr_crs, ret_dates,ret_positions
    

    def _get_trainning_content(self,id_cr: str, position:int, day_open_session:str)->str:
        header_info:dict = {
            "idCR": id_cr,
            "position": position,
            "dayOpenSession": day_open_session,
            "singleView" : True,
        }
        response: requests.Request = self.session.get(EXERCISE_DETAIL_URL,data=header_info)
        return response.text


    def get_training(self,id_cr: str, position:int, day_open_session:str)->dict[str, str]:
        training: str = self._get_trainning_content(id_cr=id_cr, position=position, day_open_session=day_open_session)
        training_parsed: dict = html.fromstring(training)
        table:dict  = training_parsed.xpath('//table[@class="exercise-table"]')
        ret_training: dict[str, str] = {}
        if table:
            rows = table[0].xpath('.//tr')
            for row in rows:
                th_elements = row.xpath('.//th')
                td_elements = row.xpath('.//td')
                # ret_training[th.text_content()] = td.text_content()
                ret_training[th_elements[0].text_content()] = td_elements[0].text_content()
                # th_values.extend([th.text_content() for th in th_elements])
                # td_values.extend([td.text_content() for td in td_elements])
        else:
            raise Exception("Table not found")

        return ret_training
