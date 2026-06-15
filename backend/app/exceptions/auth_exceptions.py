from fastapi import status
from  .base import AppException

class EmailOrPasswordException(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Incorrect Email or Password. Try LOGIN Again!"
    
class LoginTimeOut(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Could not Validate Credentials. LOGIN Again!"