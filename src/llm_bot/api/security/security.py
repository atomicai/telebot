import secrets
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette import status
from starlette.exceptions import HTTPException

from llm_bot.api.security.config import security_config

basic_security = HTTPBasic()


def get_admin_username(
        credentials: Annotated[HTTPBasicCredentials, Depends(basic_security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = security_config.admin_username.encode("utf8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = security_config.admin_password.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
